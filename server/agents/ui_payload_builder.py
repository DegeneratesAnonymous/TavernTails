"""UI Payload Builder — assembles the structured frontend payload from scene + bundle.

Produces the canonical ui_payload dict sent to every client after a scene advance.
Nothing here scrapes prose for metadata.  All data comes from validated structured
sources: game content bundle, scene director output, memory delta, world state.
"""
from __future__ import annotations

from typing import Any

from .situation_contracts import validate_situation

# ---------------------------------------------------------------------------
# Resolution Panel state names
# ---------------------------------------------------------------------------

RESOLUTION_STATES = frozenset({
    "idle",
    "checks_available",
    "rolling",
    "result",
    "combat",
    "conversation",
    "interrogation",
    "investigation",
    "travel",
    "downtime",
})

_SITUATION_TO_RESOLUTION_STATE: dict[str, str] = {
    "campaign_opening":         "checks_available",
    "new_scene_opening":        "checks_available",
    "combat_setup":             "combat",
    "combat_round":             "combat",
    "combat_resolution":        "result",
    "interrogation":            "interrogation",
    "conversation":             "conversation",
    "social_conflict":          "conversation",
    "investigation":            "investigation",
    "discovery":                "investigation",
    "mystery_reveal":           "investigation",
    "travel":                   "travel",
    "arrival":                  "travel",
    "return_to_known_location": "travel",
    "npc_reappearance":         "conversation",
    "downtime":                 "downtime",
    "shopping":                 "downtime",
    "rest":                     "downtime",
}


def resolution_state_for(situation_type: str, has_dice_rolls: bool, has_roll_result: bool) -> str:
    if has_roll_result:
        return "result"
    if situation_type in _SITUATION_TO_RESOLUTION_STATE:
        return _SITUATION_TO_RESOLUTION_STATE[situation_type]
    if has_dice_rolls:
        return "checks_available"
    return "idle"


# ---------------------------------------------------------------------------
# Scene summary fields
# ---------------------------------------------------------------------------

def _build_scene_summary(scene: dict[str, Any], content_bundle: dict[str, Any]) -> dict[str, Any]:
    sd = scene.get("scene_director_data") or {}
    bundle_content = (content_bundle or {}).get("required_content") or {}
    def one_sentence(value: Any, limit: int = 120) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        for marker in (". ", "! ", "? "):
            idx = text.find(marker)
            if idx > 0:
                text = text[:idx + 1]
                break
        return text[:limit].strip()

    objective = one_sentence(
        scene.get("current_objective")
        or bundle_content.get("immediate_problem")
        or sd.get("central_conflict")
    )
    if objective and not objective.lower().startswith(("find ", "reach ", "stop ", "protect ", "learn ", "decide ", "escape ", "convince ", "investigate ", "resolve ", "survive ", "choose ", "act ")):
        objective = f"Resolve: {objective}"

    observed = one_sentence((scene.get("visible_clues") or [""])[0])
    if not observed:
        director_clues = sd.get("player_visible_clues")
        observed = one_sentence(
            sd.get("inciting_incident")
            or (director_clues[0] if isinstance(director_clues, list) and director_clues else "")
        )

    risk = one_sentence(
        bundle_content.get("specific_stakes")
        or sd.get("immediate_stakes")
        or scene.get("immediate_stakes")
    )
    return {
        "objective": objective,
        "observed": observed,
        "risk": risk,
    }


# ---------------------------------------------------------------------------
# Resolution panel payload
# ---------------------------------------------------------------------------

