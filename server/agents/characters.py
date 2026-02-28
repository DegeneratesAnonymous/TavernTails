from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import db
from ..auth import get_current_user
from . import references as references_agent
from .system_detect import infer_ttrpg_system

router = APIRouter(prefix="/characters", tags=["characters"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unassign_character_from_sessions(character_id: int) -> None:
    """Remove a character assignment from all session meta files (best-effort)."""
    import pathlib
    sessions_base = pathlib.Path(__file__).resolve().parents[1] / "sessions"
    if not sessions_base.exists():
        return
    for session_dir in sessions_base.iterdir():
        if not session_dir.is_dir():
            continue
        meta_path = session_dir / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            continue
        changed = False
        for member in meta.get("members") or []:
            if member.get("character_id") == character_id:
                member["character_id"] = None
                changed = True
        if changed:
            try:
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
            except Exception:
                pass


def _guess_character_name_from_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    # Get basename
    base = filename.replace("\\", "/").split("/")[-1]
    # Remove extension
    if "." in base:
        base = ".".join(base.split(".")[:-1])
    # Replace separators with spaces
    base = re.sub(r"[_\-]+", " ", base).strip()
    # Remove trailing numeric tokens (IDs) like 'name_12345'
    parts = [p for p in base.split() if not p.isdigit()]
    if not parts:
        return None
    name = " ".join(parts)
    # Title-case the name for display
    name = name.title()
    return name or None


def _read_pdf_widget_values(content: bytes) -> Dict[str, str]:
    """Extract PDF widget values (interactive form fields).

    D&D Beyond PDF exports commonly store filled values as widget annotations on pages.
    Many PDF text extractors won't include these values in `extract_text()` output.
    """
    try:
        from pypdf import PdfReader
    except Exception:
        return {}

    try:
        reader = PdfReader(__import__("io").BytesIO(content))
    except Exception:
        return {}

    fields: Dict[str, str] = {}

    for page in reader.pages:
        try:
            annots = page.get("/Annots")
        except Exception:
            annots = None
        if not annots:
            continue

        try:
            annot_refs = list(annots)
        except Exception:
            continue

        for ref in annot_refs:
            try:
                annot = ref.get_object()
            except Exception:
                continue
            try:
                subtype = str(annot.get("/Subtype") or "")
            except Exception:
                subtype = ""
            if subtype != "/Widget":
                continue

            try:
                key = _as_str(annot.get("/T"))
                value = _as_str(annot.get("/V"))
            except Exception:
                continue
            if not key or value is None:
                continue
            # Keep the first occurrence; DDB PDFs can repeat widgets across pages.
            fields.setdefault(key, value)

    return fields


def _extract_fields_from_pdf_widgets(fields: Dict[str, str]) -> tuple[str | None, int | None, str | None]:
    if not fields:
        return None, None, None

    name = fields.get("CharacterName") or fields.get("CHARACTER NAME")

    # All known class names (5e + PF2e) used for conservative matching.
    candidates = [
        # D&D 5e
        "Artificer", "Barbarian", "Bard", "Cleric", "Druid", "Fighter",
        "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard",
        # Pathfinder 2e (Remaster + earlier)
        "Alchemist", "Champion", "Investigator", "Magus", "Oracle", "Psychic",
        "Summoner", "Swashbuckler", "Thaumaturge", "Witch",
        "Animist", "Exemplar", "Commander", "Guardian",
    ]

    # Find a key that looks like it contains both Class and Level.
    class_level_value: str | None = None
    for k, v in fields.items():
        up = k.upper()
        if "CLASS" in up and "LEVEL" in up and v.strip():
            class_level_value = v
            break

    class_name: str | None = None
    level: int | None = None

    if class_level_value:
        pairs = re.findall(r"\b([A-Za-z][A-Za-z ]{2,40}?)\s+(\d{1,2})\b", class_level_value)
        found_classes: list[str] = []
        total_level = 0
        for cname_raw, lvl_raw in pairs:
            cname = _as_str(cname_raw)
            lvl = _as_int(lvl_raw)
            if not cname or not isinstance(lvl, int):
                continue
            # Only accept known class names to avoid picking up random labels.
            if not any(cname.lower() == c.lower() for c in candidates):
                continue
            if cname not in found_classes:
                found_classes.append(cname)
            total_level += lvl

        if found_classes:
            class_name = " / ".join(found_classes[:3])
        if total_level > 0:
            level = total_level

        if class_name is None:
            # Last resort: if the value includes a known class name, capture it.
            for cname in candidates:
                if re.search(rf"\b{re.escape(cname)}\b", class_level_value, flags=re.IGNORECASE):
                    class_name = cname
                    break

    # PF2e and other systems use separate "Class" and "Level" widgets.
    # Only fall back to these if the combined CLASS & LEVEL key wasn't found.
    if class_name is None:
        for k, v in fields.items():
            up = k.upper().strip()
            if up == "CLASS" and v and v.strip():
                raw_val = v.strip()
                for cname in candidates:
                    if re.search(rf"\b{re.escape(cname)}\b", raw_val, flags=re.IGNORECASE):
                        class_name = cname
                        break
                if class_name is None and raw_val and len(raw_val) <= 50:
                    # Accept unknown class names verbatim for non-5e systems.
                    class_name = raw_val
                break

    if level is None:
        for k, v in fields.items():
            up = k.upper().strip()
            if up == "LEVEL" and v and v.strip():
                level = _as_int(v.strip())
                break

    return name, level, class_name


def _extract_pdf_widget_int(
    fields: Dict[str, str],
    key_candidates: list[str],
    *,
    min_value: int,
    max_value: int,
) -> int | None:
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())

    normalized_candidates = [norm(k) for k in key_candidates if k]
    normalized_candidates = [c for c in normalized_candidates if c]
    if not normalized_candidates:
        return None

    def matches(nk: str, cand: str) -> bool:
        if nk == cand:
            return True
        # Avoid short-token false positives like "ac" matching "acrobatics".
        if len(cand) <= 3:
            return False
        return cand in nk

    # Prefer exact-ish key matches.
    ordered: list[tuple[str, str, str]] = []
    for k, v in fields.items():
        nk = norm(k)
        if any(nk == c for c in normalized_candidates):
            ordered.insert(0, (k, nk, v))
        else:
            ordered.append((k, nk, v))

    for _k, nk, v in ordered:
        if v is None:
            continue
        if not any(matches(nk, c) for c in normalized_candidates):
            continue
        # Pull the first integer-looking token.
        m = re.search(r"-?\d{1,4}", str(v))
        if not m:
            continue
        n = _as_int(m.group(0))
        if not isinstance(n, int):
            continue
        if n < min_value or n > max_value:
            continue
        return n

    return None


def _extract_stats_from_pdf_widgets(fields: Dict[str, str]) -> Dict[str, int]:
    if not fields:
        return {}

    # DDB PDFs vary; we try a few common key patterns.
    result: Dict[str, int] = {}
    mapping: dict[str, list[str]] = {
        "str": ["STR", "Strength", "StrengthScore", "StrScore", "Strength Score"],
        "dex": ["DEX", "Dexterity", "DexterityScore", "DexScore", "Dexterity Score"],
        "con": ["CON", "Constitution", "ConstitutionScore", "ConScore", "Constitution Score"],
        "int": ["INT", "Intelligence", "IntelligenceScore", "IntScore", "Intelligence Score"],
        "wis": ["WIS", "Wisdom", "WisdomScore", "WisScore", "Wisdom Score"],
        "cha": ["CHA", "Charisma", "CharismaScore", "ChaScore", "Charisma Score"],
    }

    for key, candidates in mapping.items():
        n = _extract_pdf_widget_int(fields, candidates, min_value=1, max_value=30)
        if isinstance(n, int):
            result[key] = n

    return result


def _extract_ac_from_pdf_widgets(fields: Dict[str, str]) -> int | None:
    if not fields:
        return None
    candidates = [
        "ArmorClass",
        "Armor Class",
        "ARMORCLASS",
        "AC",
    ]
    return _extract_pdf_widget_int(fields, candidates, min_value=1, max_value=50)


def _extract_hp_from_pdf_widgets(fields: Dict[str, str]) -> Dict[str, int]:
    if not fields:
        return {}

    hp_current = _extract_pdf_widget_int(
        fields,
        [
            "CurrentHitPoints",
            "Current Hit Points",
            "HitPointsCurrent",
            "Hit Points Current",
            "HPCurrent",
            "HP Current",
            "CurrentHP",
            "Current HP",
            "HP",
            "Hit Points",
        ],
        min_value=0,
        max_value=5000,
    )
    hp_max = _extract_pdf_widget_int(
        fields,
        [
            "HitPointMaximum",
            "Hit Point Maximum",
            "MaximumHitPoints",
            "Maximum Hit Points",
            "HitPointsMax",
            "Hit Points Max",
            "HPMax",
            "HP Max",
            "MaxHP",
            "Max HP",
        ],
        min_value=0,
        max_value=5000,
    )
    hp_temp = _extract_pdf_widget_int(
        fields,
        [
            "TemporaryHitPoints",
            "Temporary Hit Points",
            "TempHitPoints",
            "Temp Hit Points",
            "HPTemp",
            "HP Temp",
            "TempHP",
            "Temp HP",
        ],
        min_value=0,
        max_value=5000,
    )

    # Heuristic fallback: look for keys containing "hitpoints" and parse values.
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())

    for k, v in fields.items():
        if v is None:
            continue
        nk = norm(k)
        if "hitpoints" not in nk and "hitpoint" not in nk and not nk.startswith("hp"):
            continue

        nums = [
            _as_int(x)
            for x in re.findall(r"-?\d{1,4}", str(v))
            if _as_int(x) is not None
        ]
        nums = [n for n in nums if isinstance(n, int) and 0 <= n <= 5000]
        if not nums:
            continue

        if "temp" in nk or nk.endswith("temphp"):
            hp_temp = hp_temp if isinstance(hp_temp, int) else nums[0]
            continue
        if "max" in nk or "maximum" in nk:
            hp_max = hp_max if isinstance(hp_max, int) else nums[0]
            continue
        if "current" in nk:
            hp_current = hp_current if isinstance(hp_current, int) else nums[0]
            continue

        # If the value is like "12/20", treat it as current/max.
        if len(nums) >= 2 and "/" in str(v):
            hp_current = hp_current if isinstance(hp_current, int) else nums[0]
            hp_max = hp_max if isinstance(hp_max, int) else nums[1]
            continue

        # Otherwise treat as current if unset.
        hp_current = hp_current if isinstance(hp_current, int) else nums[0]

    # Sanity: if only one is present, use it for both.
    if isinstance(hp_current, int) and not isinstance(hp_max, int):
        hp_max = hp_current
    if isinstance(hp_max, int) and not isinstance(hp_current, int):
        hp_current = hp_max
    if isinstance(hp_current, int) and isinstance(hp_max, int) and hp_max < hp_current:
        hp_max = hp_current

    out: Dict[str, int] = {}
    if isinstance(hp_current, int):
        out["current"] = hp_current
    if isinstance(hp_max, int):
        out["max"] = hp_max
    if isinstance(hp_temp, int) and hp_temp > 0:
        out["temp"] = hp_temp
    return out


