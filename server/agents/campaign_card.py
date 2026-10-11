"""Read a player's own description of a campaign back to them as a Campaign Card.

Campaign setup used to ask for the AI's settings (canon policy, creativity,
posture) and guessed tone and genre from quiz scores and keywords.  The local
model is good at the opposite job: reading a paragraph and pulling a few facts
out of it.  So setup is one text box, one bounded model call, and a card that
sorts every fact into what the player said, what was guessed, and what is
still open.

The model's answer is never trusted on its own word.  Whether a value counts as
"said" is decided here, by checking it against the player's text; a proper name
that is not in the text is dropped, because inventing the world's people is the
world skeleton's job, not the card's.  When the model is unavailable the card
is built from the text and the chosen starter alone, so setup never blocks on
the GPU.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .generation_intent import clean_text, content_tokens, trim_sentence
from .premise_seed import parse_json_object

log = logging.getLogger("taverntails.campaign_card")

SAID, GUESSED, OPEN = "said", "guessed", "open"

GENRES = ("fantasy", "horror", "sci-fi", "mystery", "political", "post-apocalyptic", "thriller", "western", "modern")
PACINGS = ("slow", "moderate", "fast")
RATINGS = ("family", "pg-13", "mature")
AI_FREEDOM = ("low", "medium", "high")

# Text fields on the card, in display order.
TEXT_FIELDS = ("name", "premise", "world_name", "starting_place", "opening_trouble", "tone", "ruleset")
CHOICE_FIELDS = {"genre": GENRES, "pacing": PACINGS, "content_rating": RATINGS, "ai_freedom": AI_FREEDOM}

MAX_TEXT_CHARS = 8000  # the description box and POST /campaigns/card accept this much
MAX_LORE_CHARS = 60000  # matches the API and the notes box
MAX_LORE_PROMPT_CHARS = 6000
MAX_FIELD_CHARS = 280
MAX_FOLLOW_UPS = 2

# Gaps that stop the first scene from starting, in the order they are asked.  The model does not
# write these questions: a fixed menu keeps them short and keeps it from fishing for lore.
FOLLOW_UP_MENU: dict[str, dict[str, str]] = {
    "starting_place": {
        "question": "Where does the story open?",
        "placeholder": "A flooded chapel, the night market, a ship's brig…",
    },
    "opening_trouble": {
        "question": "What's going wrong when the story begins?",
        "placeholder": "Someone is missing, the bridge is out, a debt is due…",
    },
}

SYSTEM = (
    "You read a player's description of the tabletop RPG campaign they want and fill in a short campaign card.\n"
    "Copy the player's own words where they give them. Where they do not say, you may make a sensible guess for "
    "name, tone, genre, pacing, content_rating and ai_freedom. For every other field leave the value empty "
    "(\"\" or []) when the text does not say. Never invent people, factions or places that are not in the text.\n"
    "Reply with ONLY a JSON object with these keys:\n"
    '  "name": a short evocative campaign title (3-6 words)\n'
    '  "premise": one sentence pitch of the campaign in the player\'s terms\n'
    f'  "genre": one of {", ".join(GENRES)}\n'
    '  "tone": 1-4 words, e.g. "grim and grounded", "cozy", "cinematic heroism"\n'
    '  "world_name": the setting\'s name if the text gives one\n'
    '  "starting_place": where the first scene happens, if the text says\n'
    '  "opening_trouble": one sentence: what is going wrong as the story begins, if the text says\n'
    '  "ruleset": the game system if the text names one (e.g. "D&D 5e", "Pathfinder 2e")\n'
    '  "starting_level": a number if the text gives one, else null\n'
    '  "pacing": one of slow, moderate, fast\n'
    '  "content_rating": one of family, pg-13, mature\n'
    '  "ai_freedom": low (stick to what I wrote), medium (fill gaps), or high (surprise me)\n'
    '  "people": list of {"name": ..., "role": ...} for people the text names\n'
    '  "factions": list of faction or group names the text names\n'
    '  "themes": up to 4 short themes\n'
    '  "content_limits": things the player says to avoid or handle carefully\n'
    '  "open_questions": up to 3 short questions about the world the text leaves open'
)


# ---------------------------------------------------------------------------
# The confirmed card, as POST /campaigns accepts it
# ---------------------------------------------------------------------------

Status = Literal["said", "guessed", "open"]


class CardField(BaseModel):
    value: str | int | float = Field(default="")
    status: Status = "open"

    @field_validator("value")
    @classmethod
    def _short(cls, value: str | int | float) -> str | int | float:
        if isinstance(value, str) and len(value) > 2000:
            raise ValueError("card values are limited to 2000 characters")
        return value


class CardPerson(BaseModel):
    name: str = Field(max_length=120)
    role: str = Field(default="", max_length=120)
    status: Status = "said"


class CardFaction(BaseModel):
    name: str = Field(max_length=120)
    status: Status = "said"


class ConfirmedCard(BaseModel):
    """What the client sends back; anything the server derived (follow-ups, settings) is recomputed."""

    model_config = ConfigDict(extra="ignore")

    fields: dict[str, CardField] = Field(default_factory=dict, max_length=24)
    people: list[CardPerson] = Field(default_factory=list, max_length=12)
    factions: list[CardFaction] = Field(default_factory=list, max_length=8)
    themes: list[str] = Field(default_factory=list, max_length=8)
    content_limits: list[str] = Field(default_factory=list, max_length=8)
    open_questions: list[str] = Field(default_factory=list, max_length=6)
    text: str = Field(default="", max_length=MAX_TEXT_CHARS)
    has_lore: bool = False
    starter: dict[str, str] = Field(default_factory=dict)

    @field_validator("fields")
    @classmethod
    def _level_is_a_level(cls, fields: dict[str, CardField]) -> dict[str, CardField]:
        level = fields.get("starting_level")
        if level is not None and level.status != OPEN and level.value != "":
            try:
                number = int(level.value)
            except (TypeError, ValueError):
                raise ValueError("starting_level must be a whole number") from None
            if not 1 <= number <= 20:
                raise ValueError("starting_level must be between 1 and 20")
        for key, choices in CHOICE_FIELDS.items():
            entry = fields.get(key)
            if entry is not None and entry.status != OPEN and entry.value not in choices:
                raise ValueError(f"{key} must be one of {', '.join(choices)}")
        return fields


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------

def _source_tokens(text: str, lore: str) -> set[str]:
    return content_tokens(f"{text} {lore}")


def is_grounded(value: str, source: str, source_tokens: set[str] | None = None) -> bool:
    """True when ``value`` is the player's own words: quoted outright, or most of its content words appear."""
    value = clean_text(value)
    if not value:
        return False
    if value.casefold() in source.casefold():
        return True
    tokens = content_tokens(value)
    if not tokens:
        return False
    found = source_tokens if source_tokens is not None else content_tokens(source)
    return len(tokens & found) / len(tokens) >= 0.6


