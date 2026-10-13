"""Braid the B plots into the main story: every few scenes, one character's own thread is moved forward.

The default scene serves the main trouble (the A plot).  A character's backstory thread is not allowed to take
over, and is not allowed to be forgotten either: after ``EVERY`` scenes without one, the next scene is asked to
advance one character's thread (taking turns) while the main trouble stays present in it.  Whether a scene did
touch a thread is checked against the text, so a scene that ignored the request does not reset the count.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .generation_intent import clean_text, content_tokens
from .thread_weaver import b_plot_rows

EVERY = 3  # a thread beat in at most one scene out of this many
STATE_FILE = "b_plot_state.json"


def _load(folder: Path) -> dict[str, Any]:
    try:
        data = json.loads((folder / STATE_FILE).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(folder: Path, state: dict[str, Any]) -> None:
    try:
        (folder / STATE_FILE).write_text(json.dumps(state))
    except OSError:
        pass


def _roster(folder: Path) -> list[int]:
    """The character ids seated in this session, so another session's characters are never brought into its scenes."""
    try:
        members = json.loads((folder / "meta.json").read_text()).get("members") or []
    except (OSError, ValueError):
        return []
    ids: list[int] = []
    for member in members:
        try:
            ids.append(int(str(member.get("character_id"))))
        except ValueError:
            continue
    return ids


def next_b_beat(folder: Path, campaign_id: str) -> dict[str, str] | None:
    """The thread to advance in the coming scene, or None when this scene belongs to the main trouble."""
    state = _load(folder)
    if int(state.get("since_b", 0)) < EVERY - 1:
        return None
    rows = sorted(b_plot_rows(campaign_id, _roster(folder)), key=lambda r: str(r.data.get("character_id")))
    if not rows:
        return None
    row = rows[int(state.get("turn", 0)) % len(rows)]
    data = row.data or {}
    return {
        "character": row.name.removesuffix("'s story"),
        "character_id": str(data.get("character_id", "")),
        "goal": str(data.get("primary_goal", "")),
        "beat": str(data.get("next_recommended_dm_move", "")),
    }


def guidance(beat: dict[str, str]) -> str:
    return (
        f"Also move {beat['character']}'s own story forward in this scene, without dropping the main trouble: "
        f"{beat['beat']} (their goal: {beat['goal']})"
    )


def touched(scene_text: str, beat: dict[str, str]) -> bool:
    """True when the scene names the character and uses a word from their goal or the suggested beat."""
    text = scene_text or ""
    if not beat.get("character") or beat["character"].casefold() not in text.casefold():
        return False
    wanted = content_tokens(clean_text(beat.get("goal", "")) + " " + clean_text(beat.get("beat", "")))
    return not wanted or bool(wanted & content_tokens(text))


def record_scene(folder: Path, scene_text: str, beat: dict[str, str] | None) -> None:
    """Count the scene.  A requested thread beat resets the count only if the scene really touched the thread."""
    state = _load(folder)
    if beat and touched(scene_text, beat):
        state.update({"since_b": 0, "turn": int(state.get("turn", 0)) + 1})
    else:
        state["since_b"] = int(state.get("since_b", 0)) + 1
    _save(folder, state)
