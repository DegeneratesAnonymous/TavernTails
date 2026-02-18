"""Notes agent provides quick recaps.

This agent intentionally stays deterministic (no LLM calls) so it can be used
in MVP flows, tests, and CI without external dependencies.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user
from . import sessions as sessions_module

router = APIRouter(tags=["notes"])


_SESSIONS_BASE = Path(__file__).resolve().parents[1] / "sessions"


def _actor_identifier(user) -> str:
    """Return a normalised, lower-cased email/username for the calling user."""
    raw: str = getattr(user, "email", "") or getattr(user, "username", "") or str(user)
    return raw.strip().lower()


def _ensure_notes_member(session_id: str, current_user) -> str:
    """Raise 403 if caller is not a session member; return their identifier."""
    folder = _SESSIONS_BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    meta_path = folder / "meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    identifier = _actor_identifier(current_user)
    if not sessions_module._user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail="Not a member of this session")
    return identifier


def _strip_role_prefix(text: str) -> str:
    # Chat sends notes like "[gm] ..." or "[ally] ...".
    value = text.strip()
    if value.startswith("[") and "]" in value[:20]:
        _, rest = value.split("]", 1)
        value = rest.strip()
    return " ".join(value.split())


def _generate_recap(notes: List[str]) -> str:
    cleaned = [_strip_role_prefix(n) for n in notes if isinstance(n, str) and n.strip()]
    if not cleaned:
        return "No notes captured."

    # Keep the recap compact and readable inside the chat pane.
    recent = cleaned[-10:]
    deduped: list[str] = []
    seen: set[str] = set()
    for entry in reversed(recent):
        key = entry.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
        if len(deduped) >= 3:
            break
    deduped.reverse()

    snippet = " \u2022 ".join(e[:120] for e in deduped)
    if len(cleaned) > len(deduped):
        return f"Recap ({len(cleaned)} notes): {snippet}"
    return f"Recap: {snippet}"


def _append_to_session_notes(session_id: str, notes: List[str], recap: str) -> None:
    folder = _SESSIONS_BASE / session_id
    if not folder.exists():
        return
    notes_path = folder / "notes.md"
    if not notes_path.exists():
        return

    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        "\n",
        f"## {timestamp}",
        "",
        f"**Recap:** {recap}",
        "",
    ]
    for note in notes[-10:]:
        value = _strip_role_prefix(str(note))
        if value:
            lines.append(f"- {value}")
    lines.append("")

    try:
        notes_path.write_text(notes_path.read_text(encoding="utf-8") + "\n".join(lines), encoding="utf-8")
    except Exception:
        # Notes logging is best-effort.
        return


class NotesRequest(BaseModel):
    session_id: str
    notes: list[str] = Field(default_factory=list)


class NotesResponse(BaseModel):
    session_id: str
    notes_logged: int
    recap: str


@router.post("/notes/log", response_model=NotesResponse)
def log_notes(payload: NotesRequest, current_user=Depends(get_current_user)) -> NotesResponse:
    _ensure_notes_member(payload.session_id, current_user)
    recap = _generate_recap(payload.notes)
    _append_to_session_notes(payload.session_id, payload.notes, recap)
    return NotesResponse(session_id=payload.session_id, notes_logged=len(payload.notes), recap=recap)
