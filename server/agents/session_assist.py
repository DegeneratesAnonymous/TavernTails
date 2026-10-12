"""Help a player take in a scene and act on it, without giving the story away.

* ``suggest-action``  one action idea for the player's own character, put in their text box on request;
* ``notice``          what the player's character would pick up on, seen through who they are;
* ``recap``           where the story stands for someone returning to it;
* ``round``           who has acted and who is ready, so a table can see whom it is waiting for;
* ``table-safety``    pause, or ask the story to leave something out.

Everything here is built from what a player is already allowed to see (``player_view`` and the player's own
character).  The GM-only fields of a scene are used for one thing only: to *reject* a model's text that repeats
something the player has not been shown.
"""
from __future__ import annotations

import json
import logging
import re
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db, steward_llm
from ..auth import get_current_user
from ..realtime import broadcaster
from .scene_privacy import GM_ONLY_NPC_KEYS, GM_ONLY_SCENE_KEYS, player_view
from .sessions import BASE, _is_dm, _normalize_email, _require_session_member
from .table_state import table_safety

logger = logging.getLogger("taverntails.session_assist")
router = APIRouter(prefix="/sessions", tags=["session-assist"])

ANGLES = ("look", "person", "background", "cautious", "bold")
_ANGLE_RULES = {
    "look": "Study or examine one specific thing the story text describes.",
    "person": "Speak to one person who is present in the story text, using their name.",
    "background": "Act because of who this character is (their class, background or personality), tied to something in the scene.",
    "cautious": "A careful, low-risk way to find out more or to stay safe.",
    "bold": "A direct, decisive action.",
}
_CLASS_ACTIONS = {
    "rogue": "I check the exits and watch who looks nervous.",
    "fighter": "I take stock of who is armed and where I would stand if this turned violent.",
    "wizard": "I study the scene for anything out of place or unnatural.",
    "sorcerer": "I stay still and pay attention to anything that feels wrong in the air.",
    "warlock": "I listen for anything that does not belong, the way my patron taught me.",
    "cleric": "I take in the mood of the place and whether anyone here needs help.",
    "paladin": "I look for who is being wronged here and who is responsible.",
    "druid": "I notice what the animals, the weather and the plants are telling me.",
    "ranger": "I look for tracks, signs of passage and anything disturbed.",
    "bard": "I read the room: who is tense, who is hiding something, who wants to talk.",
    "monk": "I steady my breathing and look for where the calm here has broken.",
    "barbarian": "I watch for where a fight wants to start and who has a reason to start it.",
}
_MIN_WORDS, _MAX_WORDS = 3, 24
_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _words(text: str) -> set[str]:
    return {w.lower().strip("'’-") for w in _WORD.findall(text or "")}


# --- who is asking ---------------------------------------------------------------------------------------------

def _load(session_id: str, current_user) -> tuple[Path, dict, str]:
    folder = BASE / session_id
    meta_path = folder / "meta.json"
    if not folder.exists() or not meta_path.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail="Failed to read meta") from err
    return folder, meta, _require_session_member(meta, current_user)


def _read_scene(folder: Path) -> dict:
    try:
        scene = json.loads((folder / "scene.json").read_text())
    except Exception:
        scene = {}
    if not isinstance(scene, dict) or not (scene.get("narrative_body") or scene.get("text")) or scene.get("setup_pending"):
        raise HTTPException(status_code=409, detail="The scene is not ready yet")
    return scene


def _member(meta: dict, identifier: str) -> dict:
    for member in meta.get("members", []) or []:
        if _normalize_email(member.get("email")) == identifier:
            return member
    return {}


def character_for(member: dict) -> dict[str, str]:
    """The player's own character: what the player already knows about them."""
    out = {"name": _clean(member.get("character_name")), "class_name": "", "notes": ""}
    char_id = member.get("character_id")
    if isinstance(char_id, int):
        try:
            ch = db.get_character_by_id(char_id)
        except Exception:
            ch = None
        if ch:
            sheet = ch.sheet if isinstance(ch.sheet, dict) else {}
            out["name"] = _clean(ch.name) or out["name"]
            out["class_name"] = _clean(ch.class_name)
            out["notes"] = " ".join(
                _clean(sheet.get(k)) for k in ("backstory", "personality_traits", "ideals", "bonds", "flaws", "appearance")
            ).strip()
    return out


