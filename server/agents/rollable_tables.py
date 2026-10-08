"""Rollable random tables that seed variation into the story.

The user's table books (PDFs) are indexed once into ``storage/rollable_tables/index.json``.
At narration time a table is picked to suit the scene, its die is actually
rolled, and the result is handed to the narrator as something it has to work
into the scene.  Story Truth and the players' own actions stay authoritative:
a roll adds an ingredient, it never overwrites what has been established.

Only the short rolled result and its provenance ever reach a prompt.  The
source text stays on disk.
"""
from __future__ import annotations

import json
import os
import random
import re
import threading
from collections import deque
from pathlib import Path
from typing import Any

INDEX_VERSION = 4
STORAGE_DIR = Path(__file__).resolve().parents[1] / "storage" / "rollable_tables"
SOURCE_DIR = STORAGE_DIR / "source"
DEFAULT_INDEX = STORAGE_DIR / "index.json"

# Scene kinds the director/composer use, mapped to the table categories that suit them.
CATEGORY_WEIGHTS: dict[str, dict[str, float]] = {
    "opening": {"encounter": 3, "complication": 3, "npc": 2, "rumor": 2, "place": 1, "object": 1, "event": 2, "sensory": 1},
    "dialogue": {"npc": 4, "rumor": 3, "motivation": 3, "event": 2, "encounter": 1, "object": 1},
    "investigation": {"clue": 4, "object": 3, "rumor": 2, "sensory": 2, "complication": 1},
    "exploration": {"sensory": 3, "place": 3, "object": 2, "encounter": 2, "complication": 2, "event": 1},
    "travel": {"encounter": 4, "event": 3, "sensory": 2, "complication": 2, "rumor": 1},
    "combat": {"complication": 4, "sensory": 1},
    "default": {"encounter": 3, "complication": 3, "npc": 2, "rumor": 2, "object": 1, "event": 2, "sensory": 1, "clue": 1, "motivation": 1},
}
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("name", ("names",)),
    ("rumor", ("rumor", "gossip", "overhear", "legend", "tale", "whisper")),
    ("clue", ("clue", "secret", "evidence", "discover", "hidden", "mystery", "riddle")),
    ("motivation", ("goal", "want", "desire", "motiv", "ambition", "obstacle", "marked because", "patron", "quest")),
    ("event", ("celebration", "festival", "today", "tonight", "performance", "market", "holiday", "ritual")),
    ("sensory", ("weather", "smell", "sound", "sight", "atmosphere", "ambien", "the space", "party sees", "party hears", "party smells")),
    ("object", ("item", "treasure", "talisman", "relic", "trinket", "pulls out", "carries", "artifact", "loot", "enchantment")),
    ("npc", ("npc", "personality", "quirk", "appearance", "trait", "demeanor", "villain", "leader", "tenant", "denizen")),
    ("place", ("location", "tavern", "city is", "town is", "settlement", "district", "building", "shop", "ruled by")),
    ("complication", ("complication", "twist", "danger", "hazard", "trouble", "problem", "must face", "also contend")),
    ("encounter", ("encounter", "party finds", "party meets", "party...", "ambush", "wandering")),
]
_STOP = frozenset(
    "about above after again against along also among another around because before being below between "
    "could does doing during each either every from have having here into just like made make many more most much "
    "must never once only other over same several should since some such than that their them then there these "
    "they this those through under until upon very were what when where which while will with within without would your".split()
)
_RECENT: deque[str] = deque(maxlen=40)
_RECENT_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"path": None, "mtime": None, "data": None}


# --------------------------------------------------------------------------- cleaning

_BAD_ROW = re.compile(
    r"\b(?:pg|pp|page|isbn|copyright|chapter)\b\.?\s*\d*|\bdc\s*\d+|saving throw|\bdamage\b|hit points|"
    r"\barea\s+\d+|\broom\s+\d+|\b(?:first|second|third|fourth|fifth|sixth|seventh)\s+chamber\b|"
    r"_{3,}|https?://|www\.|\broll (?:again|twice|on)\b|\bre-?roll\b|\bsee (?:the )?(?:table|page|map)\b|\bthis adventure\b|"
    r"\bbonus action\b|\bspell slot|\bchallenge rating\b|\bstat ?block\b|"
    r"\b(?:long|short) rest\b|\b(?:dis)?advantage\b|\bproficien|\bability check|\bskill check|\bhit die\b|\bsaves?\b|\binitiative\b|"
    r"\bdoor\s+\d+|\bgoal\s+[a-z]\b|\[[^\]]*\]|\b\d[\d,]*\s*(?:gp|sp|cp|pp)\b|^\W*[—–-]",
    re.I,
)


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split()).strip(" |")


