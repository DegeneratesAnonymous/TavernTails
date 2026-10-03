"""Arc Planner — scale-aware campaign pressure planning.

Plans payoffs, clocks, and thread pressure without scripting player decisions.
"""
from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field


class ArcPlannerRequest(BaseModel):
    campaign_contract: dict[str, Any] = Field(default_factory=dict)
    campaign_scale_profile: dict[str, Any] = Field(default_factory=dict)
    story_shape_profile: dict[str, Any] = Field(default_factory=dict)
    campaign_storyboard: dict[str, Any] = Field(default_factory=dict)
    active_threads: list[Any] = Field(default_factory=list)
    world_clocks: list[dict[str, Any]] = Field(default_factory=list)
    backstory_spotlight: list[dict[str, Any]] = Field(default_factory=list)


class ArcPlan(BaseModel):
    arc_id: str
    arc_type: str
    arc_goal: str
    current_stage: str
    stage_goals: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    required_payoffs: list[str] = Field(default_factory=list)
    optional_payoffs: list[str] = Field(default_factory=list)
    clocks_to_advance: list[dict[str, Any]] = Field(default_factory=list)
    threads_to_seed: list[str] = Field(default_factory=list)
    threads_to_resolve: list[str] = Field(default_factory=list)
    threads_to_retire: list[str] = Field(default_factory=list)
    do_not_force: list[str] = Field(default_factory=list)


def plan_arc(payload: ArcPlannerRequest | dict[str, Any]) -> ArcPlan:
    req = payload if isinstance(payload, ArcPlannerRequest) else ArcPlannerRequest(**(payload or {}))
    scale = req.campaign_scale_profile or {}
    shape = req.story_shape_profile or {}
    contract = req.campaign_contract or {}
    storyboard = req.campaign_storyboard or {}
    length = str(scale.get("campaign_length") or "standard")
    model = str(shape.get("primary_story_model") or "three_act")
    stage = str(shape.get("current_arc_stage") or _default_stage(model))
    threads = [_thread_title(t) for t in req.active_threads if _thread_title(t)]
    open_threads = [str(t) for t in (storyboard.get("open_threads") or []) if t]
    questions = [str(storyboard.get("central_question") or "")]
    questions.extend(open_threads[:3])
    arc_type = {
        "one_shot": "one_shot",
        "short": "chapter",
        "standard": "act",
        "long": "season",
        "endless": "emergent",
    }.get(length, "act")
    goal = _goal_for(length, model, stage, storyboard, contract)
    max_threads = int(scale.get("max_open_threads") or 8)
    retirement_candidates = threads[max_threads:] if len(threads) > max_threads else []
    stale_threads = [
        _thread_title(t)
        for t in req.active_threads
        if isinstance(t, dict) and t.get("retirement_candidate")
    ]
    clocks = req.world_clocks[:3]
    if model == "faction_fronts" and not clocks:
        clocks = [{"clock_id": "front-pressure", "label": "A faction advances if ignored.", "advance_by": 1}]
    required_payoffs: list[str] = []
    optional_payoffs: list[str] = []
    if length == "one_shot":
        required_payoffs = [q for q in questions if q][:1]
    elif length == "short":
        optional_payoffs = [q for q in questions if q][:2]
    else:
        optional_payoffs = [q for q in questions if q][:3]
    if model == "mystery_web":
        optional_payoffs.append("seed redundant clue paths before any reveal")
    if model == "character_web" and req.backstory_spotlight:
        optional_payoffs.extend(
            str(item.get("hook") or item.get("summary") or "")
            for item in req.backstory_spotlight[:2]
            if isinstance(item, dict)
        )
    do_not_force = list(shape.get("stage_do_not_force") or [])
    do_not_force.extend(storyboard.get("do_not_force") or [])
    do_not_force.extend([
        "player decisions",
        "single required path",
        "predetermined outcomes",
    ])
    arc_id = hashlib.sha1(f"{contract.get('campaign_id','')}-{length}-{model}-{stage}".encode()).hexdigest()[:12]
    return ArcPlan(
        arc_id=arc_id,
        arc_type=arc_type,
        arc_goal=goal,
        current_stage=stage,
        stage_goals=[str(x) for x in (shape.get("stage_goals") or [])],
        open_questions=[q for q in questions if q],
        required_payoffs=required_payoffs,
        optional_payoffs=[p for p in optional_payoffs if p],
        clocks_to_advance=clocks,
        threads_to_seed=_threads_to_seed(model, length),
        threads_to_resolve=threads[:1] if length in {"one_shot", "short"} and threads else [],
        threads_to_retire=list(dict.fromkeys(retirement_candidates + stale_threads)),
        do_not_force=list(dict.fromkeys(do_not_force)),
    )


def _thread_title(thread: Any) -> str:
    if isinstance(thread, dict):
        return str(thread.get("title") or thread.get("name") or thread.get("situation") or "")
    return str(thread or "")


def _default_stage(model: str) -> str:
    return {
        "hero_cycle": "call_to_adventure",
        "three_act": "setup",
        "five_room": "hook",
        "mystery_web": "central_question",
        "faction_fronts": "fronts",
        "episodic": "episode_hook",
        "west_marches": "home_base",
        "character_web": "backstory_hooks",
    }.get(model, "pressure")


def _goal_for(length: str, model: str, stage: str, storyboard: dict[str, Any], contract: dict[str, Any]) -> str:
    question = storyboard.get("central_question") or contract.get("campaign_pitch") or "the current pressure"
    if length == "one_shot":
        return f"Drive toward a playable session resolution for {question}."
    if length == "short":
        return f"Move {question} toward a near-finale decision without fixing the result."
    if length == "long":
        return f"Advance the current season around {question}; preserve future arcs."
    if length == "endless":
        return f"Advance active fronts and short arcs around {question}; avoid final campaign resolution."
    return f"Advance {stage} pressure around {question}."


def _threads_to_seed(model: str, length: str) -> list[str]:
    if length == "one_shot":
        return []
    if model == "faction_fronts":
        return ["front clock", "intervention point"]
    if model == "mystery_web":
        return ["clue node", "false lead"]
    if length == "endless":
        return ["local episode hook"]
    return ["optional consequence thread"]
