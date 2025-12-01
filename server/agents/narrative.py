def generate_narrative(scene, player):

"""
Narrative Agent
Generates narration, prompts players, and manages turn order.
"""

from fastapi import APIRouter, Body

router = APIRouter()

@router.post("/narrative/generate")
def generate_narrative(
    scene: str = Body(..., description="Scene description"),
    player: str = Body(..., description="Active player name"),
    style: str = Body("balanced", description="Preferred adventure style: gritty realism, cinematic heroism, or balanced"),
    weather: str = Body("clear", description="Current weather in the scene"),
    time_of_day: str = Body("day", description="Time of day in the scene")
):
    """
    Generate vivid, neutral narration and a directed prompt for the active player.
    Follows solo TTRPG GM best practices and user instructions.
    """
    # Sensory detail and dynamic factors
    sensory = [
        f"You see {scene}.",
        f"The air feels {'crisp' if weather == 'clear' else weather}.",
        f"It is {time_of_day}."
    ]
    # Style-based tone
    if style == "gritty realism":
        consequence = "Actions may have lasting, harsh consequences."
    elif style == "cinematic heroism":
        consequence = "Heroic feats are possible, but risk remains."
    else:
        consequence = "Choices matter, and outcomes may be mixed."

    # Neutral presentation, no internal states
    narration = (
        f"{' '.join(sensory)} {consequence} "
        f"There are multiple paths ahead, some obvious, some subtle."
    )

    # Directed prompt to active player
    prompt = f"{player}, what do you do next?"

    return {
        "narrative": narration,
        "prompt": prompt
    }
