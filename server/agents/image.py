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


def _pollinations_url(prompt: str, style: str) -> str:
    """Pollinations.ai direct URL — no API key, generates real images."""
    import urllib.parse
    safe = urllib.parse.quote(prompt[:400], safe='')
    portrait = style in ('portrait', 'vertical')
    width, height = (512, 832) if portrait else (832, 512)
    params = f"width={width}&height={height}&nologo=true&enhance=true&model=flux"
    return f"https://image.pollinations.ai/prompt/{safe}?{params}"


def _steward_generate(prompt: str, style: str, session_id: str | None) -> str | None:
    """Call Steward's ComfyUI image endpoint. Returns a local /api/image-file/... URL or None."""
    steward_host = os.environ.get("STEWARD_HOST", "").rstrip("/")
    if not steward_host:
        return None
    try:
        import base64

        import httpx
        portrait = style in ('portrait', 'vertical')
        width, height = (512, 832) if portrait else (832, 512)
        r = httpx.post(
            f"{steward_host}/api/image/generate",
            json={"prompt": prompt, "width": width, "height": height},
            timeout=120.0,
        )
        if not r.is_success:
            return None
        data = r.json()
        if not data.get("ok") or not data.get("image_b64"):
            return None
        img_bytes = base64.b64decode(data["image_b64"])
        mime = data.get("mime", "image/png")
        ext = "jpg" if "jpeg" in mime else "png"
        img_id = _prompt_hash(prompt, style)
        save_dir = _BASE / (session_id or "_unsaved") / "scene_images"
        save_dir.mkdir(parents=True, exist_ok=True)
        img_path = save_dir / f"{img_id}.{ext}"
        img_path.write_bytes(img_bytes)
        if session_id:
            return f"/api/image-file/{session_id}/{img_id}.{ext}"
        return f"/api/image-file/_unsaved/{img_id}.{ext}"
    except Exception:
        return None


def _resolve_image_url(prompt: str, style: str, session_id: str | None) -> str:
    """Resolve the best available image URL: Steward ComfyUI → Pollinations → stub."""
    provider = os.environ.get("TAVERNTAILS_IMAGE_PROVIDER", "auto")
    if provider == "stub":
        slug = prompt.replace(" ", "_")[:60]
        return f"https://placeholder.image/{style}/{slug}.png"
    if provider in ("auto", "steward"):
        local = _steward_generate(prompt, style, session_id)
        if local:
            return local
    if provider in ("auto", "pollinations"):
        return _pollinations_url(prompt, style)
    slug = prompt.replace(" ", "_")[:60]
    return f"https://placeholder.image/{style}/{slug}.png"


def _stub_image_url(prompt: str, style: str) -> str:
    return _resolve_image_url(prompt, style, None)


def _make_entry(prompt: str, style: str, *, cached: bool = False, session_id: str | None = None) -> dict:
    img_id = _prompt_hash(prompt, style)
    image_url = _resolve_image_url(prompt, style, session_id)
    return {
        "id": img_id,
        "prompt": prompt,
        "style": style,
        "image_url": image_url,
        "guidance": "",
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

        new_entry = _make_entry(payload.prompt, payload.style, cached=False, session_id=payload.session_id)
        gallery.append(new_entry)
        if len(gallery) > _MAX_GALLERY:
            gallery = gallery[-_MAX_GALLERY:]
        _save_gallery(payload.session_id, gallery)
        return _entry_to_response(new_entry)

    return _entry_to_response(_make_entry(payload.prompt, payload.style, session_id=None))


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


@router.get("/api/image-file/{session_id}/{filename}")
def serve_image_file(session_id: str, filename: str) -> Response:
    """Serve a locally generated scene image (produced by Steward's ComfyUI)."""
    from fastapi.responses import FileResponse
    from fastapi.responses import Response as FResponse
    safe_session = session_id.replace("..", "").replace("/", "")
    safe_file = filename.replace("..", "").replace("/", "")
    img_path = _BASE / safe_session / "scene_images" / safe_file
    if not img_path.exists() or not img_path.is_file():
        return FResponse(status_code=404)
    mime = "image/jpeg" if safe_file.lower().endswith(".jpg") else "image/png"
    return FileResponse(str(img_path), media_type=mime, headers={"Cache-Control": "max-age=86400"})

