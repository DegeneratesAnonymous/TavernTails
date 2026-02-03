from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import db
from . import references as references_agent
from ..auth import get_current_user

router = APIRouter(prefix="/characters", tags=["characters"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _guess_character_name_from_filename(filename: Optional[str]) -> Optional[str]:
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


def _extract_fields_from_pdf_widgets(fields: Dict[str, str]) -> tuple[Optional[str], Optional[int], Optional[str]]:
    if not fields:
        return None, None, None

    name = fields.get("CharacterName") or fields.get("CHARACTER NAME")

    # Find a key that looks like it contains both Class and Level.
    class_level_value: Optional[str] = None
    for k, v in fields.items():
        up = k.upper()
        if "CLASS" in up and "LEVEL" in up and v.strip():
            class_level_value = v
            break

    class_name: Optional[str] = None
    level: Optional[int] = None

    if class_level_value:
        candidates = [
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

        pairs = re.findall(r"\b([A-Za-z][A-Za-z ]{2,40}?)\s+(\d{1,2})\b", class_level_value)
        found_classes: list[str] = []
        total_level = 0
        for cname_raw, lvl_raw in pairs:
            cname = _as_str(cname_raw)
            lvl = _as_int(lvl_raw)
            if not cname or not isinstance(lvl, int):
                continue
            # Only accept known 5e class names to avoid picking up random labels.
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

    return name, level, class_name


def _extract_pdf_widget_int(
    fields: Dict[str, str],
    key_candidates: list[str],
    *,
    min_value: int,
    max_value: int,
) -> Optional[int]:
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


def _extract_ac_from_pdf_widgets(fields: Dict[str, str]) -> Optional[int]:
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
            # split on common inline separators to avoid long concatenated lines
            parts = re.split(r"\s*[|•\u2022—–\-]\s*", raw_line)
            for part in parts:
                s = part.strip(" \t\r\n•-*\u2022|–—")
                if not s:
                    continue
                # Skip obvious section headers like "=== FOO SPECIES TRAITS ===" or all-caps headings
                if re.search(r"={2,}", s):
                    continue
                if s.upper() == s and len(s) <= 80 and any(k in s.upper() for k in ("SPECIES", "TRAITS", "FEATURES", "FEATS", "CLASS")):
                    continue
                if s.lower() in {"features", "traits", "features & traits", "features and traits"}:
                    continue
                # Keep it tight for the UI preview.
                if len(s) > 200:
                    s = s[:200].rstrip() + "…"
                key = s.lower()
                if key in seen:
                    continue
                seen.add(key)
                features.append(s)
                if len(features) >= 80:
                    break
        if len(features) >= 80:
            break

    return features


def _read_pdf_text(content: bytes) -> Optional[str]:
    """Extract plain text from a PDF binary. Falls back to utf-8 decoding.

    This is best-effort: PDF parsing may fail for non-PDF uploads, so we
    gracefully fall back to decoding bytes as text.
    """
    if not content:
        return None
    try:
        from pypdf import PdfReader
        import io

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

    # Best-effort fallback: try to decode the bytes as UTF-8 (or latin-1)
    try:
        return content.decode("utf-8")
    except Exception:
        try:
            return content.decode("latin-1")
        except Exception:
            return None


def _extract_fields_from_text(text: Optional[str]) -> tuple[Optional[str], Optional[int], Optional[str]]:
    """Heuristic extraction of name, level, and class from arbitrary text.

    Keep this conservative: return None for fields we can't confidently extract.
    """
    if not text or not isinstance(text, str):
        return None, None, None

    lines = [l.strip() for l in re.split(r"\r?\n", text) if l and l.strip()]
    name: Optional[str] = None
    level: Optional[int] = None
    class_name: Optional[str] = None

    # Find level by regex like 'Level 3' or 'LVL 3'
    for l in lines[:12]:
        m = re.search(r"\blevel\b[:\s]*([0-9]{1,2})", l, flags=re.I)
        if m:
            level = _as_int(m.group(1))
            break
        m2 = re.search(r"\b(LVL|LV)\b[:\s]*([0-9]{1,2})", l, flags=re.I)
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
    for l in lines[:8]:
        up = l.upper()
        # Skip template-like headings
        if any(x in up for x in ("CLASS & LEVEL", "PLAYER NAME", "CHARACTER NAME", "SPECIES", "BACKGROUND")):
            continue
        # If the line contains a known class name and a number, capture both.
        for cname in classes:
            if re.search(rf"\b{re.escape(cname)}\b", l, flags=re.I):
                class_name = cname if not class_name else class_name
                # try to find an inline level
                m = re.search(r"(\d{1,2})", l)
                if m and level is None:
                    level = _as_int(m.group(1))
                break

    # Heuristic for name: pick the first short line that is not a template heading
    for l in lines[:6]:
        up = l.upper()
        if any(x in up for x in ("CLASS", "LEVEL", "PLAYER NAME", "CHARACTER NAME", "SPECIES", "BACKGROUND")):
            continue
        # Avoid lines that look like page headers/metadata (contain too many digits or slashes)
        if re.search(r"\d", l) and len(re.findall(r"[A-Za-z]", l)) < 3:
            continue
        # Accept short single-line names
        if 1 <= len(l) <= 60:
            name = l
            break

    return name, level, class_name


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value).strip() or None


def _extract_spells_from_text(text: Optional[str]) -> list[str]:
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


def _as_int(value: Any) -> Optional[int]:
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


def _extract_character_fields(raw: Dict[str, Any]) -> tuple[Optional[str], Optional[int], Optional[str]]:
    """Best-effort extraction from arbitrary JSON blobs.

    We intentionally keep this flexible because different exports have different shapes.
    """
    def _class_name_from_classes_list(classes: Any) -> Optional[str]:
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

    def _level_from_classes_list(classes: Any) -> Optional[int]:
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

    name: Optional[str] = None
    level: Optional[int] = None
    class_name: Optional[str] = None

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
    ddb_url: Optional[str],
    source: Optional[str],
) -> tuple[str, int, Optional[str], Dict[str, Any]]:
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

    return name, safe_level, class_name, sheet


def _build_character_import_sheet_from_pdf(
    *,
    content: bytes,
    filename: Optional[str],
    name_override: Optional[str],
    level_override: Optional[int],
    class_name_override: Optional[str],
    ddb_url: Optional[str],
    source: Optional[str],
) -> tuple[str, int, Optional[str], Dict[str, Any]]:
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    widget_values = _read_pdf_widget_values(content)
    widget_name, widget_level, widget_class_name = _extract_fields_from_pdf_widgets(widget_values)

    stats_from_widgets = _extract_stats_from_pdf_widgets(widget_values)
    ac_from_widgets = _extract_ac_from_pdf_widgets(widget_values)
    hp_from_widgets = _extract_hp_from_pdf_widgets(widget_values)
    features_from_widgets = _extract_features_from_pdf_widgets(widget_values)

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
                s = line.strip(" \t\r\n•-*_\u2022")
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

    safe_level = final_level if isinstance(final_level, int) else 1
    safe_level = max(1, min(20, safe_level))

    # Build a structured `raw` object so client-side inference helpers can read
    # values from a predictable place (e.g. `sheet.raw.speed`, `sheet.raw.deathSaves`).
    def _parse_int(v: Any) -> Optional[int]:
        try:
            return int(str(v).strip())
        except Exception:
            return None

    def _split_lines(blob: str) -> list[str]:
        out: list[str] = []
        if not blob or not isinstance(blob, str):
            return out
        for line in re.split(r"\r?\n", blob):
            s = line.strip(" \t\r\n•-*_\u2022")
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
        speeds: Dict[str, Optional[int]] = {"walk": None, "fly": None, "swim": None, "climb": None, "burrow": None}
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

    # Spells: aggregate any widget values containing 'spell' or 'cantrip', plus text-extracted spells
    spells: list[str] = []
    for k, v in widget_values.items():
        if not v:
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

    # merge with text-detected spells and clean noise tokens
    for s in spells_from_text:
        if s:
            spells.append(s)

    cleaned: list[str] = []
    seen_spells: set[str] = set()
    for s in spells:
        s2 = (s or '').strip()
        if not s2:
            continue
        # skip short/metadata tokens
        if len(s2) < 3:
            continue
        if re.match(r"^[\W_0-9]+$", s2):
            continue
        if re.match(r"^(PHB|TCoE|VGtM|BR)$", s2):
            continue
        # drop obvious durations/ranges like '1 minute', '30 ft', 'At Will'
        if re.match(r"^(at will|\d+\s*(minute|minutes|ft|feet|hour|rounds?)|\d+[A-Za-z]?)$", s2.lower()):
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
        "spells": raw_struct.get("spells", []),
        "import": {
            "source": source or "pdf",
            "imported_at": _now_iso(),
            "ddb_url": ddb_url,
            "filename": filename,
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
    class_name: Optional[str] = None
    sheet: Optional[Dict[str, Any]] = None


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    level: Optional[int] = Field(default=None, ge=1, le=20)
    class_name: Optional[str] = None
    sheet: Optional[Dict[str, Any]] = None


class CharacterImport(BaseModel):
    raw_json: str = Field(..., min_length=2, description="Raw JSON exported from a sheet/source")
    ddb_url: Optional[str] = Field(default=None, description="Optional D&D Beyond character URL")
    source: Optional[str] = Field(default="upload", description="Freeform import source label")


class CharacterImportLink(BaseModel):
    ddb_url: str = Field(..., min_length=8, description="D&D Beyond character URL")
    name: Optional[str] = Field(default=None, description="Optional display name override")


@router.get("", summary="List characters for current user")
def list_characters(current_user=Depends(get_current_user)):
    rows = db.list_characters_for_user(current_user.id)
    return {"characters": [_serialize(row) for row in rows]}


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
    ddb_url: Optional[str] = None,
    source: Optional[str] = "upload",
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
    name: Optional[str] = Form(default=None),
    level: Optional[int] = Form(default=None),
    class_name: Optional[str] = Form(default=None),
    ddb_url: Optional[str] = None,
    source: Optional[str] = "pdf",
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
    name: Optional[str] = Form(default=None),
    level: Optional[int] = Form(default=None),
    class_name: Optional[str] = Form(default=None),
    ddb_url: Optional[str] = None,
    source: Optional[str] = "pdf",
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


@router.put("/{character_id}")
def update_character(character_id: int, payload: CharacterUpdate, current_user=Depends(get_current_user)):
    character = db.update_character(
        character_id=character_id,
        owner_id=current_user.id,
        updates=payload.dict(exclude_unset=True),
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"character": _serialize(character)}


@router.delete("/{character_id}")
def delete_character(character_id: int, current_user=Depends(get_current_user)):
    ok = db.delete_character(character_id=character_id, owner_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"ok": True}
