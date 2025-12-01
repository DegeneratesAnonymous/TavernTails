# Storyboard Agent
# Tracks campaign progress and branching paths


"""
Storyboard Agent
Tracks campaign progress, scenes, branching paths, and unresolved threads.
"""

from fastapi import APIRouter, Body
from typing import List, Dict, Any

router = APIRouter()

@router.post("/storyboard/update")
def update_storyboard(
    scene: str = Body(..., description="Current scene description"),
    choices: List[str] = Body([], description="Branching choices available"),
    unresolved: List[str] = Body([], description="Unresolved threads or objectives")
):
    """
    Update campaign storyboard with scene, choices, and unresolved threads.
    """
    storyboard = {
        "scene": scene,
        "choices": choices,
        "unresolved": unresolved
    }
    return {"storyboard": storyboard}