# --- keeping the story's secrets ------------------------------------------------------------------------------

def _strings(value: Any, depth: int = 0) -> list[str]:
    if depth > 4:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v, depth + 1)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings(v, depth + 1)]
    return []


def hidden_strings(scene: dict) -> list[str]:
    """Text in the scene that a player has not been shown (what NPCs know or want, hidden pressure, plans)."""
    out: list[str] = []
    for key in GM_ONLY_SCENE_KEYS:
        out += _strings(scene.get(key))
    director = scene.get("scene_director_data") if isinstance(scene.get("scene_director_data"), dict) else {}
    out += _strings(director.get("hidden_pressure"))
    npcs = [director.get("primary_npc"), *(director.get("secondary_entities") or [])]
    for npc in npcs:
        if isinstance(npc, dict):
            for key in GM_ONLY_NPC_KEYS:
                out += _strings(npc.get(key))
    return [s for s in out if len(s.split()) >= 2]


def visible_text(view: dict, character: dict[str, str]) -> str:
    """Everything the player can see or knows: the story text, who is present, the open question, their character."""
    sv = view.get("scene_view") or {}
    parts = [
        str(view.get("narrative_body") or view.get("text") or ""),
        " ".join(f"{p.get('name', '')} {p.get('role', '')}" for p in sv.get("present", [])),
        str(sv.get("hook") or ""), str(sv.get("situation") or ""), str(sv.get("place") or ""),
        " ".join(str(c) for c in (view.get("visible_clues") or [])),
        character.get("name", ""), character.get("class_name", ""), character.get("notes", ""),
    ]
    return " ".join(parts)


def check_suggestion(
    text: str, *, visible: str, hidden: list[str], first_person: bool = True, max_words: int = _MAX_WORDS,
) -> list[str]:
    """Why ``text`` must not be shown to the player; empty when it is safe and useful."""
    issues: list[str] = []
    value = _clean(text)
    n = len(value.split())
    if not value or n < _MIN_WORDS:
        return ["Too short."]
    if n > max_words:
        issues.append(f"Too long ({n} words); one short sentence.")
    if len(re.findall(r"[.!?](?:\s|$)", value)) > 2:
        issues.append("More than one sentence.")
    if first_person and not re.match(r"^[\"'“]?\s*I\b", value):
        issues.append("Write it in the first person, starting with 'I'.")
    vis = _words(visible)
    # A name or place the player has not met is a leak even if the model made it up.
    for match in re.finditer(r"(?<![.!?\"'“]\s)(?<!^)\b([A-Z][a-z]{2,})\b", value):
        word = match.group(1).lower()
        if word not in vis and word != "i":
            issues.append(f"Names something the story has not shown: {match.group(1)}.")
            break
    hidden_only: set[str] = set()
    for secret in hidden:
        hidden_only |= {w for w in _words(secret) if len(w) >= 5 and w not in vis}
    leaked = sorted(w for w in _words(value) if w in hidden_only)
    if leaked:
        issues.append("Uses something the player has not been shown: " + ", ".join(leaked[:3]) + ".")
    if re.search(r"\band (?:finds?|discovers?|learns?|realizes?|uncovers?) (?:that|the truth)\b", value, re.IGNORECASE):
        issues.append("States an outcome; describe what the character tries, not what they find.")
    return issues


def fallback_suggestion(angle: str, view: dict, character: dict[str, str]) -> str:
    """An action that needs no model: safe by construction, because it names only what the story text names."""
    present = (view.get("scene_view") or {}).get("present") or []
    name = _clean(present[0].get("name")) if present else ""
    if angle == "person" and name:
        return f"I ask {name} what they have seen."
    if angle == "bold":
        return f"I step up to {name} and say plainly why I am here." if name else "I step forward and make my presence known."
    if angle == "cautious":
        return "I hold back and watch for a moment before I commit to anything."
    if angle == "background":
        lens = _CLASS_ACTIONS.get((character.get("class_name") or "").split("/")[0].strip().lower())
        return lens or "I think about why I came here and let that guide what I do next."
    return "I take a slow look around and note anything that seems out of place."