def _extract_features_from_pdf_widgets(fields: Dict[str, str]) -> list[str]:
    if not fields:
        return []

    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())

    def _clean_feature_title(raw: str) -> str | None:
        s = (raw or "").strip()
        if not s:
            return None

        # Drop boilerplate headings and empty placeholders.
        if re.search(r"={2,}", s):
            return None
        if s.upper() == s and len(s) <= 80 and any(k in s.upper() for k in ("SPECIES", "TRAITS", "FEATURES", "FEATS", "CLASS")):
            return None
        if s.lower() in {"features", "traits", "features & traits", "features and traits"}:
            return None

        # Strip common bullets/indentation.
        s = re.sub(r"^[\s\*\-\u2022•|]+", "", s).strip()
        if not s:
            return None

        # Prefer the leading title before source/description separators.
        parts = re.split(r"\s*(?:\uFFFD|—|–|\|)\s*|\s{2,}", s, maxsplit=1)
        if parts:
            left = parts[0].strip()
            right = parts[1].strip() if len(parts) > 1 else ""
            if right and len(left) <= 80:
                s = left

        # Remove trailing source references like "PHB 65" or "TCoE 35".
        s = re.sub(r"\s+[A-Z]{2,5}\s*\d{1,4}$", "", s).strip()

        # Trim action/time suffixes (e.g., ": 1 Action", ": Bonus Action").
        s = re.sub(
            r":\s*(\d+\s*)?(bonus\s+action|action|reaction|short rest|long rest|minute|minutes|hour|hours)\b.*$",
            "",
            s,
            flags=re.I,
        ).strip()

        # Final sanity checks.
        if len(s) < 2:
            return None
        if len(s) > 200:
            s = s[:200].rstrip() + "…"
        return s

    # Prefer the canonical DDB field (varies slightly by export).
    preferred_keys = {"featurestraits", "featuresandtraits"}
    preferred_blobs: list[str] = []
    fallback_blobs: list[str] = []
    for k, v in fields.items():
        if not v or not str(v).strip():
            continue
        nk = norm(k)
        text = str(v).strip()
        if len(text) < 10:
            continue
        if any(pk in nk for pk in preferred_keys):
            preferred_blobs.append(text)
            continue
        # Very conservative fallback: only allow explicit "features"/"traits" keys with multi-line content.
        if nk in {"features", "traits"} and ("\n" in text or len(text) > 120):
            fallback_blobs.append(text)

    hits = preferred_blobs or fallback_blobs
    if not hits:
        return []

    # Split into readable lines; keep unique.
    features: list[str] = []
    seen: set[str] = set()
    # Use the largest blob first (most likely to contain the full list).
    hits = sorted(hits, key=lambda s: len(s), reverse=True)
    for blob in hits[:5]:
        for raw_line in re.split(r"\r?\n", blob):
            line = (raw_line or "").strip()
            if not line:
                continue

            # Only keep explicit bullet/option lines to avoid descriptions.
            if not re.match(r"^[\s\*\-\u2022•|]", line):
                continue

            candidate = _clean_feature_title(line)
            if not candidate:
                continue
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            features.append(candidate)
            if len(features) >= 120:
                break
        if len(features) >= 120:
            break

    if not features:
        for blob in hits[:5]:
            for raw_line in re.split(r"\r?\n", blob):
                line = (raw_line or "").strip()
                if not line:
                    continue
                if len(line) > 120:
                    continue
                candidate = _clean_feature_title(line)
                if not candidate:
                    continue
                key = candidate.lower()
                if key in seen:
                    continue
                seen.add(key)
                features.append(candidate)
                if len(features) >= 120:
                    break
            if len(features) >= 120:
                break

    return features


def _extract_skills_from_pdf_widgets(fields: Dict[str, str]) -> list[Dict[str, Any]]:
    """Extract skill entries from PDF widget key/value pairs.

    Works for any TTRPG PDF: looks for widget keys whose names look like skill
    names (no numbers, not a known stat abbreviation, not metadata), and builds
    lightweight structured entries with name, modifier, and proficiency hints.

    Returns a list of ``{"name": str, "modifier": int | None, "proficient": bool}``.
    """
    if not fields:
        return []

    # Known non-skill single-word keys to skip (stats, metadata, etc.)
    _skip_keys = {
        "str", "dex", "con", "int", "wis", "cha",
        "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma",
        "level", "race", "class", "background", "name", "hp", "ac",
        "initiative", "speed", "proficiency", "proficiency bonus",
        "charactername", "playername", "experience", "alignment",
    }

    def _norm(s: str) -> str:
        return re.sub(r"[^a-z ]", "", s.lower()).strip()

    skills: list[Dict[str, Any]] = []
    seen: set[str] = set()

    for raw_key, raw_value in fields.items():
        # Normalise key: strip non-alpha/space chars, lowercase
        key = _norm(raw_key)
        if not key or key in _skip_keys:
            continue

        # Skip keys that match common metadata patterns
        if re.match(
            r"(armor|armorclass|hitpoint|passive|spell|weight|encumber|backstory"
            r"|personality|ideals?|bonds?|flaw|allies|features|traits|attack|death"
            r"|currency|pp|gp|ep|sp|cp|languages|proficiencies|equipment|tool)",
            key,
        ):
            continue

        # The value should look like a numeric modifier or a checkbox/proficiency flag
        val = (raw_value or "").strip()
        if not val:
            continue

        # Parse modifier: first integer-like token in the value (up to 4 digits,
        # covers percentile systems like Call of Cthulhu with values up to 100+)
        mod_match = re.search(r"([+\-]?\d{1,4})", val)
        modifier: int | None = None
        if mod_match:
            try:
                modifier = int(mod_match.group(1))
            except ValueError:
                pass

        # Proficiency hint: value looks like "Yes", "true", "1", "●", "✓"
        proficient = False
        if re.match(r"^(yes|true|1|●|✓|x|checked|on)$", val, re.I):
            proficient = True
        # Some PDFs show "+prof" suffix
        if "prof" in val.lower():
            proficient = True

        # Only include if we got at least a modifier or it's flagged proficient
        if modifier is None and not proficient:
            continue

        # Use a readable title-case skill name
        display_name = key.title()
        key_dedup = key
        if key_dedup in seen:
            continue
        seen.add(key_dedup)

        skills.append({
            "name": display_name,
            "modifier": modifier,
            "proficient": proficient,
        })

        if len(skills) >= 200:
            break

    return skills


def _extract_inventory_from_pdf_widgets(fields: Dict[str, str]) -> list[str]:
    """Extract equipment/inventory items from PDF widget key/value pairs.

    Looks for fields named 'Equipment', 'Inventory', 'Item*', 'Gear', etc.
    and returns a deduplicated list of item name strings.
    """
    if not fields:
        return []

    def _norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower()).strip()

    # Gather text blobs from equipment/inventory/item fields
    blobs: list[str] = []
    for raw_key, raw_value in fields.items():
        if not raw_value or not str(raw_value).strip():
            continue
        key = _norm(raw_key)
        # Match equipment/inventory/gear/item fields
        if re.match(r"(equipment|inventory|gear|item|weapon|armor|tool|backpack)", key):
            blobs.append(str(raw_value).strip())

    if not blobs:
        return []

    items: list[str] = []
    seen: set[str] = set()
    for blob in blobs:
        # Try splitting on newlines first, then comma fallback
        lines = re.split(r"\r?\n", blob)
        if len(lines) == 1 and "," in blob:
            lines = [p.strip() for p in blob.split(",")]
        for line in lines:
            s = re.sub(r"^[\s\*\-\u2022•|]+|[\s\*\-\u2022•|]+$", "", line).strip()
            if not s or len(s) < 2 or len(s) > 200:
                continue
            # Skip obvious non-item lines (currencies, weight values, metadata labels)
            if re.match(r"^\d+\s*(gp|sp|cp|ep|pp)$|^\d+\s*lbs?$|^(weight|total|capacity)s?$", s, re.I):
                continue
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(s)
            if len(items) >= 200:
                break
        if len(items) >= 200:
            break

    return items


def _extract_proficiencies_from_pdf_widgets(fields: Dict[str, str]) -> Dict[str, list[str]]:
    """Extract languages and proficiency lists from PDF widget fields."""
    if not fields:
        return {}

    def _split_blob(blob: str) -> list[str]:
        parts: list[str] = []
        for line in re.split(r"\r?\n|,|;", blob):
            s = re.sub(r"^[\s\*\-\u2022•]+|[\s\*\-\u2022•]+$", "", line).strip()
            if s and 1 < len(s) <= 120:
                parts.append(s)
        return parts

    def _find_blob(patterns: list[str]) -> str | None:
        for k, v in fields.items():
            if not v or not str(v).strip():
                continue
            if any(re.search(pat, k, re.I) for pat in patterns):
                return str(v).strip()
        return None

    languages_blob = _find_blob([r"languages?", r"language\s*proficiencies"])
    armor_blob = _find_blob([r"armor\s*prof", r"armorprof"])
    weapon_blob = _find_blob([r"weapon\s*prof", r"weaponprof"])
    tool_blob = _find_blob([r"tool\s*prof", r"toolprof"])
    other_blob = _find_blob([r"other\s*prof", r"proficiencies\s*&?\s*languages?"])

    result: Dict[str, list[str]] = {}
    if languages_blob:
        result["languages"] = _split_blob(languages_blob)
    if armor_blob:
        result["armor_proficiencies"] = _split_blob(armor_blob)
    if weapon_blob:
        result["weapon_proficiencies"] = _split_blob(weapon_blob)
    if tool_blob:
        result["tool_proficiencies"] = _split_blob(tool_blob)
    if other_blob:
        result["other_proficiencies"] = _split_blob(other_blob)
    return result


