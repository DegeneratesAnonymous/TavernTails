"""Notes agent provides quick recaps."""


from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["notes"])


class NotesRequest(BaseModel):
    session_id: str
    notes: list[str] = Field(default_factory=list)


class NotesResponse(BaseModel):
    session_id: str
    notes_logged: int
    recap: str


@router.post("/notes/log", response_model=NotesResponse)
def log_notes(payload: NotesRequest) -> NotesResponse:
    recap = payload.notes[-1] if payload.notes else "No notes captured."
    return NotesResponse(session_id=payload.session_id, notes_logged=len(payload.notes), recap=recap)