def pick_angle(requested: str | None, view: dict, seed: str, previous: list[str]) -> str:
    """The kind of suggestion to give next: rotates so repeated clicks offer different directions."""
    has_person = bool((view.get("scene_view") or {}).get("present"))
    options = [a for a in ANGLES if a != "person" or has_person]
    if requested in options:
        return str(requested)
    return options[(zlib.crc32(seed.encode()) + len(previous)) % len(options)]


def _suggestion_messages(view: dict, character: dict[str, str], angle: str, previous: list[str], feedback: str) -> list[dict]:
    sv = view.get("scene_view") or {}
    who = character.get("name") or "the character"
    system = (
        f"You suggest ONE action that a player might want {who} to take next in a tabletop roleplaying scene. "
        "The player asked for an idea; they do not want the plot given away.\n"
        "Rules:\n"
        "- Write one short sentence (under 16 words) that starts with 'I' and a plain verb, for example 'I ask the "
        "clerk about the ledger' or 'I look closely at the door'. Never start with 'I will', 'I would' or 'I want'. "
        "It is what the character tries, never what they find or what happens.\n"
        "- Use ONLY things the story text below shows or that the character notes say. Do not name anyone or "
        "anything that is not in them, and do not hint at anything hidden.\n"
        f"- Kind of action wanted: {_ANGLE_RULES[angle]}\n"
        "- The character notes describe THIS character only; never attribute them to anyone else in the scene.\n"
        "- Do not repeat or lightly reword an earlier suggestion.\n"
        "Return only the sentence."
    )
    lines = ["STORY TEXT:", str(view.get("narrative_body") or view.get("text") or "")]
    if sv.get("present"):
        lines.append("PEOPLE PRESENT: " + "; ".join(f"{p['name']} ({p.get('role') or 'unknown'})" for p in sv["present"]))
    lines.append(f"CHARACTER: {who}" + (f", a {character['class_name']}" if character.get("class_name") else ""))
    if character.get("notes"):
        lines.append("CHARACTER NOTES: " + character["notes"][:500])
    if previous:
        lines.append("EARLIER SUGGESTIONS (do not repeat): " + " | ".join(previous[-5:]))
    if feedback:
        lines.append("YOUR LAST ATTEMPT WAS REJECTED: " + feedback)
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(lines)}]


def generate_suggestion(
    view: dict, character: dict[str, str], *, angle: str, previous: list[str], hidden: list[str], attempts: int = 2,
) -> tuple[str, str]:
    """``(suggestion, source)``: a model draft that passed the checks, else a safe deterministic action."""
    visible = visible_text(view, character)
    feedback = ""
    for _ in range(max(1, attempts)):
        try:
            raw = steward_llm.chat_complete(
                _suggestion_messages(view, character, angle, previous, feedback),
                task_scope="taverntails_suggest", max_tokens=70, temperature=0.9, timeout=45.0,
            )
        except Exception:
            logger.exception("suggestion call failed")
            break
        draft = _clean(str(raw or "").strip().strip('"“”'))
        if not draft:
            break
        issues = check_suggestion(draft, visible=visible, hidden=hidden)
        if draft.lower() in {p.lower() for p in previous}:
            issues.append("Repeats an earlier suggestion.")
        if not issues:
            return draft, "model"
        feedback = " ".join(issues)
    return fallback_suggestion(angle, view, character), "fallback"


class SuggestRequest(BaseModel):
    previous: list[str] = Field(default_factory=list, max_length=10)
    angle: str | None = None


@router.post("/{session_id}/suggest-action")
def suggest_action(session_id: str, req: SuggestRequest, current_user=Depends(get_current_user)):
    """One action idea for the caller's own character, shown only when asked for."""
    folder, meta, identifier = _load(session_id, current_user)
    scene = _read_scene(folder)
    view = player_view(scene)
    character = character_for(_member(meta, identifier))
    previous = [_clean(p) for p in req.previous if _clean(p)]
    angle = pick_angle(req.angle, view, f"{scene.get('id', '')}:{identifier}", previous)
    suggestion, source = generate_suggestion(
        view, character, angle=angle, previous=previous, hidden=hidden_strings(scene),
    )
    return {"suggestion": suggestion, "angle": angle, "source": source}


# --- what this character notices ------------------------------------------------------------------------------

