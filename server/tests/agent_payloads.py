"""Reusable example payloads for agent contract tests.

These mirror the structures documented in TavernTAIls_Enhanced_Project_Plan.md so
pytest suites, docs, or API explorers can import the same fixtures.
"""

from __future__ import annotations

from typing import Any

NARRATIVE_REQUEST: dict[str, Any] = {
    "scene": "Rain lashes the watchtower parapet",
    "player": "Aria",
    "style": "cinematic heroism",
    "weather": "stormy",
    "time_of_day": "night",
}

SCENE_REQUEST: dict[str, Any] = {
    "scene": "Negotiations stall as blades emerge under the table",
    "actions": [
        "I persuade the envoy to calm down",
        "I scan the exits for ambushers",
    ],
    "session_id": "scene-session",
}

NPC_REQUEST: dict[str, Any] = {
    "name": "Captain Brex",
    "traits": {"faction": "Emerald Vigil"},
    "motivations": ["Protect the vault", "Expose traitors"],
    "stats": {"initiative": 3, "hp": 28},
    "quirks": ["Adjusts monocle when lying"],
    "classes": [
        {"name": "Soldier", "level": 5, "subclass": "Veteran"},
    ],
    "abilities": [
        {"name": "Tactical Command", "description": "Grants an ally a bonus action.", "tags": ["support", "combat"]},
    ],
    "spells": [],
    "session_id": "npc-session",
}

STORYBOARD_REQUEST: dict[str, Any] = {
    "scene": "City Square after the riot",
    "choices": ["Appease the crowd", "Search for agitators"],
    "unresolved": ["Who armed the saboteurs?"],
    "completed": ["Defused the bomb"],
}

NOTES_REQUEST: dict[str, Any] = {
    "session_id": "session-123",
    "notes": [
        "Met with the guild",
        "Accepted the heist",
        "Agreed on midnight rendezvous",
    ],
}

IMAGE_REQUEST: dict[str, Any] = {
    "prompt": "Moonlit battle on a bridge",
    "style": "comic",
}

AGENT_PAYLOADS: dict[str, dict[str, Any]] = {
    "narrative": NARRATIVE_REQUEST,
    "scene": SCENE_REQUEST,
    "npc": NPC_REQUEST,
    "storyboard": STORYBOARD_REQUEST,
    "notes": NOTES_REQUEST,
    "image": IMAGE_REQUEST,
}

__all__: list[str] = [
    "NARRATIVE_REQUEST",
    "SCENE_REQUEST",
    "NPC_REQUEST",
    "STORYBOARD_REQUEST",
    "NOTES_REQUEST",
    "IMAGE_REQUEST",
    "AGENT_PAYLOADS",
]
