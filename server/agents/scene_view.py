"""What a player can take in at a glance about the current scene.

The story text is the scene.  This module adds a small structured summary beside it (where and when, who is
visibly here, the one open question) so a client can show an orientation strip without parsing prose.  Every
field is derived from what the prose itself shows: a person is listed only if the story text names them, and
nothing is read from the GM-only fields (what an NPC knows or wants, hidden pressure, storyboards).
"""
from __future__ import annotations

import re
from typing import Any

MAX_PRESENT = 5
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _body(scene: dict) -> str:
    return _clean(scene.get("narrative_body") or scene.get("text"))


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text) if s.strip()]


def _name_and_role(value: Any) -> tuple[str, str]:
    """``"Ada Reed (clockmaker)"`` or ``{"name": ..., "role": ...}`` -> ``("Ada Reed", "clockmaker")``."""
    if isinstance(value, dict):
        name, role = _clean(value.get("name")), _clean(value.get("role") or value.get("occupation"))
    else:
        name, role = _clean(value), ""
    if "(" in name:
        base, _, rest = name.partition("(")
        name, role = _clean(base), role or _clean(rest.rstrip(") "))
    return name, role


def _named_in(name: str, body_lower: str) -> bool:
    """True when the story text names the person: by full name, or by a first or last name of three letters or more."""
    if not name:
        return False
    if name.lower() in body_lower:
        return True
    return any(len(part) >= 3 and re.search(rf"\b{re.escape(part.lower())}\b", body_lower) for part in name.split())


def _seen(name: str, sentences: list[str]) -> str:
    """The first sentence of the story that names the person, trimmed: what the player has actually seen them do."""
    parts = [p.lower() for p in name.split() if len(p) >= 3] + [name.lower()]
    for sentence in sentences:
        low = sentence.lower()
        if any(re.search(rf"\b{re.escape(p)}\b", low) for p in parts):
            return sentence if len(sentence) <= 140 else sentence[:137].rsplit(" ", 1)[0] + "..."
    return ""


def present_people(scene: dict) -> list[dict[str, str]]:
    """The people the story text names, with their role and what the story shows them doing."""
    body = _body(scene)
    low = body.lower()
    sentences = _sentences(body)
    director = _dict(scene.get("scene_director_data"))
    candidates = [director.get("primary_npc"), *(director.get("secondary_entities") or [])]
    candidates += list((scene.get("opening_scene") or {}).get("named_npcs") or [])
    people: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for candidate in candidates:
        name, role = _name_and_role(candidate)
        if not name or name.lower().startswith(("the nearest", "unnamed")) or name.lower() in seen_names:
            continue
        if not _named_in(name, low):
            continue  # not on stage in the prose: the player has not met them, so they are not listed
        seen_names.add(name.lower())
        people.append({"name": name, "role": role, "seen": _seen(name, sentences)})
    return people[:MAX_PRESENT]


def open_question(scene: dict) -> str:
    """The one question the scene leaves open, in the player's terms."""
    explicit = _clean(scene.get("open_question"))
    if explicit:
        return explicit
    director = _dict(scene.get("scene_director_data"))
    bundle = _dict(scene.get("content_bundle"))
    required = _dict(bundle.get("required_content"))
    for source in (scene.get("visible_clues"), director.get("player_visible_clues"), [required.get("first_clue_or_question")]):
        for item in source or []:
            text = _clean(item.get("text") if isinstance(item, dict) else item)
            if text.endswith("?"):
                return text
    return ""


def situation(scene: dict) -> str:
    """One line on what is going on right now, from the scene's own summary when it has one."""
    summary = _dict(scene.get("scene_summary"))
    for text in (summary.get("observed"), (scene.get("opening_scene") or {}).get("visible_problem")):
        text = _clean(text)
        if text:
            first = _sentences(text)[0]
            return first if len(first) <= 200 else first[:197].rsplit(" ", 1)[0] + "..."
    return ""


def build_scene_view(scene: Any) -> dict[str, Any]:
    """The orientation summary for ``scene``; empty values are simply omitted by the client."""
    if not isinstance(scene, dict):
        return {}
    place = scene.get("location")
    if isinstance(place, dict):
        place = place.get("name")
    return {
        "place": _clean(place),
        "time_of_day": _clean(scene.get("time_of_day")),
        "weather": _clean(scene.get("weather")),
        "situation": situation(scene),
        "present": present_people(scene),
        "hook": open_question(scene),
    }