def name_in_text(name: str, source: str) -> bool:
    """A proper name counts only when the text has it: every part of it, as a whole word (any case).

    Whole words, not substrings: "Art Bell" is not in a text about artifacts and belladonna.
    """
    parts = [p for p in re.findall(r"[A-Za-z][\w'-]+", name) if len(p) > 2]
    return bool(parts) and all(
        re.search(rf"(?<![\w'-]){re.escape(p)}(?![\w'-])", source, re.IGNORECASE) for p in parts
    )


_LEVEL = re.compile(r"\blevel\s*(\d{1,2})\b|\b(\d{1,2})(?:st|nd|rd|th)?[- ]level\b|\blvl\.?\s*(\d{1,2})\b", re.I)
_RULESETS = (
    (re.compile(r"\b(?:d&d|dnd|5e|5th edition|dungeons (?:and|&) dragons)\b", re.I), "D&D 5e"),
    (re.compile(r"\bpathfinder\s*(?:2e|2nd|second)\b|\bpf2e?\b", re.I), "Pathfinder 2e"),
    (re.compile(r"\bpathfinder\b", re.I), "Pathfinder"),
    (re.compile(r"\bstarfinder\b", re.I), "Starfinder"),
    (re.compile(r"\bcall of cthulhu\b|\bcoc\b", re.I), "Call of Cthulhu"),
    (re.compile(r"\bshadowrun\b", re.I), "Shadowrun"),
    (re.compile(r"\bosr\b|\bold[- ]school\b", re.I), "OSR"),
)


