"""Image agent — stub provider with session-scoped image caching."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import get_current_user

router = APIRouter(tags=["image"])

# Session storage base — mirrors the path used by sessions.py.
_BASE = Path(__file__).resolve().parents[1] / "sessions"

# Maximum cached images stored per session (oldest are evicted first).
_MAX_GALLERY = 20


class ImageRequest(BaseModel):
    prompt: str
    style: str = "realistic"
    session_id: str | None = None


class ImageResponse(BaseModel):
    id: str
    prompt: str
    style: str
    image_url: str
    guidance: str
    generated_at: str
    cached: bool = False


class GalleryResponse(BaseModel):
    session_id: str
    images: list[ImageResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _gallery_path(session_id: str) -> Path:
    return _BASE / session_id / "images.json"


def _load_gallery(session_id: str) -> list[dict]:
    path = _gallery_path(session_id)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def _save_gallery(session_id: str, entries: list[dict]) -> None:
    path = _gallery_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2))


def _prompt_hash(prompt: str, style: str) -> str:
    return hashlib.sha256(f"{style}:{prompt}".encode()).hexdigest()[:16]


def _stub_image_url(prompt: str, style: str) -> str:
    """Return a deterministic placeholder URL for the given prompt and style.

    A real implementation would call an image generation API here and return
    the resulting URL.  Configure `TAVERNTAILS_IMAGE_PROVIDER` to swap in a
    different backend without touching this router.
    """
    provider = os.environ.get("TAVERNTAILS_IMAGE_PROVIDER", "stub")
    if provider != "stub":
        # Future hook: call the configured provider.
        # raise NotImplementedError(f"Provider {provider!r} not yet wired.")
        pass
    slug = prompt.replace(" ", "_")[:60]
    return f"https://placeholder.image/{style}/{slug}.png"


def _make_entry(prompt: str, style: str, *, cached: bool = False) -> dict:
    img_id = _prompt_hash(prompt, style)
    return {
        "id": img_id,
        "prompt": prompt,
        "style": style,
        "image_url": _stub_image_url(prompt, style),
        "guidance": "Placeholder — wire TAVERNTAILS_IMAGE_PROVIDER to use a real art service.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cached": cached,
    }


def _entry_to_response(entry: dict) -> ImageResponse:
    return ImageResponse(
        id=entry.get("id", ""),
        prompt=entry.get("prompt", ""),
        style=entry.get("style", "realistic"),
        image_url=entry.get("image_url", ""),
        guidance=entry.get("guidance", ""),
        generated_at=entry.get("generated_at", ""),
        cached=entry.get("cached", False),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/image/generate", response_model=ImageResponse)
def generate_image(payload: ImageRequest, current_user=Depends(get_current_user)) -> ImageResponse:
    """Generate a scene image for the given prompt.

    If the same (style, prompt) was already generated within this session, the
    cached result is returned without re-generating.  Pass ``session_id`` to
    enable caching and gallery storage.
    """
    img_id = _prompt_hash(payload.prompt, payload.style)

    if payload.session_id:
        gallery = _load_gallery(payload.session_id)
        for entry in gallery:
            if entry.get("id") == img_id:
                cached_entry = dict(entry)
                cached_entry["cached"] = True
                return _entry_to_response(cached_entry)

        new_entry = _make_entry(payload.prompt, payload.style, cached=False)
        gallery.append(new_entry)
        # Evict oldest entries beyond the cap.
        if len(gallery) > _MAX_GALLERY:
            gallery = gallery[-_MAX_GALLERY:]
        _save_gallery(payload.session_id, gallery)
        return _entry_to_response(new_entry)

    # No session — generate without caching.
    return _entry_to_response(_make_entry(payload.prompt, payload.style))


@router.get("/image/gallery/{session_id}", response_model=GalleryResponse)
def get_gallery(session_id: str, current_user=Depends(get_current_user)) -> GalleryResponse:
    """Return the gallery of cached images for a session, newest first."""
    entries = list(reversed(_load_gallery(session_id)))
    return GalleryResponse(
        session_id=session_id,
        images=[_entry_to_response(e) for e in entries],
    )


@router.delete("/image/gallery/{session_id}", status_code=204)
def clear_gallery(session_id: str, current_user=Depends(get_current_user)) -> None:
    """Clear all cached images for a session.

    Idempotent — if no gallery exists yet the operation is a no-op and still
    returns 204 so callers don't need to guard against 404.
    """
    path = _gallery_path(session_id)
    if path.exists():
        path.write_text("[]")

