"""Situation Classifier — determines the current gameplay situation type.

Entirely deterministic. No LLM calls. Fast enough to run on every advance_scene.
Input signals are layered: keyword rules first, then world-state rules, then
director-output refinement. The classifier degrades gracefully when fields are absent.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Situation type registry
# ---------------------------------------------------------------------------

SITUATION_TYPES: frozenset[str] = frozenset({
    "campaign_opening",
    "new_scene_opening",
    "travel",
    "arrival",
    "conversation",
    "interrogation",
    "investigation",
    "combat_setup",
    "combat_round",
    "combat_resolution",
    "social_conflict",
    "downtime",
    "shopping",
    "rest",
    "discovery",
    "mystery_reveal",
    "faction_move",
    "consequence",
    "return_to_known_location",
    "npc_reappearance",
    "quest_offer",
    "quest_turn_in",
    "session_recap",
    "session_end",
})

# These situation types require a content contract before narration may proceed
REQUIRES_CONTRACT: frozenset[str] = frozenset({
    "campaign_opening",
    "new_scene_opening",
    "combat_setup",
    "combat_round",
    "interrogation",
    "investigation",
    "travel",
    "return_to_known_location",
    "npc_reappearance",
    "discovery",
})

# ---------------------------------------------------------------------------
# Keyword patterns for player action classification
# ---------------------------------------------------------------------------

_COMBAT_KEYWORDS = re.compile(
    r"\b(attack|fight|charge|strike|swing|shoot|cast.*spell|kill|slay|battle|"
    r"initiative|ambush|draw.*weapon|ready.*weapon|engage|combat)\b",
    re.IGNORECASE,
)
_TRAVEL_KEYWORDS = re.compile(
    r"\b(travel|head to|go to|move to|journey|ride|walk|march|leave|depart|"
    r"set out|make for|press on|continue toward|cross the)\b",
    re.IGNORECASE,
)
_RETURN_KEYWORDS = re.compile(
    r"\b(return|go back|head back|come back|revisit|return to)\b",
    re.IGNORECASE,
)
_INVESTIGATE_KEYWORDS = re.compile(
    r"\b(investigate|search|examine|inspect|look for|look around|check|"
    r"find clue|find evidence|study|analyse|analyze|uncover|discover|"
    r"follow the trail|track)\b",
    re.IGNORECASE,
)
_INTERROGATION_KEYWORDS = re.compile(
    r"\b(interrogate|question|press|intimidate|persuade|convince|threaten|"
    r"extract.*information|get.*truth|demand.*answer|break.*silence)\b",
    re.IGNORECASE,
)
_CONVERSATION_KEYWORDS = re.compile(
    r"\b(talk|speak|ask|say|tell|discuss|approach|greet|introduce|negotiate|"
    r"chat|converse|query|inquire)\b",
    re.IGNORECASE,
)
_REST_KEYWORDS = re.compile(
    r"\b(rest|sleep|camp|make camp|short rest|long rest|recover|recuperate|"
    r"take a break|set up camp)\b",
    re.IGNORECASE,
)
_SHOPPING_KEYWORDS = re.compile(
    r"\b(buy|purchase|sell|shop|trade|barter|browse|market|vendor|merchant|"
    r"acquire|procure|haggle)\b",
    re.IGNORECASE,
)
_DOWNTIME_KEYWORDS = re.compile(
    r"\b(downtime|craft|brew|train|study|research|carousing|practice|"
    r"write.*journal|meet.*contact|gather.*information)\b",
    re.IGNORECASE,
)
_DISCOVERY_KEYWORDS = re.compile(
    r"\b(discover|find|uncover|reveal|open.*door|open.*chest|unlock|"
    r"stumble upon|come across|notice)\b",
    re.IGNORECASE,
)

# Director scene type → situation type mapping
_DIRECTOR_TO_SITUATION: dict[str, str] = {
    "Combat": "combat_setup",
    "Investigation": "investigation",
    "Social": "conversation",
    "Revelation": "mystery_reveal",
    "Resolution": "consequence",
    "Exploration": "new_scene_opening",
    "Downtime": "downtime",
    "Travel": "travel",
    "Rest": "rest",
    "Shopping": "shopping",
    "Discovery": "discovery",
}

# Experience mode → situation type mapping (from simulation)
_EXPERIENCE_MODE_TO_SITUATION: dict[str, str] = {
    "combat_imminent": "combat_setup",
    "combat_round": "combat_round",
    "investigation": "investigation",
    "dramatic_reveal": "mystery_reveal",
    "downtime": "downtime",
    "quiet_scene": "new_scene_opening",
    "chapter_transition": "new_scene_opening",
}

# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

def _action_signal(player_actions: list[str]) -> tuple[str, float]:
    """Return the strongest situation signal from player action text."""
    text = " ".join(player_actions[-5:])  # most recent 5 actions

    # Priority-ordered checks
    checks = [
        (_COMBAT_KEYWORDS, "combat_setup", 0.90),
        (_INTERROGATION_KEYWORDS, "interrogation", 0.88),
        (_RETURN_KEYWORDS, "return_to_known_location", 0.85),
        (_INVESTIGATE_KEYWORDS, "investigation", 0.82),
        (_TRAVEL_KEYWORDS, "travel", 0.82),
        (_REST_KEYWORDS, "rest", 0.80),
        (_SHOPPING_KEYWORDS, "shopping", 0.78),
        (_DOWNTIME_KEYWORDS, "downtime", 0.75),
        (_DISCOVERY_KEYWORDS, "discovery", 0.72),
        (_CONVERSATION_KEYWORDS, "conversation", 0.65),
    ]
    for pattern, situation_type, confidence in checks:
        if pattern.search(text):
            return situation_type, confidence
    return "", 0.0


def _delta_signal(simulation_delta: dict[str, Any]) -> tuple[str, float]:
    """Infer situation from the world simulation delta."""
    if simulation_delta.get("threat_updates"):
        return "consequence", 0.70
    if simulation_delta.get("faction_advances"):
        return "faction_move", 0.72
    if simulation_delta.get("npc_movements"):
        return "npc_reappearance", 0.65
    if simulation_delta.get("consequences_triggered"):
        return "consequence", 0.80
    if simulation_delta.get("quest_updates"):
        return "quest_offer", 0.60
    return "", 0.0


def _scene_history_signal(previous_scene: dict[str, Any] | None) -> tuple[str, float]:
    """Refine classification using previous scene context."""
    if not previous_scene:
        return "", 0.0
    prev_type = previous_scene.get("situation_type", "")
    if prev_type == "travel":
        return "arrival", 0.88
    if prev_type == "combat_setup":
        return "combat_round", 0.85
    if prev_type == "combat_round":
        # Could stay in combat_round or transition to combat_resolution
        # Resolution if no active threats remain
        content_bundle = previous_scene.get("content_bundle", {})
        enemies = (content_bundle.get("combatants") or [])
        if enemies and all(e.get("hp", 1) <= 0 for e in enemies):
            return "combat_resolution", 0.85
        return "combat_round", 0.78
    return "", 0.0


def classify_situation(
    player_actions: list[str],
    previous_scene: dict[str, Any] | None = None,
    world_state: dict[str, Any] | None = None,
    simulation_delta: dict[str, Any] | None = None,
    experience_mode: str = "",
    director_scene_type: str = "",
    scene_count: int = 0,
) -> dict[str, Any]:
    """Classify the current gameplay situation.

    Returns::

        {
            "situation_type": str,
            "confidence": float,
            "reason": str,
            "secondary_situation_types": list[str],
            "requires_content_contract": bool,
        }
    """
    world_state = world_state or {}
    simulation_delta = simulation_delta or {}
    player_actions = [a for a in (player_actions or []) if a]

    # --- Layer 1: Hard-code first-scene detection ---
    if scene_count == 0 and not previous_scene:
        return {
            "situation_type": "campaign_opening",
            "confidence": 1.0,
            "reason": "First scene of campaign — no previous scene exists",
            "secondary_situation_types": [],
            "requires_content_contract": True,
        }

    candidates: dict[str, float] = {}
    reasons: list[str] = []

    # --- Layer 2: Player action keyword signal ---
    action_type, action_conf = _action_signal(player_actions)
    if action_type:
        candidates[action_type] = max(candidates.get(action_type, 0.0), action_conf)
        reasons.append(f"player action matched {action_type} keywords")

    # --- Layer 3: Experience mode from simulation ---
    if experience_mode and experience_mode in _EXPERIENCE_MODE_TO_SITUATION:
        exp_type = _EXPERIENCE_MODE_TO_SITUATION[experience_mode]
        candidates[exp_type] = max(candidates.get(exp_type, 0.0), 0.75)
        reasons.append(f"experience_mode={experience_mode}")

    # --- Layer 4: Narrative Director scene type ---
    if director_scene_type and director_scene_type in _DIRECTOR_TO_SITUATION:
        dir_type = _DIRECTOR_TO_SITUATION[director_scene_type]
        candidates[dir_type] = max(candidates.get(dir_type, 0.0), 0.70)
        reasons.append(f"director_scene_type={director_scene_type}")

    # --- Layer 5: Simulation delta signals ---
    delta_type, delta_conf = _delta_signal(simulation_delta)
    if delta_type:
        candidates[delta_type] = max(candidates.get(delta_type, 0.0), delta_conf)
        reasons.append(f"simulation_delta has {delta_type} signals")

    # --- Layer 6: Previous scene refinement ---
    history_type, history_conf = _scene_history_signal(previous_scene)
    if history_type:
        # Give previous-scene continuation a bonus when action confirms direction
        if history_type in candidates:
            candidates[history_type] = min(candidates[history_type] + 0.10, 0.95)
        else:
            candidates[history_type] = history_conf
        reasons.append(f"continuing from previous {previous_scene.get('situation_type', 'scene')}")

    # --- Fallback ---
    if not candidates:
        sit_type = "new_scene_opening"
        reasons.append("no strong signals — defaulting to new_scene_opening")
        return {
            "situation_type": sit_type,
            "confidence": 0.45,
            "reason": "; ".join(reasons),
            "secondary_situation_types": [],
            "requires_content_contract": sit_type in REQUIRES_CONTRACT,
        }

    # Pick best candidate
    best_type = max(candidates, key=lambda k: candidates[k])
    best_conf = round(candidates[best_type], 2)

    # Secondary types: all others with confidence ≥ 0.50
    secondary = sorted(
        [t for t, c in candidates.items() if t != best_type and c >= 0.50],
        key=lambda t: -candidates[t],
    )

    return {
        "situation_type": best_type,
        "confidence": best_conf,
        "reason": "; ".join(reasons),
        "secondary_situation_types": secondary[:3],
        "requires_content_contract": best_type in REQUIRES_CONTRACT,
    }