def stated_level(text: str) -> int | None:
    match = _LEVEL.search(text)
    if not match:
        return None
    level = int(next(g for g in match.groups() if g))
    return level if 1 <= level <= 20 else None


def stated_ruleset(text: str) -> str:
    for pattern, label in _RULESETS:
        if pattern.search(text):
            return label
    return ""


def relevant_lore(lore: str, query: str, budget: int = MAX_LORE_PROMPT_CHARS) -> str:
    """The parts of the setting notes that matter most to ``query``, within ``budget`` characters.

    One local GPU cannot read a 60k-character setting bible on every call, and its first few pages are
    rarely the parts that matter. Paragraphs are ranked by the content words they share with the query
    (the premise, the opening trouble, the names); the opening paragraph is always kept as orientation.
    The chosen paragraphs keep their original order.
    """
    lore = lore.strip()
    if len(lore) <= budget:
        return lore
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?=#)", lore) if p.strip()]
    wanted = content_tokens(query)
    ranked = sorted(range(1, len(paragraphs)), key=lambda i: -len(content_tokens(paragraphs[i]) & wanted))
    chosen, used = {0}, len(paragraphs[0])
    for i in ranked:
        if used + len(paragraphs[i]) + 2 > budget:
            continue
        chosen.add(i)
        used += len(paragraphs[i]) + 2
    return "\n\n".join(paragraphs[i] for i in sorted(chosen))[:budget]


# ---------------------------------------------------------------------------
# Card construction
# ---------------------------------------------------------------------------

def _field(value: Any, status: str) -> dict[str, Any]:
    return {"value": value, "status": status if value not in ("", None) else OPEN}


def _clip(value: Any) -> str:
    return clean_text(value)[:MAX_FIELD_CHARS]


def _str_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _clip(item)
        if text and text.casefold() not in {o.casefold() for o in out}:
            out.append(text)
    return out[:limit]


def _starter(starter: dict[str, Any] | None) -> dict[str, str]:
    starter = starter or {}
    return {k: clean_text(starter.get(k)) for k in ("genre", "tone", "seed_id", "title") if clean_text(starter.get(k))}


def _empty_card(text: str, lore: str, starter: dict[str, str]) -> dict[str, Any]:
    """The card the text alone supports: nothing guessed beyond the starter the player picked."""
    combined = f"{text} {lore}"
    level = stated_level(combined)
    ruleset = stated_ruleset(combined)
    genre = starter.get("genre", "")
    fields: dict[str, dict[str, Any]] = {
        "name": _field(starter.get("title", ""), GUESSED),
        "premise": _field(_clip(text) if text else "", SAID),
        "genre": _field(genre if genre in GENRES else "fantasy", SAID if genre in GENRES else GUESSED),
        "tone": _field(starter.get("tone", "balanced"), SAID if starter.get("tone") else GUESSED),
        "world_name": _field("", OPEN),
        "starting_place": _field("", OPEN),
        "opening_trouble": _field("", OPEN),
        "ruleset": _field(ruleset, SAID),
        "starting_level": _field(level or 1, SAID if level else GUESSED),
        "pacing": _field("moderate", GUESSED),
        "content_rating": _field("pg-13", GUESSED),
        "ai_freedom": _field("medium", GUESSED),
    }
    return {
        "fields": fields,
        "people": [],
        "factions": [],
        "themes": [],
        "content_limits": [],
        "open_questions": [],
    }


