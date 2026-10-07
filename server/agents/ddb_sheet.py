"""Read a D&D Beyond character sheet export (the 2024-style PDF) from its form fields.

The export is a fillable form with stable field names (``IntProf``, ``Passive1``,
``spellName0``, ``Wpn Name 2`` ...), so every value can be read exactly instead of
guessed from page text.  :func:`extract` returns sheet keys that replace whatever
the generic extractors found; it returns ``{}`` for any other PDF.
"""
from __future__ import annotations

import re
from typing import Any

_ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
_SAVE_FIELDS = {"str": "Strength", "dex": "Dexterity", "con": "Constitution",
                "int": "Intelligence", "wis": "Wisdom", "cha": "Charisma"}
_SKILLS = (
    "Acrobatics", "Animal Handling", "Arcana", "Athletics", "Deception", "History", "Insight",
    "Intimidation", "Investigation", "Medicine", "Nature", "Perception", "Performance",
    "Persuasion", "Religion", "Sleight of Hand", "Stealth", "Survival",
)
# The export abbreviates "Animal Handling" to "Animal" in its field names.
_SKILL_FIELD = {"Animal Handling": "animal"}
_PASSIVES = ("perception", "insight", "investigation")


def _norm(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def is_ddb_sheet(widgets: dict[str, Any]) -> bool:
    keys = {_norm(k) for k in widgets}
    return {"proficiencieslang", "featurestraits1", "passive1"} <= keys


def _int(value: Any) -> int | None:
    match = re.search(r"-?\d+", str(value or "").replace("−", "-"))
    return int(match.group()) if match and not str(value).strip().startswith("--") else None


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text in {"--", "Off"} else text


def _sections(blob: str) -> dict[str, list[str]]:
    """Split an "=== HEADER ===" list into {header: items}."""
    result: dict[str, list[str]] = {}
    current = ""
    for line in re.split(r"\r?\n", blob):
        line = line.strip()
        header = re.match(r"^=+\s*(.*?)\s*=+$", line)
        if header:
            current = header.group(1).upper()
            result.setdefault(current, [])
        elif line and current:
            result[current].extend(p.strip() for p in line.split(",") if p.strip())
    return result


_ENTRY = re.compile(r"^\*\s*(.+?)(?:\s*[•·]\s*(.*))?$")


def _features(widgets: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], str]:
    """Class, species and feat entries from the Features & Traits columns, in reading order."""
    blobs = [str(v) for k, v in widgets.items() if re.match(r"featurestraits\d+$", _norm(k)) and v]
    out: dict[str, list[dict[str, Any]]] = {"class": [], "racial": [], "feat": []}
    category = "class"
    current: dict[str, Any] | None = None
    subclass = ""

    def finish() -> None:
        nonlocal current
        if current:
            current["description"] = "\n".join(current.pop("_lines")).strip()
            if not current["description"]:
                current.pop("description")
            if not current.get("source"):
                current.pop("source", None)
            out[current.pop("_cat")].append(current)
        current = None

    for blob in blobs:
        for raw in re.split(r"\r?\n", blob):
            line = raw.strip()
            if not line:
                if current:
                    current["_lines"].append("")
                continue
            header = re.match(r"^=+\s*(.*?)\s*=+$", line)
            if header:
                finish()
                title = header.group(1).upper()
                category = "feat" if "FEAT" in title and "FEATURE" not in title else (
                    "racial" if re.search(r"SPECIES|RACE|RACIAL|HERITAGE", title) else "class")
                continue
            entry = _ENTRY.match(line)
            if entry:
                finish()
                current = {"name": entry.group(1).strip(), "source": (entry.group(2) or "").strip(),
                           "_cat": category, "_lines": []}
                continue
            if line.startswith("|") and current:
                detail = line.lstrip("| ").strip()
                if current["name"].lower() == "wizard subclass" or current["name"].lower().endswith(" subclass"):
                    subclass = detail
                current.setdefault("usage", [])
                current["usage"].append(detail)
                continue
            if current:
                current["_lines"].append(line)
    finish()
    return out, subclass


