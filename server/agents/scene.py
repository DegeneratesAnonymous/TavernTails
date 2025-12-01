# Scene Analysis Agent
# Detects needed dice rolls and prompts players


"""
Scene Analysis Agent
Detects needed dice rolls, enforces rules, and prompts for player actions.
"""

from fastapi import APIRouter, Body
from typing import List

router = APIRouter()

@router.post("/scene/analyze")
def analyze_scene(
    scene: str = Body(..., description="Scene description"),
    actions: List[str] = Body([], description="List of player actions")
):
    """
    Analyze the scene and player actions to detect needed dice rolls and prompts.
    """
    dice_rolls = []
    prompts = []
    # Example logic: check for uncertainty and classify actions
    for action in actions:
        if any(word in action.lower() for word in ["persuade", "convince", "deceive"]):
            dice_rolls.append({"type": "d20", "skill": "Persuasion", "reason": "Social interaction"})
            prompts.append(f"Please roll a d20 for your Persuasion check.")
        elif any(word in action.lower() for word in ["attack", "strike", "shoot"]):
            dice_rolls.append({"type": "d20", "skill": "Attack", "reason": "Combat action"})
            prompts.append(f"Please roll a d20 for your Attack roll.")
        elif any(word in action.lower() for word in ["search", "investigate", "perceive"]):
            dice_rolls.append({"type": "d20", "skill": "Perception", "reason": "Exploration"})
            prompts.append(f"Please roll a d20 for your Perception check.")
    # Always check for needed rolls after player actions
    return {
        "dice_rolls": dice_rolls,
        "prompts": prompts
    }