def _merge_model_answer(card: dict[str, Any], data: dict[str, Any], text: str, lore: str, starter: dict[str, str]) -> int:
    """Fold the model's answer into ``card``; returns how many fields it filled."""
    source = f"{text}\n{lore}"
    tokens = _source_tokens(text, lore)
    fields = card["fields"]
    filled = 0

    for key in TEXT_FIELDS:
        value = _clip(data.get(key))
        if not value:
            continue
        grounded = is_grounded(value, source, tokens)
        if key in {"world_name", "starting_place", "opening_trouble", "ruleset"} and not grounded:
            # A guessed place, crisis or system is not the player's; the world skeleton and the
            # follow-up questions fill these instead of a guess presented as a fact.
            continue
        if key == "premise" and fields["premise"]["status"] == SAID and not grounded:
            continue  # keep the player's own words over a pitch that drifted from them
        if key == "tone" and starter.get("tone") and not grounded:
            continue  # the starter they picked beats a guess
        fields[key] = _field(value, SAID if grounded else GUESSED)
        filled += 1

    for key, allowed in CHOICE_FIELDS.items():
        value = clean_text(data.get(key)).lower()
        if value not in allowed or fields[key]["status"] == SAID:
            continue  # e.g. the genre button they pressed is a statement, not a hint
        # "surprise me" is a reading of their words, not a quote, so ai_freedom is always shown as a guess.
        said = key != "ai_freedom" and re.search(rf"\b{re.escape(value)}\b", source, re.I) is not None
        fields[key] = _field(value, SAID if said else GUESSED)
        filled += 1

    level = data.get("starting_level")
    if fields["starting_level"]["status"] != SAID and isinstance(level, (int, float)) and 1 <= int(level) <= 20:
        fields["starting_level"] = _field(int(level), GUESSED)

    people: list[dict[str, str]] = []
    for person in data.get("people") or []:
        if not isinstance(person, dict):
            continue
        name = _clip(person.get("name"))[:80]
        if name and name_in_text(name, source) and name.casefold() not in {p["name"].casefold() for p in people}:
            role = _clip(person.get("role"))[:80]
            # The name is the player's; a role the text does not give is a guess and must not become canon.
            people.append({"name": name, "role": role if is_grounded(role, source, tokens) else "", "status": SAID})
    card["people"] = people[:6]
    card["factions"] = [
        {"name": name[:80], "status": SAID}
        for name in _str_list(data.get("factions"), 4)
        if name_in_text(name, source)
    ]
    card["themes"] = _str_list(data.get("themes"), 4)
    card["content_limits"] = [c for c in _str_list(data.get("content_limits"), 4) if is_grounded(c, source, tokens)]
    card["open_questions"] = [q for q in _str_list(data.get("open_questions"), 3) if q.endswith("?")]
    filled += len(people) + len(card["factions"])
    return filled


def follow_ups(card: dict[str, Any]) -> list[dict[str, str]]:
    """At most two questions, only for gaps the first scene cannot start without."""
    out = []
    for field, prompt in FOLLOW_UP_MENU.items():
        if card["fields"].get(field, {}).get("status") == OPEN:
            out.append({"id": field, "field": field, **prompt})
    return out[:MAX_FOLLOW_UPS]


def derive_settings(card: dict[str, Any], *, has_lore: bool = False, seed_id: str = "") -> dict[str, str]:
    """The AI's working settings follow from what the player wrote instead of being asked for."""
    freedom = card["fields"].get("ai_freedom", {}).get("value") or "medium"
    canon, creativity = {
        "low": ("strict_canon", "conservative"),
        "high": ("flexible_canon", "expansive"),
    }.get(freedom, ("guided_canon", "balanced"))
    if has_lore and freedom != "high":
        canon = "guided_canon" if canon == "flexible_canon" else canon
    posture = "lore_importer" if has_lore else "guided_builder" if seed_id else "player_fast_start"
    return {"canon_policy": canon, "ai_creativity_level": creativity, "creation_posture": posture}