def _build_resolution_panel(
    situation_type: str,
    content_bundle: dict[str, Any],
    dice_rolls: list[dict[str, Any]],
    turn_state: dict[str, Any],
    resolution_state: str,
) -> dict[str, Any]:
    bundle_content = (content_bundle or {}).get("required_content") or {}
    ui_payload = (content_bundle or {}).get("ui_payload") or {}

    panel: dict[str, Any] = {
        "state": resolution_state,
        "situation_type": situation_type,
    }

    if resolution_state == "idle":
        panel["message"] = "No check required. Describe an action below."

    elif resolution_state == "checks_available":
        panel["pending_rolls"] = dice_rolls[:5]
        if situation_type in ("campaign_opening", "new_scene_opening"):
            panel["objective"] = ui_payload.get("objective") or ""
            panel["first_hook"] = ui_payload.get("first_hook") or ""
            panel["starting_question"] = ui_payload.get("starting_question") or ""
            panel["key_npc"] = ui_payload.get("key_npc") or ""
            panel["suggested_first_actions"] = ui_payload.get("suggested_first_actions") or []

    elif resolution_state == "combat":
        panel["initiative_order"] = turn_state.get("initiative_order") or ui_payload.get("initiative_order") or []
        panel["active_combatant"] = turn_state.get("active") or ui_payload.get("active_combatant") or ""
        panel["enemy_cards"] = ui_payload.get("enemy_cards") or []
        panel["terrain_features"] = ui_payload.get("terrain_features") or []
        panel["hazards"] = ui_payload.get("hazards") or []
        panel["non_combat_options"] = ui_payload.get("non_combat_options") or []
        panel["victory_conditions"] = bundle_content.get("victory_conditions") or ui_payload.get("victory_conditions") or []
        panel["failure_consequences"] = bundle_content.get("failure_consequences") or ui_payload.get("failure_consequences") or []
        panel["pending_rolls"] = dice_rolls[:5]

    elif resolution_state == "interrogation":
        panel["npc_name"] = ui_payload.get("npc_name") or ""
        panel["npc_attitude"] = ui_payload.get("npc_attitude") or "neutral"
        panel["npc_goal"] = ui_payload.get("npc_goal") or ""
        panel["visible_emotional_tells"] = ui_payload.get("visible_emotional_tells") or ""
        panel["known_leverage"] = ui_payload.get("known_leverage") or []
        panel["possible_checks"] = ui_payload.get("possible_checks") or []
        panel["discovered_secrets"] = ui_payload.get("discovered_secrets") or []
        panel["failure_forward"] = ui_payload.get("failure_forward") or []
        panel["pending_rolls"] = dice_rolls[:5]

    elif resolution_state == "conversation":
        panel["npc_name"] = ui_payload.get("npc_name") or ""
        panel["npc_attitude"] = ui_payload.get("npc_attitude") or "neutral"
        panel["npc_goal"] = ui_payload.get("npc_goal") or ""
        panel["possible_checks"] = ui_payload.get("possible_checks") or []
        panel["pending_rolls"] = dice_rolls[:3]

    elif resolution_state == "investigation":
        panel["mystery_question"] = ui_payload.get("mystery_question") or ""
        panel["visible_clues"] = ui_payload.get("visible_clues") or []
        panel["leads"] = ui_payload.get("leads") or []
        panel["theories"] = ui_payload.get("theories") or []
        panel["available_checks"] = ui_payload.get("available_checks") or []
        panel["time_pressure"] = ui_payload.get("time_pressure") or ""
        panel["failure_forward"] = ui_payload.get("failure_forward") or []
        panel["pending_rolls"] = dice_rolls[:5]

    elif resolution_state == "travel":
        panel["origin"] = ui_payload.get("origin") or ""
        panel["destination"] = ui_payload.get("destination") or ""
        panel["route"] = ui_payload.get("route") or ""
        panel["travel_time"] = ui_payload.get("travel_time") or ""
        panel["weather"] = ui_payload.get("weather") or ""
        panel["road_conditions"] = ui_payload.get("road_conditions") or ""
        panel["encounter_risk"] = ui_payload.get("encounter_risk") or "low"
        panel["resource_cost"] = ui_payload.get("resource_cost") or ""
        panel["what_changed"] = ui_payload.get("what_changed") or ""

    elif resolution_state == "downtime":
        panel["activity"] = ui_payload.get("activity") or "Resting"
        panel["pending_rolls"] = dice_rolls[:3]

    elif resolution_state == "result":
        panel["roll_result"] = turn_state.get("last_roll") or {}
        panel["outcome"] = turn_state.get("outcome") or ""

    return panel


# ---------------------------------------------------------------------------
# Character quick panel
# ---------------------------------------------------------------------------

