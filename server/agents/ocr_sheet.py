"""Read a scanned character sheet from its OCR text.

OCR of a form gives text in no useful order (columns merge, large numerals and
stylised names are missed), and sheets differ too much for fixed patterns.  The
local model proposes the fields; every value it returns is then checked against the
OCR text and dropped unless it actually appears there, so a hallucinated number or
name never reaches a character.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from ..steward_llm import chat_complete

TASK_SCOPE = "taverntails_import"
MAX_TEXT = 14000

_SKILLS = (
    "Acrobatics", "Animal Handling", "Arcana", "Athletics", "Deception", "History", "Insight",
    "Intimidation", "Investigation", "Medicine", "Nature", "Perception", "Performance",
    "Persuasion", "Religion", "Sleight of Hand", "Stealth", "Survival",
)
_ABILITIES = ("str", "dex", "con", "int", "wis", "cha")

_TEMPLATE = (
    '{"name":"","class_name":"","level":0,"race":"","background":"","alignment":"",'
    '"stats":{"str":0,"dex":0,"con":0,"int":0,"wis":0,"cha":0},"hp_max":0,"ac":0,"initiative":0,'
    '"proficiency_bonus":0,"speed":0,"passives":{"perception":0,"insight":0,"investigation":0},'
    '"hit_dice":"","languages":[],"weapon_proficiencies":[],"tool_proficiencies":[],'
    '"skills":[{"name":"","modifier":0}],"saves":{"str":0,"dex":0,"con":0,"int":0,"wis":0,"cha":0},'
    '"spellcasting_ability":"","spell_save_dc":0,"spell_attack_bonus":0,'
    '"spells":[{"name":"","level":0}],"attacks":[{"name":"","attack_bonus":"","damage":""}],"features":[]}'
)

_SYSTEM = (
    "You read the OCR text of a tabletop RPG character sheet and copy its fields into JSON. "
    "The text is noisy and out of order: labels and their values may be far apart, and some values are missing. "
    "Copy only what the text clearly shows. Leave a field out, or use null, when it is not clearly there. "
    "Never guess, infer, or use outside knowledge. Return only a JSON object shaped like this example "
    "(the example values are placeholders):\n" + _TEMPLATE
)


def layout_text(tsv: str, *, min_conf: float = 25.0, char_px: float = 14.0) -> str:
    """Rebuild a page's text from tesseract TSV, keeping each word where it sits on the page.

    Words are grouped into lines by vertical position and spaced by horizontal position, so
    a value stays on the same line as its label and columns stay apart (the way
    ``pdftotext -layout`` reads a native PDF).
    """
    words: list[tuple[float, float, float, str]] = []  # left, centre-y, height, text
    for row in tsv.splitlines():
        cells = row.rstrip("\r").split("\t")
        if len(cells) < 12 or cells[0] != "5":
            continue
        try:
            left, top, height, conf = float(cells[6]), float(cells[7]), float(cells[9]), float(cells[10])
        except ValueError:
            continue
        word = cells[11].strip()
        if word and conf >= min_conf:
            words.append((left, top + height / 2, height, word))
    if not words:
        return ""
    heights = sorted(w[2] for w in words)
    tolerance = max(4.0, heights[len(heights) // 2] * 0.6)
    lines: list[list[tuple[float, float, float, str]]] = []
    for entry in sorted(words, key=lambda w: w[1]):
        if lines and abs(sum(w[1] for w in lines[-1]) / len(lines[-1]) - entry[1]) <= tolerance:
            lines[-1].append(entry)
        else:
            lines.append([entry])
    rendered = []
    for line in lines:
        out = ""
        for left, _, _, word in sorted(line):
            column = int(left / char_px)
            out += (" " * max(1, column - len(out)) if out else " " * column) + word
        rendered.append(out.rstrip())
    return "\n".join(rendered)


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w+/'-]+", " ", text.casefold())).strip()


class _Evidence:
    """What the OCR text actually contains."""

    def __init__(self, text: str):
        self.lines = text.splitlines()  # blank lines separate pages
        self.folded = f" {_fold(text)} "
        self.numbers = {int(m) for m in re.findall(r"(?<![\d.])\d{1,3}(?![\d])", text)}

    def near(self, value: Any, label: str, radius: int) -> bool:
        """``value`` appears within ``radius`` lines of a line that matches ``label``."""
        if not isinstance(value, int) or isinstance(value, bool):
            return False
        number = re.compile(rf"(?<![\d.]){abs(value)}(?!\d)")
        pattern = re.compile(label, re.I)
        for index, line in enumerate(self.lines):
            if pattern.search(line):
                window = self.lines[max(0, index - radius): index + radius + 1]
                if any(number.search(candidate) for candidate in window):
                    return True
        return False

    def leading(self, value: Any, label: str, radius: int) -> bool:
        """``value`` opens a line (a boxed score, not a number inside a row) within ``radius`` lines of ``label``."""
        if not isinstance(value, int) or isinstance(value, bool):
            return False
        number = re.compile(rf"^\W{{0,3}}[+-]?{abs(value)}(?!\d)")
        pattern = re.compile(label, re.I)
        for index, line in enumerate(self.lines):
            if pattern.search(line):
                if any(number.match(candidate.strip()) for candidate in self.lines[max(0, index - radius): index + radius + 1]):
                    return True
        return False

    @staticmethod
    def _heading(line: str) -> tuple[int, int | None] | None:
        """(spell level, slot count) when ``line`` is a spell-table heading such as "1st LEVEL  4 Slots OOOO"."""
        text = line.strip()
        if re.match(r"^\W*(?:cantrips?|\(at will\))\W*$", text, re.I):
            return 0, None
        match = re.match(r"^\W*(\d)?\s*(st|nd|rd|th)\s+level\b(.*)$", text, re.I)
        if not match:
            return None
        # OCR sometimes drops the numeral of "2nd"; the suffix still says which it is.
        level = int(match.group(1)) if match.group(1) else {"st": 1, "nd": 2, "rd": 3}.get(match.group(2).lower())
        slots = re.search(r"(\d+)\s*slots?", match.group(3), re.I)
        return (level, int(slots.group(1)) if slots else None) if level is not None else None

    def spell_level(self, name: str) -> int | None:
        """The level of the table heading above a line naming ``name`` on the same page.

        The name may also appear earlier (an attacks table); the first occurrence under a heading wins.
        """
        needle = _fold(name)
        for index, line in enumerate(self.lines):
            if not needle or needle not in _fold(line):
                continue
            if re.search(r"\d+d\d+|bludgeoning|piercing|slashing", line, re.I):
                continue  # a weapon-attack row, not a spell-table row
            for earlier in reversed(self.lines[:index]):
                if not earlier.strip():
                    break  # page boundary
                heading = self._heading(earlier)
                if heading:
                    return heading[0]
        return None

    def spell_slots(self) -> dict[str, int]:
        slots: dict[str, int] = {}
        for line in self.lines:
            heading = self._heading(line)
            if heading and heading[0] and heading[1]:
                slots[str(heading[0])] = heading[1]
        return slots

    def has_text(self, value: Any) -> bool:
        needle = _fold(str(value or ""))
        return bool(needle) and f" {needle} " in self.folded

    def has_int(self, value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and abs(value) in self.numbers

    def has_token(self, value: Any) -> bool:
        """A bonus such as "+7" or a damage string such as "2d10 Fire"."""
        needle = _fold(str(value or "").replace("−", "-"))
        return bool(needle) and needle in self.folded


# Where each number sits on a sheet: a value is only accepted close to its own label,
# because a number that is merely somewhere on the page is often a different field's.
_LABELS: dict[str, tuple[str, int]] = {
    "level": (r"class\s*(?:&|and)?\s*level|\blevel\b", 2),
    "hp_max": (r"max\s*hp|hit\s*points|\bhp\b", 2),
    "ac": (r"armou?r|\bac\b", 2),
    "initiative": (r"initiative", 2),
    "proficiency_bonus": (r"proficiency\s*bonus|\bprof", 1),
    "speed": (r"speed", 3),
    "spell_save_dc": (r"save\s*dc|spell\s*save", 2),
    "spell_attack_bonus": (r"attack\s*bonus|spell\s*attack|\batk\b", 2),
}
# Full names only: skill rows print each skill's ability as "WIS", "INT", ... and must not match.
_ABILITY_LABEL = {"str": r"strength", "dex": r"dexterity", "con": r"constitution",
                  "int": r"intelligence", "wis": r"wisdom", "cha": r"charisma"}


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    match = re.fullmatch(r"\s*([+-]?\d+)\s*", str(value or "").replace("−", "-"))
    return int(match.group(1)) if match else None


def _verified_int(raw: Any, ev: _Evidence, lo: int, hi: int, field: str = "") -> int | None:
    value = _int(raw)
    if value is None or not lo <= value <= hi or not ev.has_int(value):
        return None
    if field in _LABELS and not ev.near(value, *_LABELS[field]):
        return None
    return value


def _strings(raw: Any, ev: _Evidence, limit: int = 40) -> list[str]:
    items = raw if isinstance(raw, list) else []
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and ev.has_text(text) and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    return value if isinstance(value, list) else []


def _parse_json(reply: str | None) -> dict[str, Any]:
    if not reply:
        return {}
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(reply[start:end + 1])
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def verify(data: dict[str, Any], text: str) -> tuple[dict[str, Any], list[str]]:
    """Keep the fields whose values appear in ``text``; return them and the names that were dropped."""
    ev = _Evidence(text)
    out: dict[str, Any] = {}
    dropped: list[str] = []

    def keep(key: str, value: Any) -> None:
        if value in (None, "", [], {}):
            if data.get(key) not in (None, "", [], {}):
                dropped.append(key)
            return
        out[key] = value

    for key in ("name", "class_name", "race", "background", "alignment", "hit_dice"):
        raw = str(data.get(key) or "").strip()
        keep(key, raw if raw and ev.has_text(raw) else None)
        if raw and key not in out and key not in dropped:
            dropped.append(key)
    keep("level", _verified_int(data.get("level"), ev, 1, 30, "level"))
    keep("hp_max", _verified_int(data.get("hp_max"), ev, 1, 999, "hp_max"))
    keep("ac", _verified_int(data.get("ac"), ev, 1, 40, "ac"))
    bonus_read = _verified_int(data.get("proficiency_bonus"), ev, 1, 9, "proficiency_bonus")
    level_read = out.get("level")
    # The bonus follows from the level (2 at level 1, +1 every four levels), so a different number is a misread.
    keep("proficiency_bonus", bonus_read if bonus_read is not None and (level_read is None or bonus_read == 2 + (level_read - 1) // 4) else None)
    keep("speed", _verified_int(data.get("speed"), ev, 0, 400, "speed"))
    keep("spell_save_dc", _verified_int(data.get("spell_save_dc"), ev, 1, 40, "spell_save_dc"))
    initiative = _int(data.get("initiative"))
    keep("initiative", initiative if initiative is not None and -10 <= initiative <= 20 and ev.near(initiative, *_LABELS["initiative"]) else None)
    bonus = _int(data.get("spell_attack_bonus"))
    keep("spell_attack_bonus", bonus if bonus is not None and -5 <= bonus <= 30 and ev.near(bonus, *_LABELS["spell_attack_bonus"]) else None)
    ability = str(data.get("spellcasting_ability") or "").strip()
    keep("spellcasting_ability", ability if ability and ev.has_text(ability) else None)

    stats_raw = _dict(data, "stats")
    stats = {a: v for a in _ABILITIES if (v := _verified_int(stats_raw.get(a), ev, 1, 30)) is not None and ev.leading(v, _ABILITY_LABEL[a], 4)}
    keep("stats", stats)
    if len(stats) < 6 and stats_raw:
        dropped.extend(f"stats.{a}" for a in _ABILITIES if a not in stats and stats_raw.get(a) is not None)

    passives_raw = _dict(data, "passives")
    passives = {k: v for k in ("perception", "insight", "investigation")
                if (v := _verified_int(passives_raw.get(k), ev, 1, 40)) is not None and ev.near(v, rf"passive\s*{k}", 0)}
    keep("passives", passives)

    saves_raw = _dict(data, "saves")
    saves = {}
    for a in _ABILITIES:
        value = _int(saves_raw.get(a))
        if value is not None and -10 <= value <= 20 and ev.near(value, _ABILITY_LABEL[a], 0):
            saves[a] = value
    keep("saves", saves)

    for key in ("languages", "weapon_proficiencies", "tool_proficiencies", "features"):
        keep(key, _strings(data.get(key), ev))

    skills = []
    for item in _list(data, "skills"):
        if not isinstance(item, dict):
            continue
        name = next((s for s in _SKILLS if s.casefold() == str(item.get("name") or "").strip().casefold()), "")
        value = _int(item.get("modifier"))
        if name and value is not None and -10 <= value <= 20 and ev.near(value, re.escape(name), 0):
            skills.append({"name": name, "modifier": value})
    keep("skills", skills)

    spells: list[dict[str, Any]] = []
    for item in _list(data, "spells"):
        if not isinstance(item, dict):
            continue
        name = re.sub(r"\s*\[[A-Za-z]\]\s*$", "", str(item.get("name") or "")).strip()  # "[R]" marks a ritual
        if not name or not ev.has_text(name):
            continue
        level = ev.spell_level(name)  # from the table heading, never the model's guess
        if level is None:
            continue  # not under a spell-table heading: an attack, a feature, or a misread
        if not any(s["name"] == name for s in spells):
            spells.append({"name": name, "level": level})
    keep("spells", spells[:120])
    keep("spell_slots", ev.spell_slots() if spells else {})

    attacks = []
    for item in _list(data, "attacks"):
        if not isinstance(item, dict) or not ev.has_text(item.get("name")):
            continue
        bonus_text = str(item.get("attack_bonus") or "").strip()
        damage = str(item.get("damage") or "").strip()
        attacks.append({
            "name": str(item["name"]).strip(),
            "attack_bonus": bonus_text if bonus_text and ev.has_token(bonus_text) else None,
            "damage": damage if damage and ev.has_token(damage) else None,
        })
    keep("attacks", attacks[:20])
    return out, sorted(set(dropped))


def _chunks(text: str, limit: int | None = None) -> list[str]:
    """Whole pages (or paragraphs) grouped so that each chunk fits the model's context."""
    limit = limit or MAX_TEXT
    chunks: list[str] = []
    current = ""
    for part in re.split(r"\n\s*\n", text):
        if current and len(current) + len(part) + 2 > limit:
            chunks.append(current)
            current = ""
        current += ("\n\n" if current else "") + part
    if current:
        chunks.append(current)
    return chunks


