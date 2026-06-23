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
from .system_detect import infer_ttrpg_system, list_ttrpg_systems, override_ttrpg_system

router = APIRouter(prefix="/characters", tags=["characters"])

# Canonical D&D 5e skill names (all 18).  Used to filter out non-skill items
# (e.g. saving-throw widgets, proficiency bonus) that the generic
# _extract_skills_from_pdf_widgets extractor may inadvertently include.
_DND5E_CANONICAL_SKILLS: frozenset[str] = frozenset({
    "Acrobatics", "Animal Handling", "Arcana", "Athletics",
    "Deception", "History", "Insight", "Intimidation",
    "Investigation", "Medicine", "Nature", "Perception",
    "Performance", "Persuasion", "Religion", "Sleight of Hand",
    "Stealth", "Survival",
})


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

    _name_keys = ("CharacterName", "CHARACTER NAME", "Character Name", "Investigator Name", "INVESTIGATOR NAME", "Name", "name")
    _boilerplate_re = re.compile(r"[\u00a9\u2122\u00ae]|copyright|\bstudios?\b|\bpublishing\b|\bgames?\s+inc\b", re.I)
    name = next((fields[k] for k in _name_keys if fields.get(k) and not _boilerplate_re.search(str(fields[k]))), None)

    # All known class names (5e + PF2e + Starfinder) used for conservative matching.
    candidates = [
        # D&D 5e
        "Artificer", "Barbarian", "Bard", "Cleric", "Druid", "Fighter",
        "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard",
        # Pathfinder 2e (Remaster + earlier)
        "Alchemist", "Champion", "Investigator", "Magus", "Oracle", "Psychic",
        "Summoner", "Swashbuckler", "Thaumaturge", "Witch",
        "Animist", "Exemplar", "Commander", "Guardian",
        # Starfinder
        "Biohacker", "Envoy", "Evolutionist", "Mechanic", "Mystic",
        "Nanocyte", "Operative", "Precog", "Solarian", "Soldier",
        "Technomancer", "Vanguard", "Witchwarper",
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
                if class_name is None and raw_val and 2 <= len(raw_val) <= 50:
                    # Accept unknown class names verbatim for non-5e systems,
                    # but only if the value looks like a proper name (letters and spaces only).
                    if re.match(r"^[A-Za-z][A-Za-z\s'-]{1,49}$", raw_val):
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


# ---------------------------------------------------------------------------
# Shadowrun (SR6e) field extraction
# ---------------------------------------------------------------------------
# Canonical Shadowrun 6e attribute abbreviations as they appear on the
# Catalyst Game Labs fillable PDF.
_SR_ATTRIBUTE_KEYS = ["BOD", "AGI", "REA", "STR", "WIL", "LOG", "INT", "CHA", "EDG"]
# Optional magic/tech attributes — only one is non-zero per character.
_SR_MAGIC_KEYS = ["MAG", "RES"]
# Essence is a float (cyberware reduces it from 6.0).
_SR_ESSENCE_KEYS = ["ESS", "Essence"]
# Upper bound for Nuyen validation; high-level SR characters can have hundreds
# of thousands of ¥, but values above 10 M are likely data entry errors.
_MAX_NUYEN_VALUE = 10_000_000


def _is_shadowrun_sheet(widget_values: Dict[str, str]) -> bool:
    """Return True if the widget keys strongly suggest a Shadowrun character sheet.

    Requires at least 5 of the 9 core SR attribute abbreviations (BOD, AGI,
    REA, STR, WIL, LOG, INT, CHA, EDG) to be present as widget keys.  This
    combination is unique to Shadowrun sheets and not found on any other TTRPG
    sheet supported by TavernTAIls.
    """
    matches = sum(1 for k in widget_values if k.upper() in _SR_ATTRIBUTE_KEYS)
    return matches >= 5


def _extract_shadowrun_fields_from_widgets(fields: Dict[str, str]) -> Dict[str, Any]:
    """Extract Shadowrun 6e-specific fields from PDF widget key/value pairs.

    All keys are namespaced under ``shadowrun_*`` to avoid overloading shared
    keys like ``hp``.  Fields that have no D&D 5e equivalent (condition
    monitors, essence, nuyen, matrix stats) are stored here rather than in
    the generic sheet keys.

    Returns a dict with the following top-level keys:
    - ``shadowrun_attributes`` – core + magic/resonance attribute ratings
    - ``shadowrun_essence``    – Essence rating (float, reduced by cyberware)
    - ``shadowrun_condition_monitor`` – physical and stun damage tracks
    - ``shadowrun_skills``     – list of {name, rating, specialization?}
    - ``shadowrun_qualities``  – {positive: [...], negative: [...]}
    - ``shadowrun_cyberware``  – list of cyberware/bioware strings
    - ``shadowrun_nuyen``      – Nuyen balance (int)
    - ``shadowrun_lifestyle``  – current lifestyle tier string
    - ``shadowrun_contacts``   – list of {name, loyalty?, connection?}
    - ``shadowrun_matrix``     – matrix persona stats (Decker/Technomancer)
    """
    if not fields:
        return {}

    def _find_first(patterns: list[str]) -> str | None:
        for k, v in fields.items():
            if not v:
                continue
            for pat in patterns:
                if re.search(pat, str(k), re.I):
                    return _as_str(v)
        return None

    def _find_int(patterns: list[str], *, min_val: int = 0, max_val: int = 99) -> int | None:
        raw = _find_first(patterns)
        if raw is None:
            return None
        m = re.search(r"-?\d+", str(raw))
        if m:
            n = int(m.group(0))
            return n if min_val <= n <= max_val else None
        return None

    def _find_float(patterns: list[str]) -> float | None:
        raw = _find_first(patterns)
        if raw is None:
            return None
        m = re.search(r"\d+(\.\d+)?", str(raw))
        return float(m.group(0)) if m else None

    result: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Core attributes
    # ------------------------------------------------------------------
    attrs: Dict[str, Any] = {}
    _attr_map = {
        "body": ["^BOD$", r"\bbody\b"],
        "agility": ["^AGI$", r"\bagility\b"],
        "reaction": ["^REA$", r"\breaction\b"],
        "strength": ["^STR$", r"\bstrength\b"],
        "willpower": ["^WIL$", r"\bwillpower\b"],
        "logic": ["^LOG$", r"\blogic\b"],
        "intuition": ["^INT$", r"\bintuition\b"],
        "charisma": ["^CHA$", r"\bcharisma\b"],
        "edge": ["^EDG$", r"\bedge\b"],
    }
    for attr_name, pats in _attr_map.items():
        val = _find_int(pats, min_val=1, max_val=12)
        if val is not None:
            attrs[attr_name] = val

    # Magic or Resonance (mutually exclusive)
    mag = _find_int(["^MAG$", r"\bmagic\b(?!.*point)"], min_val=1, max_val=12)
    if mag is not None:
        attrs["magic"] = mag
    res = _find_int(["^RES$", r"\bresonance\b"], min_val=1, max_val=12)
    if res is not None:
        attrs["resonance"] = res

    if attrs:
        result["shadowrun_attributes"] = attrs

    # ------------------------------------------------------------------
    # Essence
    # ------------------------------------------------------------------
    essence = _find_float([r"^ESS$", r"\bessence\b"])
    # Essence 0.0 means the character died from cyberware overload — not valid.
    if essence is not None and 0.0 < essence <= 6.0:
        result["shadowrun_essence"] = essence

    # ------------------------------------------------------------------
    # Condition monitors
    # ------------------------------------------------------------------
    phys_max = _find_int([r"\bphys(ical)?\s*(cond(ition)?\s*)?(mon(itor)?\s*)?max\b",
                          r"\bphys(ical)?\s*dmg\s*max\b",
                          r"^PhysMonMax$", r"^PhysMax$"], min_val=1, max_val=20)
    stun_max = _find_int([r"\bstun\s*(cond(ition)?\s*)?(mon(itor)?\s*)?max\b",
                          r"\bstun\s*dmg\s*max\b",
                          r"^StunMonMax$", r"^StunMax$"], min_val=1, max_val=20)
    # Current damage filled (boxes checked)
    phys_dmg = _find_int([r"\bphys(ical)?\s*(dmg|damage|filled)\b",
                          r"^PhysDmg$", r"^PhysicalDmg$"], min_val=0, max_val=20)
    stun_dmg = _find_int([r"\bstun\s*(dmg|damage|filled)\b",
                          r"^StunDmg$"], min_val=0, max_val=20)
    cmon: Dict[str, Any] = {}
    if phys_max is not None or phys_dmg is not None:
        cmon["physical"] = {}
        if phys_max is not None:
            cmon["physical"]["max"] = phys_max
        if phys_dmg is not None:
            cmon["physical"]["damage"] = phys_dmg
    if stun_max is not None or stun_dmg is not None:
        cmon["stun"] = {}
        if stun_max is not None:
            cmon["stun"]["max"] = stun_max
        if stun_dmg is not None:
            cmon["stun"]["damage"] = stun_dmg
    if cmon:
        result["shadowrun_condition_monitor"] = cmon

    # ------------------------------------------------------------------
    # Skills (numbered rows: Skill1Name / Skill1Rating / Skill1Spec)
    # ------------------------------------------------------------------
    skills: list[Dict[str, Any]] = []
    seen_skills: set[str] = set()
    for i in range(1, 30):
        name_val = None
        rating_val = None
        spec_val = None
        for k, v in fields.items():
            if not v:
                continue
            kn = k.strip()
            # Match patterns like Skill1Name, skill_1_name, SkillName1, Skill 1 Name
            if re.match(rf"^skill\s*{i}\s*name$", kn, re.I) or re.match(rf"^skill\s*name\s*{i}$", kn, re.I):
                name_val = _as_str(v)
            elif re.match(rf"^skill\s*{i}\s*rating$", kn, re.I) or re.match(rf"^skill\s*rating\s*{i}$", kn, re.I):
                m_int = re.search(r"\d+", str(v))
                if m_int:
                    rating_val = int(m_int.group(0))
            elif re.match(rf"^skill\s*{i}\s*spec(iali[sz]ation)?$", kn, re.I):
                spec_val = _as_str(v)
        if name_val:
            lname = name_val.lower()
            if lname not in seen_skills:
                seen_skills.add(lname)
                entry: Dict[str, Any] = {"name": name_val}
                if rating_val is not None:
                    entry["rating"] = rating_val
                if spec_val:
                    entry["specialization"] = spec_val
                skills.append(entry)
    if skills:
        result["shadowrun_skills"] = skills

    # ------------------------------------------------------------------
    # Qualities
    # ------------------------------------------------------------------
    pos_quals: list[str] = []
    neg_quals: list[str] = []
    seen_quals: set[str] = set()
    for i in range(1, 20):
        for k, v in fields.items():
            if not v:
                continue
            kn = k.strip()
            if re.match(rf"^pos(itive)?\s*qual(ity)?\s*{i}$", kn, re.I):
                q = _as_str(v)
                if q and q.lower() not in seen_quals:
                    seen_quals.add(q.lower())
                    pos_quals.append(q)
            elif re.match(rf"^neg(ative)?\s*qual(ity)?\s*{i}$", kn, re.I):
                q = _as_str(v)
                if q and q.lower() not in seen_quals:
                    seen_quals.add(q.lower())
                    neg_quals.append(q)
    if pos_quals or neg_quals:
        result["shadowrun_qualities"] = {"positive": pos_quals, "negative": neg_quals}

    # ------------------------------------------------------------------
    # Cyberware / Bioware
    # ------------------------------------------------------------------
    cyberware: list[str] = []
    seen_cyber: set[str] = set()
    for i in range(1, 20):
        for k, v in fields.items():
            if not v:
                continue
            kn = k.strip()
            if re.match(rf"^(cyber|bio)ware\s*{i}(name)?$", kn, re.I):
                item = _as_str(v)
                if item and item.lower() not in seen_cyber:
                    seen_cyber.add(item.lower())
                    cyberware.append(item)
    if cyberware:
        result["shadowrun_cyberware"] = cyberware

    # ------------------------------------------------------------------
    # Nuyen and Lifestyle
    # ------------------------------------------------------------------
    nuyen = _find_int([r"\bnuyen\b", r"^¥$", r"^Nuyen$"], min_val=0, max_val=_MAX_NUYEN_VALUE)
    if nuyen is not None:
        result["shadowrun_nuyen"] = nuyen

    lifestyle = _find_first([r"\blifestyle\b"])
    if lifestyle:
        result["shadowrun_lifestyle"] = lifestyle

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------
    contacts: list[Dict[str, Any]] = []
    seen_contacts: set[str] = set()
    for i in range(1, 20):
        cname = None
        loyalty = None
        connection = None
        for k, v in fields.items():
            if not v:
                continue
            kn = k.strip()
            if re.match(rf"^contact\s*{i}\s*name$", kn, re.I) or re.match(rf"^contact\s*name\s*{i}$", kn, re.I):
                cname = _as_str(v)
            elif re.match(rf"^contact\s*{i}\s*loyalty$", kn, re.I):
                m_int = re.search(r"\d+", str(v))
                if m_int:
                    loyalty = int(m_int.group(0))
            elif re.match(rf"^contact\s*{i}\s*connection$", kn, re.I):
                m_int = re.search(r"\d+", str(v))
                if m_int:
                    connection = int(m_int.group(0))
        if cname:
            lname = cname.lower()
            if lname not in seen_contacts:
                seen_contacts.add(lname)
                entry_c: Dict[str, Any] = {"name": cname}
                if loyalty is not None:
                    entry_c["loyalty"] = loyalty
                if connection is not None:
                    entry_c["connection"] = connection
                contacts.append(entry_c)
    if contacts:
        result["shadowrun_contacts"] = contacts

    # ------------------------------------------------------------------
    # Matrix persona stats (Decker / Technomancer)
    # Attack, Sleaze, DataProcessing, Firewall
    # ------------------------------------------------------------------
    matrix: Dict[str, Any] = {}
    for mkey, pats in [
        ("attack", [r"^Attack$", r"^ATK$", r"\bmatrix\s*attack\b"]),
        ("sleaze", [r"^Sleaze$", r"^SLZ$", r"\bmatrix\s*sleaze\b"]),
        ("data_processing", [r"^DataProcessing$", r"^DP$", r"\bdata\s*proc(essing)?\b"]),
        ("firewall", [r"^Firewall$", r"^FW$", r"\bmatrix\s*firewall\b"]),
    ]:
        mv = _find_int(pats, min_val=1, max_val=12)
        if mv is not None:
            matrix[mkey] = mv
    if matrix:
        result["shadowrun_matrix"] = matrix

    # ------------------------------------------------------------------
    # Metatype (Human/Elf/Dwarf/Ork/Troll + exotic)
    # ------------------------------------------------------------------
    metatype = _find_first([r"\bmetatype\b", r"\brace\b", r"\bspecies\b"])
    if metatype:
        result["shadowrun_metatype"] = metatype

    # ------------------------------------------------------------------
    # Karma (advancement currency)
    # ------------------------------------------------------------------
    karma_total = _find_int([r"\btotal\s*karma\b", r"\bkarma\s*total\b"], min_val=0, max_val=9999)
    karma_current = _find_int([r"\bcurrent\s*karma\b", r"\bkarma\s*current\b"], min_val=0, max_val=9999)
    karma: Dict[str, Any] = {}
    if karma_total is not None:
        karma["total"] = karma_total
    if karma_current is not None:
        karma["current"] = karma_current
    if karma:
        result["shadowrun_karma"] = karma

    # ------------------------------------------------------------------
    # Initiative
    # ------------------------------------------------------------------
    init_base = _find_int([r"\binitiative\s*base\b", r"\binit\s*base\b"], min_val=1, max_val=30)
    init_dice = _find_int([r"\binitiative\s*dice\b", r"\binit\s*dice\b"], min_val=1, max_val=5)
    if init_base is not None or init_dice is not None:
        initiative: Dict[str, Any] = {}
        if init_base is not None:
            initiative["base"] = init_base
        if init_dice is not None:
            initiative["dice"] = init_dice
        result["shadowrun_initiative"] = initiative

    # ------------------------------------------------------------------
    # Knowledge skills
    # ------------------------------------------------------------------
    knowledge_skills: list[Dict[str, Any]] = []
    ks_name_keys = [k for k in fields if re.search(r"\bknowledge\s*skill\s*\d+\s*name\b", k, re.I)]
    for ksk in ks_name_keys:
        ksname = _as_str(fields.get(ksk))
        if not ksname:
            continue
        idx_m = re.search(r"\d+", ksk)
        idx = idx_m.group(0) if idx_m else ""
        ks_entry: Dict[str, Any] = {"name": ksname}
        for k2, v2 in fields.items():
            if not v2:
                continue
            if re.search(rf"\bknowledge\s*skill\s*{idx}\s*rating\b", k2, re.I):
                r_val = _as_int(str(v2).strip())
                if isinstance(r_val, int):
                    ks_entry["rating"] = r_val
        knowledge_skills.append(ks_entry)
    if knowledge_skills:
        result["shadowrun_knowledge_skills"] = knowledge_skills

    # ------------------------------------------------------------------
    # Adept powers (Awakened adepts)
    # ------------------------------------------------------------------
    adept_powers: list[str] = []
    seen_ap: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\badept\s*power\b", str(k), re.I):
            ap = _as_str(v)
            if ap and ap.lower() not in seen_ap:
                seen_ap.add(ap.lower())
                adept_powers.append(ap)
    if adept_powers:
        result["shadowrun_adept_powers"] = adept_powers

    return result


# ---------------------------------------------------------------------------
# Star Trek Adventures (STA) field extraction
# ---------------------------------------------------------------------------
_STA_ATTRIBUTES = ["Control", "Daring", "Fitness", "Insight", "Presence", "Reason"]
_STA_DISCIPLINES = ["Command", "Conn", "Engineering", "Medicine", "Science", "Security"]


def _is_sta_sheet(widget_values: Dict[str, str]) -> bool:
    """Return True if the widget keys strongly suggest a Star Trek Adventures character sheet.

    Requires at least 4 of the 12 STA-specific attribute/discipline field names
    to be present as widget keys.
    """
    sta_keys = set(_STA_ATTRIBUTES + _STA_DISCIPLINES)
    matches = sum(1 for k in widget_values if k in sta_keys)
    return matches >= 4


def _extract_sta_attributes_from_widgets(fields: Dict[str, str]) -> Dict[str, int]:
    """Extract STA attribute scores (Control, Daring, Fitness, Insight, Presence, Reason)."""
    result: Dict[str, int] = {}
    for attr in _STA_ATTRIBUTES:
        n = _extract_pdf_widget_int(fields, [attr], min_value=1, max_value=12)
        if isinstance(n, int):
            result[attr.lower()] = n
    return result


def _extract_sta_disciplines_from_widgets(fields: Dict[str, str]) -> Dict[str, int]:
    """Extract STA discipline ratings (Command, Conn, Engineering, Medicine, Science, Security)."""
    result: Dict[str, int] = {}
    for disc in _STA_DISCIPLINES:
        n = _extract_pdf_widget_int(fields, [disc], min_value=0, max_value=5)
        if isinstance(n, int):
            result[disc.lower()] = n
    return result


def _extract_sta_stress_from_widgets(fields: Dict[str, str]) -> Dict[str, int]:
    """Extract the STA stress track (replaces D&D HP as the primary health resource)."""
    current = _extract_pdf_widget_int(
        fields,
        ["Stress", "Current Stress", "Stress Current"],
        min_value=0,
        max_value=30,
    )
    maximum = _extract_pdf_widget_int(
        fields,
        ["Stress Max", "Maximum Stress", "Max Stress", "StressMax"],
        min_value=0,
        max_value=30,
    )
    out: Dict[str, int] = {}
    if isinstance(current, int):
        out["current"] = current
    if isinstance(maximum, int):
        out["max"] = maximum
    return out


def _extract_sta_list_fields_from_widgets(
    fields: Dict[str, str],
    prefixes: list[str],
    max_items: int = 6,
) -> list[str]:
    """Extract a numbered list of STA text fields (e.g. 'Value 1'…'Value 4', 'Focus 1'…'Focus 6').

    Tries both space-delimited and concatenated variants (``"Value 1"``, ``"Value1"``,
    ``"Value_1"``).  Falls back to splitting a single un-numbered blob field on
    newlines / semicolons.
    """
    items: list[str] = []
    seen: set[str] = set()
    for prefix in prefixes:
        for i in range(1, max_items + 1):
            for key in (f"{prefix} {i}", f"{prefix}{i}", f"{prefix}_{i}"):
                val = _as_str(fields.get(key))
                if val:
                    lv = val.lower()
                    if lv not in seen:
                        seen.add(lv)
                        items.append(val)
    # If nothing found via numbered keys, try a single un-numbered blob
    if not items:
        for prefix in prefixes:
            val = _as_str(fields.get(prefix))
            if val:
                for part in re.split(r"\r?\n|;", val):
                    part = part.strip()
                    if part:
                        lv = part.lower()
                        if lv not in seen:
                            seen.add(lv)
                            items.append(part)
    return items[:max_items]


# ---------------------------------------------------------------------------
# Call of Cthulhu (CoC 7e) field extraction
# ---------------------------------------------------------------------------
_COC_CHARACTERISTICS = ["STR", "CON", "SIZ", "DEX", "APP", "INT", "POW", "EDU"]
# CoC-unique characteristics that don't appear in D&D/PF sheets
_COC_UNIQUE_STATS = {"POW", "APP", "SIZ", "EDU"}


def _is_coc_sheet(widget_values: Dict[str, str]) -> bool:
    """Return True if the widget keys strongly suggest a Call of Cthulhu character sheet.

    Requires at least 2 of the CoC-unique characteristic field names (POW, APP, SIZ, EDU)
    or the presence of CoC-specific derived stat keys (Sanity Points, Magic Points, Luck).
    """
    normed_keys = {k.lower().strip() for k in widget_values}
    _coc_unique_lower = {s.lower() for s in _COC_UNIQUE_STATS}
    unique_matches = sum(1 for k in normed_keys if k in _coc_unique_lower)
    if unique_matches >= 2:
        return True
    coc_signals = {"sanity points", "magic points", "cthulhu mythos", "investigator name"}
    return bool(coc_signals & normed_keys)


def _extract_coc_characteristics_from_widgets(fields: Dict[str, str]) -> Dict[str, int]:
    """Extract CoC 7e characteristic scores (STR/CON/SIZ/DEX/APP/INT/POW/EDU).

    Values are percentile integers (typically 15–99).
    """
    result: Dict[str, int] = {}
    for char in _COC_CHARACTERISTICS:
        # Each characteristic may have variants like "STR", "STR Score", "Strength"
        n = _extract_pdf_widget_int(fields, [char, f"{char} Score", f"{char} score"], min_value=1, max_value=99)
        if isinstance(n, int):
            result[char.lower()] = n
    return result


def _extract_coc_fields_from_widgets(fields: Dict[str, str]) -> Dict[str, Any]:
    """Extract Call of Cthulhu 7e-specific fields from PDF widget key/value pairs.

    Returns a dict with CoC-namespaced keys:
    - ``characteristics``: dict of str/con/siz/dex/app/int/pow/edu
    - ``hp``: {current, max}  (Hit Points — CON+SIZ derived)
    - ``magic_points``: {current, max}  (MP — POW derived; CoC-specific, not D&D)
    - ``sanity``: {current, max}  (SAN — POW×5 derived; CoC-specific)
    - ``luck``: int  (3d6×5; CoC-specific)
    - ``skills``: dict of skill_name → percentage (int)
    - ``occupation``: str  (replaces D&D class; CoC-specific)
    - ``background``: str
    """
    if not fields:
        return {}

    result: Dict[str, Any] = {}

    # Characteristics
    characteristics = _extract_coc_characteristics_from_widgets(fields)
    if characteristics:
        result["characteristics"] = characteristics

    # Hit Points (CON+SIZ / 10, rounded down; stored here for schema consistency)
    hp_current = _extract_pdf_widget_int(
        fields,
        ["Hit Points", "HP", "Hit Points Current", "Current HP", "HitPoints", "HP Current"],
        min_value=0,
        max_value=99,
    )
    hp_max = _extract_pdf_widget_int(
        fields,
        ["Hit Points Max", "HP Max", "Maximum HP", "Max Hit Points", "HitPointsMax"],
        min_value=0,
        max_value=99,
    )
    hp: Dict[str, int] = {}
    if isinstance(hp_current, int):
        hp["current"] = hp_current
    if isinstance(hp_max, int):
        hp["max"] = hp_max
    if hp:
        result["hp"] = hp

    # Magic Points (POW / 5; CoC-specific resource — do NOT overload D&D hp)
    mp_current = _extract_pdf_widget_int(
        fields,
        ["Magic Points", "MP", "Magic Points Current", "Current MP", "MagicPoints"],
        min_value=0,
        max_value=99,
    )
    mp_max = _extract_pdf_widget_int(
        fields,
        ["Magic Points Max", "MP Max", "Maximum MP", "Max Magic Points", "MagicPointsMax"],
        min_value=0,
        max_value=99,
    )
    mp: Dict[str, int] = {}
    if isinstance(mp_current, int):
        mp["current"] = mp_current
    if isinstance(mp_max, int):
        mp["max"] = mp_max
    if mp:
        result["magic_points"] = mp

    # Sanity (POW×5; CoC-specific — stored under "sanity", not "stress" or "hp")
    san_current = _extract_pdf_widget_int(
        fields,
        ["Sanity Points", "Sanity", "SAN", "Current Sanity", "Sanity Current", "SanityPoints"],
        min_value=0,
        max_value=99,
    )
    san_max = _extract_pdf_widget_int(
        fields,
        ["Sanity Points Max", "Max Sanity", "Maximum Sanity", "Sanity Max", "SanityMax"],
        min_value=0,
        max_value=99,
    )
    san: Dict[str, int] = {}
    if isinstance(san_current, int):
        san["current"] = san_current
    if isinstance(san_max, int):
        san["max"] = san_max
    if san:
        result["sanity"] = san

    # Luck (3d6×5; CoC-specific)
    luck = _extract_pdf_widget_int(
        fields,
        ["Luck", "Current Luck", "Starting Luck"],
        min_value=0,
        max_value=99,
    )
    if isinstance(luck, int):
        result["luck"] = luck

    # Derived combat stats (CoC-specific)
    dodge = _extract_pdf_widget_int(fields, ["Dodge", "Dodge %"], min_value=1, max_value=99)
    if isinstance(dodge, int):
        result["dodge"] = dodge
    for build_key in ("Build", "build"):
        if fields.get(build_key) and str(fields[build_key]).strip():
            result["build"] = _as_str(fields[build_key])
            break
    for db_key in ("Damage Bonus", "DB", "DamageBonus"):
        if fields.get(db_key) and str(fields[db_key]).strip():
            result["damage_bonus"] = _as_str(fields[db_key])
            break
    move = _extract_pdf_widget_int(fields, ["Move Rate", "MOV", "Movement", "Move"], min_value=1, max_value=20)
    if isinstance(move, int):
        result["move"] = move

    # Age
    age = _extract_pdf_widget_int(fields, ["Age", "age"], min_value=1, max_value=130)
    if isinstance(age, int):
        result["age"] = age

    # Cash / assets
    cash = _extract_pdf_widget_int(fields, ["Cash", "Cash on Hand", "Spending Level"], min_value=0, max_value=9999999)
    if isinstance(cash, int):
        result["cash"] = cash
    for assets_key in ("Assets", "assets", "Savings"):
        if fields.get(assets_key) and str(fields[assets_key]).strip():
            result["assets"] = _as_str(fields[assets_key])
            break

    # Occupation (replaces class in CoC — stored separately to avoid conflating with D&D class)
    for k, v in fields.items():
        if re.match(r"^(occupation|Occupation|OCCUPATION)$", k) and v and v.strip():
            result["occupation"] = _as_str(v)
            break

    # Background / backstory
    for k, v in fields.items():
        kl = k.lower().strip()
        if kl in ("background", "backstory", "personal description", "description") and v and v.strip():
            result["background"] = _as_str(v)
            break

    # Skills (percentile integers, keyed by skill name)
    # Collect all widget keys that look like skill names with a numeric value.
    # CoC skill names are well-known; we capture any key whose value is 1–99.
    _coc_known_skills: set[str] = {
        "accounting", "anthropology", "appraise", "archaeology",
        "art/craft", "charm", "climb", "computer use", "credit rating",
        "cthulhu mythos", "disguise", "dodge", "drive auto",
        "electrical repair", "fast talk", "fighting", "first aid",
        "history", "hypnosis", "intimidate", "jump", "language",
        "law", "library use", "listen", "locksmith",
        "mechanical repair", "medicine", "natural world", "navigate",
        "occult", "operate heavy machinery", "persuade", "photography",
        "pilot", "psychology", "psychoanalysis", "ride", "science",
        "sleight of hand", "spot hidden", "stealth", "swim",
        "throw", "track",
        # weapon groups
        "firearms", "firearms (handgun)", "firearms (rifle)", "firearms (shotgun)",
        "brawl", "fighting (brawl)",
    }
    skills: Dict[str, int] = {}
    for k, v in fields.items():
        if not v:
            continue
        kl = k.lower().strip()
        if kl in _coc_known_skills:
            pct = _as_int(str(v).strip())
            if isinstance(pct, int) and 1 <= pct <= 99:
                skills[k] = pct
    if skills:
        result["skills"] = skills

    # Weapons (numbered list: Weapon N Name / Weapon N Skill / Weapon N Damage)
    weapons: list[Dict[str, Any]] = []
    weapon_name_keys = [k for k in fields if re.search(r"\bweapon\s*\d+\s*name\b", k, re.I)]
    for wk in weapon_name_keys:
        wname = _as_str(fields.get(wk))
        if not wname:
            continue
        idx_m = re.search(r"\d+", wk)
        idx = idx_m.group(0) if idx_m else ""
        skill_pct = None
        damage = None
        for k2, v2 in fields.items():
            if not v2:
                continue
            if re.search(rf"\bweapon\s*{idx}\s*skill\b|\bweapon\s*skill\s*{idx}\b", k2, re.I):
                skill_pct = _as_int(str(v2).strip())
            elif re.search(rf"\bweapon\s*{idx}\s*damage\b|\bweapon\s*damage\s*{idx}\b", k2, re.I):
                damage = _as_str(v2)
        entry: Dict[str, Any] = {"name": wname}
        if isinstance(skill_pct, int):
            entry["skill_pct"] = skill_pct
        if damage:
            entry["damage"] = damage
        weapons.append(entry)
    if weapons:
        result["weapons"] = weapons

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
        # 80 chars: longest realistic section-header title (e.g. "Core Ranger Subclass Features").
        # Anything longer is more likely descriptive text than a header.
        max_header_len = 80
        if s.upper() == s and len(s) <= max_header_len and any(k in s.upper() for k in ("SPECIES", "TRAITS", "FEATURES", "FEATS", "CLASS")):
            return None
        if s.lower() in {"features", "traits", "features & traits", "features and traits"}:
            return None
        # Drop section-header-style lines: strings that end with "Features", "Traits",
        # "Abilities", "Proficiencies", etc. (with an optional class/species prefix).
        # These are organisation headings like "Artificer Features" or "Core Paladin Traits",
        # not actual feature names.
        if re.search(
            r"\b(features?|traits?|abilities|proficiencies|class\s+features?|racial\s+traits?)\s*$",
            s,
            re.I,
        ) and len(s) <= max_header_len:
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
        # D&D 5e modifier/save shortcuts that appear as widget names
        "str mod", "dex mod", "con mod", "int mod", "wis mod", "cha mod",
        "strength mod", "dexterity mod", "constitution mod", "intelligence mod",
        "wisdom mod", "charisma mod",
        "str save", "dex save", "con save", "int save", "wis save", "cha save",
        "strength save", "dexterity save", "constitution save", "intelligence save",
        "wisdom save", "charisma save",
        "str modifier", "dex modifier", "con modifier", "int modifier",
        "wis modifier", "cha modifier",
        "str bonus", "dex bonus", "con bonus", "int bonus", "wis bonus", "cha bonus",
        "class level", "classlevel", "total level", "character level",
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

        # Skip keys that contain stat-modifier patterns even with extra words
        # e.g. "STRmod", "strength_modifier", "DEX Save Bonus"
        if re.match(
            r"(str|dex|con|int|wis|cha|strength|dexterity|constitution|intelligence|wisdom|charisma)\s*(mod|modifier|save|bonus|score)",
            key,
        ):
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


def _extract_pf2e_fields_from_widgets(fields: Dict[str, str]) -> Dict[str, Any]:
    """Extract Pathfinder 2e-specific fields from PDF widget key/value pairs.

    Returns a dict with PF2e-only keys: ancestry, saves (with rank), skills (dict
    keyed by name with rank), spell_slots, feats by category, bulk, traits, and
    stat modifiers.  Intentionally omits heritage/class_dc/focus_points since
    _build_character_import_sheet_from_pdf already extracts those directly.
    """
    if not fields:
        return {}

    def _find_first(patterns: list[str]) -> str | None:
        for pat in patterns:
            for k, v in fields.items():
                if not v:
                    continue
                if re.search(pat, str(k), re.I):
                    return _as_str(v)
        return None

    def _find_int(patterns: list[str]) -> int | None:
        val = _find_first(patterns)
        if val is None:
            return None
        m = re.search(r"-?\d+", str(val))
        return int(m.group(0)) if m else _as_int(val)

    _rank_map: Dict[str, str] = {
        "u": "untrained", "untrained": "untrained",
        "t": "trained", "trained": "trained",
        "e": "expert", "expert": "expert",
        "m": "master", "master": "master",
        "l": "legendary", "legendary": "legendary",
        "0": "untrained", "1": "trained", "2": "expert", "3": "master", "4": "legendary",
    }

    def _parse_rank(v: str | None) -> str | None:
        if not v:
            return None
        n = (v or "").strip().lower()
        return _rank_map.get(n) or _rank_map.get(n[:1])

    result: Dict[str, Any] = {}

    # Ancestry (distinct from D&D `species`)
    ancestry = _find_first([r"\bancestry\b", r"\bancestryname\b"])
    if ancestry:
        result["ancestry"] = ancestry

    # Focus Points (as `focus` to match the issue spec `sheet["focus"]["max"]`)
    focus_max = _find_int([r"\bfocus\s*(points?\s*)?max\b", r"\bmax\s*focus\b", r"\bfocusmax\b", r"\bfocuspointsmax\b"])
    focus_current = _find_int([r"\bfocus\s*(points?\s*)?current\b", r"\bcurrent\s*focus\b", r"\bfocuscurrent\b"])
    if focus_max is not None or focus_current is not None:
        result["focus"] = {}
        if focus_max is not None:
            result["focus"]["max"] = focus_max
        if focus_current is not None:
            result["focus"]["current"] = focus_current

    # Spell DC (class_dc already extracted by the main builder)
    spell_dc = _find_int([r"\bspell\s*dc\b", r"\bspelldc\b"])
    if spell_dc is not None:
        result["spell_dc"] = spell_dc

    # Saves with proficiency ranks
    saves: Dict[str, Any] = {}
    for save_key, patterns_total, patterns_rank in [
        ("fort", [r"\bfortitude\s*total\b", r"\bfort\s*total\b"], [r"\bfortitude\s*rank\b", r"\bfort\s*rank\b"]),
        ("ref", [r"\breflex\s*total\b", r"\bref\s*total\b"], [r"\breflex\s*rank\b", r"\bref\s*rank\b"]),
        ("will", [r"\bwill\s*total\b", r"\bwill\s*save\b"], [r"\bwill\s*rank\b"]),
    ]:
        save_entry: Dict[str, Any] = {}
        total = _find_int(patterns_total)
        if total is not None:
            save_entry["total"] = total
        rank = _parse_rank(_find_first(patterns_rank))
        if rank:
            save_entry["rank"] = rank
        if save_entry:
            saves[save_key] = save_entry
    if saves:
        result["saves"] = saves

    # Skills with proficiency ranks (stored separately from the generic skills list)
    pf2e_skills = [
        "Acrobatics", "Arcana", "Athletics", "Crafting", "Deception",
        "Diplomacy", "Intimidation", "Medicine", "Nature", "Occultism",
        "Performance", "Religion", "Society", "Stealth", "Survival", "Thievery",
    ]
    skills: Dict[str, Any] = {}
    for skill_name in pf2e_skills:
        skill_entry: Dict[str, Any] = {}
        rank = _parse_rank(_find_first([
            rf"\b{re.escape(skill_name)}\s*rank\b",
            rf"\brank\s*{re.escape(skill_name)}\b",
        ]))
        if rank:
            skill_entry["rank"] = rank
        mod_val = _find_int([
            rf"\b{re.escape(skill_name)}\s*(mod|modifier|bonus|total)\b",
        ])
        if mod_val is not None:
            skill_entry["modifier"] = mod_val
        if skill_entry:
            skills[skill_name] = skill_entry
    if skills:
        result["skills"] = skills

    # Bulk (PF2e uses Bulk instead of weight)
    bulk_current = _find_int([r"\bcurrent\s*bulk\b", r"\bbulk\s*current\b", r"\bbulkcurrent\b"])
    bulk_limit = _find_int([r"\bbulk\s*limit\b", r"\bmax\s*bulk\b", r"\bbulklimit\b"])
    if bulk_current is not None or bulk_limit is not None:
        result["bulk"] = {}
        if bulk_current is not None:
            result["bulk"]["current"] = bulk_current
        if bulk_limit is not None:
            result["bulk"]["limit"] = bulk_limit

    # Traits (character traits/tags)
    traits_blob = _find_first([r"\bcharacter\s*traits?\b", r"\btraits?\b"])
    if traits_blob:
        result["traits"] = [t.strip() for t in re.split(r"[,\n;]+", traits_blob) if t.strip()]

    # Spell slots keyed by level string
    spell_slots: Dict[str, int] = {}
    for k, v in fields.items():
        if not v:
            continue
        m = re.search(r"spell\s*slots?\s*(?:l|level|lvl)?\s*(\d+)\s*(?:max|total)?$", str(k), re.I)
        if m:
            slot_count = _as_int(str(v).strip())
            if isinstance(slot_count, int) and slot_count >= 0:
                spell_slots[m.group(1)] = slot_count
    if spell_slots:
        result["spell_slots"] = spell_slots

    # Feats by category
    feat_categories: Dict[str, list[str]] = {"ancestry": [], "class": [], "skill": [], "general": []}
    for k, v in fields.items():
        if not v or not str(v).strip():
            continue
        kl = str(k).lower()
        feat_name = _as_str(v)
        if not feat_name:
            continue
        if re.search(r"\bancestry\s*feat\b", kl):
            feat_categories["ancestry"].append(feat_name)
        elif re.search(r"\bclass\s*feat\b", kl):
            feat_categories["class"].append(feat_name)
        elif re.search(r"\bskill\s*feat\b", kl):
            feat_categories["skill"].append(feat_name)
        elif re.search(r"\bgeneral\s*feat\b", kl):
            feat_categories["general"].append(feat_name)
    if any(v for v in feat_categories.values()):
        result["feats"] = {cat: names for cat, names in feat_categories.items() if names}

    # Equipment (list of item names)
    equipment: list[str] = []
    seen_items: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\b(equipment|item|gear|weapon|armor)\b", str(k), re.I):
            item_name = _as_str(v)
            if item_name and item_name.lower() not in seen_items and len(item_name) > 1:
                seen_items.add(item_name.lower())
                equipment.append(item_name)
    if equipment:
        result["equipment"] = equipment

    return result


def _extract_pf1e_fields_from_widgets(fields: Dict[str, str]) -> Dict[str, Any]:
    """Extract Pathfinder 1e-specific fields from PDF widget key/value pairs.

    Returns a dict with PF1e-only keys: race, background=None, bab, cmb, cmd,
    saves (integer totals), skills (dict with ranks/total), spells_per_day,
    feats (flat list), equipment, and special_abilities.
    """
    if not fields:
        return {}

    def _find_first(patterns: list[str]) -> str | None:
        for pat in patterns:
            for k, v in fields.items():
                if not v:
                    continue
                if re.search(pat, str(k), re.I):
                    return _as_str(v)
        return None

    def _find_int(patterns: list[str]) -> int | None:
        val = _find_first(patterns)
        if val is None:
            return None
        m = re.search(r"-?\d+", str(val))
        return int(m.group(0)) if m else _as_int(val)

    result: Dict[str, Any] = {}

    # Race (PF1e uses Race, not Ancestry/Heritage)
    race = _find_first([r"\brace\b"])
    if race:
        result["race"] = race

    # Background is not a PF1e concept; explicitly null for schema consistency
    result["background"] = None

    # Combat stats unique to PF1e
    bab = _find_int([r"\b(base\s*attack\s*bonus|bab)\b"])
    if bab is not None:
        result["bab"] = bab

    cmb = _find_int([r"\b(combat\s*maneuver\s*bonus|cmb)\b"])
    if cmb is not None:
        result["cmb"] = cmb

    cmd = _find_int([r"\b(combat\s*maneuver\s*defense|cmd)\b"])
    if cmd is not None:
        result["cmd"] = cmd

    # Saving throws (integer totals; no proficiency ranks)
    saves: Dict[str, Any] = {}
    for save_key, patterns in [
        ("fort", [r"\bfortitude\s*total\b", r"\bfort\s*save\b", r"\bfortitudesave\b", r"\bfortitude\b"]),
        ("ref", [r"\breflex\s*total\b", r"\bref\s*save\b", r"\breflexsave\b", r"\breflex\b"]),
        ("will", [r"\bwill\s*total\b", r"\bwill\s*save\b", r"\bwillsave\b", r"\bwill\b"]),
    ]:
        total = _find_int(patterns)
        if total is not None:
            saves[save_key] = total
    if saves:
        result["saves"] = saves

    # Skills with explicit integer ranks and totals (dict keyed by skill name)
    pf1e_skills = [
        "Acrobatics", "Appraise", "Bluff", "Climb", "Craft", "Diplomacy",
        "Disable Device", "Disguise", "Escape Artist", "Fly", "Handle Animal",
        "Heal", "Intimidate", "Knowledge", "Linguistics", "Perception",
        "Perform", "Profession", "Ride", "Sense Motive", "Sleight of Hand",
        "Spellcraft", "Stealth", "Survival", "Swim", "Use Magic Device",
    ]
    skills: Dict[str, Any] = {}
    for skill_name in pf1e_skills:
        skill_entry: Dict[str, Any] = {}
        ranks_val = _find_int([
            rf"\b{re.escape(skill_name)}\s*ranks?\b",
            rf"\branks?\s*{re.escape(skill_name)}\b",
        ])
        if ranks_val is not None:
            skill_entry["ranks"] = ranks_val
        total_val = _find_int([
            rf"\b{re.escape(skill_name)}\s*total\b",
            rf"\btotal\s*{re.escape(skill_name)}\b",
        ])
        if total_val is not None:
            skill_entry["total"] = total_val
        if skill_entry:
            skills[skill_name] = skill_entry
    if skills:
        result["skills"] = skills

    # Spells per day (dict keyed by spell level string)
    spells_per_day: Dict[str, int] = {}
    for k, v in fields.items():
        if not v:
            continue
        m = re.search(r"spells?\s*per\s*day\s*(?:l|level|lvl)?\s*(\d+)", str(k), re.I)
        if m:
            val = _as_int(str(v).strip())
            if isinstance(val, int) and val >= 0:
                spells_per_day[m.group(1)] = val
    if spells_per_day:
        result["spells_per_day"] = spells_per_day

    # Feats — flat list (PF1e has no feat-type subdivision)
    feats: list[str] = []
    seen_feats: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\bfeat\b", str(k), re.I) and not re.search(r"\b(ancestry|class|skill|general)\b", str(k), re.I):
            feat_name = _as_str(v)
            if feat_name and feat_name.lower() not in seen_feats:
                seen_feats.add(feat_name.lower())
                feats.append(feat_name)
    if feats:
        result["feats"] = feats

    # Equipment / gear
    equipment: list[str] = []
    seen_items: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\b(equipment|item|gear|weapon|armor)\b", str(k), re.I):
            item_name = _as_str(v)
            if item_name and item_name.lower() not in seen_items and len(item_name) > 1:
                seen_items.add(item_name.lower())
                equipment.append(item_name)
    if equipment:
        result["equipment"] = equipment

    # Special abilities / class features / racial traits
    special_abilities: list[str] = []
    seen_abilities: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\b(special\s*abilit(?:y|ies)|class\s*feature|racial\s*trait)\b", str(k), re.I):
            ability_name = _as_str(v)
            if ability_name and ability_name.lower() not in seen_abilities:
                seen_abilities.add(ability_name.lower())
                special_abilities.append(ability_name)
    if special_abilities:
        result["special_abilities"] = special_abilities

    return result


# ---------------------------------------------------------------------------
# D&D 5e-specific field extraction
# ---------------------------------------------------------------------------

def _extract_dnd5e_fields_from_widgets(fields: Dict[str, str]) -> Dict[str, Any]:
    """Extract D&D 5e-specific fields from PDF widget key/value pairs.

    Returns a dict with 5e-only keys: race, background, proficiency_bonus,
    initiative, saves (with proficiency flag), skills (dict with proficiency
    and expertise flags), spell_slots (keyed by level string), features
    (flat list), hit_dice, inspiration, and death_saves.

    Fields with no D&D 5e equivalent that map to system-namespaced keys
    (e.g. ``d&d_stress``) are not emitted; HP / AC / stats are handled by
    the shared extractors already called by the main import builder.
    """
    if not fields:
        return {}

    def _find_first(patterns: list[str]) -> str | None:
        for k, v in fields.items():
            if not v:
                continue
            for pat in patterns:
                if re.search(pat, str(k), re.I):
                    return _as_str(v)
        return None

    def _find_int(patterns: list[str]) -> int | None:
        val = _find_first(patterns)
        if val is None:
            return None
        m = re.search(r"-?\d+", str(val))
        return int(m.group(0)) if m else _as_int(val)

    def _find_bool(patterns: list[str]) -> bool | None:
        val = _find_first(patterns)
        if val is None:
            return None
        v = str(val).strip().lower()
        if v in ("yes", "true", "1", "on"):
            return True
        if v in ("no", "false", "0", "off", ""):
            return False
        return None

    result: Dict[str, Any] = {}

    # Race / Species (D&D 5e uses Race; "species" already extracted by the shared builder
    # but we also store the raw widget value under "race" for schema consistency).
    race = _find_first([r"\brace\b", r"\bspecies\b", r"\bsubrace\b"])
    if race:
        result["race"] = race

    # Proficiency Bonus
    prof_bonus = _find_int([r"\bprof(?:iciency)?\s*bonus\b", r"\bprofbonus\b"])
    if prof_bonus is not None:
        result["proficiency_bonus"] = prof_bonus

    # Initiative (D&D 5e tracks this as a separate field; typically = DEX mod)
    initiative = _find_int([r"\binitiative\b"])
    if initiative is not None:
        result["initiative"] = initiative

    # Inspiration (boolean)
    inspiration = _find_bool([r"\binspiration\b", r"\binspired\b"])
    if inspiration is not None:
        result["inspiration"] = inspiration

    # Hit Dice (e.g. "d8" or "5d8"; D&D 5e tracks hit die type per level)
    hit_dice = _find_first([r"\bhit\s*dice\b", r"\bhd\s*type\b", r"\bhd\s*total\b", r"\bhdtotal\b", r"\bhit_dice\b"])
    if hit_dice:
        result["hit_dice"] = hit_dice

    # Death Saves (successes / failures counts)
    ds_successes = _find_int([r"\bdeath\s*save\s*success", r"\bds\s*success", r"\bdeathsavesuccess"])
    ds_failures = _find_int([r"\bdeath\s*save\s*fail", r"\bds\s*fail", r"\bdeathsavefail"])
    death_saves: Dict[str, Any] = {}
    if ds_successes is not None:
        death_saves["successes"] = ds_successes
    if ds_failures is not None:
        death_saves["failures"] = ds_failures
    if death_saves:
        result["death_saves"] = death_saves

    # Saving throws — D&D 5e has 6 ability-score saves, each with a proficiency flag.
    saves: Dict[str, Any] = {}
    for save_key, patterns_total, patterns_prof in [
        ("str", [r"\bstr\s*save\b", r"\bstrength\s*save\b", r"\bst\s*strength\b"],
                [r"\bstr\s*save\s*prof\b", r"\bstsaveprof\b"]),
        ("dex", [r"\bdex\s*save\b", r"\bdexterity\s*save\b", r"\bst\s*dexterity\b"],
                [r"\bdex\s*save\s*prof\b"]),
        ("con", [r"\bcon\s*save\b", r"\bconstitution\s*save\b", r"\bst\s*constitution\b"],
                [r"\bcon\s*save\s*prof\b"]),
        ("int", [r"\bint\s*save\b", r"\bintelligence\s*save\b", r"\bst\s*intelligence\b"],
                [r"\bint\s*save\s*prof\b"]),
        ("wis", [r"\bwis\s*save\b", r"\bwisdom\s*save\b", r"\bst\s*wisdom\b"],
                [r"\bwis\s*save\s*prof\b"]),
        ("cha", [r"\bcha\s*save\b", r"\bcharisma\s*save\b", r"\bst\s*charisma\b"],
                [r"\bcha\s*save\s*prof\b"]),
    ]:
        save_entry: Dict[str, Any] = {}
        total = _find_int(patterns_total)
        if total is not None:
            save_entry["total"] = total
        prof = _find_bool(patterns_prof)
        if prof is not None:
            save_entry["proficient"] = prof
        if save_entry:
            saves[save_key] = save_entry
    if saves:
        result["saves"] = saves

    # Skills — D&D 5e has 18 skills each with a modifier, proficiency flag, and
    # optional expertise flag.
    dnd5e_skills = [
        "Acrobatics", "Animal Handling", "Arcana", "Athletics",
        "Deception", "History", "Insight", "Intimidation",
        "Investigation", "Medicine", "Nature", "Perception",
        "Performance", "Persuasion", "Religion", "Sleight of Hand",
        "Stealth", "Survival",
    ]
    skills: Dict[str, Any] = {}
    for skill_name in dnd5e_skills:
        skill_entry: Dict[str, Any] = {}
        # Widget key variants seen on D&D Beyond and community fillable PDFs:
        #   "Acrobatics", "AcrobaticsBonus", "Acrobatics Total"
        safe = re.escape(skill_name)
        mod_val = _find_int([
            rf"\b{safe}\s*(bonus|modifier|total|mod)\b",
            rf"\b{safe}\b",
        ])
        if mod_val is not None:
            skill_entry["modifier"] = mod_val
        prof = _find_bool([rf"\b{safe}\s*prof(?:iciency)?\b"])
        if prof is not None:
            skill_entry["proficient"] = prof
        exp = _find_bool([rf"\b{safe}\s*exp(?:ertise)?\b"])
        if exp is not None:
            skill_entry["expertise"] = exp
        if skill_entry:
            skills[skill_name] = skill_entry
    if skills:
        result["skills"] = skills

    # Spell slots keyed by level string ("1"–"9").
    # Matches D&D Beyond PDF widgets ("SlotsTotal1", "SlotsRemaining1"),
    # community fillable sheet variants ("SpellSlots1", "Spell Slot L1"),
    # and the plain "Spell Slots Total 1" format.
    # Capturing group 1 = the level digit.
    _slot_total_pat = re.compile(
        r"(?:spell\s*slots?\s*(?:total|max)?|slots?\s*total|spell\s*slot\s*(?:l|lvl|level)?\s*)(\d)$",
        re.I,
    )
    _slot_remaining_pat = re.compile(
        r"(?:slots?\s*remaining|spell\s*slots?\s*(?:remaining|left|current)|remaining\s*slots?)(\d)$",
        re.I,
    )
    spell_slots_max: Dict[str, int] = {}
    spell_slots_remaining: Dict[str, int] = {}
    for k, v in fields.items():
        if not v:
            continue
        m = _slot_total_pat.search(str(k))
        if m:
            slot_count = _as_int(str(v).strip())
            if isinstance(slot_count, int) and slot_count >= 0:
                spell_slots_max[m.group(1)] = slot_count
            continue
        m2 = _slot_remaining_pat.search(str(k))
        if m2:
            remaining = _as_int(str(v).strip())
            if isinstance(remaining, int) and remaining >= 0:
                spell_slots_remaining[m2.group(1)] = remaining
    if spell_slots_max:
        # Build a richer structure when both total and remaining are known,
        # falling back to simple int when only total is available.
        if spell_slots_remaining:
            result["spell_slots"] = {
                lvl: {
                    "max": max_val,
                    "used": max_val - spell_slots_remaining.get(lvl, max_val),
                }
                for lvl, max_val in spell_slots_max.items()
            }
        else:
            result["spell_slots"] = spell_slots_max

    # Class features / traits (D&D 5e calls them "Features & Traits")
    features: list[str] = []
    seen_feats: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\b(feature|trait|class\s*feature|racial\s*trait)\b", str(k), re.I):
            feat_name = _as_str(v)
            if feat_name and feat_name.lower() not in seen_feats:
                seen_feats.add(feat_name.lower())
                features.append(feat_name)
    if features:
        result["features"] = features

    # Equipment / gear
    equipment: list[str] = []
    seen_items: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\b(equipment|item|gear|weapon|armor)\b", str(k), re.I):
            item_name = _as_str(v)
            if item_name and item_name.lower() not in seen_items and len(item_name) > 1:
                seen_items.add(item_name.lower())
                equipment.append(item_name)
    if equipment:
        result["equipment"] = equipment

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


# ---------------------------------------------------------------------------
# D&D 5e field extraction
# ---------------------------------------------------------------------------


def _extract_dnd5e_fields_from_widgets(fields: Dict[str, str]) -> Dict[str, Any]:
    """Extract D&D 5e-specific fields from PDF widget key/value pairs.

    Returns: race, alignment, proficiency_bonus, initiative, inspiration,
    hit_dice, death_saves, exhaustion, saves (per-ability), skills (18),
    spell_slots (levels 1-9), spell_attack_bonus, spell_save_dc,
    currency, class_resources, features, equipment.
    """
    if not fields:
        return {}

    def _find_first(patterns: list[str]) -> str | None:
        for pat in patterns:
            for k, v in fields.items():
                if not v:
                    continue
                if re.search(pat, str(k), re.I):
                    return _as_str(v)
        return None

    def _find_int(patterns: list[str]) -> int | None:
        val = _find_first(patterns)
        if val is None:
            return None
        m = re.search(r"-?\d+", str(val))
        return int(m.group(0)) if m else _as_int(val)

    def _find_bool(patterns: list[str]) -> bool | None:
        val = _find_first(patterns)
        if val is None:
            return None
        v = str(val).strip().lower()
        if v in ("yes", "true", "1", "on"):
            return True
        if v in ("no", "false", "0", "off", ""):
            return False
        return None

    result: Dict[str, Any] = {}

    race = _find_first([r"\brace\b", r"\bspecies\b", r"\bsubrace\b"])
    if race:
        result["race"] = race

    alignment = _find_first([r"\balignment\b"])
    if alignment:
        result["alignment"] = alignment

    prof_bonus = _find_int([r"\bprof(?:iciency)?\s*bonus\b", r"\bprofbonus\b"])
    if prof_bonus is not None:
        result["proficiency_bonus"] = prof_bonus

    initiative = _find_int([r"\binitiative\b"])
    if initiative is not None:
        result["initiative"] = initiative

    inspiration = _find_bool([r"\binspiration\b", r"\binspired\b"])
    if inspiration is not None:
        result["inspiration"] = inspiration

    hit_dice = _find_first([r"\bhit\s*dice\b", r"\bhd\s*type\b", r"\bhd\s*total\b", r"\bhdtotal\b"])
    if hit_dice:
        result["hit_dice"] = hit_dice

    exhaustion = _find_int([r"\bexhaustion\b", r"\bexhaustion\s*level\b"])
    if exhaustion is not None:
        result["exhaustion"] = exhaustion

    # Death saves
    ds_successes = _find_int([r"\bdeath\s*save\s*success", r"\bds\s*success", r"\bdeathsavesuccess"])
    ds_failures = _find_int([r"\bdeath\s*save\s*fail", r"\bds\s*fail", r"\bdeathsavefail"])
    death_saves: Dict[str, Any] = {}
    if ds_successes is not None:
        death_saves["successes"] = ds_successes
    if ds_failures is not None:
        death_saves["failures"] = ds_failures
    if death_saves:
        result["death_saves"] = death_saves

    # Saving throws (6 ability saves)
    saves: Dict[str, Any] = {}
    for save_key, patterns_total, patterns_prof in [
        (
            "str",
            [r"\bstr\s*save\b", r"\bstrength\s*save\b", r"\bst\s*strength\b"],
            [r"\bstr\s*save\s*prof\b", r"\bstsaveprof\b"],
        ),
        (
            "dex",
            [r"\bdex\s*save\b", r"\bdexterity\s*save\b", r"\bst\s*dexterity\b"],
            [r"\bdex\s*save\s*prof\b"],
        ),
        (
            "con",
            [r"\bcon\s*save\b", r"\bconstitution\s*save\b", r"\bst\s*constitution\b"],
            [r"\bcon\s*save\s*prof\b"],
        ),
        (
            "int",
            [r"\bint\s*save\b", r"\bintelligence\s*save\b", r"\bst\s*intelligence\b"],
            [r"\bint\s*save\s*prof\b"],
        ),
        (
            "wis",
            [r"\bwis\s*save\b", r"\bwisdom\s*save\b", r"\bst\s*wisdom\b"],
            [r"\bwis\s*save\s*prof\b"],
        ),
        (
            "cha",
            [r"\bcha\s*save\b", r"\bcharisma\s*save\b", r"\bst\s*charisma\b"],
            [r"\bcha\s*save\s*prof\b"],
        ),
    ]:
        save_entry: Dict[str, Any] = {}
        total = _find_int(patterns_total)
        if total is not None:
            save_entry["total"] = total
        prof = _find_bool(patterns_prof)
        if prof is not None:
            save_entry["proficient"] = prof
        if save_entry:
            saves[save_key] = save_entry
    if saves:
        result["saves"] = saves

    # 18 Skills
    dnd5e_skills = [
        "Acrobatics",
        "Animal Handling",
        "Arcana",
        "Athletics",
        "Deception",
        "History",
        "Insight",
        "Intimidation",
        "Investigation",
        "Medicine",
        "Nature",
        "Perception",
        "Performance",
        "Persuasion",
        "Religion",
        "Sleight of Hand",
        "Stealth",
        "Survival",
    ]
    skills: Dict[str, Any] = {}
    for skill_name in dnd5e_skills:
        skill_entry: Dict[str, Any] = {}
        safe = re.escape(skill_name)
        mod_val = _find_int([
            rf"\b{safe}\s*(bonus|modifier|total|mod)\b",
            rf"\b{safe}\b",
        ])
        if mod_val is not None:
            skill_entry["modifier"] = mod_val
        prof = _find_bool([rf"\b{safe}\s*prof(?:iciency)?\b"])
        if prof is not None:
            skill_entry["proficient"] = prof
        exp = _find_bool([rf"\b{safe}\s*exp(?:ertise)?\b"])
        if exp is not None:
            skill_entry["expertise"] = exp
        if skill_entry:
            skills[skill_name] = skill_entry
    if skills:
        result["skills"] = skills

    # Spell slots levels 1-9 with optional remaining-slot tracking.
    _slot_total_pat = re.compile(
        r"(?:spell\s*slots?\s*(?:total|max)?|slots?\s*total|spell\s*slot\s*(?:l|lvl|level)?\s*)(\d)$",
        re.I,
    )
    _slot_remaining_pat = re.compile(
        r"(?:slots?\s*remaining|spell\s*slots?\s*(?:remaining|left|current)|remaining\s*slots?)(\d)$",
        re.I,
    )
    spell_slots_max: Dict[str, int] = {}
    spell_slots_remaining: Dict[str, int] = {}
    for k, v in fields.items():
        if not v:
            continue
        m = _slot_total_pat.search(str(k))
        if m:
            slot_count = _as_int(str(v).strip())
            if isinstance(slot_count, int) and slot_count >= 0:
                spell_slots_max[m.group(1)] = slot_count
            continue
        m2 = _slot_remaining_pat.search(str(k))
        if m2:
            remaining = _as_int(str(v).strip())
            if isinstance(remaining, int) and remaining >= 0:
                spell_slots_remaining[m2.group(1)] = remaining
    if spell_slots_max:
        if spell_slots_remaining:
            result["spell_slots"] = {
                lvl: {
                    "max": max_val,
                    "used": max_val - spell_slots_remaining.get(lvl, max_val),
                }
                for lvl, max_val in spell_slots_max.items()
            }
        else:
            result["spell_slots"] = spell_slots_max

    # Spellcasting bonus and save DC
    spell_atk = _find_int([r"\bspell\s*attack\s*(bonus|mod|modifier)\b", r"\bspellatk\b", r"\bspell\s*atk\b"])
    if spell_atk is not None:
        result["spell_attack_bonus"] = spell_atk
    spell_dc = _find_int([r"\bspell\s*save\s*dc\b", r"\bspellsavedc\b", r"\bspell\s*dc\b"])
    if spell_dc is not None:
        result["spell_save_dc"] = spell_dc

    # Currency (copper/silver/electrum/gold/platinum)
    currency: Dict[str, int] = {}
    for coin, patterns in [
        ("cp", [r"\bcopper\b", r"\bcp\b"]),
        ("sp", [r"\bsilver\b", r"\bsp\b"]),
        ("ep", [r"\belectrum\b", r"\bep\b"]),
        ("gp", [r"\bgold\b", r"\bgp\b"]),
        ("pp", [r"\bplatinum\b", r"\bpp\b"]),
    ]:
        val = _find_int(patterns)
        if val is not None:
            currency[coin] = val
    if currency:
        result["currency"] = currency

    # Class-specific resources
    class_resources: Dict[str, Any] = {}
    for res_key, patterns in [
        ("ki_points", [r"\bki\s*points?\b", r"\bkipoints\b"]),
        ("sorcery_points", [r"\bsorcery\s*points?\b", r"\bsorcerypoints\b"]),
        ("bardic_inspiration", [r"\bbardic\s*inspiration\b", r"\bbardicinsp\b"]),
        ("lay_on_hands", [r"\blay\s*on\s*hands\b", r"\blayonhands\b"]),
        ("channel_divinity", [r"\bchannel\s*divinity\b", r"\bchanneldivinity\b"]),
        ("superiority_dice", [r"\bsuperiority\s*dice\b", r"\bsuperioritydice\b"]),
        ("wild_shape", [r"\bwild\s*shape\b", r"\bwildshape\b"]),
        ("arcane_recovery", [r"\barcane\s*recovery\b", r"\barcanerecovery\b"]),
        ("action_surge", [r"\baction\s*surge\b", r"\bactionsurge\b"]),
        ("second_wind", [r"\bsecond\s*wind\b", r"\bsecondwind\b"]),
        ("rage", [r"\brage\s*(?:uses|count|remaining)?\b", r"\brages\b"]),
        ("sneak_attack", [r"\bsneak\s*attack\b", r"\bsneakattack\b"]),
    ]:
        val = _find_int(patterns)
        if val is not None:
            class_resources[res_key] = val
    if class_resources:
        result["class_resources"] = class_resources

    # Features / Traits
    features: list[str] = []
    seen_feats: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\b(feature|trait|class\s*feature|racial\s*trait)\b", str(k), re.I):
            feat_name = _as_str(v)
            if feat_name and feat_name.lower() not in seen_feats:
                seen_feats.add(feat_name.lower())
                features.append(feat_name)
    if features:
        result["features"] = features

    # Equipment
    equipment: list[str] = []
    seen_items: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\b(equipment|item|gear|weapon|armor)\b", str(k), re.I):
            item_name = _as_str(v)
            if item_name and item_name.lower() not in seen_items and len(item_name) > 1:
                seen_items.add(item_name.lower())
                equipment.append(item_name)
    if equipment:
        result["equipment"] = equipment

    return result



# ---------------------------------------------------------------------------
# Starfinder field extraction
# ---------------------------------------------------------------------------


def _extract_starfinder_fields_from_widgets(fields: Dict[str, str]) -> Dict[str, Any]:
    """Extract Starfinder-specific fields.

    Returns race/species, theme, homeworld, deity, alignment,
    starfinder_stamina, starfinder_resolve, starfinder_kac, starfinder_eac,
    starfinder_initiative, saves, skills, feats, class_features, equipment,
    bulk, spell_slots, starfinder_credits, starfinder_augmentations.
    """
    if not fields:
        return {}

    def _find_first(patterns: list[str]) -> str | None:
        for pat in patterns:
            for k, v in fields.items():
                if not v:
                    continue
                if re.search(pat, str(k), re.I):
                    return _as_str(v)
        return None

    def _find_int(patterns: list[str]) -> int | None:
        val = _find_first(patterns)
        if val is None:
            return None
        m = re.search(r"-?\d+", str(val))
        return int(m.group(0)) if m else _as_int(val)

    result: Dict[str, Any] = {}

    race = _find_first([r"\brace\b", r"\bspecies\b", r"\bancestry\b"])
    if race:
        result["race"] = race

    theme = _find_first([r"\btheme\b"])
    if theme:
        result["starfinder_theme"] = theme

    homeworld = _find_first([r"\bhomeworld\b", r"\bhome\s*world\b"])
    if homeworld:
        result["starfinder_homeworld"] = homeworld

    deity = _find_first([r"\bdeity\b", r"\bgod\b"])
    if deity:
        result["starfinder_deity"] = deity

    alignment = _find_first([r"\balignment\b"])
    if alignment:
        result["alignment"] = alignment

    # Stamina Points (Starfinder-unique resource)
    sp_max = _find_int([r"\bsp\s*max\b", r"\bmax\s*sp\b", r"\bstamina\s*(?:points?\s*)?max\b"])
    sp_cur = _find_int([r"\bsp\s*current\b", r"\bcurrent\s*sp\b", r"\bstamina\s*(?:points?\s*)?current\b"])
    stamina: Dict[str, Any] = {}
    if sp_max is not None:
        stamina["max"] = sp_max
    if sp_cur is not None:
        stamina["current"] = sp_cur
    if stamina:
        result["starfinder_stamina"] = stamina

    # Resolve Points
    rp_max = _find_int([r"\brp\s*max\b", r"\bmax\s*rp\b", r"\bresolve\s*(?:points?\s*)?max\b"])
    rp_cur = _find_int([r"\brp\s*current\b", r"\bcurrent\s*rp\b", r"\bresolve\s*(?:points?\s*)?current\b"])
    resolve: Dict[str, Any] = {}
    if rp_max is not None:
        resolve["max"] = rp_max
    if rp_cur is not None:
        resolve["current"] = rp_cur
    if resolve:
        result["starfinder_resolve"] = resolve

    # Armor Classes
    kac = _find_int([r"\bkac\b", r"\bkinetic\s*ac\b", r"\bkinetic\s*armor\b"])
    if kac is not None:
        result["starfinder_kac"] = kac
    eac = _find_int([r"\beac\b", r"\benergy\s*ac\b", r"\benergy\s*armor\b"])
    if eac is not None:
        result["starfinder_eac"] = eac

    initiative = _find_int([r"\binitiative\b", r"\binit\b"])
    if initiative is not None:
        result["starfinder_initiative"] = initiative

    # Saves (Fort/Ref/Will as integers)
    saves: Dict[str, int] = {}
    for save_key, patterns in [
        ("fort", [r"\bfortitude\b", r"\bfort\b"]),
        ("ref", [r"\breflex\b", r"\bref\b"]),
        ("will", [r"\bwill\b"]),
    ]:
        val = _find_int(patterns)
        if val is not None:
            saves[save_key] = val
    if saves:
        result["saves"] = saves

    # Skills with ranks + total
    sf_skills = [
        "Acrobatics",
        "Athletics",
        "Bluff",
        "Computers",
        "Culture",
        "Diplomacy",
        "Disguise",
        "Engineering",
        "Intimidate",
        "Life Science",
        "Medicine",
        "Mysticism",
        "Perception",
        "Physical Science",
        "Piloting",
        "Profession",
        "Sense Motive",
        "Sleight of Hand",
        "Stealth",
        "Survival",
    ]
    skills: Dict[str, Any] = {}
    for skill_name in sf_skills:
        skill_entry: Dict[str, Any] = {}
        safe = re.escape(skill_name)
        ranks = _find_int([rf"\b{safe}\s*ranks?\b"])
        if ranks is not None:
            skill_entry["ranks"] = ranks
        total = _find_int([rf"\b{safe}\s*total\b", rf"\b{safe}\s*bonus\b", rf"\b{safe}\b"])
        if total is not None:
            skill_entry["total"] = total
        if skill_entry:
            skills[skill_name] = skill_entry
    if skills:
        result["skills"] = skills

    # Feats
    feats: list[str] = []
    seen_feats: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\bfeat\b", str(k), re.I):
            feat_name = _as_str(v)
            if feat_name and feat_name.lower() not in seen_feats:
                seen_feats.add(feat_name.lower())
                feats.append(feat_name)
    if feats:
        result["feats"] = feats

    # Class features
    class_features: list[str] = []
    seen_cf: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\bclass\s*feature\b", str(k), re.I):
            cf = _as_str(v)
            if cf and cf.lower() not in seen_cf:
                seen_cf.add(cf.lower())
                class_features.append(cf)
    if class_features:
        result["class_features"] = class_features

    # Equipment / gear
    equipment: list[str] = []
    seen_items: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\b(equipment|item|gear|weapon|armor)\b", str(k), re.I):
            item_name = _as_str(v)
            if item_name and item_name.lower() not in seen_items and len(item_name) > 1:
                seen_items.add(item_name.lower())
                equipment.append(item_name)
    if equipment:
        result["equipment"] = equipment

    # Bulk
    bulk_current = _find_int([r"\bcurrent\s*bulk\b", r"\bbulk\s*current\b"])
    bulk_limit = _find_int([r"\bbulk\s*limit\b", r"\bmax\s*bulk\b"])
    if bulk_current is not None or bulk_limit is not None:
        bulk: Dict[str, Any] = {}
        if bulk_current is not None:
            bulk["current"] = bulk_current
        if bulk_limit is not None:
            bulk["limit"] = bulk_limit
        result["bulk"] = bulk

    # Spell slots
    spell_slots: Dict[str, int] = {}
    for k, v in fields.items():
        if not v:
            continue
        m = re.search(r"spell\s*slots?\s*(?:l|level|lvl)?\s*(\d+)\s*(?:max|total)?$", str(k), re.I)
        if m:
            slot_count = _as_int(str(v).strip())
            if isinstance(slot_count, int) and slot_count >= 0:
                spell_slots[m.group(1)] = slot_count
    if spell_slots:
        result["spell_slots"] = spell_slots

    # Credits (Starfinder currency)
    credits_val = _find_int([r"\bcredits?\b", r"\bcr\b"])
    if credits_val is not None:
        result["starfinder_credits"] = credits_val

    # Augmentations (cybernetics, biotech, etc.)
    augmentations: list[Dict[str, Any]] = []
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\baugment(?:ation)?\b|\bcybernetics?\b|\bbiotech\b|\bneuroblock\b", str(k), re.I):
            aug_name = _as_str(v)
            if aug_name and len(aug_name) > 1:
                augmentations.append({"name": aug_name})
    if augmentations:
        result["starfinder_augmentations"] = augmentations

    return result


# ---------------------------------------------------------------------------
# Shadow of the Demon Lord (SotDL) field extraction
# ---------------------------------------------------------------------------

_SOTDL_ATTRIBUTES = ["Strength", "Agility", "Intellect", "Will"]


def _is_sotdl_sheet(widget_values: Dict[str, str]) -> bool:
    """Detect SotDL sheets via attribute + unique-key presence."""
    attr_hits = sum(
        1 for k in widget_values if any(re.search(rf"\b{re.escape(a)}\b", k, re.I) for a in _SOTDL_ATTRIBUTES)
    )
    unique_hits = sum(
        1 for k in widget_values if re.search(r"\bcorruption\b|\bhealing\s*rate\b|\bnovice\s*path\b|\binsanity\b", k, re.I)
    )
    return attr_hits >= 3 and unique_hits >= 1


def _extract_sotdl_fields_from_widgets(fields: Dict[str, str]) -> Dict[str, Any]:
    """Extract SotDL-specific fields.

    Returns stats (Str/Agi/Int/Will), hp, ac (defense), sotdl_healing_rate,
    sotdl_perception, sotdl_corruption, sotdl_insanity, sotdl_speed,
    sotdl_fortune_dice, sotdl_paths, sotdl_professions, race (ancestry),
    talents, spells, equipment, languages.
    """
    if not fields:
        return {}

    def _find_first(patterns: list[str]) -> str | None:
        for pat in patterns:
            for k, v in fields.items():
                if not v:
                    continue
                if re.search(pat, str(k), re.I):
                    return _as_str(v)
        return None

    def _find_int(patterns: list[str]) -> int | None:
        val = _find_first(patterns)
        if val is None:
            return None
        m = re.search(r"-?\d+", str(val))
        return int(m.group(0)) if m else _as_int(val)

    result: Dict[str, Any] = {}

    # 4 Core Attributes
    stats: Dict[str, int] = {}
    for attr, patterns in [
        ("strength", [r"\bstrength\b", r"\bstr\b"]),
        ("agility", [r"\bagility\b", r"\bagi\b"]),
        ("intellect", [r"\bintellect\b", r"\bint\b"]),
        ("will", [r"\bwill\b"]),
    ]:
        val = _find_int(patterns)
        if val is not None:
            stats[attr] = val
    if stats:
        result["stats"] = stats

    # Health → hp
    health_max = _find_int([r"\bhealth\s*max\b", r"\bmax\s*health\b", r"\bhp\s*max\b"])
    health_cur = _find_int([r"\bhealth\s*current\b", r"\bcurrent\s*health\b", r"\bhealth\b"])
    hp: Dict[str, Any] = {}
    if health_max is not None:
        hp["max"] = health_max
    elif health_cur is not None:
        hp["max"] = health_cur
    if health_cur is not None:
        hp["current"] = health_cur
    if hp:
        result["hp"] = hp

    # Defense → ac
    defense = _find_int([r"\bdefense\b", r"\bdef\b"])
    if defense is not None:
        result["ac"] = defense

    # SotDL-unique fields
    healing_rate = _find_int([r"\bhealing\s*rate\b", r"\bhealingrate\b"])
    if healing_rate is not None:
        result["sotdl_healing_rate"] = healing_rate

    perception = _find_int([r"\bperception\b", r"\bperc\b"])
    if perception is not None:
        result["sotdl_perception"] = perception

    corruption = _find_int([r"\bcorruption\b"])
    if corruption is not None:
        result["sotdl_corruption"] = corruption

    insanity = _find_int([r"\binsanity\b"])
    if insanity is not None:
        result["sotdl_insanity"] = insanity

    speed = _find_int([r"\bspeed\b", r"\bmovement\b"])
    if speed is not None:
        result["sotdl_speed"] = speed

    fortune_dice = _find_int([r"\bfortune\s*dice\b", r"\bfortune\b", r"\bfortune\s*points?\b"])
    if fortune_dice is not None:
        result["sotdl_fortune_dice"] = fortune_dice

    # Path progression
    paths: Dict[str, str] = {}
    novice = _find_first([r"\bnovice\s*path\b", r"\bnovicepath\b"])
    if novice:
        paths["novice"] = novice
    expert = _find_first([r"\bexpert\s*path\b", r"\bexpertpath\b"])
    if expert:
        paths["expert"] = expert
    master = _find_first([r"\bmaster\s*path\b", r"\bmasterpath\b"])
    if master:
        paths["master"] = master
    if paths:
        result["sotdl_paths"] = paths

    # Ancestry (→ race)
    ancestry = _find_first([r"\bancestry\b", r"\brace\b", r"\bspecies\b"])
    if ancestry:
        result["race"] = ancestry

    # Talents
    talents: list[str] = []
    seen_t: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\btalent\b", str(k), re.I):
            t = _as_str(v)
            if t and t.lower() not in seen_t:
                seen_t.add(t.lower())
                talents.append(t)
    if talents:
        result["talents"] = talents

    # Spells
    spells: list[str] = []
    seen_sp: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\bspell\b", str(k), re.I):
            sp = _as_str(v)
            if sp and sp.lower() not in seen_sp:
                seen_sp.add(sp.lower())
                spells.append(sp)
    if spells:
        result["spells"] = spells

    # Equipment
    equipment: list[str] = []
    seen_eq: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\b(equipment|item|gear|weapon|armor)\b", str(k), re.I):
            item_name = _as_str(v)
            if item_name and item_name.lower() not in seen_eq and len(item_name) > 1:
                seen_eq.add(item_name.lower())
                equipment.append(item_name)
    if equipment:
        result["equipment"] = equipment

    # Languages
    lang_blob = _find_first([r"\blanguages?\b"])
    if lang_blob:
        result["languages"] = [lang.strip() for lang in re.split(r"[,\n;]+", lang_blob) if lang.strip()]

    # Professions
    prof_blob = _find_first([r"\bprofessions?\b"])
    if prof_blob:
        result["sotdl_professions"] = [p.strip() for p in re.split(r"[,\n;]+", prof_blob) if p.strip()]

    # Background / story text
    background = _find_first([r"\bbackground\b", r"\bstory\b", r"\bhistory\b"])
    if background:
        result["sotdl_background"] = background

    return result


# ---------------------------------------------------------------------------
# Warhammer Fantasy Roleplay (WFRP 4e) field extraction
# ---------------------------------------------------------------------------

_WFRP_CHAR_ABBREVS = ["WS", "BS", "S", "T", "I", "Agi", "Dex", "Int", "WP", "Fel"]


def _is_wfrp_sheet(widget_values: Dict[str, str]) -> bool:
    """Detect WFRP 4e sheets by presence of ≥4 characteristic widget keys."""
    hits = sum(
        1
        for abbr in _WFRP_CHAR_ABBREVS
        if any(re.search(rf"\b{re.escape(abbr)}\b", k, re.I) for k in widget_values)
    )
    return hits >= 4


def _extract_wfrp_fields_from_widgets(fields: Dict[str, str]) -> Dict[str, Any]:
    """Extract WFRP 4e-specific fields.

    Returns warhammer_characteristics (WS/BS/S/T/I/Agi/Dex/Int/WP/Fel),
    warhammer_wounds, warhammer_fate, warhammer_resilience,
    warhammer_corruption, warhammer_experience, warhammer_career,
    warhammer_skills, warhammer_talents, warhammer_trappings,
    warhammer_ambitions, warhammer_species (race), warhammer_movement,
    warhammer_money, warhammer_spells.
    """
    if not fields:
        return {}

    def _find_first(patterns: list[str]) -> str | None:
        for pat in patterns:
            for k, v in fields.items():
                if not v:
                    continue
                if re.search(pat, str(k), re.I):
                    return _as_str(v)
        return None

    def _find_int(patterns: list[str]) -> int | None:
        val = _find_first(patterns)
        if val is None:
            return None
        m = re.search(r"-?\d+", str(val))
        return int(m.group(0)) if m else _as_int(val)

    result: Dict[str, Any] = {}

    # 10 Characteristics (each has initial/advances/total sub-fields)
    char_full_names = {
        "WS": "weapon_skill",
        "BS": "ballistic_skill",
        "S": "strength",
        "T": "toughness",
        "I": "initiative",
        "Agi": "agility",
        "Dex": "dexterity",
        "Int": "intelligence",
        "WP": "willpower",
        "Fel": "fellowship",
    }
    characteristics: Dict[str, Any] = {}
    for abbr, full_name in char_full_names.items():
        char_entry: Dict[str, Any] = {}
        safe = re.escape(abbr)
        # Try labelled "WS Initial" first; fall back to plain exact key "WS" (common on real sheets)
        initial = _find_int([rf"\b{safe}\s*initial\b", rf"\b{safe}\s*init\b", rf"\b{safe}\s*start\b", rf"^{safe}$"])
        if initial is not None:
            char_entry["initial"] = initial
        advances = _find_int([rf"\b{safe}\s*advances?\b", rf"\b{safe}\s*adv\b", rf"^{safe}\s*advances?$"])
        if advances is not None:
            char_entry["advances"] = advances
        # Compute total from initial + advances when both available; otherwise read from widget
        if initial is not None and advances is not None:
            char_entry["total"] = initial + advances
        elif initial is not None:
            char_entry["total"] = initial
        else:
            total = _find_int([rf"\b{safe}\s*total\b", rf"\b{safe}\s*current\b"])
            if total is not None:
                char_entry["total"] = total
        if char_entry:
            characteristics[full_name] = char_entry
    if characteristics:
        result["warhammer_characteristics"] = characteristics

    # Wounds (WFRP HP equivalent)
    wounds_max = _find_int([r"\bwounds\s*max\b", r"\bmax\s*wounds\b", r"\bwounds\s*total\b", r"^wounds$"])
    wounds_cur = _find_int([r"\bwounds\s*current\b", r"\bcurrent\s*wounds\b", r"^current\s*wounds$"])
    wounds: Dict[str, Any] = {}
    if wounds_max is not None:
        wounds["max"] = wounds_max
    if wounds_cur is not None:
        wounds["current"] = wounds_cur
    if wounds:
        result["warhammer_wounds"] = wounds

    # Fate & Fortune
    fate_pts = _find_int([r"\bfate\s*points?\b", r"\bfate\b"])
    fortune_pts = _find_int([r"\bfortune\s*points?\b", r"\bfortune\b"])
    fate: Dict[str, Any] = {}
    if fate_pts is not None:
        fate["fate"] = fate_pts
    if fortune_pts is not None:
        fate["fortune"] = fortune_pts
    if fate:
        result["warhammer_fate"] = fate

    # Resilience & Resolve
    res_pts = _find_int([r"\bresilience\s*points?\b", r"\bresilience\b"])
    resolve_pts = _find_int([r"\bresolve\s*points?\b", r"\bresolve\b"])
    resil: Dict[str, Any] = {}
    if res_pts is not None:
        resil["resilience"] = res_pts
    if resolve_pts is not None:
        resil["resolve"] = resolve_pts
    if resil:
        result["warhammer_resilience"] = resil

    # Corruption
    corruption = _find_int([r"\bcorruption\b", r"\bcorrupt\s*pts?\b"])
    if corruption is not None:
        result["warhammer_corruption"] = corruption

    # Experience
    xp_total = _find_int([r"\bxp\s*total\b", r"\btotal\s*xp\b", r"\bexperience\s*total\b", r"^experience$"])
    xp_spent = _find_int([r"\bxp\s*spent\b", r"\bspent\s*xp\b", r"\bexperience\s*spent\b"])
    xp_current = _find_int([r"\bxp\s*current\b", r"\bcurrent\s*xp\b"])
    xp: Dict[str, Any] = {}
    if xp_total is not None:
        xp["total"] = xp_total
    if xp_spent is not None:
        xp["spent"] = xp_spent
    if xp_current is not None:
        xp["current"] = xp_current
    if xp:
        result["warhammer_experience"] = xp

    # Career
    career_name = _find_first([r"\bcareer\s*name\b", r"\bcareer\b"])
    _raw_career_level = _find_first([r"\bcareer\s*level\b"])
    if _raw_career_level is not None:
        try:
            career_level: Any = int(_raw_career_level.strip())
        except (ValueError, AttributeError):
            career_level = _raw_career_level
    else:
        career_level = None
    career_status = _find_first([r"\bcareer\s*status\b", r"\bstatus\b"])
    career: Dict[str, Any] = {}
    if career_name:
        career["name"] = career_name
        result.setdefault("class_name", career_name)
    if career_level is not None:
        career["level"] = career_level
    if career_status:
        career["status"] = career_status
    if career:
        result["warhammer_career"] = career

    # Skills
    skills: list[Dict[str, Any]] = []
    skill_name_keys = [
        k for k in fields if re.search(r"\bskill\s*\d*\s*name|skill\s*name\s*\d*|\bskills?\b", k, re.I)
    ]
    seen_skills: set[str] = set()
    for sk in skill_name_keys:
        sname = _as_str(fields.get(sk))
        if not sname or sname.lower() in seen_skills:
            continue
        seen_skills.add(sname.lower())
        idx_m = re.search(r"\d+", sk)
        idx = idx_m.group(0) if idx_m else ""
        char_key = None
        advances = None
        for k2, v2 in fields.items():
            if not v2:
                continue
            if re.search(rf"\bskill\s*{idx}\s*char(?:acteristic)?\b|\bskill\s*char(?:acteristic)?\s*{idx}\b", k2, re.I):
                char_key = _as_str(v2)
            elif re.search(rf"\bskill\s*{idx}\s*adv(?:ances?)?\b|\bskill\s*adv(?:ances?)?\s*{idx}\b", k2, re.I):
                advances = _as_int(str(v2).strip())
        entry: Dict[str, Any] = {"name": sname}
        if char_key:
            entry["characteristic"] = char_key
        if advances is not None:
            entry["advances"] = advances
        skills.append(entry)
    if skills:
        result["warhammer_skills"] = skills

    # Talents
    talents: list[str] = []
    seen_tal: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\btalent\b", str(k), re.I):
            t = _as_str(v)
            if t and t.lower() not in seen_tal:
                seen_tal.add(t.lower())
                talents.append(t)
    if talents:
        result["warhammer_talents"] = talents

    # Armour points
    armour = _find_int([r"\barmour\s*points?\b", r"\bap\b", r"\barmor\s*points?\b"])
    if armour is not None:
        result["warhammer_armour_points"] = armour

    # Trappings / equipment
    trappings: list[str] = []
    seen_tr: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\btrapping\b|\bequipment\b|\bitem\b|\bgear\b|\bweapon\b", str(k), re.I):
            t = _as_str(v)
            if t and t.lower() not in seen_tr and len(t) > 1:
                seen_tr.add(t.lower())
                trappings.append(t)
    if trappings:
        result["warhammer_trappings"] = trappings

    # Ambitions
    ambitions: Dict[str, str] = {}
    short_amb = _find_first([r"\bshort\s*(?:term\s*)?ambition\b"])
    long_amb = _find_first([r"\blong\s*(?:term\s*)?ambition\b"])
    if short_amb:
        ambitions["short"] = short_amb
    if long_amb:
        ambitions["long"] = long_amb
    if ambitions:
        result["warhammer_ambitions"] = ambitions

    # Species / Race
    species = _find_first([r"\bspecies\b", r"\brace\b"])
    if species:
        result["warhammer_species"] = species

    # Movement
    movement = _find_int([r"\bmovement\b", r"\bmove\b", r"\bmov\b"])
    if movement is not None:
        result["warhammer_movement"] = movement

    # Money (Gold Crowns / Silver Shillings / Brass Pennies)
    money: Dict[str, int] = {}
    gc = _find_int([r"\bgold\s*crowns?\b", r"\bgc\b"])
    ss = _find_int([r"\bsilver\s*shillings?\b", r"\bss\b"])
    bp = _find_int([r"\bbrass\s*pennies\b", r"\bbp\b"])
    if gc is not None:
        money["gc"] = gc
    if ss is not None:
        money["ss"] = ss
    if bp is not None:
        money["bp"] = bp
    if money:
        result["warhammer_money"] = money

    # Spells and Prayers
    spells: list[str] = []
    seen_sp: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\bspell\b|\bprayer\b|\boratory\b", str(k), re.I):
            sp = _as_str(v)
            if sp and sp.lower() not in seen_sp and len(sp) > 1:
                seen_sp.add(sp.lower())
                spells.append(sp)
    if spells:
        result["warhammer_spells"] = spells

    return result


# ---------------------------------------------------------------------------
# Alien RPG (Year Zero Engine) field extraction
# ---------------------------------------------------------------------------

_ALIEN_RPG_ATTRIBUTES = ["Strength", "Agility", "Wits", "Empathy"]
_ALIEN_RPG_SKILLS = [
    "Heavy Machinery",
    "Stamina",
    "Close Combat",
    "Mobility",
    "Piloting",
    "Ranged Combat",
    "Observation",
    "Comtech",
    "Survival",
    "Manipulation",
    "Medical Aid",
    "Command",
]


def _is_alien_rpg_sheet(widget_values: Dict[str, str]) -> bool:
    """Detect YZE/Alien RPG sheets by distinctive widget keys."""
    alien_keys = {"wits", "empathy", "comtech", "agenda", "panic", "stress", "colonial"}
    matched = sum(
        1 for k in widget_values if any(re.search(rf"\b{re.escape(u)}\b", k, re.I) for u in alien_keys)
    )
    return matched >= 4


def _extract_alien_rpg_attributes_from_widgets(fields: Dict[str, str]) -> Dict[str, int]:
    """Extract Alien RPG 4 core attributes."""
    result: Dict[str, int] = {}
    for attr in _ALIEN_RPG_ATTRIBUTES:
        for k, v in fields.items():
            if re.search(rf"\b{re.escape(attr)}\b", k, re.I) and v:
                n = _as_int(str(v).strip())
                if isinstance(n, int):
                    result[attr.lower()] = n
                    break
    return result


def _extract_alien_rpg_skills_from_widgets(fields: Dict[str, str]) -> Dict[str, int]:
    """Extract Alien RPG 12 skills."""
    result: Dict[str, int] = {}
    for skill in _ALIEN_RPG_SKILLS:
        for k, v in fields.items():
            if re.search(rf"\b{re.escape(skill)}\b", k, re.I) and v:
                n = _as_int(str(v).strip())
                if isinstance(n, int) and 0 <= n <= 5:
                    result[skill.lower().replace(" ", "_")] = n
                    break
    return result


def _extract_alien_rpg_health_from_widgets(fields: Dict[str, str]) -> Dict[str, int]:
    """Extract Alien RPG health."""
    result: Dict[str, int] = {}
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\bhealth\s*max\b|\bmax\s*health\b", k, re.I):
            n = _as_int(str(v).strip())
            if isinstance(n, int):
                result["max"] = n
        elif re.search(r"\bhealth\s*current\b|\bcurrent\s*health\b|\bhealth\b", k, re.I):
            n = _as_int(str(v).strip())
            if isinstance(n, int):
                result.setdefault("current", n)
    return result


def _extract_alien_rpg_stress_from_widgets(fields: Dict[str, str]) -> Dict[str, int]:
    """Extract Alien RPG stress (panic mechanic)."""
    result: Dict[str, int] = {}
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\bstress\b", k, re.I):
            n = _as_int(str(v).strip())
            if isinstance(n, int):
                result["current"] = n
                break
    return result


def _extract_alien_rpg_fields(fields: Dict[str, str]) -> Dict[str, Any]:
    """Extract full Alien RPG character data.

    Returns alien_attributes, alien_skills, alien_health, alien_stress,
    alien_armor, alien_radiation, alien_encumbrance, alien_pride,
    alien_dark_secret, career, agenda, buddy, rival, appearance, experience,
    gear, critical_injuries.
    """
    if not fields:
        return {}

    def _find_first(patterns: list[str]) -> str | None:
        for pat in patterns:
            for k, v in fields.items():
                if not v:
                    continue
                if re.search(pat, str(k), re.I):
                    return _as_str(v)
        return None

    def _find_int(patterns: list[str]) -> int | None:
        val = _find_first(patterns)
        if val is None:
            return None
        m = re.search(r"-?\d+", str(val))
        return int(m.group(0)) if m else _as_int(val)

    result: Dict[str, Any] = {}

    attrs = _extract_alien_rpg_attributes_from_widgets(fields)
    if attrs:
        result["alien_attributes"] = attrs

    skills = _extract_alien_rpg_skills_from_widgets(fields)
    if skills:
        result["alien_skills"] = skills

    health = _extract_alien_rpg_health_from_widgets(fields)
    if health:
        result["alien_health"] = health

    stress = _extract_alien_rpg_stress_from_widgets(fields)
    if stress:
        result["alien_stress"] = stress

    # Armor rating
    armor = _find_int([r"\barmor\s*rating\b", r"\barmour\s*rating\b", r"\barmor\b"])
    if armor is not None:
        result["alien_armor"] = armor

    # Radiation (exposure level)
    radiation = _find_int([r"\bradiation\b", r"\brad\b"])
    if radiation is not None:
        result["alien_radiation"] = radiation

    # Encumbrance
    enc_cur = _find_int([r"\bencumbrance\s*current\b", r"\bcurrent\s*encumbrance\b"])
    enc_max = _find_int([r"\bencumbrance\s*max\b", r"\bmax\s*encumbrance\b", r"\bencumbrance\b"])
    if enc_cur is not None or enc_max is not None:
        enc: Dict[str, Any] = {}
        if enc_cur is not None:
            enc["current"] = enc_cur
        if enc_max is not None:
            enc["max"] = enc_max
        result["alien_encumbrance"] = enc

    # Character traits
    pride = _find_first([r"\bpride\b"])
    if pride:
        result["alien_pride"] = pride

    dark_secret = _find_first([r"\bdark\s*secret\b", r"\bdarksecret\b"])
    if dark_secret:
        result["alien_dark_secret"] = dark_secret

    # Core identity
    career = _find_first([r"\bcareer\b"])
    if career:
        result["career"] = career

    agenda = _find_first([r"\bagenda\b"])
    if agenda:
        result["agenda"] = agenda

    buddy = _find_first([r"\bbuddy\b"])
    if buddy:
        result["alien_buddy"] = buddy

    rival = _find_first([r"\brival\b"])
    if rival:
        result["alien_rival"] = rival

    appearance = _find_first([r"\bappearance\b"])
    if appearance:
        result["alien_appearance"] = appearance

    # Experience
    xp = _find_int([r"\bexperience\b", r"\bxp\b"])
    if xp is not None:
        result["alien_experience"] = xp

    # Gear
    gear: list[str] = []
    seen_gear: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\bgear\b|\bequipment\b|\bitem\b|\bweapon\b", str(k), re.I):
            g = _as_str(v)
            if g and g.lower() not in seen_gear and len(g) > 1:
                seen_gear.add(g.lower())
                gear.append(g)
    if gear:
        result["alien_gear"] = gear

    # Critical injuries
    crit_injuries: list[str] = []
    seen_ci: set[str] = set()
    for k, v in fields.items():
        if not v:
            continue
        if re.search(r"\bcritical\s*injur(?:y|ies)\b|\bcrit\s*injur\b", str(k), re.I):
            ci = _as_str(v)
            if ci and ci.lower() not in seen_ci:
                seen_ci.add(ci.lower())
                crit_injuries.append(ci)
    if crit_injuries:
        result["alien_critical_injuries"] = crit_injuries

    return result



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
    _name_boilerplate = re.compile(r"[\u00a9\u2122\u00ae]|copyright|\bstudios?\b|\bpublishing\b|\bgames?\s+inc\b", re.I)
    for line in lines[:6]:
        up = line.upper()
        if any(x in up for x in ("CLASS", "LEVEL", "PLAYER NAME", "CHARACTER NAME", "SPECIES", "BACKGROUND")):
            continue
        # Avoid lines that look like page headers/metadata (contain too many digits or slashes)
        if re.search(r"\d", line) and len(re.findall(r"[A-Za-z]", line)) < 3:
            continue
        # Skip copyright/trademark/legal boilerplate lines
        if _name_boilerplate.search(line):
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
            # Track cantrip/level headers — broaden match to handle variants like
            # "1st Level Spells", "6th-Level Spells", "CANTRIPS (AT WILL)", etc.
            if re.match(
                r"^(cantrips?(\s+\(at\s+will\))?|\d+(st|nd|rd|th)[\s\-]+level(\s+spells?)?)$",
                line,
                re.I,
            ) or re.match(
                r"^(cantrips?|\d+(st|nd|rd|th)[\s\-]+level)\s+spells?\s*$",
                line,
                re.I,
            ):
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
    system_override: str | None = None,
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

    # Patterns that identify class/level identifiers — these are NOT feature blobs.
    # Matches things like "Fighter 5", "Artificer 6 Paladin 7", "Wizard/Sorcerer 3/4".
    _class_level_pattern = re.compile(
        r"^[\w\s/\\]+\s+\d{1,2}(\s*/?\s*[\w\s]+\s+\d{1,2})*$"
    )

    for k, v in widget_values.items():
        if not v or not isinstance(v, str):
            continue
        kn = k.lower()
        stripped = v.strip()
        if "class" in kn and len(stripped) > 10:
            # Skip values that look like a plain "ClassName Level" or "Class1 N / Class2 M"
            # (the class & level field) — these are identifiers, not feature lists.
            if "\n" not in stripped and _class_level_pattern.match(stripped):
                continue
            class_blobs.append(v)
        elif any(x in kn for x in ("race", "species", "subrace", "racial")) and len(stripped) > 10:
            race_blobs.append(v)
        elif any(x in kn for x in ("feature", "trait")) and len(stripped) > 10:
            other_blobs.append(v)

    # Matches a trailing source reference like "PHB 114", "EGTW 184", "SOTDQ,26", "TCOE 80", "PHB"
    _src_ref_pat = re.compile(r"\s+([A-Z][A-Za-z0-9&]{1,7}(?:[,\s]\s*\d{1,4}(?:-\d+)?)?)\s*$")
    # Usage info lines: start with a digit + "/" (e.g. "1 / Long Rest Special")
    _usage_line_pat = re.compile(r"^\d+\s*/", re.I)

    def _is_feature_name(s: str) -> bool:
        """Heuristic: is this line a feature header rather than description text?"""
        if len(s) > 80 or s.endswith("."):
            return False
        if _src_ref_pat.search(s):
            return True
        # Short ALL-CAPS line with no sentence structure → sub-heading like "CHRONURGY MAGIC"
        if len(s) <= 50 and s == s.upper() and re.search(r"[A-Z]{2}", s):
            return True
        return False

    def _lines_from_blobs(blobs: list[str]) -> list[dict]:
        """Parse PDF text blobs into grouped feature objects {name, source?, description?}."""
        features: list[dict] = []
        seen_names: set[str] = set()
        current: dict | None = None

        def _flush() -> None:
            if current is None:
                return
            name = current.get("name", "").strip()
            if not name or len(name) < 2:
                return
            key = name.lower()
            if key not in seen_names:
                seen_names.add(key)
                features.append(dict(current))

        for blob in blobs:
            for raw in re.split(r"\r?\n", blob):
                line = re.sub(r"^[ \t\r\n•\-*_\u2022]+|[ \t\r\n•\-*_\u2022]+$", "", raw)
                if not line:
                    continue
                # Skip DDB section delimiter lines like "=== CLASS FEATURES ==="
                if re.match(r"^={2,}.*={2,}$", line):
                    continue
                # Lines starting with "|" are sub-items/usage — always attach as description
                if line.startswith("|"):
                    sub = line.lstrip("| \t")
                    if current is not None:
                        existing = current.get("description") or ""
                        current["description"] = (existing + "\n" + sub).strip() if existing else sub
                    continue

                if _is_feature_name(line):
                    _flush()
                    m = _src_ref_pat.search(line)
                    if m:
                        name_part = line[:m.start()].strip().rstrip(" •·")
                        src_part = m.group(1).strip() or None
                    else:
                        name_part = line
                        src_part = None
                    current = {"name": name_part, "source": src_part}
                elif _usage_line_pat.match(line):
                    if current is None:
                        current = {"name": line}
                    else:
                        existing = current.get("description") or ""
                        current["description"] = (existing + "\n" + line).strip() if existing else line
                else:
                    # Description / continuation text
                    if current is None:
                        current = {"name": line[:80].rstrip()}
                    else:
                        existing = current.get("description") or ""
                        snippet = line if len(line) <= 400 else line[:400].rstrip() + "…"
                        current["description"] = (existing + "\n" + snippet).strip() if existing else snippet

                if len(features) >= 150:
                    break
            _flush()
            current = None
            if len(features) >= 150:
                break

        return features

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
    # For STA sheets, fall back to the Department widget as the character's "class"
    if not final_class_name:
        _sta_dept = _as_str(widget_values.get("Department")) or _as_str(widget_values.get("department"))
        if _sta_dept:
            final_class_name = _sta_dept
    # For CoC sheets, fall back to the Occupation widget as the character's "class"
    if not final_class_name:
        _coc_occ = _as_str(widget_values.get("Occupation")) or _as_str(widget_values.get("occupation"))
        if _coc_occ:
            final_class_name = _coc_occ
    # For WFRP sheets, fall back to the Career widget as the character's "class"
    if not final_class_name:
        _wfrp_career = _as_str(widget_values.get("Career")) or _as_str(widget_values.get("career"))
        if _wfrp_career:
            final_class_name = _wfrp_career

    # Parse blobs using === section headers to categorize features.
    # DDB PDFs put all features in one "FeaturesTraits" blob with headers like
    # "=== WIZARD FEATURES ===" and "=== KENDER SPECIES TRAITS ===".
    _CLASS_HDR = re.compile(
        r"===\s*(?:\w+\s+)*(?:FEATURES?|SUBCLASS(?:\s+FEATURES?)?)\s*===", re.I
    )
    _RACIAL_HDR = re.compile(
        r"===\s*(?:\w+\s+)*(?:SPECIES|RACIAL|RACE)(?:\s+TRAITS?|FEATURES?)?\s*===", re.I
    )
    _FEATS_HDR = re.compile(r"===\s*FEATS?\s*===", re.I)

    def _parse_categorized(blobs: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
        """Route features to class/racial/other by parsing === section headers."""
        buckets: dict[str, list[dict]] = {"class": [], "racial": [], "other": []}
        seen: set[str] = set()
        cat = "other"
        current: dict | None = None

        def _flush(dest: str) -> None:
            if current is None:
                return
            name = current.get("name", "").strip()
            if not name or len(name) < 2:
                return
            key = name.lower()
            if key not in seen:
                seen.add(key)
                buckets[dest].append(dict(current))

        for blob in blobs:
            for raw in re.split(r"\r?\n", blob):
                line = re.sub(r"^[ \t\r\n•\-*_\u2022]+|[ \t\r\n•\-*_\u2022]+$", "", raw)
                if not line:
                    continue
                # Section header → change category
                if re.match(r"^={2,}.*={2,}$", line):
                    _flush(cat)
                    current = None
                    if _RACIAL_HDR.search(line):
                        cat = "racial"
                    elif _FEATS_HDR.search(line):
                        cat = "other"
                    elif _CLASS_HDR.search(line):
                        cat = "class"
                    else:
                        cat = "other"
                    continue
                # Lines starting with "|" are sub-items/usage — always attach as description
                if line.startswith("|"):
                    sub = line.lstrip("| \t")
                    if current is not None:
                        existing = current.get("description") or ""
                        current["description"] = (existing + "\n" + sub).strip() if existing else sub
                    continue
                # Feature name or description (same logic as _lines_from_blobs)
                if _is_feature_name(line):
                    _flush(cat)
                    m = _src_ref_pat.search(line)
                    if m:
                        name_part = line[:m.start()].strip().rstrip(" •·")
                        src_part = m.group(1).strip() or None
                    else:
                        name_part = line
                        src_part = None
                    current = {"name": name_part, "source": src_part}
                elif _usage_line_pat.match(line):
                    if current is not None:
                        existing = current.get("description") or ""
                        current["description"] = (existing + "\n" + line).strip() if existing else line
                    # else: orphaned usage line before any feature — skip
                else:
                    if current is not None:
                        existing = current.get("description") or ""
                        snippet = line if len(line) <= 400 else line[:400].rstrip() + "…"
                        current["description"] = (existing + "\n" + snippet).strip() if existing else snippet
                    # else: orphaned description text before any feature — skip
            # Do NOT reset cat or current between blobs.
            # Two-column PDFs produce separate blobs where the second column
            # continues the same section without repeating the === header.
        _flush(cat)
        return buckets["class"], buckets["racial"], buckets["other"]

    # If other_blobs have === headers, use the categorized parser; else fall back to flat.
    has_section_headers = any(re.search(r"={2,}.*={2,}", b) for b in other_blobs)
    if has_section_headers:
        cf_other, rf_other, of_other = _parse_categorized(other_blobs)
        class_features = _lines_from_blobs(class_blobs) + cf_other
        racial_features = _lines_from_blobs(race_blobs) + rf_other
        other_features = of_other
    else:
        class_features = _lines_from_blobs(class_blobs)
        racial_features = _lines_from_blobs(race_blobs)
        other_features = _lines_from_blobs(other_blobs)

    # Last resort: no blobs at all — use the flat feature title list from widget extraction.
    if not class_features and not racial_features and not other_features and features_from_widgets:
        other_features = [{"name": f} for f in features_from_widgets]

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
    focus_points_max = _first_widget_int([r"focus\s*points?\s*max", r"max\s*focus\s*points?", r"^focusmax$"])
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
    # Include STA attributes and CoC characteristics in the stats dict so the
    # respective signatures can be scored even when standard D&D ability-score
    # widgets are absent.
    try:
        sta_attrs_for_detection = _extract_sta_attributes_from_widgets(widget_values)
        coc_chars_for_detection = _extract_coc_characteristics_from_widgets(widget_values)
        detect_input = {
            "class_name": final_class_name,
            "multiclass": multiclass,
            "skills": skills_from_widgets,
            "stats": {**stats_from_widgets, **sta_attrs_for_detection, **coc_chars_for_detection},
            "raw_text": (combined_text or "")[:10000],
            "import": {"source": source, "ddb_url": ddb_url, "filename": filename},
            "widget_keys": list(widget_values.keys()),
        }
        sheet["detected_system"] = infer_ttrpg_system(detect_input)
        if system_override:
            sheet["detected_system"] = override_ttrpg_system(sheet["detected_system"], system_override)
    except Exception:
        pass

    # Convenience key: sheet["system"] mirrors the core fields of detected_system.
    try:
        ds = sheet.get("detected_system") or {}
        sheet["system"] = {
            "name": ds.get("system_name", "Unknown"),
            "publisher": ds.get("publisher", ""),
        }
    except Exception:
        pass

    # STA-specific field population (only when the sheet is identified as STA).
    if _is_sta_sheet(widget_values):
        sta_attributes = _extract_sta_attributes_from_widgets(widget_values)
        sta_disciplines = _extract_sta_disciplines_from_widgets(widget_values)
        sta_stress = _extract_sta_stress_from_widgets(widget_values)
        sta_values = _extract_sta_list_fields_from_widgets(widget_values, ["Value", "Values"], max_items=6)
        sta_focuses = _extract_sta_list_fields_from_widgets(widget_values, ["Focus", "Focuses"], max_items=6)
        sta_talents = _extract_sta_list_fields_from_widgets(widget_values, ["Talent", "Talents"], max_items=6)
        sta_traits = _extract_sta_list_fields_from_widgets(widget_values, ["Trait", "Traits"], max_items=4)
        sta_injuries = _extract_sta_list_fields_from_widgets(widget_values, ["Injury", "Injuries"], max_items=6)
        sta_rank = _as_str(widget_values.get("Rank"))
        sta_assignment = _as_str(widget_values.get("Assignment"))

        if sta_attributes:
            sheet["attributes"] = sta_attributes
        if sta_disciplines:
            sheet["disciplines"] = sta_disciplines
        if sta_stress:
            sheet["stress"] = sta_stress
        if sta_values:
            sheet["values"] = sta_values
        if sta_focuses:
            sheet["focuses"] = sta_focuses
        if sta_talents:
            sheet["talents"] = sta_talents
        if sta_traits:
            sheet["traits"] = sta_traits
        if sta_injuries:
            sheet["injuries"] = sta_injuries
        if sta_rank:
            sheet["rank"] = sta_rank
        if sta_assignment:
            sheet["assignment"] = sta_assignment
        sta_determination = _first_widget_int([r"\bdetermination\b"])
        if sta_determination is not None:
            sheet["determination"] = sta_determination
        sta_resistance = _first_widget_int([r"\bresistance\b"])
        if sta_resistance is not None:
            sheet["resistance"] = sta_resistance
        sta_reputation = _first_widget_int([r"\breputation\b"])
        if sta_reputation is not None:
            sheet["reputation"] = sta_reputation
        # Equipment for STA: gather weapon/item widget blobs
        sta_equipment: list[str] = []
        _sta_equip_seen: set[str] = set()
        for k, v in widget_values.items():
            if not v:
                continue
            kn = k.lower()
            if re.match(r"(weapon|item|gear|equipment)\s*\d*$", kn):
                val = _as_str(v)
                if val and val.lower() not in _sta_equip_seen:
                    _sta_equip_seen.add(val.lower())
                    sta_equipment.append(val)
        if sta_equipment:
            sheet["equipment"] = sta_equipment

    # Alien RPG-specific field population (only when the sheet is identified as Alien RPG).
    if _is_alien_rpg_sheet(widget_values):
        alien_attributes = _extract_alien_rpg_attributes_from_widgets(widget_values)
        alien_skills = _extract_alien_rpg_skills_from_widgets(widget_values)
        alien_health = _extract_alien_rpg_health_from_widgets(widget_values)
        alien_stress = _extract_alien_rpg_stress_from_widgets(widget_values)

        if alien_attributes:
            sheet["alien_attributes"] = alien_attributes
        if alien_skills:
            sheet["alien_skills"] = alien_skills
        if alien_health:
            sheet["alien_health"] = alien_health
        if alien_stress:
            sheet["alien_stress"] = alien_stress

        # Career maps to the sheet career field (analogous to class in D&D).
        alien_career = _as_str(widget_values.get("Career") or widget_values.get("Job"))
        if alien_career:
            sheet["alien_career"] = alien_career

        # Agenda is a unique Alien RPG field: the character's secret personal objective.
        alien_agenda = _as_str(widget_values.get("Agenda"))
        if alien_agenda:
            sheet["agenda"] = alien_agenda

        # Buddy / Rival — optional relational fields on the Alien RPG sheet.
        alien_buddy = _as_str(widget_values.get("Buddy"))
        if alien_buddy:
            sheet["alien_buddy"] = alien_buddy
        alien_rival = _as_str(widget_values.get("Rival"))
        if alien_rival:
            sheet["alien_rival"] = alien_rival

        # Appearance / personal description.
        alien_appearance = _as_str(widget_values.get("Appearance"))
        if alien_appearance:
            sheet["alien_appearance"] = alien_appearance

        # Experience points.
        alien_xp = _extract_pdf_widget_int(widget_values, ["Experience", "XP"], min_value=0, max_value=999)
        if isinstance(alien_xp, int):
            sheet["alien_experience"] = alien_xp

        # Gear / equipment (numbered list, e.g. "Gear 1" … "Gear 10").
        # Reuses _extract_sta_list_fields_from_widgets which is system-agnostic
        # despite its name — it extracts any numbered widget prefix list.
        alien_gear: list[str] = _extract_sta_list_fields_from_widgets(
            widget_values, ["Gear", "Equipment", "Item", "Weapon"], max_items=10
        )
        if alien_gear:
            sheet["equipment"] = alien_gear

        # Critical injuries (numbered list).
        alien_injuries: list[str] = _extract_sta_list_fields_from_widgets(
            widget_values, ["Critical Injury", "Injury", "Critical"], max_items=8
        )
        if alien_injuries:
            sheet["injuries"] = alien_injuries

    # Merge Pathfinder-specific fields extracted from widget keys.
    system_name = (sheet.get("system") or {}).get("name", "Unknown")
    if system_name == "Pathfinder 2e":
        pf_fields = _extract_pf2e_fields_from_widgets(widget_values)
        for k, v in pf_fields.items():
            sheet[k] = v
    elif system_name == "Pathfinder 1e":
        pf_fields = _extract_pf1e_fields_from_widgets(widget_values)
        for k, v in pf_fields.items():
            sheet[k] = v
    elif system_name == "D&D 5e":
        dnd5e_fields = _extract_dnd5e_fields_from_widgets(widget_values)
        for k, v in dnd5e_fields.items():
            sheet[k] = v
        # Convert D&D 5e skills from dict → list so both LoggedInDashboard and
        # CharacterSheetModal can handle them uniformly.
        # Dict shape: {"Acrobatics": {"modifier": 3, "proficient": True}, ...}
        # List shape: [{"name": "Acrobatics", "modifier": 3, "proficient": True}, ...]
        if isinstance(sheet.get("skills"), dict):
            sheet["skills"] = [
                {"name": skill_name, **skill_data}
                for skill_name, skill_data in sheet["skills"].items()
            ]
        elif isinstance(sheet.get("skills"), list):
            # The D&D 5e–specific extractor did not supply a skills dict (no
            # matching widget keys), so the generic _extract_skills_from_pdf_widgets
            # result is still in place.  That generic extractor includes many
            # non-skill items (saving-throw widgets, proficiency bonus, HD total,
            # etc.) that share numeric values with real skills.  Filter the list
            # down to the 18 canonical D&D 5e skills only.
            _canonical_lower = {s.lower() for s in _DND5E_CANONICAL_SKILLS}
            sheet["skills"] = [
                s for s in sheet["skills"]
                if isinstance(s, dict) and s.get("name", "").lower() in _canonical_lower
            ]
    elif system_name == "Call of Cthulhu":
        coc_fields = _extract_coc_fields_from_widgets(widget_values)
        for k, v in coc_fields.items():
            sheet[k] = v
    elif system_name == "Starfinder":
        sf_fields = _extract_starfinder_fields_from_widgets(widget_values)
        for k, v in sf_fields.items():
            sheet[k] = v
    elif system_name == "Shadow of the Demon Lord":
        sotdl_fields = _extract_sotdl_fields_from_widgets(widget_values)
        for k, v in sotdl_fields.items():
            sheet[k] = v
    elif system_name == "Warhammer Fantasy Roleplay":
        wfrp_fields = _extract_wfrp_fields_from_widgets(widget_values)
        for k, v in wfrp_fields.items():
            sheet[k] = v
    elif system_name == "Alien RPG":
        alien_fields = _extract_alien_rpg_fields(widget_values)
        for k, v in alien_fields.items():
            sheet[k] = v
    elif system_name == "Shadowrun":
        sr_fields = _extract_shadowrun_fields_from_widgets(widget_values)
        for k, v in sr_fields.items():
            sheet[k] = v

    # Merge Call of Cthulhu-specific fields when the sheet is identified as CoC.
    if _is_coc_sheet(widget_values) or system_name == "Call of Cthulhu":
        coc_fields = _extract_coc_fields_from_widgets(widget_values)
        for k, v in coc_fields.items():
            sheet[k] = v

    # Merge WFRP-specific fields when the sheet is identified as Warhammer Fantasy Roleplay.
    # Both conditions are intentional:
    #   - system_name check: covers manual system_override to WFRP even if widget keys differ
    #   - _is_wfrp_sheet check: catches WFRP sheets where system detection scored it as Unknown
    # _extract_wfrp_fields_from_widgets is only called once regardless of which branch fires.
    if system_name == "Warhammer Fantasy Roleplay" or _is_wfrp_sheet(widget_values):
        wfrp_fields = _extract_wfrp_fields_from_widgets(widget_values)
        for k, v in wfrp_fields.items():
            sheet[k] = v

    # Merge Shadowrun-specific fields (only when sheet is identified as Shadowrun).
    if _is_shadowrun_sheet(widget_values):
        sr_fields = _extract_shadowrun_fields_from_widgets(widget_values)
        for k, v in sr_fields.items():
            sheet[k] = v
        # Ensure sheet.system reflects Shadowrun even if detection confidence was low.
        if sheet.get("system", {}).get("name") in (None, "Unknown"):
            sheet["system"] = {"name": "Shadowrun", "publisher": "Catalyst Game Labs"}

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
    sheet_patch: dict[str, Any] | None = None


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


@router.get("/import/systems", summary="List supported TTRPG systems for the PDF import game-system selector")
def list_import_systems(current_user=Depends(get_current_user)):
    """Return all TTRPG systems that the importer can recognise and that users
    can select from the game-system dropdown.  Listing system names in a UI
    selector is purely referential and does not reproduce any copyrighted
    rules content.
    """
    return {"systems": list_ttrpg_systems()}


@router.post("/import/pdf", status_code=201, summary="Import a character from an uploaded PDF (best-effort)")
async def import_character_pdf(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    level: int | None = Form(default=None),
    class_name: str | None = Form(default=None),
    game_system: str | None = Form(default=None),
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
        system_override=game_system or None,
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
    game_system: str | None = Form(default=None),
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
        system_override=game_system or None,
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