def _build_character_quick_panel(player_stats: dict[str, Any] | None) -> dict[str, Any]:
    if not player_stats:
        return {}
    return {
        "name": player_stats.get("name") or "",
        "class": player_stats.get("class") or player_stats.get("character_class") or "",
        "level": player_stats.get("level") or "",
        "hp": player_stats.get("hp") or player_stats.get("hit_points") or "",
        "ac": player_stats.get("ac") or player_stats.get("armor_class") or "",
        "initiative_modifier": player_stats.get("initiative") or player_stats.get("initiative_mod") or 0,
    }


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_ui_payload(
    scene: dict[str, Any],
    content_bundle: dict[str, Any],
    memory_delta: dict[str, Any],
    world_state: dict[str, Any],
    simulation_delta: dict[str, Any],
    campaign_contract: dict[str, Any] | None = None,
    player_stats: dict[str, Any] | None = None,
    turn_state: dict[str, Any] | None = None,
    dice_rolls: list[dict[str, Any]] | None = None,
    debug_mode: bool = False,
) -> dict[str, Any]:
    """Build the complete structured UI payload for a scene advance.

    This is the canonical payload the frontend consumes.  Nothing should be
    scraped from prose; all data comes from the arguments.
    """
    ts = turn_state or {}
    dr = dice_rolls or []

    situation_type = scene.get("situation_type") or ""
    has_dice_rolls = len(dr) > 0
    has_roll_result = bool(ts.get("last_roll"))

    resolution_state = resolution_state_for(situation_type, has_dice_rolls, has_roll_result)

    scene_obj = {
        "id": scene.get("id") or "",
        "title": scene.get("title") or "",
        "narrative_body": scene.get("narrative_body") or scene.get("text") or "",
        "player_prompt": scene.get("player_prompt") or "",
        "choices": scene.get("choices") or [],
        "location": scene.get("location") or "",
        "weather": scene.get("weather") or world_state.get("weather") or "",
        "time_of_day": scene.get("time_of_day") or world_state.get("time_of_day") or "",
        "situation_type": situation_type,
        "active_threads": scene.get("active_threads") or [],
    }

    world_updates = []
    for change in (memory_delta.get("world_state_changes") or []):
        if isinstance(change, dict):
            world_updates.append(change)

    archive_updates: list[dict[str, Any]] = []
    for npc in (memory_delta.get("new_npcs") or []):
        archive_updates.append({"type": "npc", "name": npc.get("name") if isinstance(npc, dict) else str(npc), "action": "new"})
    for loc in (memory_delta.get("new_locations") or []):
        archive_updates.append({"type": "location", "name": loc.get("name") if isinstance(loc, dict) else str(loc), "action": "new"})
    for thread in (memory_delta.get("new_threads") or []):
        archive_updates.append({"type": "thread", "name": thread, "action": "new"})
    for clue in (memory_delta.get("new_clues") or []):
        archive_updates.append({"type": "clue", "name": clue, "action": "discovered"})

    payload: dict[str, Any] = {
        "scene": scene_obj,
        "scene_summary": _build_scene_summary(scene, content_bundle),
        "resolution_panel": _build_resolution_panel(
            situation_type, content_bundle, dr, ts, resolution_state
        ),
        "character_quick_panel": _build_character_quick_panel(player_stats),
        "world_updates": world_updates,
        "archive_updates": archive_updates,
        "visible_clues": scene.get("visible_clues") or [],
        "pending_rolls": dr[:5],
        "suggested_actions": scene.get("suggested_actions") or [],
        "experience_mode": (content_bundle or {}).get("ui_payload", {}).get("experience_mode") or "quiet_scene",
        "situation_type": situation_type,
    }

    if debug_mode:
        payload["debug"] = {
            "campaign_contract": {
                k: campaign_contract.get(k)
                for k in ("contract_version", "canon_policy", "validator_policy", "creation_posture")
            } if campaign_contract else {},
            "world_tick": {
                k: world_state.get(k)
                for k in ("campaign_day", "time_of_day", "weather", "global_threat_level", "season")
            },
            "simulation_delta": simulation_delta,
            "situation_type": situation_type,
            "content_bundle": {
                "bundle_id": content_bundle.get("bundle_id") or "",
                "bundle_type": content_bundle.get("bundle_type") or "",
                "validated": content_bundle.get("validated"),
                "validation_result": content_bundle.get("validation_result") or {},
                "situation_type": content_bundle.get("situation_type") or "",
            } if content_bundle else {},
            "situation_validation": content_bundle.get("validation_result") or {} if content_bundle else {},
            "director_output": scene.get("scene_director_data") or {},
            "campaign_storyboard": scene.get("campaign_storyboard") or {},
            "session_storyboard": scene.get("session_storyboard") or {},
            "scene_beat_plan": scene.get("scene_beat_plan") or {},
            "beat_type_chosen": scene.get("beat_type_chosen") or "",
            "beat_selection_reason": scene.get("beat_selection_reason") or "",
            "rejected_candidate_beats": scene.get("rejected_candidate_beats") or [],
            "repetition_warnings": scene.get("repetition_warnings") or [],
            "active_clocks": scene.get("active_clocks") or [],
            "threads_advanced": scene.get("threads_advanced") or [],
            "do_not_force": scene.get("do_not_force") or [],
            "writer_output": {
                "title": scene.get("title") or "",
                "narrative_body": (scene.get("narrative_body") or "")[:200],
                "suggested_actions": scene.get("suggested_actions") or [],
                "visible_clues": scene.get("visible_clues") or [],
            },
            "narrative_validation": scene.get("quality_validation") or {},
            "memory_delta": memory_delta,
            "canon_changes": memory_delta.get("game_content_bundle_updates") or [],
            "ui_payload": {
                k: payload.get(k)
                for k in ("scene_summary", "experience_mode", "situation_type")
            },
        }

    return payload


# ---------------------------------------------------------------------------
# Validation report for UI payload
# ---------------------------------------------------------------------------

def validate_ui_payload(payload: dict[str, Any], situation_type: str) -> dict[str, Any]:
    """Check that the UI payload has required fields for the given situation."""
    issues = []
    score = 100

    if not payload.get("scene", {}).get("narrative_body"):
        issues.append("scene.narrative_body is empty")
        score -= 30
    if not payload.get("scene", {}).get("player_prompt"):
        issues.append("scene.player_prompt is empty")
        score -= 15
    if not payload.get("suggested_actions"):
        issues.append("suggested_actions is empty")
        score -= 10

    resolution = payload.get("resolution_panel") or {}
    rs = resolution.get("state") or "idle"
    if situation_type in ("combat_setup", "combat_round") and rs != "combat":
        issues.append(f"combat situation has resolution state '{rs}', expected 'combat'")
        score -= 20
    if situation_type == "investigation" and rs != "investigation":
        issues.append(f"investigation situation has resolution state '{rs}', expected 'investigation'")
        score -= 15

    return {
        "valid": score >= 70,
        "score": max(0, score),
        "issues": issues,
        "recommended_fix": issues[0] if issues else "",
    }
