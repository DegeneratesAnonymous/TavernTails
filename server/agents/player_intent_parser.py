"""Player intent parser for scene advancement."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


class PlayerIntent(BaseModel):
    declared_actions: list[str] = Field(default_factory=list)
    implied_intents: list[str] = Field(default_factory=list)
    target_entities: list[str] = Field(default_factory=list)
    requested_mode: str = "other"
    risk_level: str = "low"
    time_commitment: str = "scene"
    likely_checks: list[str] = Field(default_factory=list)
    requires_roll: bool = False


_MODE_PATTERNS: list[tuple[str, re.Pattern[str], list[str]]] = [
    ("fight", re.compile(r"\b(attack|strike|shoot|fight|charge|cast .*fire|draw .*weapon)\b", re.I), ["Attack"]),
    ("investigate", re.compile(r"\b(search|inspect|investigate|examine|look for|track|study|analyze|analyse)\b", re.I), ["Perception", "Investigation"]),
    ("talk", re.compile(r"\b(talk|ask|persuade|convince|negotiate|interrogate|threaten|lie|deceive)\b", re.I), ["Persuasion", "Insight"]),
    ("travel", re.compile(r"\b(go to|head to|travel|leave|ride|march|return to|press on)\b", re.I), []),
    ("rest", re.compile(r"\b(rest|sleep|camp|long rest|short rest|recover)\b", re.I), []),
    ("shop", re.compile(r"\b(buy|sell|shop|trade|barter|haggle)\b", re.I), ["Persuasion"]),
    ("cast_spell", re.compile(r"\b(cast|spell|ritual|magic|cantrip)\b", re.I), ["Arcana"]),
    ("use_item", re.compile(r"\b(use|drink|open|unlock|activate|equip)\b", re.I), []),
    ("wait", re.compile(r"\b(wait|watch|hold position|observe|listen)\b", re.I), ["Perception"]),
]


def parse_player_intent(
    recent_player_chat: list[str],
    selected_character: dict[str, Any] | None = None,
    current_scene: dict[str, Any] | None = None,
    pending_rolls: list[dict[str, Any]] | None = None,
    active_situation: str = "",
) -> PlayerIntent:
    actions = [str(a).strip() for a in recent_player_chat if str(a).strip()]
    text = " ".join(actions[-5:])
    mode = "other"
    checks: list[str] = []
    for candidate, pattern, candidate_checks in _MODE_PATTERNS:
        if pattern.search(text):
            mode = candidate
            checks.extend(candidate_checks)
            break
    targets = _extract_targets(text, current_scene or {})
    risk = "high" if mode in {"fight", "cast_spell"} else "medium" if mode in {"travel", "investigate", "talk"} else "low"
    if any(term in text.lower() for term in ("carefully", "slowly", "take time", "thorough")):
        time_commitment = "extended"
    elif mode in {"fight", "use_item", "cast_spell"}:
        time_commitment = "immediate"
    else:
        time_commitment = "scene"
    pending = pending_rolls or []
    requires_roll = bool(checks or pending)
    intents = []
    if mode != "other":
        intents.append(f"player wants to {mode.replace('_', ' ')}")
    if active_situation:
        intents.append(f"active situation: {active_situation}")
    if selected_character and selected_character.get("name"):
        intents.append(f"acting character: {selected_character['name']}")
    return PlayerIntent(
        declared_actions=actions,
        implied_intents=intents,
        target_entities=targets,
        requested_mode=mode,
        risk_level=risk,
        time_commitment=time_commitment,
        likely_checks=list(dict.fromkeys(checks + [str(r.get("skill")) for r in pending if isinstance(r, dict) and r.get("skill")])),
        requires_roll=requires_roll,
    )


def _extract_targets(text: str, scene: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    for name in [
        scene.get("location"),
        ((scene.get("scene_director_data") or {}).get("location") or {}).get("name"),
        ((scene.get("scene_director_data") or {}).get("primary_npc") or {}).get("name"),
        *(scene.get("active_threads") or []),
        *(scene.get("visible_clues") or []),
    ]:
        if name and str(name).lower() in text.lower():
            targets.append(str(name))
    proper = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", text)
    targets.extend(proper[:4])
    return list(dict.fromkeys(targets))
