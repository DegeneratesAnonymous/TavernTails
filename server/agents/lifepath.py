"""Staged life-path builders: a world wizard and a character backstory wizard.

Both wizards collect a handful of choices (each with room for the player's own words) and end in a
short narrative of those choices that the player can edit.  This module:

* ``POST /lifepath/narrative``  drafts that narrative from the choices, checks it against them, and
  falls back to a plain template when the model is unavailable or invents something;
* applies a confirmed backstory to a character (add to what is there, or overwrite it, with undo) or
  keeps it for one campaign only.

The narrative states what the player chose and nothing else.  Whether it does is decided here, by
checking the draft against the choices, not by trusting the model: a proper name nobody supplied, a
question, or a missing link to the main trouble sends the draft back with feedback, and after two
failed drafts the template is used.  Backstory is the B plot: a character's link to the world's main
conflict is required.
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db, steward_llm
from ..auth import get_current_user
from ..generation_workers import run_generation
from .campaign_card import name_in_text
from .generation_intent import clean_text, content_tokens, trim_sentence
from .opening_voice import first_to_third

logger = logging.getLogger("taverntails.lifepath")
router = APIRouter(prefix="/lifepath", tags=["lifepath"])

LINK_KINDS = ("faction", "place", "conflict", "tie", "story")
TEXT_FIELDS = ("bonds", "flaws", "ideals", "personality_traits")
LIST_FIELDS = ("allies", "rivals")
HISTORY_LIMIT = 5
GOAL_LIMIT = 9
MAX_ATTEMPTS = 2


class Entry(BaseModel):
    """One answer the player gave: a card they chose, or words they typed."""

    stage: str = Field(max_length=40)
    question: str = Field(default="", max_length=200)
    answer: str = Field(max_length=600)
    clause: str = Field(default="", max_length=300)  # the answer as part of a sentence; see ``_sentence``
    source: Literal["option", "typed"] = "option"


class Link(BaseModel):
    kind: Literal["faction", "place", "conflict", "tie", "story"]
    name: str = Field(default="", max_length=300)


class WorldContext(BaseModel):
    world_name: str = Field(default="", max_length=120)
    conflict: str = Field(default="", max_length=400)
    factions: list[str] = Field(default_factory=list, max_length=12)
    places: list[str] = Field(default_factory=list, max_length=12)
    tone: str = Field(default="", max_length=120)
    narrative: str = Field(default="", max_length=3000)


class NarrativeRequest(BaseModel):
    kind: Literal["world", "character"]
    name: str = Field(default="", max_length=120)  # the character's name; the world's name for a world
    entries: list[Entry] = Field(default_factory=list, max_length=30)
    freeform: str = Field(default="", max_length=1200)
    link: Link | None = None
    context: WorldContext = Field(default_factory=WorldContext)


# ---------------------------------------------------------------------------
# What the narrative may say
# ---------------------------------------------------------------------------

def _supplied_text(req: NarrativeRequest) -> str:
    """Everything the player (or their world) has supplied: the only source of names."""
    ctx = req.context
    parts = [req.name, req.freeform, ctx.world_name, ctx.conflict, ctx.tone, ctx.narrative, *ctx.factions, *ctx.places]
    for entry in req.entries:
        parts += [entry.answer, entry.clause]
    if req.link:
        parts.append(req.link.name)
    return " ".join(p for p in parts if p)


_STARTERS = frozenset(
    "the a an in on at by of for from with when while after before every some one his her their its they he she it we "
    "this that these those there here then now once years long all each but and so yet as if no not".split()
)
_CAP_RUN = re.compile(r"[A-Z][a-z][\w'’-]*(?: [A-Z][a-z][\w'’-]*)*")


def invented_names(text: str, supplied: str) -> list[str]:
    """Proper names in ``text`` that ``supplied`` does not contain.

    A single capitalised word that opens a sentence is just a sentence start and is ignored.
    """
    found: list[str] = []
    for match in _CAP_RUN.finditer(text):
        run = match.group(0)
        before = text[: match.start()].rstrip(" \t\"“‘'(")
        starts_sentence = not before or before[-1] in ".!?\n"
        words = [re.sub(r"['’]s$", "", w) for w in run.split()]  # "Orrin's" names Orrin
        if starts_sentence:
            if len(words) == 1:
                continue
            if words[0].lower() in _STARTERS:
                words = words[1:]
                if not words:
                    continue
        if name_in_text(" ".join(words), supplied):
            continue
        for word in words:
            if word.lower() not in _STARTERS and not name_in_text(word, supplied) and word not in found:
                found.append(word)
    return found


# Relationships and genders a draft likes to add; allowed only when the player's own words use them.
_KIN = frozenset(
    "mother father mom dad mum brother sister son daughter wife husband grandmother grandfather grandma grandpa "
    "uncle aunt cousin nephew niece lover fiance fiancee girlfriend boyfriend child children orphan".split()
)


def invented_kin(text: str, supplied: str) -> list[str]:
    """Family and relationship words in ``text`` that the player's own words never use."""
    have = set(re.findall(r"[a-z]+", supplied.lower()))
    return sorted({w for w in re.findall(r"[a-z]+", text.lower()) if w in _KIN and w not in have})