def _read_pdf_text(content: bytes) -> str | None:
    """Extract plain text from a PDF binary. Falls back to utf-8 decoding.

    This is best-effort: PDF parsing may fail for non-PDF uploads, so we
    gracefully fall back to decoding bytes as text.
    """
    if not content:
        return None
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        pages: list[str] = []
        for p in reader.pages:
            try:
                t = p.extract_text() or ""
            except Exception:
                t = ""
            if t:
                pages.append(t)
        if pages:
            return "\n\n".join(pages)
    except Exception:
        # Fall through to text decoding below
        pass

    # Second pass: pdfplumber can yield better table-aligned text.
    try:
        import io

        import pdfplumber

        pages: list[str] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                try:
                    t = page.extract_text(layout=True) or ""
                except Exception:
                    t = ""
                if not t:
                    try:
                        t = page.extract_text() or ""
                    except Exception:
                        t = ""
                if t:
                    pages.append(t)
        if pages:
            return "\n\n".join(pages)
    except Exception:
        pass

    # OCR fallback (for image-only PDFs) using CLI tools.
    if os.environ.get("TAVERNTAILS_ENABLE_OCR", "1") == "1":
        try:
            tesseract_cmd = os.environ.get("TAVERNTAILS_TESSERACT_CMD", "tesseract")
            pdftoppm_cmd = os.environ.get("TAVERNTAILS_PDFTOPPM_CMD", "pdftoppm")
            with tempfile.TemporaryDirectory() as tmpdir:
                pdf_path = os.path.join(tmpdir, "source.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(content)

                base = os.path.join(tmpdir, "page")
                subprocess.run(
                    [pdftoppm_cmd, "-png", "-r", "200", pdf_path, base],
                    check=True,
                    capture_output=True,
                )
                images = sorted(glob.glob(base + "-*.png"))
                ocr_pages: list[str] = []
                for img in images:
                    proc = subprocess.run(
                        [tesseract_cmd, img, "stdout"],
                        check=True,
                        capture_output=True,
                    )
                    text = proc.stdout.decode("utf-8", errors="ignore")
                    if text:
                        ocr_pages.append(text)
                if ocr_pages:
                    return "\n\n".join(ocr_pages)
        except Exception:
            pass

    # Best-effort fallback: try to decode the bytes as UTF-8 (or latin-1)
    try:
        return content.decode("utf-8")
    except Exception:
        try:
            return content.decode("latin-1")
        except Exception:
            return None


def _extract_fields_from_text(text: str | None) -> tuple[str | None, int | None, str | None]:
    """Heuristic extraction of name, level, and class from arbitrary text.

    Keep this conservative: return None for fields we can't confidently extract.
    """
    if not text or not isinstance(text, str):
        return None, None, None

    lines = [line.strip() for line in re.split(r"\r?\n", text) if line and line.strip()]
    name: str | None = None
    level: int | None = None
    class_name: str | None = None

    # Find level by regex like 'Level 3' or 'LVL 3'
    for line in lines[:12]:
        m = re.search(r"\blevel\b[:\s]*([0-9]{1,2})", line, flags=re.I)
        if m:
            level = _as_int(m.group(1))
            break
        m2 = re.search(r"\b(LVL|LV)\b[:\s]*([0-9]{1,2})", line, flags=re.I)
        if m2:
            level = _as_int(m2.group(2))
            break

    # Known class names for conservative matching
    classes = [
        "Artificer",
        "Barbarian",
        "Bard",
        "Cleric",
        "Druid",
        "Fighter",
        "Monk",
        "Paladin",
        "Ranger",
        "Rogue",
        "Sorcerer",
        "Warlock",
        "Wizard",
    ]

    # Try to find a line that looks like a class or 'Class / Level' combined line.
    for line in lines[:8]:
        up = line.upper()
        # Skip template-like headings
        if any(x in up for x in ("CLASS & LEVEL", "PLAYER NAME", "CHARACTER NAME", "SPECIES", "BACKGROUND")):
            continue
        # If the line contains a known class name and a number, capture both.
        for cname in classes:
            if re.search(rf"\b{re.escape(cname)}\b", line, flags=re.I):
                class_name = cname if not class_name else class_name
                # try to find an inline level
                m = re.search(r"(\d{1,2})", line)
                if m and level is None:
                    level = _as_int(m.group(1))
                break

    # Heuristic for name: pick the first short line that is not a template heading
    for line in lines[:6]:
        up = line.upper()
        if any(x in up for x in ("CLASS", "LEVEL", "PLAYER NAME", "CHARACTER NAME", "SPECIES", "BACKGROUND")):
            continue
        # Avoid lines that look like page headers/metadata (contain too many digits or slashes)
        if re.search(r"\d", line) and len(re.findall(r"[A-Za-z]", line)) < 3:
            continue
        # Accept short single-line names
        if 1 <= len(line) <= 60:
            name = line
            break

    return name, level, class_name


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value).strip() or None


def _extract_spells_from_text(text: str | None) -> list[str]:
    """Try to extract spell names from extracted PDF text.

    Heuristic: find CANTRIPS / SPELLS headings and collect following bullet lines
    until a blank line or another heading. Also look for 'Spellcasting' blocks.
    """
    if not text or not isinstance(text, str):
        return []
    out: list[str] = []
    seen: set[str] = set()
    lines = re.split(r"\r?\n", text)
    in_spell_block = False
    for raw_line in lines:
        line = (raw_line or '').strip()
        if not line:
            in_spell_block = False
            continue
        # heading detection
        if re.search(r"\b(CANTRIPS|SPELLS|KNOWN SPELLS|SPELLCASTING)\b", line, re.I):
            in_spell_block = True
            continue
        if not in_spell_block:
            continue
        # remove bullets and separators
        m = re.match(r"^[\u2022\*\-\s]*\s*(.*)$", raw_line)
        candidate = (m.group(1).strip() if m else line).strip()
        # sanitize candidate: skip short tokens and tokens that look like components or metadata
        if not candidate or len(candidate) < 2:
            continue
        if re.match(r"^[VSMvsm/.,()\s-]+$", candidate):
            continue
        # drop tokens that are clearly metadata (PHB, durations like '1 minute', ranges like '30 ft')
        if re.match(r"^(PHB|TCoE|VGtM|BR)$", candidate):
            continue
        if re.match(r"^\d+\s*(ft|minute|hour|h|m|\/|\d+)$", candidate):
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
        if len(out) >= 200:
            break
    return out


