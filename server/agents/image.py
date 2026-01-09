"""Image agent stub for scene art."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["image"])


class ImageRequest(BaseModel):
    prompt: str
    style: str = "realistic"


class ImageResponse(BaseModel):
    prompt: str
    style: str
    image_url: str
    guidance: str


@router.post("/image/generate", response_model=ImageResponse)
def generate_image(payload: ImageRequest) -> ImageResponse:
    guidance = "Use this as a placeholder until the art service is wired."
    return ImageResponse(
        prompt=payload.prompt,
        style=payload.style,
        image_url=f"https://placeholder.image/{payload.prompt.replace(' ', '_')}.png",
        guidance=guidance,
    )