def _link_present(text: str, req: NarrativeRequest) -> bool:
    link = req.link
    if link is None or link.kind == "story" or not link.name.strip():
        return True
    if link.kind in ("faction", "place"):
        return name_in_text(link.name, text)
    wanted = content_tokens(link.name or req.context.conflict)
    return not wanted or len(wanted & content_tokens(text)) >= min(2, len(wanted))


def check_narrative(text: str, req: NarrativeRequest) -> list[str]:
    """Problems with a draft; empty when it may be shown to the player."""
    issues: list[str] = []
    body = (text or "").strip()
    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not 1 <= len(paragraphs) <= 5 or not 80 <= len(body) <= 2400:
        issues.append("Write 2 to 4 short paragraphs.")
    if "?" in body:
        issues.append("Do not ask questions.")
    names = invented_names(body, _supplied_text(req))
    if names:
        issues.append("Remove these names, which the player did not give: " + ", ".join(names[:5]) + ".")
    extra_kin = invented_kin(body, _supplied_text(req))
    if extra_kin:
        issues.append("Remove these, which the choices do not say: " + ", ".join(extra_kin[:4]) + ".")
    if req.kind == "character" and not _link_present(body, req):
        issues.append("State plainly how this character's story touches " + (req.link.name if req.link else "the main trouble") + ".")
    if req.entries:
        used = sum(1 for e in req.entries if _entry_used(body, e))
        if used / len(req.entries) < 0.6:
            issues.append("Use more of the player's choices, in their own terms.")
    return issues


def _entry_used(body: str, entry: Entry) -> bool:
    wanted = content_tokens(entry.clause or entry.answer)
    return not wanted or bool(wanted & content_tokens(body))


# ---------------------------------------------------------------------------
# Drafting
# ---------------------------------------------------------------------------