def _extract_spellbook_from_text(text: str | None, debug: bool = False) -> list[dict[str, Any]]:
    """Extract structured spell rows from PDF text tables.

    Looks for headers like "SPELL NAME" or "PREP SPELL NAME" and parses
    subsequent rows by splitting on 2+ spaces.
    """
    if not text or not isinstance(text, str):
        return []

    lines = [ln.strip() for ln in re.split(r"\r?\n", text) if ln and ln.strip()]
    entries: list[dict[str, Any]] = []
    in_table = False
    current_header: str | None = None
    sources = [
        "Artificer",
        "Barbarian",
        "Bard",
        "Cleric",
        "Druid",
        "Fighter",
        "Monk",
        "Paladin",
        "Ranger",
        "Rogue",
        "Sorcerer",
        "Warlock",
        "Wizard",
        "Acolyte of Nature",
    ]

    def _split_cols(line: str) -> list[str]:
        return [c.strip() for c in re.split(r"\s{2,}", line) if c and c.strip()]

    def _page_ref(line: str) -> str | None:
        m = re.search(r"\b([A-Z]{2,5})\s*(\d{2,4})\b", line)
        if m:
            return f"{m.group(1)} {m.group(2)}"
        return None

    def _components(line: str) -> str | None:
        m = re.search(r"\bV\s*,?\s*S\s*,?\s*M\b|\bV\s*,?\s*S\b|\bV\b|\bS\b|\bM\b", line, re.I)
        if m:
            return m.group(0).replace(" ", "")
        return None

    def _duration(line: str) -> str | None:
        m = re.search(r"\b(instantaneous|concentration|up to \d+\s*(rounds?|minutes?|hours?|days?)|\d+\s*(rounds?|minutes?|hours?|days?))\b", line, re.I)
        return m.group(1) if m else None

    def _time(line: str) -> str | None:
        m = re.search(r"\b(\d+\s*BA|\d+\s*A|\d+\s*R|\d+\s*rounds?|\d+\s*minutes?|\d+\s*hours?|action|bonus action|reaction)\b", line, re.I)
        return m.group(1) if m else None

    def _range(line: str) -> str | None:
        m = re.search(r"\b(self|touch|sight|special|\d+\s*ft\.?|\d+\s*feet|\d+\s*mi\.?|\d+\s*miles?)\b", line, re.I)
        return m.group(1) if m else None

    for raw in lines:
        line = raw.strip()
        if re.match(r"^[=\-]{2,}\s*.*\s*[=\-]{2,}$", line):
            header = re.sub(r"^[=\-]+|[=\-]+$", "", line).strip()
            if header:
                current_header = header
            continue

        if re.match(r"^\(at will\)$", line, re.I):
            if current_header:
                current_header = f"{current_header} (At Will)"
            continue

        # Detect table header (various formats)
        if (
            (re.search(r"\b(PREP\s+)?SPELL\s+NAME\b", line, re.I) and re.search(r"\bSOURCE\b", line, re.I)) or
            (re.search(r"\bNAME\b", line, re.I) and re.search(r"\b(SAVE|ATK|HIT)\b", line, re.I)) or
            (re.search(r"\bSPELL\b", line, re.I) and re.search(r"\b(TIME|RANGE|COMP|DUR)\b", line, re.I))
        ):
            in_table = True
            continue

        if not in_table:
            # Track cantrip/level headers
            if re.match(r"^(cantrips?|\d+(st|nd|rd|th)\s+level)$", line, re.I):
                current_header = line
            # If we see a recognizable spell-like line after a header, treat as simple list
            elif current_header and len(line) > 2 and not re.match(r"^[=\-]+$", line):
                # Aggressively filter out metadata - only accept lines that look like spell names

                # Skip empty or dash-only lines
                if re.match(r"^[—\-\s]+$", line):
                    continue

                # Skip class names
                if re.match(r"^(druid|cleric|wizard|sorcerer|bard|warlock|paladin|ranger|artificer|fighter|monk|rogue|barbarian|acolyte|monk)$", line, re.I):
                    continue

                # Skip lines containing "/" or "," (components, class combos, stats)
                if "/" in line or "," in line:
                    continue

                # Skip obvious metadata: stats, durations, ranges, components, pages, actions
                if re.match(r"^(\d+\s*[ABR]A?|[1-9]\s*BA|[1-9]\s*A|[1-9]\s*R|action|bonus\s*action|reaction|touch|self|sight|\d+\s*ft|phb|ee|xgte|tcoe|scag|v|s|m|v/s|s/m|v/m|v/s/m|instantaneous|concentration|wis|int|cha|dex|str|con)$", line, re.I):
                    continue

                # Skip lines with colon prefix (D:, R:, C:, T:, etc)
                if re.match(r"^[A-Z]:\s*", line):
                    continue

                # Skip parenthetical notes
                if re.match(r"^\(", line):
                    continue

                # Skip pure numbers, short codes, durations, or all-caps abbreviations
                if re.match(r"^(\d+|[A-Z]{1,3}|\d+m|\d+h|\d+\s*min|\d+\s*hr|\d+\s*hour)$", line):
                    continue

                # Skip page references
                if re.search(r"\b(PHB|EE|XGTE|TCOE|SCAG)\s*\d+", line, re.I):
                    continue

                # Skip common spell attributes that appear alone
                if re.match(r"^(prepared|ritual|—)$", line, re.I):
                    continue

                # If it passed all filters, treat as spell name
                entries.append({"name": line, "header": current_header})
                if len(entries) >= 500:
                    break
            continue

        # stop table on obvious section separators
        if re.match(r"^(page\s+\d+|notes?)$", line, re.I):
            in_table = False
            continue

        cols = _split_cols(line)
        prepared = None
        if cols and cols[0] in {"O", "0", "○", "◯", "•", "x", "X"}:
            prepared = "yes" if cols[0].lower() != "x" else "no"
            cols = cols[1:]

        if len(cols) >= 6:
            name = cols[0]
            source = cols[1] if len(cols) > 1 else None
            save_hit = cols[2] if len(cols) > 2 else None
            time = cols[3] if len(cols) > 3 else None
            range_ = cols[4] if len(cols) > 4 else None
            components = cols[5] if len(cols) > 5 else None
            duration = cols[6] if len(cols) > 6 else None
            page = cols[7] if len(cols) > 7 else None
            notes = " ".join(cols[8:]) if len(cols) > 8 else None
            entries.append(
                {
                    "name": name,
                    "source": source,
                    "save_hit": save_hit,
                    "time": time,
                    "range": range_,
                    "components": components,
                    "duration": duration,
                    "page": page,
                    "notes": notes,
                    "prepared": prepared,
                    "header": current_header,
                }
            )
            if len(entries) >= 500:
                break
            continue

        # Fallback: parse noisy OCR lines with regex heuristics
        scan_line = line
        prep = None
        if re.match(r"^[O0○◯•xX]\s+", scan_line):
            prep = "yes" if scan_line[0].lower() != "x" else "no"
            scan_line = scan_line[1:].strip()

        source = None
        name = None
        rest = scan_line
        for s in sources:
            m = re.search(rf"\b{re.escape(s)}\b", scan_line)
            if m:
                source = s
                name = scan_line[: m.start()].strip()
                rest = scan_line[m.end():].strip()
                break
        if not name:
            continue

        page = _page_ref(scan_line)
        components = _components(scan_line)
        duration = _duration(scan_line)
        time = _time(scan_line)
        range_ = _range(scan_line)

        save_hit = None
        m_save = re.search(r"\b([A-Z]{3})\s*(\+?\d{1,2})\b", rest)
        if m_save:
            save_hit = f"{m_save.group(1)} {m_save.group(2)}"
        else:
            m_save2 = re.search(r"\b([+\-]?\d{1,2})\b", rest)
            if m_save2:
                save_hit = m_save2.group(1)

        entries.append(
            {
                "name": name,
                "source": source,
                "save_hit": save_hit,
                "time": time,
                "range": range_,
                "components": components,
                "duration": duration,
                "page": page,
                "notes": None,
                "prepared": prep,
                "header": current_header,
            }
        )

        if len(entries) >= 500:
            break

    return entries


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        v = value.strip()
        if v.isdigit():
            return int(v)
    try:
        return int(value)
    except Exception:
        return None


def _extract_character_fields(raw: Dict[str, Any]) -> tuple[str | None, int | None, str | None]:
    """Best-effort extraction from arbitrary JSON blobs.

    We intentionally keep this flexible because different exports have different shapes.
    """
    def _class_name_from_classes_list(classes: Any) -> str | None:
        if not isinstance(classes, list) or not classes:
            return None
        names: list[str] = []
        for item in classes:
            if not isinstance(item, dict):
                continue
            cname = _as_str(item.get("name") or item.get("class") or item.get("class_name"))
            if cname:
                names.append(cname)
        if not names:
            return None
        if len(names) == 1:
            return names[0]
        return " / ".join(names[:3])

    def _level_from_classes_list(classes: Any) -> int | None:
        if not isinstance(classes, list) or not classes:
            return None
        total = 0
        found_any = False
        for item in classes:
            if not isinstance(item, dict):
                continue
            lvl = _as_int(item.get("level"))
            if isinstance(lvl, int):
                total += lvl
                found_any = True
        return total if found_any else None

    name: str | None = None
    level: int | None = None
    class_name: str | None = None

    # Search likely roots in order: top-level, then common nesting wrappers.
    roots: list[Dict[str, Any]] = [raw]
    for key in ("character", "data"):
        nested = raw.get(key)
        if isinstance(nested, dict):
            roots.append(nested)

    for root in roots:
        name = name or _as_str(root.get("name"))
        level = level or _as_int(root.get("level") or root.get("characterLevel"))
        class_name = class_name or _as_str(root.get("class_name") or root.get("class"))

        classes = root.get("classes")
        if class_name is None:
            class_name = _class_name_from_classes_list(classes)
        if level is None:
            level = _level_from_classes_list(classes)

        # If the class is an object (common in some exports), try to pull its name.
        if class_name is None:
            cls_obj = root.get("class")
            if isinstance(cls_obj, dict):
                class_name = _as_str(cls_obj.get("name"))

        # Alternative shapes.
        if class_name is None:
            class_info = root.get("classInfo")
            if isinstance(class_info, dict):
                class_name = _as_str(class_info.get("name"))

        if name and level is not None:
            break

    return name, level, class_name


def _build_character_import_sheet_from_json(
    *,
    raw_json: str,
    ddb_url: str | None,
    source: str | None,
) -> tuple[str, int, str | None, Dict[str, Any]]:
    try:
        parsed = json.loads(raw_json)
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid JSON") from err
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="JSON must be an object")

    name, level, class_name = _extract_character_fields(parsed)
    if not name:
        name = "Imported Character"

    safe_level = level if isinstance(level, int) else 1
    safe_level = max(1, min(20, safe_level))

    sheet: Dict[str, Any] = {
        "import": {
            "source": source or "upload",
            "imported_at": _now_iso(),
            "ddb_url": ddb_url,
        },
        "raw": parsed,
    }

    # Detect TTRPG system from whatever the JSON provides.
    try:
        detect_input = {
            "class_name": class_name,
            "multiclass": parsed.get("classes") or [],
            "skills": parsed.get("skills") or [],
            "stats": parsed.get("stats") or parsed.get("abilities") or {},
            "raw_text": raw_json[:10000],
            "import": {"source": source, "ddb_url": ddb_url},
        }
        sheet["detected_system"] = infer_ttrpg_system(detect_input)
    except Exception:
        pass

    return name, safe_level, class_name, sheet


