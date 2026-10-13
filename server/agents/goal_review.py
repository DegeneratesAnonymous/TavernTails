"""Goals during play: who wants what, what the story has moved, and the players' own decisions about them.

Proactive play lets players set their characters' goals and change them as the story does.  So nothing here
changes a goal on its own.  The model reads the recent story and *suggests* that a goal has moved, quoting the
words that show it (a suggestion with no quote that is really in the story is dropped), and only the character's
own player can apply a change.  Goals are shared with the table; backstory text is not.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db, steward_llm
from ..auth import get_current_user
from ..generation_workers import run_generation
from . import thread_weaver
from .generation_intent import clean_text
from .lifepath import GOAL_LIMIT, GOAL_STATUSES, _clean_goals, goal_id
from .premise_seed import parse_json_object
from .session_assist import _load

logger = logging.getLogger("taverntails.goal_review")
router = APIRouter(prefix="/sessions", tags=["goals"])

STATE_FILE = "goal_review.json"
STORY_CHARS = 3500
SUGGESTION_STATUSES = ("progressed", "done", "blocked")
ACTIVE_LIMIT = 6


def _members(meta: dict, user) -> list[tuple[Any, bool]]:
    out = []
    seen: set[int] = set()
    for member in meta.get("members") or []:
        try:
            char_id = int(str(member.get("character_id")))
        except ValueError:
            continue
        character = db.get_character_by_id(char_id)
        if character is not None and char_id not in seen:
            seen.add(char_id)
            out.append((character, character.owner_id == user.id))
    return out


def _campaign_entry(campaign_id: str | None, character_id: int) -> dict[str, Any] | None:
    """The campaign's own backstory for a character, when their player kept one for this campaign only."""
    campaign = db.get_campaign_by_id(str(campaign_id)) if campaign_id else None
    for entry in (campaign.metadata_json or {}).get("player_backstories", []) if campaign else []:
        if isinstance(entry, dict) and str(entry.get("character_id")) == str(character_id) and entry.get("goals"):
            return entry
    return None


def _sheet_goals(character, campaign_id: str | None = None) -> list[dict[str, str]]:
    """The goals in effect: the campaign's own copy when there is one (it overrides the sheet), else the sheet's."""
    entry = _campaign_entry(campaign_id, character.id)
    if entry is not None:
        return _clean_goals([g for g in entry["goals"] if isinstance(g, dict)])
    sheet = character.sheet if isinstance(character.sheet, dict) else {}
    return _clean_goals([g for g in sheet.get("goals", []) if isinstance(g, dict)])


def _narrations(folder: Path) -> list[str]:
    try:
        entries = json.loads((folder / "story.json").read_text())
    except (OSError, ValueError):
        return []
    return [str(e.get("text") or "") for e in entries if isinstance(e, dict) and e.get("type") == "narration"]


