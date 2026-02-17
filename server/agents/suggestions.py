"""Suggestion surface fed by recent chat context."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from .. import db
from ..auth import get_current_user
from ..realtime import broadcaster

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


DEFAULT_SUGGESTIONS = [
    "Survey the immediate area",
    "Check in with the party",
    "Assess resources and next steps",
    "Document the scene in your notes",
]

THEME_KEYWORDS = {
    "combat": ["attack", "strike", "swing", "blood", "initiative", "enemy"],
    "social": ["talk", "persuade", "convince", "request", "parley", "negotiate"],
    "exploration": ["search", "investigate", "scout", "explore", "track", "map"],
}

THEME_SUGGESTIONS = {
    "combat": [
        "Focus the party's attacks on the most fragile foe",
        "Use the environment for cover or high ground",
        "Call out for aid or reposition to protect allies",
        "Trigger a prepared ability before the next strike",
    ],
    "social": [
        "Ask a pointed question to reveal motives",
        "Offer a concession or trade to build rapport",
        "Sense if anyone is holding something back",
        "Compare stories with an Insight or Deception check",
    ],
    "exploration": [
        "Inspect the surroundings for hidden clues or traps",
        "Chart exits or fallback positions on your map",
        "Sample the environment for magical or historical traces",
        "Secure the area before advancing to the next room",
    ],
}


SESSIONS_DIR = Path(__file__).resolve().parents[1] / "sessions"


def _infer_theme_from_text(text: str) -> str:
    window = (text or "").lower()
    for theme, keywords in THEME_KEYWORDS.items():
        if any(token in window for token in keywords):
            return theme
    return "default"


def _load_scene_context(session_id: str) -> tuple[str, list[str]]:
    """Best-effort load of (scene text, choice labels) from a session."""
    if not session_id:
        return "", []
    scene_path = SESSIONS_DIR / str(session_id) / "scene.json"
    if not scene_path.exists():
        return "", []
    try:
        raw = json.loads(scene_path.read_text())
    except Exception:
        return "", []
    if not isinstance(raw, dict):
        return "", []
    text = str(raw.get("text") or "")
    choices = raw.get("choices")
    labels: list[str] = []
    if isinstance(choices, list):
        for item in choices:
            if isinstance(item, dict):
                label = str(item.get("label") or "").strip()
                if label:
                    labels.append(label)
            elif isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    labels.append(cleaned)
    return text, labels


class SuggestionResponse(BaseModel):
    session_id: str | None
    source: str
    suggestions: list[str]


def _infer_theme(messages: list[db.ChatMessage]) -> str:
    window = " ".join((msg.message or "").lower() for msg in messages[-5:])
    for theme, keywords in THEME_KEYWORDS.items():
        if any(token in window for token in keywords):
            return theme
    return "default"


def _dedupe(items: list[str]) -> list[str]:
    seen = {}
    for item in items:
        cleaned = (item or "").strip()
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen[cleaned] = True
    return list(seen.keys())


@router.get("", response_model=SuggestionResponse)
async def get_suggestions(
    session_id: str | None = Query(None, description="Session to derive context from"),
    limit: int = Query(4, ge=1, le=8, description="Number of suggestions to return"),
    current_user=Depends(get_current_user),
) -> SuggestionResponse:
    source = "default"
    pool: list[str] = list(DEFAULT_SUGGESTIONS)
    if session_id:
        rows = db.list_chat_messages(session_id=session_id, limit=25)
        if rows:
            theme = _infer_theme(rows)
            source = f"chat:{theme}"
            pool = THEME_SUGGESTIONS.get(theme, DEFAULT_SUGGESTIONS)
        else:
            scene_text, choice_labels = _load_scene_context(str(session_id))
            if scene_text or choice_labels:
                theme = _infer_theme_from_text(scene_text + " " + " ".join(choice_labels))
                source = f"scene:{theme}"
                pool = list(choice_labels) + list(THEME_SUGGESTIONS.get(theme, DEFAULT_SUGGESTIONS))
    deduped = _dedupe(pool)
    if not deduped:
        deduped = list(DEFAULT_SUGGESTIONS)
    payload = SuggestionResponse(session_id=session_id, source=source, suggestions=deduped[:limit])
    if session_id:
        await broadcaster.broadcast_json(session_id, {
            "type": "suggestions.update",
            "session_id": session_id,
            "suggestions": payload.suggestions,
            "source": payload.source,
        })
    return payload
