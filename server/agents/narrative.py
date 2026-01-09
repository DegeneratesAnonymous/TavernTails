"""Narrative Agent: generates narration + prompt."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["narrative"])


class NarrativeRequest(BaseModel):
    scene: str = Field(..., description="Scene description")
    player: str = Field(..., description="Active player name")
    style: str = Field("balanced", description="gritty realism | cinematic heroism | balanced")
    weather: str = Field("clear", description="Weather descriptor")
    time_of_day: str = Field("day", description="Time descriptor")


class NarrativeResponse(BaseModel):
    narrative: str
    prompt: str
    tone: str


STYLE_TONES = {
    "gritty realism": "Actions may leave scars; consequences stick.",
    "cinematic heroism": "Daring feats succeed when risk is embraced.",
    "balanced": "Choices matter and outcomes stay flexible.",
}


@router.post("/narrative/generate", response_model=NarrativeResponse)
def generate_narrative(payload: NarrativeRequest) -> NarrativeResponse:
    weather_desc = "crisp" if payload.weather == "clear" else payload.weather
    tone = STYLE_TONES.get(payload.style.lower(), STYLE_TONES["balanced"])
    narration = (
        f"You see {payload.scene}. The air feels {weather_desc}. It is {payload.time_of_day}. "
        f"{tone} Paths branch ahead, some obvious, others subtle."
    )
    prompt = f"{payload.player}, what do you do next?"
    return NarrativeResponse(narrative=narration, prompt=prompt, tone=payload.style.lower())