def _state(folder: Path) -> dict[str, Any]:
    try:
        data = json.loads((folder / STATE_FILE).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", text.casefold())).strip()


def check_suggestions(
    raw: dict[str, Any] | None, goals_by_character: dict[str, dict[str, dict[str, str]]], story: str,
    names: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Keep a suggestion only if it names a real active goal and quotes words that are really in the story.

    ``goals_by_character`` is keyed by character id.  A reply names its character by id; a name is accepted only
    when exactly one seated character has it.
    """
    kept: list[dict[str, Any]] = []
    haystack = _norm(story)
    for item in (raw or {}).get("updates") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id", "")).strip()
        if key not in goals_by_character:
            matches = (names or {}).get(clean_text(item.get("character")).casefold(), [])
            key = matches[0] if len(matches) == 1 else ""
        goal = goals_by_character.get(key, {}).get(clean_text(item.get("goal")).casefold())
        evidence = clean_text(item.get("evidence"))
        status = clean_text(item.get("status")).casefold()
        if goal and status in SUGGESTION_STATUSES and len(_norm(evidence)) >= 12 and _norm(evidence) in haystack:
            kept.append({"character_id": int(key), "goal_id": goal["id"], "goal": goal["text"], "status": status, "evidence": evidence[:200]})
    return kept


def suggest_updates(characters: list[Any], story: str, *, call=None, campaign_id: str | None = None) -> list[dict[str, Any]]:
    by_character: dict[str, dict[str, dict[str, str]]] = {}
    names: dict[str, list[str]] = {}
    lines = []
    for character in characters:
        active = [g for g in _sheet_goals(character, campaign_id) if g["status"] == "active"]
        if active:
            by_character[str(character.id)] = {g["text"].casefold(): g for g in active}
            names.setdefault(character.name.casefold(), []).append(str(character.id))
            lines.append(f"- id {character.id}, {character.name}: " + "; ".join(f"{g['term']} goal: {g['text']}" for g in active))
    if not lines or not story.strip():
        return []
    system = (
        "You help a tabletop group keep track of character goals. Read the recent story and say which goals it moved. "
        'Reply with ONLY JSON: {"updates":[{"id":<the character\'s id number>,"goal":"<the goal text, exactly as given>",'
        '"status":"progressed|done|blocked","evidence":"<a short exact quote from the story>"}]}. '
        "Only include a goal the story clearly moved. The quote must be copied from the story. Use [] if none."
    )
    user = "Goals:\n" + "\n".join(lines) + "\n\nStory:\n" + story
    ask = call or steward_llm.chat_complete
    try:
        raw = ask([{"role": "system", "content": system}, {"role": "user", "content": user}],
                  task_scope="taverntails_analysis", max_tokens=500, temperature=0.2, timeout=60.0)
    except Exception:
        logger.exception("goal review call failed")
        return []
    return check_suggestions(parse_json_object(str(raw or "")), by_character, story, names)


# ---------------------------------------------------------------------------
# Changing goals (only by the character's own player)
# ---------------------------------------------------------------------------

def _edit_goals(character, campaign_id: str | None, change) -> list[dict[str, str]]:
    """Apply ``change(goals) -> goals`` where the goals in effect live (the campaign's copy, else the sheet), then
    bring the character's stored story thread in line so scenes stop serving a goal that was just finished."""
    goals = change(_sheet_goals(character, campaign_id))
    if _campaign_entry(campaign_id, character.id) is not None and campaign_id:
        def mutate(meta: dict[str, Any]) -> None:
            entries = [dict(e) if isinstance(e, dict) else e for e in meta.get("player_backstories") or []]
            for entry in entries:
                if isinstance(entry, dict) and str(entry.get("character_id")) == str(character.id):
                    entry["goals"] = goals
            meta["player_backstories"] = entries
        db.update_campaign_metadata(campaign_id, mutate)
    else:
        db.update_character(character.id, character.owner_id, {"sheet_patch": {"goals": goals}})
    if campaign_id:
        thread_weaver.refresh_after_goal_change(campaign_id, character.id, goals)
    return goals


class ApplyBody(BaseModel):
    character_id: int
    goal_id: str = Field(max_length=16)
    status: Literal["active", "done", "dropped"]
    note: str = Field(default="", max_length=200)


class AddBody(BaseModel):
    character_id: int
    term: Literal["short", "mid", "long"] = "mid"
    text: str = Field(min_length=1, max_length=300)
    because: str = Field(default="", max_length=300)
    but: str = Field(default="", max_length=300)


def _own_character(meta: dict, user, character_id: int):
    for character, mine in _members(meta, user):
        if character.id == character_id:
            if not mine:
                raise HTTPException(status_code=403, detail="Only the character's player can change their goals")
            return character
    raise HTTPException(status_code=404, detail="Character not in this session")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/{session_id}/goals")
def get_goals(session_id: str, current_user=Depends(get_current_user)):
    folder, meta, _ = _load(session_id, current_user)
    since = max(0, len(_narrations(folder)) - int(_state(folder).get("narrations", 0)))
    return {
        "characters": [{"character_id": c.id, "name": c.name, "you": mine, "goals": _sheet_goals(c, meta.get("campaign_id"))} for c, mine in _members(meta, current_user)],
        "scenes_since_review": since,
    }


@router.post("/{session_id}/goals/review")
async def review_goals(session_id: str, current_user=Depends(get_current_user)):
    folder, meta, _ = _load(session_id, current_user)
    narrations = _narrations(folder)
    story = "\n\n".join(narrations[-8:])[-STORY_CHARS:]
    members = _members(meta, current_user)
    found = await run_generation(suggest_updates, [c for c, _mine in members], story, campaign_id=meta.get("campaign_id"))
    try:
        (folder / STATE_FILE).write_text(json.dumps({"narrations": len(narrations)}))
    except OSError:
        pass
    mine = {c.id for c, is_mine in members if is_mine}
    names = {c.id: c.name for c, _ in members}
    return {"suggestions": [{**s, "character": names.get(s["character_id"], ""), "you": s["character_id"] in mine} for s in found]}


@router.post("/{session_id}/goals/apply")
def apply_goal(session_id: str, body: ApplyBody, current_user=Depends(get_current_user)):
    _folder, meta, _ = _load(session_id, current_user)
    character = _own_character(meta, current_user, body.character_id)
    if body.goal_id not in {g["id"] for g in _sheet_goals(character, meta.get("campaign_id"))}:
        raise HTTPException(status_code=404, detail="Goal not found")

    def change(goals: list[dict[str, str]]) -> list[dict[str, str]]:
        return [{**g, "status": body.status, "note": body.note or g["note"]} if g["id"] == body.goal_id else g for g in goals]

    return {"goals": _edit_goals(character, meta.get("campaign_id"), change)}


@router.post("/{session_id}/goals/add")
def add_goal(session_id: str, body: AddBody, current_user=Depends(get_current_user)):
    _folder, meta, _ = _load(session_id, current_user)
    character = _own_character(meta, current_user, body.character_id)
    current = _sheet_goals(character, meta.get("campaign_id"))
    if sum(1 for g in current if g["status"] == "active") >= ACTIVE_LIMIT or len(current) >= GOAL_LIMIT:
        raise HTTPException(status_code=409, detail="That is plenty of goals at once. Finish or drop one first.")
    if goal_id(body.text) in {g["id"] for g in current}:
        raise HTTPException(status_code=409, detail="That goal is already on the list.")

    def change(goals: list[dict[str, str]]) -> list[dict[str, str]]:
        return [*goals, *_clean_goals([{"term": body.term, "text": body.text, "because": body.because, "but": body.but}])]

    return {"goals": _edit_goals(character, meta.get("campaign_id"), change)}


__all__ = ["GOAL_STATUSES", "router"]