def _merge(into: dict[str, Any], more: dict[str, Any]) -> None:
    for key, value in more.items():
        if key not in into or into[key] in (None, "", [], {}):
            into[key] = value
        elif isinstance(value, list) and isinstance(into[key], list):
            into[key] = into[key] + [v for v in value if v not in into[key]]
        elif isinstance(value, dict) and isinstance(into[key], dict):
            into[key] = {**value, **into[key]}


def extract(text: str, *, llm: Callable[..., str | None] | None = None) -> tuple[dict[str, Any], list[str]]:
    """Verified fields read from OCR ``text`` by the local model, and the field names rejected."""
    if not text or not text.strip():
        return {}, []
    ask = llm or chat_complete
    merged: dict[str, Any] = {}
    for chunk in _chunks(text):
        messages = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": f"OCR text:\n\n{chunk}"}]
        for _attempt in range(2):  # a local model occasionally returns nothing or truncated JSON
            data = _parse_json(ask(messages, task_scope=TASK_SCOPE, max_tokens=2500, temperature=0.0, timeout=300.0))
            if data:
                _merge(merged, data)
                break
    return verify(merged, text)


def apply(sheet: dict[str, Any], fields: dict[str, Any]) -> None:
    """Merge verified OCR fields into ``sheet``; the OCR heuristics' guesses are replaced."""
    for key in ("race", "background", "alignment", "hit_dice", "proficiency_bonus", "ac", "initiative",
                "spell_save_dc", "spell_attack_bonus", "spellcasting_ability", "passives", "languages",
                "weapon_proficiencies", "tool_proficiencies", "features", "stats"):
        if key in fields:
            sheet[key] = fields[key]
    if "species" not in sheet and "race" in fields:
        sheet["species"] = fields["race"]
    if "hp_max" in fields:
        sheet["hp"] = {"current": fields["hp_max"], "max": fields["hp_max"]}
        sheet["hp_max"] = sheet["hp_current"] = fields["hp_max"]
    if "speed" in fields:
        sheet["speed"] = {"walk": fields["speed"], "fly": None, "swim": None, "climb": None, "burrow": None}
    if "saves" in fields:
        sheet["saves"] = {a: {"total": v} for a, v in fields["saves"].items()}
    if "skills" in fields:
        sheet["skills"] = list(fields["skills"])
    if "attacks" in fields:
        sheet["attacks"] = [
            {**a, "description": ", ".join(p for p in (f"{a['attack_bonus']} to hit" if a.get("attack_bonus") else "", a.get("damage") or "") if p)}
            for a in fields["attacks"]
        ]
    if "spell_slots" in fields:
        sheet["spell_slots"] = fields["spell_slots"]
    if "spells" in fields:
        names: list[str] = []
        for spell in fields["spells"]:
            if spell["name"] not in names:
                names.append(spell["name"])
        sheet["spells"] = names
        sheet["spellbook"] = [{"name": s["name"], "level": s["level"]} for s in fields["spells"]]