def _messages(req: NarrativeRequest, feedback: str) -> list[dict[str, str]]:
    if req.kind == "world":
        system = (
            "You write a short description of a tabletop RPG world from the player's own choices. Write 2 to 4 short "
            "paragraphs in the present tense, plain and concrete, in the tone they chose. State only what the choices "
            "say. Do not invent names of people, places or groups. Do not use 'you'. Do not ask questions."
        )
    else:
        system = (
            "You write a character's backstory from the player's own choices. Write 2 to 4 short paragraphs about the "
            f"character, third person, past tense, using the name {req.name or 'the character'}. State only what the "
            "choices say, in plain concrete prose. Do not add events, causes, relationships, ages or genders that the "
            "choices do not state (a 'grandparent' stays a grandparent; a loss has no invented cause). Where a choice "
            "is brief, keep what you write about it brief. Do not invent names of people, places or groups. Mention how "
            "the character's story touches the main trouble. Do not give the character abilities or numbers. Do not ask "
            "questions."
        )
    lines = [f"- {e.stage}: {e.answer}" for e in req.entries]
    if req.freeform.strip():
        lines.append(f"- In their own words: {req.freeform.strip()}")
    ctx = req.context
    facts: list[str] = []
    if req.kind == "character":
        if ctx.world_name:
            facts.append(f"World: {ctx.world_name}")
        if ctx.conflict:
            facts.append(f"The main trouble: {ctx.conflict}")
        if req.link and req.link.name:
            facts.append(f"The character's link to it: {req.link.kind} - {req.link.name}")
    user = "\n".join([*facts, "Choices:", *lines] + ([f"Fix this: {feedback}"] if feedback else []))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _sentence(req: NarrativeRequest, entry: Entry) -> str:
    """One entry as a sentence for the template.  Characters' clauses are predicates, the world's are sentences."""
    if entry.clause.strip():
        text = clean_text(entry.clause)
        if req.kind == "character" and req.name:
            text = f"{req.name} {text}"
    else:
        text = first_to_third(clean_text(entry.answer))
    return trim_sentence(text[:1].upper() + text[1:]) if text else ""


def build_template(req: NarrativeRequest) -> str:
    """The narrative as plain sentences, grouped three to a paragraph.  Used when no draft passes."""
    sentences = [s for s in (_sentence(req, e) for e in req.entries) if s]
    link = req.link
    if req.kind == "character" and link is not None:
        who = req.name or "Their"
        if link.kind == "story" or not link.name.strip():
            sentences.append(f"How {who}'s story meets the main trouble is left for the story to reveal." if req.name else
                             "How their story meets the main trouble is left for the story to reveal.")
        elif link.kind == "conflict":
            sentences.append(f"Their story runs straight through the main trouble: {clean_text(link.name)}.")
        else:
            sentences.append(f"Their story is tied to {clean_text(link.name)}, and through it to the main trouble.")
    if req.freeform.strip():
        sentences.append(trim_sentence(first_to_third(req.freeform.strip())))
    return "\n\n".join(" ".join(sentences[i:i + 3]) for i in range(0, len(sentences), 3))


def write_narrative(req: NarrativeRequest, *, call: Callable[..., Any] | None = None) -> dict[str, Any]:
    """``{"narrative", "source", "issues"}``: a checked model draft, else the template."""
    ask = call or steward_llm.chat_complete
    feedback = ""
    last_issues: list[str] = []
    if req.entries:
        for _ in range(MAX_ATTEMPTS):
            try:
                raw = ask(_messages(req, feedback), task_scope="taverntails_setup", max_tokens=700, temperature=0.7, timeout=60.0)
            except Exception:
                logger.exception("lifepath narrative call failed")
                break
            draft = str(raw or "").strip().strip('"')
            if not draft:
                break
            last_issues = check_narrative(draft, req)
            if not last_issues:
                return {"narrative": draft, "source": "model", "issues": []}
            feedback = " ".join(last_issues)
    return {"narrative": build_template(req), "source": "template", "issues": last_issues}


# ---------------------------------------------------------------------------
# Writing a confirmed backstory onto a character
# ---------------------------------------------------------------------------

class BackstoryPayload(BaseModel):
    backstory: str = Field(default="", max_length=6000)
    label: str = Field(default="", max_length=120)  # heading for an added section, e.g. the world's name
    bonds: str = Field(default="", max_length=1500)
    flaws: str = Field(default="", max_length=1500)
    ideals: str = Field(default="", max_length=1500)
    personality_traits: str = Field(default="", max_length=1500)
    alignment: str = Field(default="", max_length=60)
    allies: list[str] = Field(default_factory=list, max_length=10)
    rivals: list[str] = Field(default_factory=list, max_length=10)
    patron: str = Field(default="", max_length=200)
    goals: list[dict[str, str]] = Field(default_factory=list, max_length=GOAL_LIMIT)
    link: Link | None = None
    lifepath: dict[str, Any] = Field(default_factory=dict)