def _strip_ellipsis(text: str) -> str:
    text = re.sub(r"^(?:\.{2,}|…)\s*", "", text).strip()
    return re.sub(r"(?<=\w)\.{2,}(?=\s+[a-z])", "", text)  # "below the.. party" -> "below the party"


_COMMON_CAPS = frozenset("I A An The Lady Lord King Queen Prince Princess Duke Duchess Baron Baroness Captain Sir Dame God Gods Goddess Elf Elves Dwarf Dwarves Halfling Gnome Orc Orcs Goblin Goblins Drow Human Tiefling Dragonborn Deva Fey Feywild Shadowfell Material Plane".split())


def _local_proper_nouns(value: str) -> int:
    """Mid-sentence capitalised words that are not generic: signs of a row tied to one adventure."""
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", value)
    count = 0
    for word in words[1:]:
        prev = value[: value.find(word)].rstrip()[-1:] if word in value else ""
        if word[0].isupper() and word not in _COMMON_CAPS and prev not in ".!?:\"“”—":
            count += 1
    return count


def _usable_entry(text: str, *, names_ok: bool = False) -> bool:
    value = _clean(text)
    if len(value) < 4 or len(value) > 380:
        return False
    if not names_ok and re.match(r"^(?:this|the)\s+(?:item|artifact|weapon|space|entity|room|chamber)\b", value, re.I):
        return False  # describes "this item/space" from the book's own context; nothing for a scene to hang it on
    if not names_ok and (len(value.split()) < 3 or re.match(r"^\d+\s+[a-z]", value)):
        return False  # a fragment, not a result
    if _BAD_ROW.search(value):
        return False
    if not names_ok and _local_proper_nouns(value) >= 2:
        return False
    if value.endswith(("...", "…", ",", ":", " and", " or", " the", " of", " a", " from", " to", " in", " with", " that", " at", " by", " on")):
        return False  # truncated by the extractor or a template stub
    if re.search(r"\([^)]*\/[^)]*\)", value):
        return False  # fill-in-the-blank option list: "(wealth/information/prestige)"
    if re.search(r"\bparty members\b|\bPCs?\b|\bplayers?\b", value):
        return False  # written at the table, not in the fiction
    if re.search(r"\b[a-z]{3,}\s[b-hj-zB-HJ-Z]\b(?!\.)", value):
        return False  # PDF kerning split a word ("heft y")
    letters = sum(ch.isalpha() for ch in value)
    return letters >= len(value) * 0.55


def _category_for(title: str, rows: list[str]) -> str:
    """Title decides; untitled tables fall back to a narrow read of their first rows."""
    t = title.lower()
    for category, words in _CATEGORY_KEYWORDS:
        if any(word in t for word in words):
            return category
    if t == "name":
        return "name"
    return "general"


def _lead_in(title: str, rows: list[str]) -> str:
    """The sentence stem a table's rows complete, e.g. 'The party encounters'."""
    t = _clean(title)
    if t.endswith(("...", "…")):
        return t.rstrip(".… ").strip()
    return ""


# Player-facing prompts about the characters, not the fiction: nothing a narrator can put in a scene.
_SKIP_SOURCES = ("proactiveroleplaying",)
_SKIP_TITLE = re.compile(r"where should you begin|^section$|^table \d|^map$|^puzzle$|^type$|chapter|contents|\bpcs?\b|\bcode\b", re.I)