def _build_character_import_sheet_from_pdf(
    *,
    content: bytes,
    filename: str | None,
    name_override: str | None,
    level_override: int | None,
    class_name_override: str | None,
    ddb_url: str | None,
    source: str | None,
) -> tuple[str, int, str | None, Dict[str, Any]]:
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    widget_values = _read_pdf_widget_values(content)
    widget_name, widget_level, widget_class_name = _extract_fields_from_pdf_widgets(widget_values)

    stats_from_widgets = _extract_stats_from_pdf_widgets(widget_values)
    ac_from_widgets = _extract_ac_from_pdf_widgets(widget_values)
    hp_from_widgets = _extract_hp_from_pdf_widgets(widget_values)
    features_from_widgets = _extract_features_from_pdf_widgets(widget_values)
    skills_from_widgets = _extract_skills_from_pdf_widgets(widget_values)
    inventory_from_widgets = _extract_inventory_from_pdf_widgets(widget_values)
    proficiencies_from_widgets = _extract_proficiencies_from_pdf_widgets(widget_values)

    # Try to group features into class / racial / other using widget keys when available.
    class_features: list[str] = []
    racial_features: list[str] = []
    other_features: list[str] = []
    # Collect blobs by key hints
    class_blobs: list[str] = []
    race_blobs: list[str] = []
    other_blobs: list[str] = []
    for k, v in widget_values.items():
        if not v or not isinstance(v, str):
            continue
        kn = k.lower()
        if "class" in kn and len(v.strip()) > 10:
            class_blobs.append(v)
        elif any(x in kn for x in ("race", "species", "subrace", "racial")) and len(v.strip()) > 10:
            race_blobs.append(v)
        elif any(x in kn for x in ("feature", "trait")) and len(v.strip()) > 10:
            other_blobs.append(v)

    def _lines_from_blobs(blobs: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for blob in blobs:
            for line in re.split(r"\r?\n", blob):
                s = re.sub(r"^[ \t\r\n•\-*_\u2022]+|[ \t\r\n•\-*_\u2022]+$", "", line)
                if not s:
                    continue
                key = s.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(s if len(s) <= 200 else s[:200].rstrip() + "…")
                if len(out) >= 200:
                    break
            if len(out) >= 200:
                break
        return out

    text = _read_pdf_text(content)
    # Combine extracted page text + widget key/value lines for better downstream parsing.
    widget_lines = "\n".join([f"{k}: {v}" for k, v in list(widget_values.items())[:600]])
    combined_text = (text or "") + ("\n\n" + widget_lines if widget_lines else "")
    extracted_name, extracted_level, extracted_class_name = _extract_fields_from_text(combined_text)

    # Prefer widget-derived values over regex-from-text values.
    if widget_name:
        extracted_name = widget_name
    if isinstance(widget_level, int):
        extracted_level = widget_level
    if widget_class_name:
        extracted_class_name = widget_class_name

    # Extract spells from combined text as a fallback (cantrip/spell lists inside feature blobs)
    spells_from_text = _extract_spells_from_text(combined_text)
    final_name = _as_str(name_override) or extracted_name or _guess_character_name_from_filename(filename)
    if not final_name:
        final_name = "Imported Character"

    final_level = level_override if isinstance(level_override, int) else extracted_level
    final_class_name = _as_str(class_name_override) or extracted_class_name

    class_features = _lines_from_blobs(class_blobs)
    racial_features = _lines_from_blobs(race_blobs)
    other_features = _lines_from_blobs(other_blobs)
    # If grouping failed, fall back to the general extracted features list.
    if not class_features and features_from_widgets:
        # try to pick entries that mention the class name
        if final_class_name:
            cands = [f for f in features_from_widgets if final_class_name.lower() in f.lower()]
            class_features = cands
    if not racial_features and features_from_widgets:
        # rough heuristic: look for common race/species words or short lists near top
        cands = [f for f in features_from_widgets if any(x in f.lower() for x in ("elf", "dwarf", "halfling", "human", "tiefling", "dragonborn", "gnome", "goliath", "aasimar"))]
        racial_features = cands
    # remaining go to other_features
    remaining = [f for f in features_from_widgets if f not in class_features and f not in racial_features]
    other_features = other_features or remaining

    safe_level = final_level if isinstance(final_level, int) else 1
    safe_level = max(1, min(20, safe_level))

    class_names = [
        # D&D 5e
        "Artificer", "Barbarian", "Bard", "Cleric", "Druid", "Fighter",
        "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard",
        # Pathfinder 2e (including Remaster classes)
        "Alchemist", "Champion", "Investigator", "Magus", "Oracle", "Psychic",
        "Summoner", "Swashbuckler", "Thaumaturge", "Witch",
        "Animist", "Exemplar", "Commander", "Guardian",
    ]

    def _first_widget_value(patterns: list[str]) -> str | None:
        for k, v in widget_values.items():
            if not v:
                continue
            for pat in patterns:
                if re.search(pat, str(k), re.I):
                    return _as_str(v)
        return None

    def _first_widget_int(patterns: list[str]) -> int | None:
        val = _first_widget_value(patterns)
        if val is None:
            return None
        m = re.search(r"(\d+)", str(val))
        return int(m.group(1)) if m else _as_int(val)

    passives = {
        "perception": _first_widget_int([r"passive\s*perception", r"passive\s*perc", r"passiveperc"]),
        "insight": _first_widget_int([r"passive\s*insight", r"passiveinsight"]),
        "investigation": _first_widget_int([r"passive\s*investigation", r"passiveinvestigation"]),
    }

    # PF2e uses "Ancestry" in place of Race/Species; prefer it if present.
    species = (
        _first_widget_value([r"\bancestry\b"])
        or _first_widget_value([r"\brace\b", r"species", r"subrace"])
    )
    background = _first_widget_value([r"background"])

    # Pathfinder 2e-specific fields
    heritage = _first_widget_value([r"\bheritage\b"])
    class_dc = _first_widget_int([r"class\s*dc\b", r"classdc"])
    focus_points_max = _first_widget_int([r"focus\s*points?\s*max", r"max\s*focus\s*points?", r"^focusmax$", r"^focus$"])
    focus_points_current = _first_widget_int([r"focus\s*points?\s*(current|used|spent|remaining)", r"^focuscurrent$", r"^focusused$"])

    class_line = _first_widget_value([r"class\s*&?\s*level", r"class\s*level"])

    def _parse_multiclass(text_value: str | None) -> list[dict[str, Any]]:
        if not text_value:
            return []
        out: list[dict[str, Any]] = []
        for cname in class_names:
            m = re.search(rf"\b{re.escape(cname)}\b\s*(\d{{1,2}})", text_value, re.I)
            if m:
                out.append({"class_name": cname, "level": int(m.group(1))})
        if not out and final_class_name and "/" in final_class_name:
            for part in re.split(r"\s*/\s*", final_class_name):
                if part:
                    out.append({"class_name": part.strip(), "level": None})
        return out

    multiclass = _parse_multiclass(class_line or extracted_class_name)

    carry = {
        "weight_current": _first_widget_int([r"weight\s*carried", r"carried\s*weight", r"current\s*weight"]),
        "weight_capacity": _first_widget_int([r"carry\s*capacity", r"carrying\s*capacity", r"max\s*weight"]),
        "encumbered_at": _first_widget_int([r"encumbered" ]),
        "heavily_encumbered_at": _first_widget_int([r"heavily\s*encumbered", r"heavy\s*encumbered"]),
        "use_encumbrance": False,
    }
    if any(v is not None for k, v in carry.items() if k != "use_encumbrance"):
        carry["use_encumbrance"] = True

    story = {
        "backstory": _first_widget_value([r"backstory", r"back\s*story"]),
        "personality_traits": _first_widget_value([r"personality\s*traits?"] ),
        "ideals": _first_widget_value([r"ideals?"] ),
        "bonds": _first_widget_value([r"bonds?"] ),
        "flaws": _first_widget_value([r"flaws?"] ),
        "allies": _first_widget_value([r"allies", r"organizations", r"organizations\s*&\s*allies"]),
    }

    # Detect whether the PDF is a ship/vehicle sheet rather than a character sheet.
    # Ship sheets (Pathfinder, Starfinder) typically have hull points, maneuverability,
    # drift rating, or frame fields that character sheets never have.
    _ship_sheet_patterns = [
        r"\bhull\s*points?\b", r"\bhullpoints?\b",
        r"\bmaneuverability\b",
        r"\bdrift\s*rating\b", r"\bdriftrating\b",
        r"\bship\s*name\b", r"\bshipname\b",
        r"\bship\s*type\b", r"\bshiptype\b",
        r"\bship\s*frame\b", r"\bshipframe\b",
        r"\bframe\s*hp\b", r"\bframehp\b",
        r"\bship\s*tier\b", r"\bshiptier\b",
        r"\bpcu\b",
        r"\bct\b.*\bdt\b",  # critical threshold / damage threshold (Starfinder ship stat)
        r"\bkac\b",  # KAC (Kinetic Armor Class) unique to Starfinder ships
        r"\btargeting\s*systems?\b",
    ]
    _is_ship_sheet = any(
        re.search(pat, k, re.I)
        for k in widget_values.keys()
        for pat in _ship_sheet_patterns
    )

    # Build a structured `raw` object so client-side inference helpers can read
    # values from a predictable place (e.g. `sheet.raw.speed`, `sheet.raw.deathSaves`).
    def _parse_int(v: Any) -> int | None:
        try:
            return int(str(v).strip())
        except Exception:
            return None

    def _split_lines(blob: str) -> list[str]:
        out: list[str] = []
        if not blob or not isinstance(blob, str):
            return out
        for line in re.split(r"\r?\n", blob):
            s = re.sub(r"^[ \t\r\n•\-*_\u2022]+|[ \t\r\n•\-*_\u2022]+$", "", line)
            if not s:
                continue
            if len(s) > 200:
                s = s[:200].rstrip() + "…"
            out.append(s)
            if len(out) >= 200:
                break
        return out

    raw_struct: Dict[str, Any] = {}

    # Speeds: prefer widget values, fall back to regex/text later.
    speed_keys = [k for k in widget_values.keys() if re.search(r"speed|movement|walk|base", k, re.I)]
    if speed_keys:
        speeds: Dict[str, int | None] = {"walk": None, "fly": None, "swim": None, "climb": None, "burrow": None}
        for k in speed_keys:
            v = widget_values.get(k)
            if not v:
                continue
            # Try to extract any number in the value
            m = re.search(r"(\d+)", str(v))
            if not m:
                continue
            val = _parse_int(m.group(1))
            kn = k.lower()
            if "fly" in kn or "flying" in kn:
                speeds["fly"] = val
            elif "swim" in kn or "swimming" in kn:
                speeds["swim"] = val
            elif "climb" in kn or "climbing" in kn:
                speeds["climb"] = val
            elif "burrow" in kn or "burrowing" in kn:
                speeds["burrow"] = val
            else:
                # treat as walk/base
                speeds["walk"] = val or speeds["walk"]
        raw_struct["speed"] = speeds

    # Death saves
    ds_key = next((k for k in widget_values.keys() if re.search(r"death|deathsave", k, re.I)), None)
    if ds_key:
        val = str(widget_values.get(ds_key) or "")
        # try pattern like "Successes: 2 Failures: 1" or "2/1"
        succ = None
        fail = None
        m = re.search(r"(\d+)\s*/\s*(\d+)", val)
        if m:
            succ = _parse_int(m.group(1))
            fail = _parse_int(m.group(2))
        else:
            ms = re.search(r"success(?:es)?:?\s*(\d+)", val, re.I)
            mf = re.search(r"fail(?:ures)?:?\s*(\d+)", val, re.I)
            if ms:
                succ = _parse_int(ms.group(1))
            if mf:
                fail = _parse_int(mf.group(1))
        raw_struct["deathSaves"] = {"successes": succ, "failures": fail}

    # Rest / hit dice / inspiration / exhaustion
    # Look for explicit widget keys first
    hd_used = next((widget_values.get(k) for k in widget_values.keys() if re.search(r"hitdiceused|hit_dice_used|hitdiceused", k, re.I)), None)
    hd_total = next((widget_values.get(k) for k in widget_values.keys() if re.search(r"hitdicetotal|hit_dice_total|hitdicetotal|hitdice", k, re.I)), None)
    insp = next((widget_values.get(k) for k in widget_values.keys() if re.search(r"inspiration|inspired", k, re.I)), None)
    ex = next((widget_values.get(k) for k in widget_values.keys() if re.search(r"exhaustion|exhaustionlevel", k, re.I)), None)
    hd_used_n = _parse_int(hd_used) if hd_used is not None else None
    hd_total_n = _parse_int(hd_total) if hd_total is not None else None
    insp_b = None
    if isinstance(insp, str):
        insp_b = True if insp.strip().lower() in ("yes", "true", "1") else False if insp.strip().lower() in ("no", "false", "0") else None
    elif isinstance(insp, (int, float)):
        insp_b = bool(int(insp))
    ex_n = _parse_int(ex) if ex is not None else None
    raw_struct["rest"] = {"hitDiceUsed": hd_used_n, "hitDiceTotal": hd_total_n, "inspiration": insp_b, "exhaustion": ex_n}

    # Spells: prefer spellName widgets; otherwise fall back to heuristic extraction.
    spells: list[str] = []
    spell_entries: list[dict[str, Any]] = []
    spell_name_keys = [k for k in widget_values.keys() if re.match(r"^spellname\d+$", k, re.I)]

    def _spell_key_order(key: str) -> int:
        m = re.search(r"(\d+)$", key)
        return int(m.group(1)) if m else 0

    if spell_name_keys:
        # Build structured entries from indexed fields to support a table UI.
        indices = sorted({_spell_key_order(k) for k in spell_name_keys})
        for idx in indices:
            name = _as_str(widget_values.get(f"spellName{idx}"))
            if not name:
                continue
            entry: dict[str, Any] = {
                "name": name,
                "source": _as_str(widget_values.get(f"spellSource{idx}")),
                "save_hit": _as_str(widget_values.get(f"spellSaveHit{idx}")),
                "time": _as_str(widget_values.get(f"spellCastingTime{idx}")),
                "range": _as_str(widget_values.get(f"spellRange{idx}")),
                "components": _as_str(widget_values.get(f"spellComponents{idx}")),
                "duration": _as_str(widget_values.get(f"spellDuration{idx}")),
                "page": _as_str(widget_values.get(f"spellPage{idx}")),
                "notes": _as_str(widget_values.get(f"spellNotes{idx}")),
                "prepared": _as_str(widget_values.get(f"spellPrepared{idx}")),
                "header": _as_str(widget_values.get(f"spellHeader{idx}")),
                "slot_header": _as_str(widget_values.get(f"spellSlotHeader{idx}")),
            }
            spell_entries.append(entry)
            spells.append(name)
    else:
        # Try extracting structured spellbook from combined text
        spell_entries = _extract_spellbook_from_text(combined_text)
        if spell_entries:
            spells = [e.get("name") for e in spell_entries if isinstance(e.get("name"), str)]
        else:
            spell_entries = []
        for k, v in widget_values.items():
            if not v:
                continue
            # Skip spell metadata fields to avoid adding garbage
            if re.search(r"spell(source|time|range|comp|duration|page|save|hit|prepared|header|slot|level|class|school|ritual|material|attack|dc)", k, re.I):
                continue
            if re.search(r"spell|cantrip", k, re.I):
                if isinstance(v, str) and ("\n" in v or "," in v):
                    parts = re.split(r"\r?\n|,", v)
                    for p in parts:
                        s = p.strip()
                        if s:
                            spells.append(s)
                else:
                    spells.append(str(v).strip())

        # merge with text-detected spells only if widgets did not provide names
        for s in spells_from_text:
            if s:
                spells.append(s)

    def _is_noise_spell_line(text: str) -> bool:
        t = (text or '').strip()
        if not t:
            return True
        if len(t) < 3:
            return True
        # Skip widget field names (spellSource0:, spellTime1:, etc.)
        if re.match(r"^spell\w+\d*:?$", t, re.I):
            return True
        # Skip generic words that aren't spells
        if re.match(r"^(additional|your|the|and|or|of|in|to|a|an)$", t, re.I):
            return True
        # Skip empty or dash-only lines
        if re.match(r"^[—\-\s]+$", t):
            return True
        # Skip class names
        if re.match(r"^(druid|cleric|wizard|sorcerer|bard|warlock|paladin|ranger|artificer|fighter|monk|rogue|barbarian|acolyte|monk)$", t, re.I):
            return True
        # Skip lines containing "/" or "," (components, ranges, multi-values)
        if "/" in t or "," in t:
            return True
        # Skip distances/ranges (including variations like "30 ft./5 ft. Cube")
        if re.search(r"\d+\s*ft\.?|feet|mile", t, re.I):
            return True
        # Skip metadata patterns
        if re.match(r"^(\d+\s*[ABR]A?|[1-9]\s*BA|[1-9]\s*A|[1-9]\s*R|action|bonus\s*action|reaction|touch|self|sight|phb|ee|xgte|tcoe|scag|v|s|m|v/s|s/m|v/m|v/s/m|instantaneous|concentration|wis|int|cha|dex|str|con)$", t, re.I):
            return True
        # Skip lines with colon prefix
        if re.match(r"^[A-Z]:\s*", t):
            return True
        # Skip parenthetical notes
        if re.match(r"^\(", t):
            return True
        # Skip pure numbers, codes, durations
        if re.match(r"^(\d+|[A-Z]{1,3}|\d+m|\d+h|\d+\s*min|\d+\s*hr)$", t):
            return True
        # Skip page references
        if re.search(r"\b(PHB|EE|XGTE|TCOE|SCAG)\s*\d+", t, re.I):
            return True
        # Skip common spell attributes
        if re.match(r"^(prepared|ritual|—|at\s*will|===.*===)$", t, re.I):
            return True
        # Skip stat patterns
        if re.match(r"^[A-Z]{3}\s*\d+$", t) or re.match(r"^[A-Z]{3}\s*/\s*[A-Z]{3}$", t):
            return True
        # headers / separators
        if re.search(r"\b(cantrips?|spellcasting|spells?\s*known)\b", t, re.I):
            return True
        # drop obvious numeric-only or symbol-only
        if re.match(r"^[\W_0-9]+$", t):
            return True
        # Skip anything ending with asterisk or starting with asterisk (notes/annotations)
        if re.match(r"^\*|.*\*$", t):
            return True
        return False

    cleaned: list[str] = []
    seen_spells: set[str] = set()
    for s in spells:
        s2 = (s or '').strip()
        if not s2:
            continue
        # skip noise/metadata tokens
        if _is_noise_spell_line(s2):
            continue
        key = s2.lower()
        if key in seen_spells:
            continue
        seen_spells.add(key)
        cleaned.append(s2)
        if len(cleaned) >= 500:
            break

    raw_struct["spells"] = cleaned

    # Also include the combined text so clients can still inspect raw text if needed
    raw_struct["text"] = (combined_text or "")[:50000]

    sheet: Dict[str, Any] = {
        # Canonical lightweight fields used by the UI.
        "stats": stats_from_widgets,
        "ac": ac_from_widgets,
        "hp": hp_from_widgets,
        # Legacy/compat keys (some codepaths accept either shape).
        "hp_current": hp_from_widgets.get("current") if isinstance(hp_from_widgets, dict) else None,
        "hp_max": hp_from_widgets.get("max") if isinstance(hp_from_widgets, dict) else None,
        "hp_temp": hp_from_widgets.get("temp") if isinstance(hp_from_widgets, dict) else None,
        "features": features_from_widgets,
        "classFeatures": class_features,
        "racialFeatures": racial_features,
        "otherFeatures": other_features,
        "skills": skills_from_widgets,
        "inventory": inventory_from_widgets,
        "languages": proficiencies_from_widgets.get("languages", []),
        "armor_proficiencies": proficiencies_from_widgets.get("armor_proficiencies", []),
        "weapon_proficiencies": proficiencies_from_widgets.get("weapon_proficiencies", []),
        "tool_proficiencies": proficiencies_from_widgets.get("tool_proficiencies", []),
        "other_proficiencies": proficiencies_from_widgets.get("other_proficiencies", []),
        "spells": raw_struct.get("spells", []),
        "spellbook": spell_entries,
        "speed": raw_struct.get("speed"),
        "passives": passives,
        "species": species,
        "background": background,
        # Pathfinder 2e-specific fields (ignored for other systems)
        "heritage": heritage,
        "class_dc": class_dc,
        "focus_points": (
            {"max": focus_points_max, "current": focus_points_current}
            if focus_points_max is not None or focus_points_current is not None
            else None
        ),
        "multiclass": multiclass,
        "carry": carry,
        "portrait_url": None,
        "story": story,
        # sheet_type identifies non-standard sheets (e.g. "ship" for vehicle sheets).
        "sheet_type": "ship" if _is_ship_sheet else "character",
        "import": {
            "source": source or "pdf",
            "imported_at": _now_iso(),
            "ddb_url": ddb_url,
            "filename": filename,
            "warnings": [],
            "overrides": {
                "name": _as_str(name_override),
                "level": level_override if isinstance(level_override, int) else None,
                "class_name": _as_str(class_name_override),
            },
            "extracted": {
                "name": extracted_name,
                "level": extracted_level,
                "class_name": extracted_class_name,
            },
            "raw_text_len": len(text or ""),
            "pdf_widgets": {
                "count": len(widget_values),
                "valued_sample": {k: widget_values[k] for k in list(widget_values.keys())[:30]},
                # Store a bounded set of values so we can re-parse later without keeping the PDF binary.
                # Keep only non-empty values and cap size to avoid bloating DB rows.
                "values": {
                    k: str(v)[:2000]
                    for k, v in list({kk: vv for kk, vv in widget_values.items() if str(vv).strip()}.items())[:800]
                },
            },
        },
        # Store extracted text for future parsing improvements (avoid storing large binaries in DB).
        "raw_text": (combined_text or "")[:50000],
    }

    warnings: list[str] = []
    if _is_ship_sheet:
        warnings.append("Ship/vehicle sheet detected — fields may be stored as a document instead of a character")
    elif not species:
        warnings.append("Missing species")
    if not background and not _is_ship_sheet:
        warnings.append("Missing background")
    if not any(v is not None for v in passives.values()) and not _is_ship_sheet:
        warnings.append("Missing passive scores")
    if not carry.get("use_encumbrance") and not _is_ship_sheet:
        warnings.append("Missing encumbrance data")
    if warnings:
        sheet["import"]["warnings"] = warnings

    # Attach reference matches for features and spells (if reference corpus uploaded).
    try:
        refs: Dict[str, Any] = {"features": {}, "spells": {}}
        # search top 2 matches per feature/spell to avoid bloating
        top_k = 2
        # iterate combined features list (class/racial/other + general)
        all_features = list({*(class_features or []), *(racial_features or []), *(other_features or []), * (features_from_widgets or [])})
        for f in all_features[:200]:
            if not f or not isinstance(f, str):
                continue
            try:
                hits = references_agent.search_query(f, top_k=top_k)
            except Exception:
                hits = []
            if hits:
                refs["features"][f] = hits

        for s in (raw_struct.get("spells") or [])[:200]:
            if not s or not isinstance(s, str):
                continue
            try:
                hits = references_agent.search_query(s, top_k=top_k)
            except Exception:
                hits = []
            if hits:
                refs["spells"][s] = hits

        # Only attach if we found anything
        if refs["features"] or refs["spells"]:
            sheet["references"] = refs
    except Exception:
        # Do not fail the import if reference lookup errors occur
        pass

    # Detect TTRPG system from extracted sheet data.
    try:
        detect_input = {
            "class_name": final_class_name,
            "multiclass": multiclass,
            "skills": skills_from_widgets,
            "stats": stats_from_widgets,
            "raw_text": (combined_text or "")[:10000],
            "import": {"source": source, "ddb_url": ddb_url, "filename": filename},
        }
        sheet["detected_system"] = infer_ttrpg_system(detect_input)
    except Exception:
        pass

    return final_name, safe_level, final_class_name, sheet


def _serialize(character: db.Character) -> Dict[str, Any]:
    return {
        "id": character.id,
        "name": character.name,
        "level": character.level,
        "class_name": character.class_name,
        "sheet": character.sheet or {},
    }


class CharacterCreate(BaseModel):
    name: str
    level: int = Field(default=1, ge=1, le=20)
    class_name: str | None = None
    sheet: dict[str, Any] | None = None


class CharacterUpdate(BaseModel):
    name: str | None = None
    level: int | None = Field(default=None, ge=1, le=20)
    class_name: str | None = None
    sheet: dict[str, Any] | None = None


class CharacterImport(BaseModel):
    raw_json: str = Field(..., min_length=2, description="Raw JSON exported from a sheet/source")
    ddb_url: str | None = Field(default=None, description="Optional D&D Beyond character URL")
    source: str | None = Field(default="upload", description="Freeform import source label")


class CharacterImportLink(BaseModel):
    ddb_url: str = Field(..., min_length=8, description="D&D Beyond character URL")
    name: str | None = Field(default=None, description="Optional display name override")


class CharacterImportDDB(BaseModel):
    ddb_url: str = Field(..., min_length=5, description="D&D Beyond character URL or numeric character ID")


def _build_character_import_sheet_from_ddb(
    *,
    ddb_url: str,
) -> tuple[str, int, str | None, Dict[str, Any]]:
    """Fetch a character from the DDB character service API and build an import sheet."""
    try:
        from ..tools.parse_ddb_pdf import import_from_ddb
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"DDB import module unavailable: {exc}") from exc

    try:
        parsed = import_from_ddb(ddb_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Build the canonical sheet dict that matches the shape used by the UI
    def _ability_dict(ab: Any) -> Dict[str, Any]:
        return {"score": getattr(ab, "score", 10), "modifier": getattr(ab, "modifier", 0)}

    def _skill_dict(sk: Any) -> Dict[str, Any]:
        return {
            "name": getattr(sk, "name", ""),
            "modifier": getattr(sk, "modifier", 0),
            "proficient": getattr(sk, "proficient", False),
            "expertise": getattr(sk, "expertise", False),
        }

    def _feature_dict(ft: Any) -> Dict[str, Any]:
        return {
            "name": getattr(ft, "name", ""),
            "source": getattr(ft, "source", ""),
            "description": getattr(ft, "description", ""),
        }

    def _equipment_dict(eq: Any) -> Dict[str, Any]:
        return {
            "name": getattr(eq, "name", ""),
            "quantity": getattr(eq, "quantity", 1),
            "weight": getattr(eq, "weight", 0.0),
            "equipped": getattr(eq, "equipped", False),
            "attuned": getattr(eq, "attuned", False),
        }

    sheet: Dict[str, Any] = {
        # Canonical combat stats
        "stats": {k: v.score for k, v in parsed.abilities.items()},
        "ac": parsed.armor_class,
        "hp": {"current": parsed.hp_current, "max": parsed.hp_max, "temp": parsed.hp_temp},
        "hp_current": parsed.hp_current,
        "hp_max": parsed.hp_max,
        "hp_temp": parsed.hp_temp,
        # Character identity
        "species": parsed.species,
        "background": parsed.background,
        "subclass": parsed.subclass,
        "experience_points": parsed.experience_points,
        # Combat
        "initiative": parsed.initiative,
        "proficiency_bonus": parsed.proficiency_bonus,
        "ability_save_dc": parsed.ability_save_dc,
        "hit_dice": parsed.hit_dice,
        "heroic_inspiration": parsed.heroic_inspiration,
        # Speed
        "speed": {
            "walk": parsed.speed_walking,
            "fly": parsed.speed_flying,
            "swim": parsed.speed_swimming,
            "climb": parsed.speed_climbing,
            "burrow": parsed.speed_burrowing,
        },
        # Passives
        "passives": {
            "perception": parsed.passive_perception,
            "insight": parsed.passive_insight,
            "investigation": parsed.passive_investigation,
        },
        # Rich data
        "abilities": {k: _ability_dict(v) for k, v in parsed.abilities.items()},
        "skills": [_skill_dict(s) for s in parsed.skills],
        "features": [_feature_dict(f) for f in parsed.features_and_traits],
        "classFeatures": [_feature_dict(f) for f in parsed.features_and_traits if f.source not in ("Feat",)],
        "equipment": [_equipment_dict(e) for e in parsed.equipment],
        # Simple string lists for UI display
        "inventory": [name for e in parsed.equipment if (name := getattr(e, "name", ""))],
        "spells": parsed.spells,
        "languages": parsed.languages,
        "armor_proficiencies": parsed.armor_proficiencies,
        "weapon_proficiencies": parsed.weapon_proficiencies,
        "tool_proficiencies": parsed.tool_proficiencies,
        "currencies": parsed.currencies,
        "multiclass": parsed.multiclass,
        "story": parsed.story,
        "portrait_url": None,
        # Tracking fields
        "spell_slots": parsed.spell_slots,
        "exhaustion": parsed.exhaustion,
        "death_saves": {
            "successes": parsed.death_save_successes,
            "failures": parsed.death_save_failures,
        },
        # Import metadata
        "import": {
            "source": "ddb-api",
            "imported_at": _now_iso(),
            "ddb_url": parsed.ddb_url,
            "ddb_character_id": parsed.ddb_character_id,
            "warnings": parsed.parse_warnings,
        },
    }

    safe_level = max(1, min(20, parsed.level))
    return parsed.name, safe_level, parsed.class_name, sheet


@router.get("", summary="List characters for current user")
def list_characters(current_user=Depends(get_current_user)):
    rows = db.list_characters_for_user(current_user.id)
    return {"characters": [_serialize(row) for row in rows]}


@router.delete("/purge", summary="Delete characters for current user by name tokens")
def purge_characters(name_like: str | None = None, current_user=Depends(get_current_user)):
    if not db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    tokens: List[str] = []
    if name_like:
        tokens = [part.strip() for part in name_like.split(',') if part.strip()]
    deleted = db.purge_characters(owner_id=current_user.id, name_tokens=tokens)
    return {"deleted": deleted}


@router.post("", status_code=201)
def create_character(payload: CharacterCreate, current_user=Depends(get_current_user)):
    character = db.create_character(
        owner_id=current_user.id,
        name=payload.name,
        level=payload.level,
        class_name=payload.class_name,
        sheet=payload.sheet,
    )
    return {"character": _serialize(character)}


@router.get("/{character_id}")
def get_character(character_id: int, current_user=Depends(get_current_user)):
    character = db.get_character_for_owner(character_id=character_id, owner_id=current_user.id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"character": _serialize(character)}


@router.post("/import/preview", summary="Preview a JSON character import without creating a character")
def preview_import_character(payload: CharacterImport, current_user=Depends(get_current_user)):
    name, safe_level, class_name, sheet = _build_character_import_sheet_from_json(
        raw_json=payload.raw_json,
        ddb_url=payload.ddb_url,
        source=payload.source,
    )
    return {
        "preview": {
            "name": name,
            "level": safe_level,
            "class_name": class_name,
            "sheet": sheet,
        }
    }


@router.post("/import", status_code=201, summary="Import a character from pasted JSON")
def import_character(payload: CharacterImport, current_user=Depends(get_current_user)):
    name, safe_level, class_name, sheet = _build_character_import_sheet_from_json(
        raw_json=payload.raw_json,
        ddb_url=payload.ddb_url,
        source=payload.source,
    )

    character = db.create_character(
        owner_id=current_user.id,
        name=name,
        level=safe_level,
        class_name=class_name,
        sheet=sheet,
    )
    return {"character": _serialize(character)}


@router.post("/import/file", status_code=201, summary="Import a character from an uploaded JSON file")
async def import_character_file(
    file: UploadFile = File(...),
    ddb_url: str | None = None,
    source: str | None = "upload",
    current_user=Depends(get_current_user),
):
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except Exception:
        text = content.decode("utf-8", errors="ignore")

    return import_character(
        CharacterImport(raw_json=text, ddb_url=ddb_url, source=source or "upload"),
        current_user=current_user,
    )


@router.post("/import/pdf", status_code=201, summary="Import a character from an uploaded PDF (best-effort)")
async def import_character_pdf(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    level: int | None = Form(default=None),
    class_name: str | None = Form(default=None),
    ddb_url: str | None = None,
    source: str | None = "pdf",
    current_user=Depends(get_current_user),
):
    content = await file.read()
    final_name, safe_level, final_class_name, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename=getattr(file, "filename", None),
        name_override=name,
        level_override=level,
        class_name_override=class_name,
        ddb_url=ddb_url,
        source=source,
    )

    character = db.create_character(
        owner_id=current_user.id,
        name=final_name,
        level=safe_level,
        class_name=final_class_name,
        sheet=sheet,
    )
    return {"character": _serialize(character)}


