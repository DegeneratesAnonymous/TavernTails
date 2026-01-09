"""Scene agent: classifies actions and recommends rolls."""

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..realtime import broadcaster

router = APIRouter(tags=["scene"])


class SceneAnalysisRequest(BaseModel):
    scene: str = Field(..., description="Scene description")
    actions: List[str] = Field(default_factory=list, description="Player actions")
    session_id: Optional[str] = Field(default=None, description="Active session to broadcast cues toward")


class RollRecommendation(BaseModel):
    type: str
    skill: str
    reason: str


class SceneAnalysisResponse(BaseModel):
    dice_rolls: List[RollRecommendation]
    prompts: List[str]


KEYWORDS = {
    "Persuasion": ["persuade", "convince", "deceive", "charm"],
    "Attack": ["attack", "strike", "shoot", "swing"],
    "Perception": ["search", "investigate", "perceive", "scan"],
}


@router.post("/scene/analyze", response_model=SceneAnalysisResponse)
async def analyze_scene(payload: SceneAnalysisRequest) -> SceneAnalysisResponse:
    dice_rolls: List[RollRecommendation] = []
    prompts: List[str] = []

    for action in payload.actions:
        lowered = action.lower()
        for skill, tokens in KEYWORDS.items():
            if any(token in lowered for token in tokens):
                dice_rolls.append(RollRecommendation(type="d20", skill=skill, reason=f"{skill} triggered by action"))
                prompts.append(f"Roll a d20 for {skill}: '{action}'.")
                break
    response = SceneAnalysisResponse(dice_rolls=dice_rolls, prompts=prompts)
    if payload.session_id:
        await broadcaster.broadcast_json(payload.session_id, {
            "type": "scene.cues",
            "session_id": payload.session_id,
            "scene": payload.scene,
            "actions": payload.actions,
            "dice_rolls": [rec.model_dump() for rec in dice_rolls],
            "prompts": prompts,
        })
    return response