def read_campaign_card(
    text: str,
    *,
    starter: dict[str, Any] | None = None,
    lore: str = "",
    complete: Callable[..., str | None] | None = None,
    timeout: float = 45.0,
) -> dict[str, Any]:
    """One model call -> a Campaign Card; falls back to the text and starter alone."""
    text = (text or "").strip()[:MAX_TEXT_CHARS]
    lore = (lore or "").strip()[:MAX_LORE_CHARS]
    picked = _starter(starter)
    card = _empty_card(text, lore, picked)
    diagnostics: dict[str, Any] = {"source": "fallback"}

    if text or lore:
        call = complete
        if call is None:
            from ..steward_llm import chat_complete

            call = chat_complete
        hints = [f"Genre button pressed: {picked['genre']}"] if picked.get("genre") else []
        if picked.get("tone"):
            hints.append(f"Tone chosen: {picked['tone']}")
        user = "\n".join([*hints, f"Player's description:\n{text or '(none)'}"])
        if lore:
            user += f"\n\nTheir setting notes (the parts most relevant to the description):\n{relevant_lore(lore, text)}"
        try:
            raw = call(
                [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                task_scope="taverntails_setup", max_tokens=700, temperature=0.3, timeout=timeout,
            )
        except Exception:  # noqa: BLE001 - the text-only card is always usable
            log.warning("campaign card call failed", exc_info=True)
            raw = None
            diagnostics["reason"] = "model_error"
        data = parse_json_object(raw)
        if data is None:
            diagnostics.setdefault("reason", "unparseable" if raw else "no_answer")
        elif _merge_model_answer(card, data, text, lore, picked) == 0:
            diagnostics["reason"] = "nothing_usable"
        else:
            diagnostics = {"source": "model"}
    else:
        diagnostics["reason"] = "empty_text"

    card["text"] = text
    card["has_lore"] = bool(lore)
    card["starter"] = picked
    card["follow_ups"] = follow_ups(card)
    card["derived"] = derive_settings(card, has_lore=bool(lore), seed_id=picked.get("seed_id", ""))
    card["diagnostics"] = diagnostics
    return card


# ---------------------------------------------------------------------------
# Card -> campaign records
# ---------------------------------------------------------------------------

def _value(card: dict[str, Any], key: str) -> Any:
    entry = (card.get("fields") or {}).get(key) or {}
    if entry.get("status") == OPEN:
        return ""
    return entry.get("value")


def apply_answers(card: dict[str, Any], answers: dict[str, str] | None) -> dict[str, Any]:
    """Follow-up answers are the player's words, so they land on the card as said."""
    fields = dict(card.get("fields") or {})
    for key, answer in (answers or {}).items():
        text = _clip(answer)
        if key in FOLLOW_UP_MENU and text:
            fields[key] = {"value": text, "status": SAID}
    return {**card, "fields": fields}


def card_to_campaign(card: dict[str, Any]) -> dict[str, Any]:
    """Settings, variables and description for ``create_campaign``.

    Every value left on the card when the player presses Create was shown to
    them, so it is kept: a guess they read and did not change is a guess they
    accepted.  Open fields stay out, so later stages see them as unknown.
    """
    text = trim_sentence(card.get("text"))
    premise = clean_text(_value(card, "premise"))
    trouble = clean_text(_value(card, "opening_trouble"))
    summary = text or trim_sentence(premise)
    if text and premise and not is_grounded(premise, text):
        # The player rewrote the premise on the card: that correction leads, ahead of the first draft.
        summary = f"{trim_sentence(premise)} {text}"
    if trouble and trouble.casefold() not in summary.casefold():
        summary = f"{summary} {trim_sentence(trouble)}".strip()

    has_lore = bool(card.get("has_lore"))
    starter = card.get("starter") or {}
    derived = derive_settings(card, has_lore=has_lore, seed_id=str(starter.get("seed_id") or ""))
    settings: dict[str, Any] = {
        "genre": _value(card, "genre") or "fantasy",
        "tone": _value(card, "tone") or "balanced",
        "setting_summary": summary,
        "world_name": clean_text(_value(card, "world_name")),
        "ruleset": clean_text(_value(card, "ruleset")),
        "starting_level": int(_value(card, "starting_level") or 1),
        "pacing": _value(card, "pacing") or "moderate",
        "content_rating": _value(card, "content_rating") or "pg-13",
        **derived,
    }
    place = clean_text(_value(card, "starting_place"))
    if place:
        settings["starting_location"] = place
    if trouble:
        settings["opening_trouble"] = trouble
    limits = [str(c) for c in card.get("content_limits") or []]
    if limits:
        settings["content_limits"] = limits

    variables = {
        "themes": [str(t) for t in card.get("themes") or []],
        "pacing": settings["pacing"],
        "content_rating": settings["content_rating"],
        "factions": [{"name": f["name"]} for f in card.get("factions") or [] if isinstance(f, dict) and f.get("name")],
        "content_limits": limits,
    }
    return {
        "name": clean_text(_value(card, "name")),
        "description": premise or summary[:400],
        "settings": settings,
        "variables": variables,
    }
