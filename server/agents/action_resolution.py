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


def _question_issues(
    actions: list[str], resolutions: list[dict[str, Any]], body: str | None = None,
) -> list[str]:
    # First resolution wins, matching the director's existing ordering policy.
    by_index = {
        item["action_index"]: item for item in reversed(resolutions)
        if isinstance(item.get("action_index"), (int, float))
    }
    folded_body = body.casefold() if body is not None else None
    issues = []
    missing_lines = []
    for index, action in enumerate(actions):
        if not direct_question(action):
            continue
        item = by_index.get(index, {})
        status = item.get("status")
        reply = str(item.get("reply") or "").strip()
        reason = str(item.get("reason") or "").strip()
        posture = re.search(r"\b(?:glances?|looks?|turns?|shifts?|shrugs?)\b.{0,40}\b(?:away|shoulder|posture|nervously|silence)\b", reply, re.I)
        if status not in {"answered", "cannot_answer"} or not reply or posture:
            issues.append(f"Question {index} requires an actual reply, not a reaction or posture description.")
        elif status == "cannot_answer" and not reason:
            issues.append(f"Question {index} requires an explicit reason the NPC cannot answer.")
        # Planned dialogue must appear in the prose, not only in director data.
        if folded_body is not None:
            keys = ("reply", "reason") if status == "cannot_answer" else ("reply",)
            for key in keys:
                value = str(item.get(key) or "").strip()
                if value and value.casefold() not in folded_body:
                    missing_lines.append(f"Question {index}: include the planned {key} in the narration.")
    return issues + missing_lines


def resolution_issues(actions: list[str], resolutions: list[dict[str, Any]]) -> list[str]:
    return _question_issues(actions, resolutions)


def continuation_issues(
    body: str, actions: list[str], resolutions: list[dict[str, Any]],
    *, known_names: list[str], allow_new_names: bool,
) -> list[str]:
    issues = _question_issues(actions, resolutions, body)
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