def _spells(widgets: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: dict[int, dict[str, Any]] = {}
    level: int | None = None
    slots: dict[str, int] = {}
    order: list[int] = []
    for key, value in widgets.items():
        norm = _norm(key)
        header = re.match(r"spellheader(\d+)$", norm)
        if header and value:
            text = str(value)
            level = 0 if re.search(r"cantrip", text, re.I) else (_int(text) or level)
            continue
        slot = re.match(r"spellslotheader(\d+)$", norm)
        if slot and value and level:
            count = re.match(r"\s*(\d+)\s*slots?", str(value), re.I)
            if count:
                slots[str(level)] = int(count.group(1))
            continue
        field = re.match(r"spell(name|source|savehit|castingtime|range|components|duration|page|notes|prepared)(\d+)$", norm)
        if not field:
            continue
        index = int(field.group(2))
        row = rows.setdefault(index, {"level": level})
        if field.group(1) == "name":
            order.append(index)
            row["level"] = level
        row[field.group(1)] = _text(value)
    spellbook: list[dict[str, Any]] = []
    for index in sorted(set(order)):
        row = rows[index]
        raw_name = row.get("name", "")
        name = re.sub(r"\s*\[[A-Za-z]\]\s*$", "", raw_name).strip()
        if not name:
            continue
        duration = row.get("duration", "")
        spellbook.append({
            "name": name, "level": row.get("level"), "source": row.get("source") or None,
            "save_hit": row.get("savehit") or None, "time": row.get("castingtime") or None,
            "range": row.get("range") or None, "components": row.get("components") or None,
            "duration": duration or None, "page": row.get("page") or None, "notes": row.get("notes") or None,
            "prepared": bool(row.get("prepared")), "ritual": raw_name != name and "[R]" in raw_name,
            "concentration": duration.lower().startswith("concentration"),
        })
    return spellbook, slots


def _by_norm(widgets: dict[str, Any]) -> dict[str, Any]:
    return {_norm(k): v for k, v in widgets.items()}


def extract(widgets: dict[str, Any]) -> dict[str, Any]:
    """Sheet keys read exactly from a D&D Beyond export, or ``{}`` for other PDFs."""
    if not widgets or not is_ddb_sheet(widgets):
        return {}
    w = _by_norm(widgets)
    out: dict[str, Any] = {}

    saves = {}
    for key, label in _SAVE_FIELDS.items():
        saves[key] = {"total": _int(w.get(_norm(f"ST {label}"))), "proficient": bool(_text(w.get(f"{key}prof")))}
    out["saves"] = saves

    skills = []
    for name in _SKILLS:
        field = _SKILL_FIELD.get(name) or _norm(name)
        mark = _text(w.get(f"{field}prof")).upper()
        skills.append({"name": name, "modifier": _int(w.get(field)), "proficient": mark in {"P", "E"}, "expertise": mark == "E"})
    out["skills"] = skills

    out["passives"] = {label: _int(w.get(f"passive{i}")) for i, label in enumerate(_PASSIVES, 1)}
    if _int(w.get("init")) is not None:
        out["initiative"] = _int(w.get("init"))
    dice = _text(w.get("total"))
    if re.fullmatch(r"\d+d\d+", dice):
        out["hit_dice"] = dice

    prof = _sections(str(w.get("proficiencieslang") or ""))
    out["languages"] = prof.get("LANGUAGES", [])
    out["weapon_proficiencies"] = prof.get("WEAPONS", [])
    out["armor_proficiencies"] = prof.get("ARMOR", [])
    out["tool_proficiencies"] = prof.get("TOOLS", [])

    out["spellcasting_ability"] = _text(w.get("spellcastingability0")) or None
    out["spellcasting_class"] = _text(w.get("spellcastingclass0")) or None
    if _int(w.get("spellsavedc0")) is not None:
        out["spell_save_dc"] = _int(w.get("spellsavedc0"))
    if _int(w.get("spellatkbonus0")) is not None:
        out["spell_attack_bonus"] = _int(w.get("spellatkbonus0"))
    spellbook, slots = _spells(widgets)
    if spellbook:
        out["spellbook"] = spellbook
        names: list[str] = []
        for entry in spellbook:
            if entry["name"] not in names:
                names.append(entry["name"])
        out["spells"] = names
    if slots:
        out["spell_slots"] = slots

    attacks = []
    for i in range(1, 13):
        name = _text(w.get("wpnname" if i == 1 else f"wpnname{i}"))
        if not name:
            continue
        bonus, damage = _text(w.get(f"wpn{i}atkbonus")), _text(w.get(f"wpn{i}damage"))
        notes = _text(w.get(f"wpnnotes{i}"))
        attacks.append({"name": name, "attack_bonus": bonus or None, "damage": damage or None, "notes": notes or None,
                        "description": ", ".join(p for p in (f"{bonus} to hit" if bonus else "", damage, notes) if p)})
    if attacks:
        out["attacks"] = attacks
    if _text(w.get("actions1")):
        out["actions_text"] = _text(w.get("actions1"))

    features, subclass = _features(widgets)
    out["classFeatures"] = features["class"]
    out["racialFeatures"] = features["racial"]
    out["otherFeatures"] = features["feat"]
    out["features"] = [f["name"] for f in (*features["class"], *features["racial"], *features["feat"])]
    if subclass:
        out["subclass"] = subclass

    look = {label: _text(w.get(label.lower())) for label in ("Size", "Height", "Weight", "Skin", "Eyes", "Hair", "Age", "Gender")}
    look = {k.lower(): v for k, v in look.items() if v}
    if look:
        out["appearance_details"] = look
        out["appearance"] = "; ".join(f"{k}: {v}" for k, v in look.items())
    if _text(w.get("experiencepoints")):
        out["experience"] = _text(w.get("experiencepoints"))
    return out