@router.post("/import/pdf/preview", summary="Preview a PDF character import without creating a character")
async def preview_import_character_pdf(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    level: int | None = Form(default=None),
    class_name: str | None = Form(default=None),
    ddb_url: str | None = None,
    source: str | None = "pdf",
    current_user=Depends(get_current_user),
):
    content = await file.read()
    final_name, safe_level, final_class_name, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename=getattr(file, "filename", None),
        name_override=name,
        level_override=level,
        class_name_override=class_name,
        ddb_url=ddb_url,
        source=source,
    )
    return {
        "preview": {
            "name": final_name,
            "level": safe_level,
            "class_name": final_class_name,
            "sheet": sheet,
        }
    }


@router.post("/import/link", status_code=201, summary="Create a character from a shared DDB link (no scraping)")
def import_character_link(payload: CharacterImportLink, current_user=Depends(get_current_user)):
    url = payload.ddb_url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="DDB URL must start with http:// or https://")
    name = (payload.name or "DDB Character").strip() or "DDB Character"

    sheet: Dict[str, Any] = {
        "import": {
            "source": "ddb-link",
            "imported_at": _now_iso(),
            "ddb_url": url,
        },
        "raw": {},
    }
    character = db.create_character(owner_id=current_user.id, name=name, level=1, class_name=None, sheet=sheet)
    return {"character": _serialize(character)}


