"""Conservative checks for concrete replies and continuity on player turns.

These are structural checks, not a claim to judge whether an answer is true.
The director must supply a per-action reply; the writer must actually use it.
"""
from __future__ import annotations

import re
from typing import Any

from .generation_intent import OpeningIntent, find_unsupported_claims, make_fact


def direct_question(action: str) -> bool:
    return bool(re.search(r"\b(?:ask|question)\b", action, re.I) or action.rstrip().endswith("?"))


def movement_destination(actions: list[str]) -> str:
    destination = ""
    for action in actions:
        match = re.search(
            r"\b(?:go|walk|head|travel|move|leave\s+.+?\s+and\s+go)\s+(?:out\s+)?to\s+(?:the\s+)?([^.!?\n]+)",
            action, re.I,
        )
        if match:
            destination = match.group(1).strip()
    return destination


def resolution_issues(actions: list[str], resolutions: list[dict[str, Any]]) -> list[str]:
    issues = []
    for index, action in enumerate(actions):
        if not direct_question(action):
            continue
        item = next((r for r in resolutions if r.get("action_index") == index), {})
        status = item.get("status")
        reply = str(item.get("reply") or "").strip()
        reason = str(item.get("reason") or "").strip()
        posture = re.search(r"\b(?:glances?|looks?|turns?|shifts?|shrugs?)\b.{0,40}\b(?:away|shoulder|posture|nervously|silence)\b", reply, re.I)
        if status not in {"answered", "cannot_answer"} or not reply or posture:
            issues.append(f"Question {index} requires an actual reply, not a reaction or posture description.")
        elif status == "cannot_answer" and not reason:
            issues.append(f"Question {index} requires an explicit reason the NPC cannot answer.")
    return issues


def continuation_issues(
    body: str, actions: list[str], resolutions: list[dict[str, Any]],
    *, known_names: list[str], allow_new_names: bool,
) -> list[str]:
    issues = resolution_issues(actions, resolutions)
    for index, action in enumerate(actions):
        if not direct_question(action):
            continue
        item = next((r for r in resolutions if r.get("action_index") == index), {})
        # Require verbatim dialogue so a vague paragraph cannot pass merely
        # because the director planned an answer that the writer never used.
        for key in ("reply", "reason") if item.get("status") == "cannot_answer" else ("reply",):
            value = str(item.get(key) or "").strip()
            if value and value.casefold() not in body.casefold():
                issues.append(f"Question {index}: include the planned {key} in the narration.")
    if not allow_new_names:
        intent = OpeningIntent(allowed_names=known_names)
        for name in known_names:
            intent.add(make_fact("actor", name, "confirmed_canon", confirmed_by="previous scene"))
        for claim in find_unsupported_claims(body, intent):
            if claim.get("kind") == "named_entity":
                issues.append(f"Stay with established people and places: unsupported name {claim['text']}.")
    return issues


def unavailable_reply(action: str, npc: str) -> dict[str, Any]:
    # Missing model output must not turn into an invented winding time, secret,
    # guilty reaction or a claim that this NPC already knows the solution.
    return {
        "status": "cannot_answer", "npc": npc or "the witness",
        "reply": "I can't give you a reliable answer to that.",
        "reason": "I don't have enough information to say.",
        "action": action,
    }
