"""Storyboard agent: track beats and hooks."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List

router = APIRouter(tags=["storyboard"])


class StoryboardRequest(BaseModel):
    scene: str
    choices: List[str] = Field(default_factory=list)
    unresolved: List[str] = Field(default_factory=list)
    completed: List[str] = Field(default_factory=list)


class StoryboardResponse(BaseModel):
    storyboard: dict
    next_focus: str


@router.post("/storyboard/update", response_model=StoryboardResponse)
def update_storyboard(payload: StoryboardRequest) -> StoryboardResponse:
    next_focus = payload.unresolved[0] if payload.unresolved else "Introduce a fresh complication."
    storyboard = {
        "scene": payload.scene,
        "choices": payload.choices,
        "unresolved": payload.unresolved,
        "completed": payload.completed,
    }
    return StoryboardResponse(storyboard=storyboard, next_focus=next_focus)
