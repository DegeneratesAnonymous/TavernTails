import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import db
from ..auth import get_current_user
from ..realtime import broadcaster

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageCreate(BaseModel):
    message: str = Field(..., max_length=2000)
    session_id: Optional[str] = None
    campaign_id: Optional[str] = None
    role: Optional[str] = Field(default="player", max_length=32)


class ChatMessageOut(BaseModel):
    id: int
    session_id: Optional[str]
    campaign_id: Optional[str]
    sender_name: Optional[str]
    role: str
    message: str
    created_at: str
    mentions: List[str] = Field(default_factory=list)


MENTION_REGEX = re.compile(r"@([A-Za-z0-9_\-]{2,32})")


def _extract_mentions(text: str) -> List[str]:
    seen: List[str] = []
    if not text:
        return seen
    for match in MENTION_REGEX.findall(text):
        canonical = match.lower()
        if canonical not in seen:
            seen.append(canonical)
    return seen


def _serialize_chat_message(record: db.ChatMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=int(record.id or 0),
        session_id=record.session_id,
        campaign_id=record.campaign_id,
        sender_name=record.sender_name,
        role=record.role,
        message=record.message,
        created_at=record.created_at.isoformat() if record.created_at else "",
        mentions=_extract_mentions(record.message or ""),
    )


@router.get("", response_model=list[ChatMessageOut])
@router.get("/messages", response_model=list[ChatMessageOut])
def list_messages(
    session_id: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(get_current_user),
):
    if not session_id and not campaign_id:
        raise HTTPException(status_code=400, detail="session_id or campaign_id required")
    rows = db.list_chat_messages(session_id=session_id, campaign_id=campaign_id, limit=limit)
    return [_serialize_chat_message(r) for r in rows]


@router.post("", response_model=ChatMessageOut, status_code=201)
@router.post("/messages", response_model=ChatMessageOut, status_code=201)
async def create_message(payload: ChatMessageCreate, current_user=Depends(get_current_user)):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message content required")
    if not payload.session_id and not payload.campaign_id:
        raise HTTPException(status_code=400, detail="session_id or campaign_id required")
    sender_name = current_user.profile.get("name") if getattr(current_user, "profile", None) else None
    record = db.log_chat_message(
        message=payload.message.strip(),
        session_id=payload.session_id,
        campaign_id=payload.campaign_id,
        sender_id=getattr(current_user, "id", None),
        sender_name=sender_name or getattr(current_user, "username", None) or getattr(current_user, "email", None),
        role=payload.role or "player",
        metadata=None,
    )
    serialized = _serialize_chat_message(record)
    if payload.session_id:
        serialized_payload = serialized.model_dump() if hasattr(serialized, "model_dump") else serialized.dict()
        serialized_payload["mentions"] = serialized.mentions
        await broadcaster.broadcast_json(payload.session_id, {
            "type": "chat.message",
            "session_id": payload.session_id,
            "message": serialized_payload,
        })
    return serialized
