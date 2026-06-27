"""Situation Contracts — required content definitions and per-situation validators.

Each situation type has:
  - A contract definition (what fields must exist before narration)
  - A validator function (checks whether those fields are present and specific enough)

Validators return a standard result dict so the narrative pipeline can decide
whether to regenerate structured content before writing prose.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Generic validation helpers
# ---------------------------------------------------------------------------

_GENERIC_NAMES = frozenset({
    "stranger", "figure", "man", "woman", "person", "guard", "soldier",
    "villager", "peasant", "merchant", "traveler", "traveller", "bandit", "thug",
    "unknown", "npc", "enemy", "creature",
})

_GENERIC_LOCATIONS = frozenset({
    "tavern", "inn", "pub", "alehouse", "bar", "the inn", "the tavern",
    "a tavern", "an inn", "the local tavern", "the local inn",
    "somewhere", "a place", "a room", "a location", "the location",
})

_GENERIC_THREATS = frozenset({
    "mysterious threat", "unknown threat", "great danger", "great evil",
    "shadowy figure", "dark force", "the darkness", "something evil",
    "an enemy", "some enemies",
})

_ABSTRACT_STAKES_PATTERNS = [
    r"if no one acts",
    r"the stakes are (high|personal|grave|dire)",
    r"(everything|the world|all) (is at stake|could be lost|hangs in the balance)",
    r"danger looms",
    r"the threat grows",
    r"consequences will follow",
]

_TAVERN_OPENING_PATTERNS = [
    r"\bwayward lantern\b",
    r"\brusty (flagon|nail|sword|axe)\b",
    r"\bprancing pony\b",
    r"\bsleeping dragon\b",
    r"\bthe (broken|cracked|leaky) (barrel|mug|tankard)\b",
    r"the party.{0,30}(enters?|arrives? at|is in|sits? in).{0,40}(tavern|inn|alehouse|pub)",
    r"you (are in|find yourself in|sit in|enter).{0,40}(tavern|inn|alehouse|pub)",
]


def _is_generic(text: str, generic_set: frozenset[str]) -> bool:
    return text.strip().lower() in generic_set


def _has_abstract_stakes(text: str) -> bool:
    tl = text.lower()
    return any(re.search(p, tl) for p in _ABSTRACT_STAKES_PATTERNS)


def _is_tavern_default(text: str) -> bool:
    tl = text.lower()
    return any(re.search(p, tl) for p in _TAVERN_OPENING_PATTERNS)


def _make_result(
    valid: bool,
    score: int,
    missing: list[str] | None = None,
    weak: list[str] | None = None,
    generic: list[str] | None = None,
    violations: list[str] | None = None,
    gaps: list[str] | None = None,
    fix: str = "",
) -> dict[str, Any]:
    return {
        "valid": valid,
        "score": score,
        "missing_required_fields": missing or [],
        "weak_fields": weak or [],
        "generic_defaults_detected": generic or [],
        "canon_violations": violations or [],
        "mechanical_gaps": gaps or [],
        "recommended_fix": fix,
    }


# ---------------------------------------------------------------------------
# CONTRACT DEFINITIONS
# ---------------------------------------------------------------------------

SITUATION_CONTRACTS: dict[str, dict[str, Any]] = {
    "campaign_opening": {
        "required_fields": [
            "starting_location", "location_identity", "inciting_event",
            "named_npc_or_visible_threat", "immediate_problem",
            "specific_stakes", "first_clue_or_question", "player_decision",
        ],
        "optional_fields": ["memory_updates", "weather", "time_of_day"],
        "entity_requirements": ["at least one named NPC or named threat"],
        "mechanical_requirements": ["concrete player choice presented"],
        "memory_requirements": ["new location record", "new NPC or threat record"],
        "ui_requirements": ["objective", "first_hook", "starting_question", "key_location"],
        "validation_rules": [
            "no_tavern_default",
            "no_mysterious_threat",
            "no_if_no_one_acts",
            "requires_concrete_stakes",
            "requires_named_entities",
        ],
    },
    "new_scene_opening": {
        "required_fields": [
            "location", "situation_description", "immediate_problem",
            "player_decision",
        ],
        "optional_fields": ["npcs_present", "visible_clues", "stakes"],
        "entity_requirements": [],
        "mechanical_requirements": ["player choice presented"],
        "memory_requirements": [],
        "ui_requirements": ["objective", "first_hook"],
        "validation_rules": ["requires_concrete_stakes"],
    },
    "combat_setup": {
        "required_fields": [
            "encounter_id", "combatants", "battlefield", "stakes",
            "victory_conditions", "failure_consequences",
        ],
        "optional_fields": ["non_combat_options", "round_state"],
        "entity_requirements": ["every combatant has hp, ac, attacks, tactics, goal"],
        "mechanical_requirements": ["battlefield has terrain features", "initiative can be rolled"],
        "memory_requirements": ["combatant records", "encounter record"],
        "ui_requirements": ["initiative", "enemy_cards", "terrain", "actions"],
        "validation_rules": [
            "all_enemies_have_stats",
            "battlefield_has_features",
            "combat_has_stakes",
            "non_combat_options_present",
        ],
    },
    "combat_round": {
        "required_fields": [
            "encounter_id", "active_combatant", "round_state",
            "available_actions", "current_hp_map",
        ],
        "optional_fields": ["terrain_events", "morale_checks"],
        "entity_requirements": [],
        "mechanical_requirements": ["round_state tracks initiative"],
        "memory_requirements": [],
        "ui_requirements": ["initiative", "current_hp", "active_actions"],
        "validation_rules": ["round_state_valid"],
    },
    "interrogation": {
        "required_fields": [
            "npc", "secrets", "pressure_points", "trust_state",
            "possible_checks", "failure_forward_options",
        ],
        "optional_fields": ["relationship_changes", "leverage_available"],
        "entity_requirements": ["NPC has goal, fear, attitude, knows, is_hiding"],
        "mechanical_requirements": ["secrets have reveal conditions", "failure paths exist"],
        "memory_requirements": ["NPC social profile", "secret records"],
        "ui_requirements": ["npc_attitude", "leverage", "possible_checks", "discovered_secrets"],
        "validation_rules": [
            "npc_wants_something",
            "npc_knows_something",
            "secrets_have_reveal_conditions",
            "failure_forward_exists",
        ],
    },
    "investigation": {
        "required_fields": [
            "mystery_question", "scene_location",
            "visible_clues", "required_conclusions",
        ],
        "optional_fields": [
            "hidden_clues", "red_herrings", "witnesses",
            "time_pressure", "failure_forward",
        ],
        "entity_requirements": ["every conclusion has at least 3 clue paths"],
        "mechanical_requirements": ["clues are concrete objects or evidence"],
        "memory_requirements": ["clue records", "mystery thread"],
        "ui_requirements": ["visible_clues", "leads", "theories", "available_checks"],
        "validation_rules": [
            "conclusions_have_clue_paths",
            "visible_clues_are_concrete",
            "failure_produces_progress",
            "clues_dont_reveal_everything",
        ],
    },
    "travel": {
        "required_fields": [
            "origin", "destination", "route",
            "travel_time", "complication_or_discovery",
            "arrival_state",
        ],
        "optional_fields": [
            "distance", "weather", "road_conditions", "landmark",
            "resource_cost", "choice_point", "encounter_risk",
        ],
        "entity_requirements": [],
        "mechanical_requirements": [
            "travel changes time", "travel changes location",
            "travel includes discovery, cost, danger, clue, or decision",
        ],
        "memory_requirements": ["location change record"],
        "ui_requirements": ["route", "travel_time", "weather", "road_risk"],
        "validation_rules": [
            "travel_changes_location",
            "travel_changes_time",
            "travel_has_meaningful_content",
        ],
    },
    "return_to_known_location": {
        "required_fields": [
            "location", "last_known_state", "what_changed",
            "new_visible_detail", "prompt",
        ],
        "optional_fields": ["npcs_present", "open_threads_here", "current_tension"],
        "entity_requirements": [],
        "mechanical_requirements": ["location reflects memory"],
        "memory_requirements": ["location history", "prior NPC states"],
        "ui_requirements": ["location_summary", "what_changed", "open_threads"],
        "validation_rules": [
            "location_reflects_memory",
            "change_or_persistence_noted",
        ],
    },
    "npc_reappearance": {
        "required_fields": [
            "npc", "last_seen", "relationship_to_party",
            "what_changed_for_npc", "what_npc_wants_now", "prompt",
        ],
        "optional_fields": ["new_information"],
        "entity_requirements": ["NPC must have prior relationship record"],
        "mechanical_requirements": ["NPC reflects prior history"],
        "memory_requirements": ["NPC relationship record"],
        "ui_requirements": ["npc_summary", "relationship", "what_they_want"],
        "validation_rules": [
            "npc_reflects_history",
            "npc_wants_something",
        ],
    },
    "conversation": {
        "required_fields": ["npc", "topic", "player_decision"],
        "optional_fields": ["npc_wants", "possible_checks"],
        "entity_requirements": [],
        "mechanical_requirements": [],
        "memory_requirements": [],
        "ui_requirements": ["npc_summary"],
        "validation_rules": [],
    },
    "social_conflict": {
        "required_fields": [
            "npc", "conflict_topic", "stakes",
            "leverage_available", "possible_checks", "failure_forward_options",
        ],
        "optional_fields": ["relationship_changes"],
        "entity_requirements": ["NPC has goal and attitude"],
        "mechanical_requirements": ["failure paths exist"],
        "memory_requirements": ["relationship record"],
        "ui_requirements": ["npc_attitude", "leverage", "possible_checks"],
        "validation_rules": ["npc_wants_something", "failure_forward_exists"],
    },
}


# ---------------------------------------------------------------------------
# Per-situation validators
# ---------------------------------------------------------------------------

def validate_campaign_opening(bundle: dict[str, Any]) -> dict[str, Any]:
    missing, weak, generic, gaps = [], [], [], []
    score = 100

    loc = str(bundle.get("starting_location") or bundle.get("location") or "")
    if not loc:
        missing.append("starting_location")
        score -= 25
    elif _is_generic(loc, _GENERIC_LOCATIONS):
        generic.append(f"starting_location is generic default: '{loc}'")
        score -= 20
    elif _is_tavern_default(loc):
        generic.append(f"starting_location defaults to tavern/inn: '{loc}'")
        score -= 20

    full_text = " ".join(str(v) for v in bundle.values() if isinstance(v, str))
    if _is_tavern_default(full_text):
        generic.append("opening defaults to a tavern/inn — use a different location type")
        score -= 15

    npc = str(bundle.get("named_npc_or_visible_threat") or bundle.get("primary_npc") or "")
    if not npc:
        missing.append("named_npc_or_visible_threat")
        score -= 20
    elif _is_generic(npc.split(",")[0].strip(), _GENERIC_NAMES):
        generic.append(f"NPC/threat is unnamed generic: '{npc}'")
        score -= 10
    elif _is_generic(npc.split(",")[0].strip().lower(), _GENERIC_THREATS):
        generic.append(f"NPC/threat is a generic abstract threat: '{npc}'")
        score -= 10

    for field in ("inciting_event", "immediate_problem"):
        val = str(bundle.get(field) or "")
        if not val:
            missing.append(field)
            score -= 15
        elif len(val) < 15:
            weak.append(f"{field} is too brief (< 15 chars)")
            score -= 8

    stakes = str(bundle.get("specific_stakes") or "")
    if not stakes:
        missing.append("specific_stakes")
        score -= 15
    elif _has_abstract_stakes(stakes):
        generic.append("specific_stakes is abstract — add concrete consequences")
        score -= 10

    for field in ("first_clue_or_question", "player_decision"):
        if not bundle.get(field):
            missing.append(field)
            score -= 10

    valid = score >= 75 and not missing
    fix = ""
    if missing:
        fix = f"Add missing fields: {', '.join(missing[:3])}."
    elif generic:
        fix = f"Replace generic defaults: {generic[0]}"
    return _make_result(valid, max(score, 0), missing, weak, generic, gaps=gaps, fix=fix)


def validate_combat_setup(bundle: dict[str, Any]) -> dict[str, Any]:
    missing, weak, generic, gaps = [], [], [], []
    score = 100

    combatants = bundle.get("combatants") or []
    if not combatants:
        missing.append("combatants")
        score -= 30
    else:
        for c in combatants:
            if not isinstance(c, dict):
                continue
            name = c.get("name") or "unnamed"
            for stat in ("hp", "ac", "attacks", "tactics", "goal"):
                if not c.get(stat):
                    gaps.append(f"combatant '{name}' missing: {stat}")
                    score -= 5

    battlefield = bundle.get("battlefield") or {}
    if not battlefield:
        missing.append("battlefield")
        score -= 20
    else:
        features = list(battlefield.get("terrain_features") or []) + list(battlefield.get("hazards") or []) + list(battlefield.get("interactive_objects") or [])
        if len(features) < 2:
            gaps.append("battlefield needs at least 2 terrain or interactive features")
            score -= 10

    stakes = str(bundle.get("stakes") or "")
    if not stakes:
        missing.append("stakes")
        score -= 15
    elif stakes.lower().strip() in ("kill enemies", "defeat the enemies", "win the fight", "survive"):
        generic.append("combat stakes are generic — add context-specific consequences")
        score -= 10

    if not bundle.get("victory_conditions"):
        weak.append("victory_conditions not specified")
        score -= 5
    if not bundle.get("failure_consequences"):
        weak.append("failure_consequences not specified")
        score -= 5

    valid = score >= 75 and not missing
    fix = f"Add missing fields: {', '.join(missing[:3])}." if missing else (gaps[0] if gaps else "")
    return _make_result(valid, max(score, 0), missing, weak, generic, gaps=gaps, fix=fix)


def validate_interrogation(bundle: dict[str, Any]) -> dict[str, Any]:
    missing, weak, generic, gaps = [], [], [], []
    score = 100

    npc = bundle.get("npc") or {}
    if not npc:
        missing.append("npc")
        score -= 25
    else:
        if isinstance(npc, dict):
            for field in ("goal", "fear", "attitude", "knows", "is_hiding"):
                if not npc.get(field):
                    gaps.append(f"npc missing: {field}")
                    score -= 6
        if not npc.get("goal") if isinstance(npc, dict) else True:
            generic.append("NPC has no goal — NPC must want something")
            score -= 10

    secrets = bundle.get("secrets") or []
    if not secrets:
        missing.append("secrets")
        score -= 20
    else:
        for s in secrets:
            if not isinstance(s, dict):
                continue
            if not s.get("disclosure_threshold") or not s.get("revealed_by"):
                gaps.append(f"secret '{str(s.get('secret',''))[:40]}' missing reveal conditions")
                score -= 8

    if not bundle.get("pressure_points"):
        weak.append("pressure_points not specified")
        score -= 5
    if not bundle.get("failure_forward_options"):
        gaps.append("failure_forward_options missing — failed rolls must not dead-end the scene")
        score -= 10

    valid = score >= 75 and not missing
    fix = f"Add missing fields: {', '.join(missing[:3])}." if missing else (gaps[0] if gaps else "")
    return _make_result(valid, max(score, 0), missing, weak, generic, gaps=gaps, fix=fix)


def validate_investigation(bundle: dict[str, Any]) -> dict[str, Any]:
    missing, weak, generic, gaps = [], [], [], []
    score = 100

    if not bundle.get("mystery_question"):
        missing.append("mystery_question")
        score -= 20
    if not bundle.get("scene_location"):
        missing.append("scene_location")
        score -= 15

    visible_clues = bundle.get("visible_clues") or []
    if not visible_clues:
        missing.append("visible_clues")
        score -= 20
    else:
        abstract = [c for c in visible_clues if isinstance(c, str) and len(c) < 10]
        if abstract:
            weak.append(f"{len(abstract)} visible clue(s) are too vague")
            score -= 8

    required_conclusions = bundle.get("required_conclusions") or []
    if not required_conclusions:
        missing.append("required_conclusions")
        score -= 15
    else:
        for rc in required_conclusions:
            if not isinstance(rc, dict):
                continue
            paths = rc.get("clue_paths") or []
            if len(paths) < 3:
                gaps.append(f"conclusion '{str(rc.get('conclusion',''))[:40]}' has fewer than 3 clue paths ({len(paths)})")
                score -= 8

    if not bundle.get("failure_forward"):
        weak.append("no failure_forward paths specified")
        score -= 5

    valid = score >= 75 and not missing
    fix = f"Add missing fields: {', '.join(missing[:3])}." if missing else (gaps[0] if gaps else "")
    return _make_result(valid, max(score, 0), missing, weak, generic, gaps=gaps, fix=fix)


def validate_travel(bundle: dict[str, Any]) -> dict[str, Any]:
    missing, weak, generic, gaps = [], [], [], []
    score = 100

    for field in ("origin", "destination"):
        if not bundle.get(field):
            missing.append(field)
            score -= 15

    if not bundle.get("travel_time"):
        missing.append("travel_time")
        score -= 10

    complication = str(bundle.get("complication_or_discovery") or "")
    if not complication:
        missing.append("complication_or_discovery")
        score -= 20
    elif len(complication) < 15:
        weak.append("complication_or_discovery is too brief — travel must have meaningful content")
        score -= 10

    if not bundle.get("arrival_state"):
        missing.append("arrival_state")
        score -= 10

    # Travel must change both time and location
    if not bundle.get("origin") or not bundle.get("destination"):
        gaps.append("travel must change location — origin and destination must differ")
    if not bundle.get("travel_time"):
        gaps.append("travel must change time — travel_time is required")

    valid = score >= 75 and not missing
    fix = f"Add missing fields: {', '.join(missing[:3])}." if missing else ""
    return _make_result(valid, max(score, 0), missing, weak, generic, gaps=gaps, fix=fix)


def validate_return_to_known_location(bundle: dict[str, Any]) -> dict[str, Any]:
    missing, weak, generic, gaps = [], [], [], []
    score = 100

    if not bundle.get("location"):
        missing.append("location")
        score -= 20
    if not bundle.get("last_known_state"):
        weak.append("last_known_state not provided — location will not reflect memory")
        score -= 10
    if not bundle.get("what_changed"):
        missing.append("what_changed")
        score -= 20
    if not bundle.get("new_visible_detail"):
        weak.append("new_visible_detail missing — return visit should show a change or meaningful sameness")
        score -= 8
    if not bundle.get("prompt"):
        missing.append("prompt")
        score -= 12

    valid = score >= 75 and not missing
    fix = f"Add missing fields: {', '.join(missing[:3])}." if missing else ""
    return _make_result(valid, max(score, 0), missing, weak, generic, gaps=gaps, fix=fix)


def validate_npc_reappearance(bundle: dict[str, Any]) -> dict[str, Any]:
    missing, weak, generic, gaps = [], [], [], []
    score = 100

    npc = str(bundle.get("npc") or "")
    if not npc:
        missing.append("npc")
        score -= 20
    elif _is_generic(npc, _GENERIC_NAMES):
        generic.append(f"npc is generic unnamed: '{npc}'")
        score -= 15

    if not bundle.get("last_seen"):
        weak.append("last_seen not provided — NPC may not reflect prior history")
        score -= 8
    if not bundle.get("relationship_to_party"):
        weak.append("relationship_to_party not specified")
        score -= 8
    if not bundle.get("what_changed_for_npc"):
        missing.append("what_changed_for_npc")
        score -= 15
    if not bundle.get("what_npc_wants_now"):
        missing.append("what_npc_wants_now")
        score -= 15
    if not bundle.get("prompt"):
        missing.append("prompt")
        score -= 12

    valid = score >= 75 and not missing
    fix = f"Add missing fields: {', '.join(missing[:3])}." if missing else ""
    return _make_result(valid, max(score, 0), missing, weak, generic, gaps=gaps, fix=fix)


def validate_social_conflict(bundle: dict[str, Any]) -> dict[str, Any]:
    missing, weak, generic, gaps = [], [], [], []
    score = 100

    npc = bundle.get("npc") or {}
    if not npc:
        missing.append("npc")
        score -= 20
    else:
        if isinstance(npc, dict):
            for field in ("goal", "attitude"):
                if not npc.get(field):
                    gaps.append(f"npc missing: {field}")
                    score -= 8

    if not bundle.get("conflict_topic"):
        missing.append("conflict_topic")
        score -= 15
    stakes = str(bundle.get("stakes") or "")
    if not stakes:
        missing.append("stakes")
        score -= 15
    elif _has_abstract_stakes(stakes):
        generic.append("stakes are abstract — add concrete consequences")
        score -= 8
    if not bundle.get("failure_forward_options"):
        gaps.append("failure_forward_options missing — failed rolls must not dead-end scene")
        score -= 10

    valid = score >= 75 and not missing
    fix = f"Add missing fields: {', '.join(missing[:3])}." if missing else (gaps[0] if gaps else "")
    return _make_result(valid, max(score, 0), missing, weak, generic, gaps=gaps, fix=fix)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_VALIDATORS: dict[str, Any] = {
    "campaign_opening": validate_campaign_opening,
    "new_scene_opening": validate_campaign_opening,  # same rules apply
    "combat_setup": validate_combat_setup,
    "combat_round": lambda b: _make_result(True, 90),  # round state validated at runtime
    "interrogation": validate_interrogation,
    "investigation": validate_investigation,
    "travel": validate_travel,
    "return_to_known_location": validate_return_to_known_location,
    "npc_reappearance": validate_npc_reappearance,
    "social_conflict": validate_social_conflict,
    "conversation": lambda b: _make_result(bool(b.get("npc")), 90 if b.get("npc") else 60),
}


def validate_situation(situation_type: str, bundle: dict[str, Any]) -> dict[str, Any]:
    """Run the appropriate validator for the given situation type.

    Returns a standard validation result dict.  Unknown situation types
    pass through as valid with score 100.
    """
    validator = _VALIDATORS.get(situation_type)
    if validator is None:
        return _make_result(True, 100, fix="No validator registered for this situation type.")
    return validator(bundle)


# ---------------------------------------------------------------------------
# Entity completeness levels
# ---------------------------------------------------------------------------

def background_npc(name: str, role: str, one_line: str) -> dict[str, Any]:
    return {"name": name, "role": role, "one_line": one_line, "completeness": "background"}


def social_npc(
    name: str, role: str, goal: str,
    attitude: str = "neutral",
    knows: list[str] | None = None,
    secret: str = "",
    leverage: str = "",
) -> dict[str, Any]:
    return {
        "name": name, "role": role, "goal": goal, "attitude": attitude,
        "knows": knows or [], "secret": secret, "leverage": leverage,
        "completeness": "social",
    }


def combat_npc(
    name: str, role: str, hp: int, ac: int,
    stats: dict[str, Any] | None = None,
    attacks: list[dict[str, Any]] | None = None,
    tactics: str = "",
) -> dict[str, Any]:
    return {
        "name": name, "role": role, "hp": hp, "ac": ac,
        "stats": stats or {}, "attacks": attacks or [], "tactics": tactics,
        "completeness": "combat",
    }


def recurring_npc(
    name: str, role: str,
    goals: list[str] | None = None,
    relationships: dict[str, Any] | None = None,
    backstory: str = "",
    knowledge: list[str] | None = None,
    secrets: list[str] | None = None,
    resources: list[str] | None = None,
    current_arc: str = "",
) -> dict[str, Any]:
    return {
        "name": name, "role": role,
        "goals": goals or [], "relationships": relationships or {},
        "backstory": backstory, "knowledge": knowledge or [],
        "secrets": secrets or [], "resources": resources or [],
        "current_arc": current_arc, "completeness": "recurring",
    }


def upgrade_npc_for_combat(npc: dict[str, Any], hp: int = 10, ac: int = 12) -> dict[str, Any]:
    """Promote any NPC to combat completeness, preserving existing fields."""
    upgraded = dict(npc)
    if not upgraded.get("hp"):
        upgraded["hp"] = hp
    if not upgraded.get("ac"):
        upgraded["ac"] = ac
    if not upgraded.get("attacks"):
        upgraded["attacks"] = [{"name": "Strike", "damage": "1d6", "hit_bonus": 2}]
    if not upgraded.get("tactics"):
        upgraded["tactics"] = "Engage nearest threat."
    upgraded["completeness"] = "combat"
    return upgraded


def upgrade_npc_for_social(npc: dict[str, Any], goal: str = "", attitude: str = "neutral") -> dict[str, Any]:
    """Promote any NPC to social completeness."""
    upgraded = dict(npc)
    if not upgraded.get("goal"):
        upgraded["goal"] = goal or "Protect their interests."
    if not upgraded.get("attitude"):
        upgraded["attitude"] = attitude
    if not upgraded.get("knows"):
        upgraded["knows"] = []
    upgraded["completeness"] = "social"
    return upgraded