def _notice_messages(view: dict, character: dict[str, str], feedback: str) -> list[dict]:
    from .narrative import _CLASS_PERSPECTIVE

    who = character.get("name") or "the character"
    lens = _CLASS_PERSPECTIVE.get((character.get("class_name") or "").split("/")[0].strip().lower(), "")
    system = (
        f"In ONE sentence, in the second person ('You notice...'), say what {who} picks up on in this scene "
        "because of who they are. Use ONLY details already in the story text; add no new facts, names or events, and "
        "do not explain or solve anything. Return only the sentences."
    )
    user = "STORY TEXT:\n" + str(view.get("narrative_body") or view.get("text") or "")
    user += f"\nCHARACTER: {who}" + (f", a {character['class_name']} who {lens}" if lens else "")
    if character.get("notes"):
        user += "\nCHARACTER NOTES: " + character["notes"][:400]
    if feedback:
        user += "\nYOUR LAST ATTEMPT WAS REJECTED: " + feedback
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def generate_notice(view: dict, character: dict[str, str], hidden: list[str]) -> str:
    """What the character notices, or ``""`` when there is no character or no draft passed the checks."""
    if not character.get("name") or character["name"].lower() == "the party":
        return ""
    visible = visible_text(view, character)
    feedback = ""
    for _ in range(2):
        try:
            raw = steward_llm.chat_complete(
                _notice_messages(view, character, feedback), task_scope="taverntails_suggest",
                max_tokens=90, temperature=0.8, timeout=45.0,
            )
        except Exception:
            logger.exception("notice call failed")
            return ""
        draft = _clean(str(raw or "").strip().strip('"“”'))
        if not draft:
            return ""
        issues = check_suggestion(draft, visible=visible, hidden=hidden, first_person=False, max_words=45)
        issues = [i for i in issues if not i.startswith("More than one sentence")]
        if not draft.lower().startswith("you "):
            issues.append("Start with 'You notice'.")
        if not issues:
            return draft
        feedback = " ".join(issues)
    return ""


@router.post("/{session_id}/notice")
def notice(session_id: str, current_user=Depends(get_current_user)):
    """What the caller's character picks up on in the current scene (made once per scene and character)."""
    folder, meta, identifier = _load(session_id, current_user)
    scene = _read_scene(folder)
    key = f"{scene.get('id', '')}:{identifier}"
    cache_path = folder / "notices.json"
    try:
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    except Exception:
        cache = {}
    if key in cache:
        return {"notice": cache[key], "cached": True}
    text = generate_notice(
        player_view(scene), character_for(_member(meta, identifier)), hidden_strings(scene),
    )
    cache[key] = text
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(list(cache.items())[-40:])))
    tmp.replace(cache_path)
    return {"notice": text, "cached": False}


# --- coming back to the story ----------------------------------------------------------------------------------

def _first_sentences(text: str, count: int = 2, limit: int = 220) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", _clean(text))
    out = " ".join(sentences[:count])
    return out if len(out) <= limit else out[: limit - 3].rsplit(" ", 1)[0] + "..."


