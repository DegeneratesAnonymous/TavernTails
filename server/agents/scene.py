"""Scene agent: classifies actions and recommends dice rolls via Steward."""

import json

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..realtime import broadcaster
from ..steward_llm import chat_complete
from . import sessions as sessions_agent

router = APIRouter(tags=["scene"])


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


# Keyword fallback — used when Steward LLM is unavailable
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


@router.post("/scene/analyze", response_model=SceneAnalysisResponse)
async def analyze_scene(payload: SceneAnalysisRequest) -> SceneAnalysisResponse:
    if payload.session_id and sessions_agent.is_player_run_mode(payload.session_id):
        return SceneAnalysisResponse(dice_rolls=[], prompts=[])

    dice_rolls: list[RollRecommendation] = []
    prompts: list[str] = []

    # Try LLM-backed analysis first
    if payload.scene or payload.actions:
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

    # Keyword fallback if LLM returned nothing
    if not dice_rolls and payload.actions:
        dice_rolls, prompts = _keyword_fallback(payload.actions)

    response = SceneAnalysisResponse(dice_rolls=dice_rolls, prompts=prompts)
    if payload.session_id:
        await broadcaster.broadcast_json(payload.session_id, {
            "type": "scene.cues",
            "session_id": payload.session_id,
            "dice_rolls": [r.model_dump() for r in dice_rolls],
            "prompts": prompts,
        })
    return response