@router.post("/import/ddb", status_code=201, summary="Import a character directly from D&D Beyond API")
def import_character_ddb(payload: CharacterImportDDB, current_user=Depends(get_current_user)):
    name, safe_level, class_name, sheet = _build_character_import_sheet_from_ddb(ddb_url=payload.ddb_url)
    character = db.create_character(
        owner_id=current_user.id,
        name=name,
        level=safe_level,
        class_name=class_name,
        sheet=sheet,
    )
    return {"character": _serialize(character)}


@router.post("/import/ddb/preview", summary="Preview a D&D Beyond character import without creating")
def preview_import_character_ddb(payload: CharacterImportDDB, current_user=Depends(get_current_user)):
    name, safe_level, class_name, sheet = _build_character_import_sheet_from_ddb(ddb_url=payload.ddb_url)
    return {
        "preview": {
            "name": name,
            "level": safe_level,
            "class_name": class_name,
            "sheet": sheet,
        }
    }


@router.put("/{character_id}")
def update_character(character_id: int, payload: CharacterUpdate, current_user=Depends(get_current_user)):
    character = db.update_character(
        character_id=character_id,
        owner_id=current_user.id,
        updates=payload.model_dump(exclude_unset=True),
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"character": _serialize(character)}


@router.delete("/{character_id}")
def delete_character(character_id: int, current_user=Depends(get_current_user)):
    # Unassign from any session files before deleting (best-effort, non-blocking)
    _unassign_character_from_sessions(character_id)
    # Try owner delete first, fall back to admin delete if user is admin
    ok = db.delete_character(character_id=character_id, owner_id=current_user.id)
    if not ok and db.is_admin_user(current_user):
        ok = db.delete_character_any(character_id=character_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"ok": True}