class ApplyRequest(BaseModel):
    mode: Literal["add", "overwrite"]
    backstory: BackstoryPayload
    commit: bool = False  # False returns the before and after without writing


def _lines(value: Any) -> list[str]:
    return [p.strip() for p in re.split(r"[\n;]+", str(value or "")) if p.strip()]


def _merge_lines(old: Any, new: Any) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for line in [*_lines(old), *_lines(new)]:
        if line.casefold() not in seen:
            seen.add(line.casefold())
            out.append(line)
    return "\n".join(out)


def _merge_list(old: Any, new: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in [*(old if isinstance(old, list) else _lines(old)), *new]:
        text = str(item).strip()
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    return out


GOAL_STATUSES = ("active", "done", "dropped")


def goal_id(text: str) -> str:
    """A goal's stable id: the same words always give the same id, so a goal can be found again."""
    return hashlib.sha1(clean_text(text).casefold().encode()).hexdigest()[:8]


def _clean_goals(goals: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    used: set[str] = set()
    for goal in goals[:GOAL_LIMIT]:
        text = clean_text(goal.get("text"))
        if not text:
            continue
        term = str(goal.get("term")) if goal.get("term") in ("short", "mid", "long") else "mid"
        gid = goal_id(text)
        if gid in used:  # the same words under two horizons are two goals, each with its own id
            gid = goal_id(f"{text}|{term}")
        while gid in used:
            gid = goal_id(f"{text}|{term}|{len(used)}")
        used.add(gid)
        out.append({
            "id": gid, "term": term, "text": text[:300],
            "because": clean_text(goal.get("because"))[:300], "but": clean_text(goal.get("but"))[:300],
            "status": str(goal.get("status")) if goal.get("status") in GOAL_STATUSES else "active",
            "note": clean_text(goal.get("note"))[:200],
        })
    return out


def apply_backstory(sheet: dict[str, Any], payload: BackstoryPayload, mode: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """``(new_sheet, changes)``.  ``changes`` lists each field's value before and after, for the preview.

    ``add`` keeps what the sheet has and appends; ``overwrite`` replaces each field the payload fills in and
    keeps the previous values in ``backstory_history`` so the change can be undone.
    """
    old = dict(sheet) if isinstance(sheet, dict) else {}
    new = dict(old)
    overwrite = mode == "overwrite"
    story = payload.backstory.strip()
    if story:
        if overwrite or not str(old.get("backstory") or "").strip():
            new["backstory"] = story
        else:
            heading = f"{payload.label.strip()}\n" if payload.label.strip() else ""
            new["backstory"] = f"{str(old['backstory']).rstrip()}\n\n{heading}{story}"
    for key in TEXT_FIELDS:
        value = str(getattr(payload, key) or "").strip()
        if value:
            new[key] = value if overwrite else _merge_lines(old.get(key), value)
    if payload.alignment.strip() and (overwrite or not str(old.get("alignment") or "").strip()):
        new["alignment"] = payload.alignment.strip()
    for key in LIST_FIELDS:
        values = [v for v in getattr(payload, key) if str(v).strip()]
        if values:
            new[key] = values if overwrite else _merge_list(old.get(key), values)
    if payload.patron.strip() and (overwrite or not str(old.get("patron") or "").strip()):
        new["patron"] = payload.patron.strip()
    goals = _clean_goals(payload.goals)
    if goals:
        existing = [g for g in old.get("goals", []) if isinstance(g, dict)]
        if overwrite:
            new["goals"] = goals
        else:
            texts = {str(g.get("text", "")).casefold() for g in existing}
            new["goals"] = (existing + [g for g in goals if g["text"].casefold() not in texts])[:GOAL_LIMIT]
    if payload.link is not None:
        new["backstory_link"] = payload.link.model_dump()
    if payload.lifepath:
        new["lifepath"] = payload.lifepath
    touched = [k for k in new if new.get(k) != old.get(k)]
    if overwrite and touched:
        history = [h for h in old.get("backstory_history", []) if isinstance(h, dict)]
        history.append({
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "values": {k: old.get(k) for k in touched if k != "backstory_history"},
        })
        new["backstory_history"] = history[-HISTORY_LIMIT:]
    changes = [{"field": k, "before": old.get(k), "after": new.get(k)} for k in touched if k != "backstory_history"]
    return new, changes


def undo_backstory(sheet: dict[str, Any]) -> dict[str, Any] | None:
    """The sheet with its latest overwritten values restored, or None when there is nothing to undo."""
    history = [h for h in (sheet or {}).get("backstory_history", []) if isinstance(h, dict)]
    if not history:
        return None
    last = history[-1]
    restored = dict(sheet)
    for key, value in (last.get("values") or {}).items():
        if value is None:
            restored.pop(key, None)
        else:
            restored[key] = value
    restored["backstory_history"] = history[:-1]
    return restored


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/narrative")
async def draft_narrative(req: NarrativeRequest, current_user=Depends(get_current_user)):
    return await run_generation(write_narrative, req)


@router.post("/characters/{character_id}/apply")
def apply_to_character(character_id: int, req: ApplyRequest, current_user=Depends(get_current_user)):
    character = db.get_character_for_owner(character_id=character_id, owner_id=current_user.id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    new_sheet, changes = apply_backstory(character.sheet or {}, req.backstory, req.mode)
    if req.commit and changes:
        db.update_character(character_id=character_id, owner_id=current_user.id, updates={"sheet": new_sheet})
    return {"committed": bool(req.commit and changes), "changes": changes}


@router.post("/characters/{character_id}/undo")
def undo_on_character(character_id: int, current_user=Depends(get_current_user)):
    character = db.get_character_for_owner(character_id=character_id, owner_id=current_user.id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    restored = undo_backstory(character.sheet or {})
    if restored is None:
        raise HTTPException(status_code=409, detail="Nothing to undo")
    db.update_character(character_id=character_id, owner_id=current_user.id, updates={"sheet": restored})
    return {"ok": True}


@router.post("/campaigns/{campaign_id}/characters/{character_id}")
def keep_for_campaign(campaign_id: str, character_id: int, payload: BackstoryPayload, current_user=Depends(get_current_user)):
    """Keep a backstory for one campaign without touching the character's own sheet."""
    campaign = db.get_campaign_by_id(campaign_id)
    if not campaign or campaign.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    character = db.get_character_for_owner(character_id=character_id, owner_id=current_user.id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    meta = dict(campaign.metadata_json or {})
    fields = {k: getattr(payload, k).strip() for k in (*TEXT_FIELDS, "alignment", "patron") if getattr(payload, k).strip()}
    # The campaign has no sheet to put these on, so they go in the story text its contract and scenes read.
    labelled = "\n".join(f"{k.replace('_', ' ').capitalize()}: {v.replace(chr(10), '; ')}" for k, v in fields.items() if k != "patron")
    entry = {
        "character_id": str(character_id), "character_name": character.name,
        "backstory": "\n\n".join(p for p in (payload.backstory.strip(), labelled) if p),
        "fields": fields, "lifepath": payload.lifepath,
        "goals": _clean_goals(payload.goals), "allies": payload.allies, "rivals": payload.rivals, "patron": payload.patron,
        "link": payload.link.model_dump() if payload.link else None,
    }
    kept = [b for b in meta.get("player_backstories", []) if isinstance(b, dict) and str(b.get("character_id")) != str(character_id)]
    # An empty contract is rebuilt, with this backstory folded in, the next time the campaign is used.
    db.set_campaign_metadata_keys(campaign_id, current_user.id, {"player_backstories": [*kept, entry], "campaign_contract": {}})
    return {"ok": True}
