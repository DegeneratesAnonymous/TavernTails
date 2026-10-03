"""Scene agent: classifies actions and recommends dice rolls via Steward."""

import json
import os
import time

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..realtime import broadcaster
from ..steward_llm import chat_complete
from . import sessions as sessions_agent

router = APIRouter(tags=["scene"])

_SCENE_LLM_CACHE: dict[str, tuple[float, "SceneAnalysisResponse"]] = {}
_SCENE_LLM_CACHE_MAX = 64


class SceneAnalysisRequest(BaseModel):
    scene: str = Field(..., description="Scene description")
    actions: list[str] = Field(default_factory=list, description="Player actions")
    session_id: str | None = Field(default=None, description="Active session to broadcast cues toward")


class RollRecommendation(BaseModel):
    type: str
    skill: str
    reason: str


class SceneAnalysisResponse(BaseModel):
    dice_rolls: list[RollRecommendation]
    prompts: list[str]


def check_roll_consistency(
    content_bundle: dict,
    scene_analysis: SceneAnalysisResponse | dict,
) -> dict:
    """Compare scene-analysis rolls with checks supported by the content bundle."""
    required = (content_bundle or {}).get("required_content") or {}
    supported = set()
    for field in ("possible_checks", "available_checks"):
        values = required.get(field) or []
        supported.update(str(v) for v in values if v)
    npc = required.get("npc") or {}
    if isinstance(npc, dict):
        supported.update(str(v) for v in (npc.get("possible_checks") or []) if v)
    analysis_rolls = (
        scene_analysis.dice_rolls
        if isinstance(scene_analysis, SceneAnalysisResponse)
        else (scene_analysis or {}).get("dice_rolls") or []
    )
    implied = [
        roll.skill if isinstance(roll, RollRecommendation) else str(roll.get("skill") or "")
        for roll in analysis_rolls
    ]
    implied = [skill for skill in implied if skill]
    unsupported = [
        skill for skill in implied
        if supported and skill not in supported
    ]
    missing = [
        skill for skill in supported
        if skill and skill not in implied
    ]
    return {
        "valid": not unsupported,
        "supported_checks": sorted(supported),
        "implied_checks": implied,
        "unsupported_implied_checks": unsupported,
        "supported_but_not_implied": missing,
        "warning": (
            "Scene analysis implied checks not present in content bundle."
            if unsupported else ""
        ),
    }


# Deterministic roll cues. These catch the common, unambiguous action phrases so
# the scene agent can stay fast and reserve LLM calls for nuanced situations.
_KEYWORD_MAP = {
    "Persuasion": ["persuade", "convince", "charm", "barter", "negotiate"],
    "Deception": ["deceive", "lie", "bluff", "trick", "mislead"],
    "Intimidation": ["intimidate", "threaten", "menace", "frighten"],
    "Stealth": ["sneak", "hide", "creep", "skulk", "shadow"],
    "Perception": ["search", "investigate", "perceive", "scan", "look", "watch"],
    "Athletics": ["climb", "jump", "swim", "dash", "grapple"],
    "Acrobatics": ["dodge", "tumble", "flip", "balance", "evade"],
    "Arcana": ["identify", "recall", "spellcraft", "magical"],
    "Attack": ["attack", "strike", "shoot", "swing", "stab", "slash", "fire"],
    "Insight": ["read", "sense motive", "gauge", "judge", "discern"],
}


def _keyword_fallback(actions: list[str]) -> tuple[list[RollRecommendation], list[str]]:
    rolls: list[RollRecommendation] = []
    prompts: list[str] = []
    for action in actions:
        lowered = action.lower()
        for skill, tokens in _KEYWORD_MAP.items():
            if any(tok in lowered for tok in tokens):
                rolls.append(RollRecommendation(type="d20", skill=skill, reason=f"{skill} check for: {action}"))
                prompts.append(f"Roll {skill} (d20): '{action}'")
                break
    return rolls, prompts


def _cache_key(payload: SceneAnalysisRequest) -> str:
    return json.dumps({
        "scene": payload.scene[:500] if payload.scene else "",
        "actions": payload.actions[:5],
    }, sort_keys=True)