@router.delete("/admin-delete/{character_id}")
def admin_delete_character(character_id: int, current_user=Depends(get_current_user)):
    if not db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    ok = db.delete_character_any(character_id=character_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"ok": True}


@router.post("/{character_id}/reparse-spells")
def reparse_character_spells(character_id: int, current_user=Depends(get_current_user)):
    print(f"\n=== REPARSE SPELLS FOR CHARACTER {character_id} ===")
    # allow owners or admins to reparse
    character = db.get_character_for_owner(character_id=character_id, owner_id=current_user.id)
    if not character:
        if not db.is_admin_user(current_user):
            raise HTTPException(status_code=404, detail="Character not found")
        character = db.get_character_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

    sheet = character.sheet or {}
    raw_text = sheet.get("raw_text") or (sheet.get("raw", {}) if isinstance(sheet.get("raw"), dict) else {}).get("text") or ""
    raw_text = raw_text if isinstance(raw_text, str) else ""
    print(f"Raw text length: {len(raw_text)}")

    widget_values: Dict[str, Any] = {}
    try:
        import_meta = sheet.get("import", {}) if isinstance(sheet.get("import"), dict) else {}
        pdf_widgets = import_meta.get("pdf_widgets", {}) if isinstance(import_meta.get("pdf_widgets"), dict) else {}
        widget_values = pdf_widgets.get("values", {}) if isinstance(pdf_widgets.get("values"), dict) else {}
    except Exception:
        widget_values = {}
    print(f"Widget values with 'spell': {len([k for k in widget_values.keys() if 'spell' in k.lower()])}")

    # Rebuild spellbook/spells
    spell_entries = _extract_spellbook_from_text(raw_text)
    print(f"Extracted {len(spell_entries)} spell entries from text")
    spells: list[str] = []
    if spell_entries:
        spells = [e.get("name") for e in spell_entries if isinstance(e.get("name"), str)]
        print(f"  -> {len(spells)} spell names from entries")
    else:
        # Extract from widget values, but skip metadata fields
        for k, v in widget_values.items():
            if not v:
                continue
            # Skip metadata fields (time, range, components, duration, source, etc.)
            if re.search(r"spell(time|range|comp|duration|source|save|attack|dc|hit|page|level|class|school|ritual|material)", str(k), re.I):
                continue
            if re.search(r"spell|cantrip", str(k), re.I):
                if isinstance(v, str) and ("\n" in v or "," in v):
                    parts = re.split(r"\r?\n|,", v)
                    for p in parts:
                        s = p.strip()
                        if s:
                            spells.append(s)
                else:
                    spells.append(str(v).strip())
        for s in _extract_spells_from_text(raw_text):
            if s:
                spells.append(s)

    # Clean and de-dup with aggressive filtering
    cleaned: list[str] = []
    seen: set[str] = set()
    for s in spells:
        s2 = (s or "").strip()
        if not s2:
            continue

        # Apply same aggressive filters as during extraction
        # Skip widget field names
        if re.match(r"^spell\w+\d*:?$", s2, re.I):
            continue
        # Skip generic filler words
        if re.match(r"^(additional|your|the|and|or|of|in|to|a|an)$", s2, re.I):
            continue
        # Skip empty or dash-only lines
        if re.match(r"^[—\-\s]+$", s2):
            continue
        # Skip class names
        if re.match(r"^(druid|cleric|wizard|sorcerer|bard|warlock|paladin|ranger|artificer|fighter|monk|rogue|barbarian|acolyte)$", s2, re.I):
            continue
        # Skip lines containing "/" or ","
        if "/" in s2 or "," in s2:
            continue
        # Skip distances/ranges
        if re.search(r"\d+\s*ft\.?|feet|mile", s2, re.I):
            continue
        # Skip metadata patterns
        if re.match(r"^(\d+\s*[ABR]A?|[1-9]\s*BA|[1-9]\s*A|[1-9]\s*R|action|bonus\s*action|reaction|touch|self|sight|\d+\s*ft|phb|ee|xgte|tcoe|scag|v|s|m|v/s|s/m|v/m|v/s/m|instantaneous|concentration|wis|int|cha|dex|str|con)$", s2, re.I):
            continue
        # Skip lines with colon prefix
        if re.match(r"^[A-Z]:\s*", s2):
            continue
        # Skip parenthetical notes
        if re.match(r"^\(", s2):
            continue
        # Skip pure numbers, codes, durations
        if re.match(r"^(\d+|[A-Z]{1,3}|\d+m|\d+h|\d+\s*min|\d+\s*hr)$", s2):
            continue
        # Skip page references
        if re.search(r"\b(PHB|EE|XGTE|TCOE|SCAG)\s*\d+", s2, re.I):
            continue
        # Skip common spell attributes
        if re.match(r"^(prepared|ritual|—|at\s*will|===.*===)$", s2, re.I):
            continue
        # Skip stat patterns like "CON 14", "WIS / WIS"
        if re.match(r"^[A-Z]{3}\s*\d+$", s2) or re.match(r"^[A-Z]{3}\s*/\s*[A-Z]{3}$", s2):
            continue
        # Skip asterisk annotations
        if re.match(r"^\*|.*\*$", s2):
            continue

        key = s2.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s2)
        if len(cleaned) >= 500:
            break

    sheet["spellbook"] = spell_entries
    sheet["spells"] = cleaned
    print(f"Final counts - spellbook: {len(spell_entries)}, spells: {len(cleaned)}")
    if cleaned:
        print(f"First 10 cleaned spells: {cleaned[:10]}")

    if db.is_admin_user(current_user) and (not character or character.owner_id != current_user.id):
        updated = db.update_character_any(character_id=character_id, updates={"sheet": sheet})
    else:
        updated = db.update_character(character_id=character_id, owner_id=current_user.id, updates={"sheet": sheet})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update character")
    return {"character": _serialize(updated)}