def build_tables(raw_tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn raw extractor output into clean, storable tables."""
    out: list[dict[str, Any]] = []
    for raw in raw_tables:
        if any(marker in str(raw.get("source") or "") for marker in _SKIP_SOURCES):
            continue
        title = _clean(raw.get("title"))
        if len(title.split()) > 9 or not re.match(r"^[A-Z0-9]", title):
            title = ""  # a stray prose line caught above the table, not a heading
        if _SKIP_TITLE.search(title):
            continue
        names_table = bool(re.search(r"\bnames?\b|^location$", title, re.I))
        rows: list[dict[str, Any]] = []
        for row in raw.get("rows") or []:
            text = _strip_ellipsis(_clean(row.get("text")))
            rows.append({"lo": int(row["lo"]), "hi": int(row["hi"]), "text": text, "ok": _usable_entry(text, names_ok=names_table)})
        usable = [r for r in rows if r["ok"]]
        if len(usable) < 4 or len(usable) < len(rows) * 0.75:
            continue
        lead = _lead_in(title, [r["text"] for r in usable])
        if not names_table and not lead and sorted(len(r["text"].split()) for r in usable)[len(usable) // 2] < 3:
            continue  # lists of bare words ("Eldritch", "Fire Plate") are not something a scene can use
        die = max(r["hi"] for r in rows)
        texts = [r["text"] for r in usable]
        out.append({
            "id": f"{Path(str(raw.get('source'))).stem[:24]}:{raw.get('page')}:{len(out)}",
            "title": title,
            "lead": lead,
            "die": die,
            "category": _category_for(title, texts),
            "source": raw.get("source"),
            "page": raw.get("page"),
            "rows": [{"lo": r["lo"], "hi": r["hi"], "text": r["text"]} for r in rows if r["ok"]],
        })
    return out


OCR_CACHE = STORAGE_DIR / "ocr_cache"


def _ocr_reader():
    """Page image -> tesseract TSV via Steward's OCR nodes (needs STEWARD_HOST), or None when unavailable."""
    from ..ocr_client import _remote, remote_enabled

    if not remote_enabled():
        return None
    return lambda png, psm=11: _remote(png, "tsv", psm)


def _tables_from_pdf(pdf: Path, *, ocr: bool, progress=None) -> tuple[list[dict[str, Any]], str]:
    """(clean tables, how it was read): 'text', 'ocr', or 'skipped' for a scan with no OCR available."""
    from . import rollable_tables_extract as extract

    if extract.is_scanned(pdf):
        reader = _ocr_reader() if ocr else None
        if reader is None:
            return [], "skipped"
        pages = extract.ocr_pdf_pages(pdf, reader, cache_dir=OCR_CACHE / pdf.stem, progress=progress)
        empty = sum(1 for _n, _w, _h, words in pages if not words)
        if pages and empty > len(pages) * 0.5:
            raise RuntimeError(f"OCR returned nothing for {empty} of {len(pages)} pages")
        return build_tables(extract.extract_scanned_tables(pages, pdf.name)), "ocr"
    return build_tables(extract.extract_pdf_tables(pdf)), "text"


def build_index(source_dir: Path = SOURCE_DIR, destination: Path = DEFAULT_INDEX, *, ocr: bool = True, progress=None) -> dict[str, Any]:
    pdfs = sorted(Path(source_dir).rglob("*.pdf"))
    tables: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for pdf in pdfs:
        try:
            made, how = _tables_from_pdf(pdf, ocr=ocr, progress=progress)
            tables.extend(made)
            sources.append({"source": pdf.name, "read": how, "tables": len(made), "rows": sum(len(t["rows"]) for t in made)})
        except Exception as exc:  # one bad book must not sink the rest
            errors.append({"source": pdf.name, "error": str(exc)})
    payload = {
        "version": INDEX_VERSION, "pdf_count": len(pdfs), "table_count": len(tables),
        "entry_count": sum(len(t["rows"]) for t in tables), "sources": sources, "errors": errors, "tables": tables,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(destination)
    _CACHE["data"] = None
    return payload


def load_index(path: Path | None = None) -> dict[str, Any]:
    path = Path(path or DEFAULT_INDEX)
    empty = {"version": INDEX_VERSION, "table_count": 0, "entry_count": 0, "tables": [], "available": False}
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return empty
    if _CACHE["data"] is not None and _CACHE["path"] == str(path) and _CACHE["mtime"] == mtime:
        return _CACHE["data"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if int(data.get("version") or 0) != INDEX_VERSION:
            return empty
    except (OSError, ValueError):
        return empty
    data["available"] = bool(data.get("tables"))
    _CACHE.update(path=str(path), mtime=mtime, data=data)
    return data


# --------------------------------------------------------------------------- rolling

def enabled(contract: dict[str, Any] | None = None) -> bool:
    """Tables are D&D-fantasy flavoured; stay out of other genres and honour opt-outs."""
    if os.getenv("TAVERNTAILS_ROLLABLE_TABLES", "1").strip().lower() in {"0", "false", "no", "off"}:
        return False
    contract = contract or {}
    if contract.get("random_tables") is False:
        return False
    genre = str((contract.get("campaign_dna") or {}).get("genre") or "").lower()
    return not re.search(r"sci|space|cyber|modern|western|noir|steampunk|post-?apoc|superhero|contemporary", genre)


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{5,}", (text or "").lower()) if w not in _STOP}


def _weights(scene_type: str) -> dict[str, float]:
    return CATEGORY_WEIGHTS.get((scene_type or "").lower(), CATEGORY_WEIGHTS["default"])


_DETERMINERS = frozenset("a an the some one two three four five six seven eight nine ten several many few another each every no".split())


def _soften(text: str) -> str:
    """The narrator is told never to say 'the party'; keep the rolled wording consistent with that."""
    text = re.sub(r"\b(The|the) party (\w+?)s\b(?<!ss)", lambda m: f"{m.group(1)} characters {m.group(2)}" if m.group(2) not in {"mu", "wa"} else m.group(0), text)
    return re.sub(r"\bthe party\b", "the characters", re.sub(r"\bThe party\b", "The characters", text))


def _compose(table: dict[str, Any], row_text: str) -> str:
    lead = table.get("lead") or ""
    if lead:  # some scans repeat the lead-in at the start of the row itself
        row_text = re.sub(rf"^(?:{re.escape(lead)}|the party \w+)[\s.…]*", "", row_text, flags=re.I).strip() or row_text
    first = row_text.split(" ", 1)[0].lower()
    if lead:
        body = row_text[:1].lower() + row_text[1:] if first in _DETERMINERS else row_text
        return _soften(f"{lead} {body}".strip())
    title = (table.get("title") or "").rstrip(".: ")
    if (title and len(title.split()) <= 5 and not title.isupper() and not title.lower().endswith("table")
            and not re.match(r"^(?:name|location|table|the party|and|or|of|the)\b", title, re.I)):
        return _soften(f"{title}: {row_text}")
    return _soften(row_text)


def _pick_table(tables: list[dict[str, Any]], context: str, scene_type: str, rng: random.Random, avoid_categories: set[str]) -> dict[str, Any] | None:
    weights = _weights(scene_type)
    ctx = _terms(context)
    with _RECENT_LOCK:
        recent = set(_RECENT)
    scored: list[tuple[float, dict[str, Any]]] = []
    for table in tables:
        category = table.get("category") or "general"
        weight = weights.get(category, 0.8 if category == "general" else 0.0)
        if weight <= 0 or category in avoid_categories:
            continue
        if table["id"] in recent:
            weight *= 0.05
        overlap = len(ctx & _terms(" ".join(r["text"] for r in table["rows"][:6]) + " " + table.get("title", "")))
        scored.append((weight * (1 + min(overlap, 3) * 0.5) * rng.random() ** 0.5, table))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]


def roll_table(table: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """Actually roll the table's die and read off the matching row."""
    die = max(2, int(table.get("die") or len(table["rows"])))
    value = rng.randint(1, die)
    row = next((r for r in table["rows"] if r["lo"] <= value <= r["hi"]), None)
    if row is None:  # a row was dropped as unusable: take the nearest surviving one
        row = min(table["rows"], key=lambda r: min(abs(r["lo"] - value), abs(r["hi"] - value)))
    return {
        "table_id": table["id"], "table": table.get("title") or "", "category": table.get("category"),
        "die": f"1d{die}", "roll": value, "result": _compose(table, row["text"]),
        "source": table.get("source"), "page": table.get("page"),
    }


def roll_for_scene(*, context: str = "", scene_type: str = "default", count: int = 1, seed: Any = None, index: dict[str, Any] | None = None, exclude: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """Roll ``count`` tables suited to the scene.  ``seed`` makes the rolls reproducible (tests)."""
    data = index if index is not None else load_index()
    tables = data.get("tables") or []
    if not tables or count <= 0:
        return []
    rng = random.Random(seed) if seed is not None else random.Random()
    rolls: list[dict[str, Any]] = []
    used_categories: set[str] = set(exclude)
    for _ in range(count):
        table = _pick_table(tables, context, scene_type, rng, used_categories)
        if table is None:
            break
        rolls.append(roll_table(table, rng))
        used_categories.add(str(table.get("category")))
        with _RECENT_LOCK:
            _RECENT.append(table["id"])
    return rolls


# --------------------------------------------------------------------------- prompt + check

_CATEGORY_HINTS = {
    "name": "  (use this as the name of a person or thing newly introduced in the scene)",
    "place": "  (use this as the name of a place the scene mentions or moves toward)",
}


def rolls_prompt_block(rolls: list[dict[str, Any]], *, is_opening: bool = False) -> str:
    """Instruction block that makes the narrator work the rolled results into the scene."""
    if not rolls:
        return ""
    lines = [
        "═══ THE DICE HAVE SPOKEN — ROLLED STORY INGREDIENTS (REQUIRED) ═══",
        "  These results came from random tables rolled for THIS scene. Weave EVERY one into the scene as something concrete the characters can see, hear, meet or react to.",
        "  Adapt names, numbers, and wording to fit the established location, people, and tone — keep the core of what was rolled; do not swap it for something safer.",
        "  If a result seems out of place (a sea monster at a desert well), reskin it to fit the setting (a sand leviathan) rather than dropping it.",
        "  Never override what the players just did or what is already established; let the roll complicate, colour or redirect it instead." if not is_opening
        else "  Let the roll shape the opening's specifics (who, what is happening, what stands out) without contradicting the campaign premise.",
        "  Never mention dice, tables, rolls, books, or this list in the prose.",
    ]
    for i, roll in enumerate(rolls, 1):
        hint = _CATEGORY_HINTS.get(str(roll.get("category")), "")
        lines.append(f"  {i}. [{roll.get('category')}] {roll['result']}{hint}")
    return "\n".join(lines)


_LEAD_WORDS = frozenset("characters character encounter encounters finds find sees hears hear meets meet notice notices face must contend".split())


def rolls_user_reminder(rolls: list[dict[str, Any]]) -> str:
    """One line for the end of the user message, where small models weigh instructions most."""
    if not rolls:
        return ""
    return "Work these rolled ingredients into the scene: " + " | ".join(r["result"][:200] for r in rolls)


def woven_terms(result: str) -> list[str]:
    """Distinctive words a narrator would have to keep (or inflect) when using this result."""
    words = re.findall(r"[a-z]{4,}", re.sub(r"\d+d\d+|\d+", " ", (result or "").lower()))
    return sorted({w for w in words if w not in _STOP and w not in _LEAD_WORDS})


def rolls_missing(narrative: str, rolls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rolls whose distinctive wording does not appear in the narrative at all."""
    stems = {w[:4] for w in re.findall(r"[a-z]{4,}", (narrative or "").lower())}
    missing = []
    for roll in rolls:
        terms = woven_terms(roll["result"])
        if not terms:
            continue
        hits = sum(1 for t in terms if t[:4] in stems)
        if hits < (1 if len(terms) <= 4 else 2):
            missing.append(roll)
    return missing


def corpus_status(path: Path | None = None) -> dict[str, Any]:
    data = load_index(path)
    return {
        "available": bool(data.get("available")), "pdf_count": int(data.get("pdf_count") or 0),
        "table_count": int(data.get("table_count") or 0), "entry_count": int(data.get("entry_count") or 0),
        "sources": data.get("sources") or [], "version": INDEX_VERSION,
    }


def rolls_needed(is_opening: bool) -> int:
    return 2 if is_opening else 1