def build_recap(folder: Path, scene: dict, meta: dict, character: dict[str, str]) -> dict[str, Any]:
    """Where the story stands: what happened before, what is going on now, who is here, what is open."""
    view = player_view(scene)
    sv = view.get("scene_view") or {}
    try:
        entries = json.loads((folder / "story.json").read_text())
    except Exception:
        entries = []
    current = _clean(scene.get("text") or scene.get("narrative_body"))
    earlier = [
        _first_sentences(e.get("text", ""))
        for e in entries
        if isinstance(e, dict) and e.get("type") == "narration" and _clean(e.get("text")) and _clean(e.get("text")) != current
    ]
    last_played = None
    for name in ("scene.json", "story.json"):
        try:
            stamp = datetime.fromtimestamp((folder / name).stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            continue
        last_played = max(filter(None, [last_played, stamp]))
    return {
        "title": _clean(meta.get("name")),
        "character": character.get("name") or "",
        "previously": [e for e in earlier[-3:] if e],
        "right_now": sv.get("situation") or _first_sentences(current, 2),
        "place": sv.get("place") or "",
        "present": sv.get("present") or [],
        "open_question": sv.get("hook") or "",
        "last_played_at": last_played,
    }


@router.get("/{session_id}/recap")
def recap(session_id: str, current_user=Depends(get_current_user)):
    folder, meta, identifier = _load(session_id, current_user)
    return build_recap(folder, _read_scene(folder), meta, character_for(_member(meta, identifier)))


# --- who has acted this round ----------------------------------------------------------------------------------

def round_status(folder: Path, meta: dict, scene: dict) -> dict[str, Any]:
    """Who has said what they do this round, and who has said they are done: the table can see whom it waits for."""
    cursor = int(scene.get("last_resolved_message_id") or 0)
    messages = db.list_chat_messages(session_id=meta.get("id") or folder.name, limit=None, after_id=cursor)
    acted: dict[int, int] = {}
    for m in messages:
        if m.role in ("gm", "narrator", "system") or not _clean(m.message) or m.sender_id is None:
            continue
        acted[m.sender_id] = acted.get(m.sender_id, 0) + 1
    try:
        ready = json.loads((folder / "ready.json").read_text())
    except Exception:
        ready = {}
    members = []
    for member in meta.get("members", []) or []:
        email = _normalize_email(member.get("email"))
        user = db.get_user_by_identifier(email) if email else None
        uid = getattr(user, "id", None)
        members.append({
            "name": _clean(member.get("character_name")) or _clean(getattr(user, "username", "")) or email,
            "acted": bool(uid is not None and acted.get(uid)),
            "actions": acted.get(uid, 0) if uid is not None else 0,
            "ready": bool(ready.get(email)),
        })
    safety = table_safety(meta)
    return {
        "members": members,
        "paused": bool(safety.get("paused")),
        "avoid": list(safety.get("avoid") or []),
        "waiting_on": [m["name"] for m in members if not m["ready"]],
        "quiet": [m["name"] for m in members if not m["acted"]],
        "all_ready": bool(members) and all(m["ready"] for m in members),
    }


@router.get("/{session_id}/round")
def round_view(session_id: str, current_user=Depends(get_current_user)):
    folder, meta, _ = _load(session_id, current_user)
    try:
        scene = json.loads((folder / "scene.json").read_text())
    except Exception:
        scene = {}
    return round_status(folder, meta, scene if isinstance(scene, dict) else {})


# --- table safety ----------------------------------------------------------------------------------------------

class SafetyRequest(BaseModel):
    kind: str = Field(..., pattern="^(pause|resume|skip|soften)$")
    topic: str = Field("", max_length=120)




@router.post("/{session_id}/table-safety")
async def set_table_safety(session_id: str, req: SafetyRequest, current_user=Depends(get_current_user)):
    """Any player can pause the table or ask the story to leave something out; the DM can resume."""
    folder, meta, identifier = _load(session_id, current_user)
    safety = {**{"avoid": [], "events": [], "paused": False}, **table_safety(meta)}
    topic = _clean(req.topic)
    member = _member(meta, identifier)
    who = _clean(member.get("character_name")) or _clean(getattr(current_user, "username", "")) or identifier
    if req.kind == "resume":
        if safety.get("paused") and not (_is_dm(meta, current_user) or identifier == _normalize_email(meta.get("owner"))):
            raise HTTPException(status_code=403, detail="Only the owner or DM can resume the table")
        safety["paused"] = False
    elif req.kind == "pause":
        safety["paused"] = True
    else:
        safety["avoid"] = list(dict.fromkeys([*safety.get("avoid", []), topic or "what was just described"]))[-12:]
    safety["events"] = [*safety.get("events", []), {"by": who, "kind": req.kind, "topic": topic, "at": datetime.now(timezone.utc).isoformat()}][-50:]
    meta["table_safety"] = safety
    meta_path = folder / "meta.json"
    tmp = meta_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta))
    tmp.replace(meta_path)
    note = {
        "pause": f"{who} paused the table.", "resume": "The table has resumed.",
        "skip": f"{who} asked the story to leave that out.", "soften": f"{who} asked the story to soften that.",
    }[req.kind]
    try:
        db.log_chat_message(note, session_id=session_id, campaign_id=meta.get("campaign_id"), role="system", sender_name="Table")
    except Exception:
        logger.exception("could not log the table safety note")
    await broadcaster.broadcast_json(session_id, {
        "type": "table.safety", "session_id": session_id, "kind": req.kind, "paused": safety["paused"], "message": note,
    })
    return {"ok": True, "paused": safety["paused"], "avoid": safety["avoid"], "message": note}
