"""Scene Beat Selector — chooses what the next scene should accomplish."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .storyboard import (
    CampaignStoryboard,
    PacingPatternState,
    SceneBeatSelectionInput,
    SessionStoryboard,
    select_scene_beat,
)


class SceneBeatSelectorInput(BaseModel):
    session_storyboard: dict[str, Any] = Field(default_factory=dict)
    campaign_storyboard: dict[str, Any] = Field(default_factory=dict)
    arc_plan: dict[str, Any] = Field(default_factory=dict)
    player_intent: dict[str, Any] = Field(default_factory=dict)
    simulation_delta: dict[str, Any] = Field(default_factory=dict)
    current_location: dict[str, Any] | str = Field(default_factory=dict)
    active_npcs: list[Any] = Field(default_factory=list)
    active_threads: list[Any] = Field(default_factory=list)
    recent_scene_types: list[str] = Field(default_factory=list)
    recent_motifs: list[str] = Field(default_factory=list)
    backstory_spotlight: list[dict[str, Any]] = Field(default_factory=list)


def select_scene_beat_plan(payload: SceneBeatSelectorInput | dict[str, Any]) -> dict[str, Any]:
    req = payload if isinstance(payload, SceneBeatSelectorInput) else SceneBeatSelectorInput(**(payload or {}))
    campaign = _campaign_storyboard(req.campaign_storyboard, req.arc_plan, req.active_threads)
    session = _session_storyboard(req.session_storyboard, campaign, req.arc_plan)
    player_actions = list(req.player_intent.get("declared_actions") or [])
    requested_mode = str(req.player_intent.get("requested_mode") or "")
    if requested_mode and requested_mode != "other":
        player_actions.insert(0, requested_mode)
    result = select_scene_beat(SceneBeatSelectionInput(
        session_storyboard=session,
        campaign_storyboard=campaign,
        player_actions=player_actions,
        world_tick_delta=req.simulation_delta,
        active_clocks=req.arc_plan.get("clocks_to_advance") or [],
        current_location=_location_name(req.current_location),
        npcs_present=[_npc_name(n) for n in req.active_npcs if _npc_name(n)],
        recent_scene_types=req.recent_scene_types,
        unresolved_threads=[_thread_name(t) for t in req.active_threads if _thread_name(t)],
        backstory_spotlight_tracker={"items": req.backstory_spotlight},
        recent_patterns=PacingPatternState(
            recent_scene_types=req.recent_scene_types,
            recent_motifs=req.recent_motifs,
            recent_locations=[_location_name(req.current_location)] if _location_name(req.current_location) else [],
        ),
    ))
    plan = result.selected_plan.model_dump()
    plan["selection_reason"] = result.beat_selection_reason
    plan["rejected_candidate_beats"] = result.rejected_candidate_beats
    plan["repetition_warnings"] = result.repetition_warnings
    plan["threads_advanced"] = result.threads_advanced
    plan["arc_plan"] = req.arc_plan
    return plan


def _campaign_storyboard(data: dict[str, Any], arc_plan: dict[str, Any], threads: list[Any]) -> CampaignStoryboard:
    raw = dict(data or {})
    raw.setdefault("campaign_id", raw.get("campaign_id") or "campaign")
    if not raw.get("central_question"):
        raw["central_question"] = (arc_plan.get("open_questions") or ["What pressure is active next?"])[0]
    if not raw.get("open_threads"):
        raw["open_threads"] = [_thread_name(t) for t in threads if _thread_name(t)]
    raw.setdefault("do_not_force", arc_plan.get("do_not_force") or [])
    return CampaignStoryboard(**raw)


def _session_storyboard(data: dict[str, Any], campaign: CampaignStoryboard, arc_plan: dict[str, Any]) -> SessionStoryboard:
    raw = dict(data or {})
    raw.setdefault("session_id", raw.get("session_id") or "session")
    raw.setdefault("campaign_id", campaign.campaign_id)
    raw.setdefault("session_goal", arc_plan.get("arc_goal") or campaign.central_question)
    raw.setdefault("candidate_beats", _candidate_beats_from_arc(arc_plan, campaign))
    raw.setdefault("fallback_beats", [{"beat_type": "consequence", "purpose": "show consequence without forcing a path"}])
    raw.setdefault("desired_tension_curve", [25, 40, 55, 70])
    raw.setdefault("do_not_force", arc_plan.get("do_not_force") or [])
    return SessionStoryboard(**raw)


def _candidate_beats_from_arc(arc_plan: dict[str, Any], campaign: CampaignStoryboard) -> list[dict[str, Any]]:
    stage = str(arc_plan.get("current_stage") or "")
    thread = (campaign.open_threads or arc_plan.get("open_questions") or [""])[0]
    if "clue" in stage or "question" in stage:
        return [{"beat_type": "mystery_clue", "thread": thread, "purpose": "advance a question with an earned clue"}]
    if "clock" in stage or arc_plan.get("clocks_to_advance"):
        return [{"beat_type": "faction_move", "thread": thread, "purpose": "advance a visible clock"}]
    return [{"beat_type": "discovery", "thread": thread, "purpose": "surface a concrete choice"}]


def _location_name(value: dict[str, Any] | str) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("location") or "")
    return str(value or "")


def _npc_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return str(value or "")


def _thread_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("title") or value.get("name") or value.get("situation") or "")
    return str(value or "")