def _load_llm_cache(key: str) -> SceneAnalysisResponse | None:
    ttl = float(os.environ.get("TAVERNTAILS_SCENE_ANALYSIS_CACHE_SECONDS", "90"))
    if ttl <= 0:
        return None
    cached = _SCENE_LLM_CACHE.get(key)
    if not cached:
        return None
    saved_at, response = cached
    if time.time() - saved_at > ttl:
        _SCENE_LLM_CACHE.pop(key, None)
        return None
    return response


def _save_llm_cache(key: str, response: SceneAnalysisResponse) -> None:
    if len(_SCENE_LLM_CACHE) >= _SCENE_LLM_CACHE_MAX:
        oldest = min(_SCENE_LLM_CACHE, key=lambda k: _SCENE_LLM_CACHE[k][0])
        _SCENE_LLM_CACHE.pop(oldest, None)
    _SCENE_LLM_CACHE[key] = (time.time(), response)


@router.post("/scene/analyze", response_model=SceneAnalysisResponse)
async def analyze_scene(payload: SceneAnalysisRequest) -> SceneAnalysisResponse:
    if payload.session_id and sessions_agent.is_player_run_mode(payload.session_id):
        return SceneAnalysisResponse(dice_rolls=[], prompts=[])

    dice_rolls: list[RollRecommendation] = []
    prompts: list[str] = []

    # Fast path: obvious player action verbs do not need a model call. Adjust
    # _KEYWORD_MAP above when adding/changing which actions map to which checks.
    if payload.actions:
        dice_rolls, prompts = _keyword_fallback(payload.actions)

    # Ask the LLM only when deterministic cues found nothing. This keeps the
    # agent responsive during busy sessions while preserving nuance for scenes
    # that need interpretation beyond a direct verb/skill mapping.
    llm_cache_key: str | None = None
    if not dice_rolls and (payload.scene or payload.actions):
        llm_cache_key = _cache_key(payload)
        cached = _load_llm_cache(llm_cache_key)
        if cached:
            response = cached
            if payload.session_id:
                await broadcaster.broadcast_json(payload.session_id, {
                    "type": "scene.cues",
                    "session_id": payload.session_id,
                    "dice_rolls": [r.model_dump() for r in response.dice_rolls],
                    "prompts": response.prompts,
                })
            return response

        system = (
            "You are a D&D 5e Dungeon Master's assistant analyzing a scene to find skill check opportunities.\n"
            "Given the scene description and player actions, identify which D&D 5e skill checks apply.\n"
            "Return JSON only:\n"
            '{"dice_rolls": [{"skill": "<Skill Name>", "type": "d20", "reason": "<why this check applies>"}], '
            '"prompts": ["<short prompt for each roll>"]}\n'
            "Only include genuine skill checks. Return empty arrays if none apply. Max 3 rolls."
        )
        user_content = json.dumps({
            "scene": payload.scene[:500] if payload.scene else "",
            "actions": payload.actions[:5],
        })
        text = chat_complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
            task_scope="taverntails_analysis",
            max_tokens=250,
            timeout=30.0,
        )
        if text:
            try:
                start, end = text.find("{"), text.rfind("}")
                if start != -1 and end > start:
                    parsed = json.loads(text[start:end + 1])
                    for r in (parsed.get("dice_rolls") or [])[:3]:
                        dice_rolls.append(RollRecommendation(
                            type=str(r.get("type", "d20")),
                            skill=str(r.get("skill", "Perception")),
                            reason=str(r.get("reason", "")),
                        ))
                    prompts = [str(p) for p in (parsed.get("prompts") or [])[:3]]
            except Exception:
                pass

    response = SceneAnalysisResponse(dice_rolls=dice_rolls, prompts=prompts)
    if llm_cache_key:
        _save_llm_cache(llm_cache_key, response)
    if payload.session_id:
        await broadcaster.broadcast_json(payload.session_id, {
            "type": "scene.cues",
            "session_id": payload.session_id,
            "dice_rolls": [r.model_dump() for r in dice_rolls],
            "prompts": prompts,
        })
    return response
