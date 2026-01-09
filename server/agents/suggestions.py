"""Suggestion surface fed by recent chat context."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import List, Optional

from ..auth import get_current_user
from .. import db
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


class SuggestionResponse(BaseModel):
    session_id: Optional[str]
    source: str
    suggestions: List[str]


def _infer_theme(messages: List[db.ChatMessage]) -> str:
    window = " ".join((msg.message or "").lower() for msg in messages[-5:])
    for theme, keywords in THEME_KEYWORDS.items():
        if any(token in window for token in keywords):
            return theme
    return "default"


def _dedupe(items: List[str]) -> List[str]:
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
    session_id: Optional[str] = Query(None, description="Session to derive context from"),
    limit: int = Query(4, ge=1, le=8, description="Number of suggestions to return"),
    current_user=Depends(get_current_user),
) -> SuggestionResponse:
    source = "default"
    pool: List[str] = list(DEFAULT_SUGGESTIONS)
    if session_id:
        rows = db.list_chat_messages(session_id=session_id, limit=25)
        if rows:
            theme = _infer_theme(rows)
            source = f"chat:{theme}"
            pool = THEME_SUGGESTIONS.get(theme, DEFAULT_SUGGESTIONS)
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
