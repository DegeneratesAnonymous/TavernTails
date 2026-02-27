import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import db
from ..auth import get_current_user
from ..realtime import broadcaster

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageCreate(BaseModel):
    message: str = Field(..., max_length=2000)
    session_id: str | None = None
    campaign_id: str | None = None
    role: str | None = Field(default="player", max_length=32)


class ChatMessageOut(BaseModel):
    id: int
    session_id: str | None
    campaign_id: str | None
    sender_name: str | None
    sender_id: int | None = None
    role: str
    message: str
    created_at: str
    mentions: list[str] = Field(default_factory=list)
    pinned: bool = False



MENTION_REGEX = re.compile(r"@([A-Za-z0-9_\-]{2,32})")

# Keywords used to produce contextual GM acknowledgements for @GM mentions.
_QUESTION_KEYWORDS = ("can i", "can we", "is it", "does", "do i", "am i", "are we")
_COMBAT_KEYWORDS = ("attack", "strike", "hit", "fight")
_INVESTIGATION_KEYWORDS = ("search", "look", "investigate", "examine", "check")


def _extract_mentions(text: str) -> list[str]:
    seen: list[str] = []
    if not text:
        return seen
    for match in MENTION_REGEX.findall(text):
        canonical = match.lower()
        if canonical not in seen:
            seen.append(canonical)
    return seen


def _serialize_chat_message(record: db.ChatMessage, *, pinned: bool = False) -> ChatMessageOut:
    return ChatMessageOut(
        id=int(record.id or 0),
        session_id=record.session_id,
        campaign_id=record.campaign_id,
        sender_id=record.sender_id,
        sender_name=record.sender_name,
        role=record.role,
        message=record.message,
        created_at=record.created_at.isoformat() if record.created_at else "",
        mentions=_extract_mentions(record.message or ""),
        pinned=pinned,
    )


@router.get("", response_model=list[ChatMessageOut])
@router.get("/messages", response_model=list[ChatMessageOut])
def list_messages(
    session_id: str | None = Query(None),
    campaign_id: str | None = Query(None),
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
        serialized_payload = serialized.model_dump()
        serialized_payload["mentions"] = serialized.mentions
        await broadcaster.broadcast_json(payload.session_id, {
            "type": "chat.message",
            "session_id": payload.session_id,
            "message": serialized_payload,
        })

    # If the player tagged @GM, the Narrator acknowledges the question in-chat.
    if payload.session_id and "gm" in [m.lower() for m in serialized.mentions]:
        gm_text = _gm_acknowledge(payload.message)
        gm_record = db.log_chat_message(
            message=gm_text,
            session_id=payload.session_id,
            campaign_id=payload.campaign_id,
            sender_id=None,
            sender_name="GM",
            role="gm",
            metadata=None,
        )
        gm_serialized = _serialize_chat_message(gm_record).model_dump()
        await broadcaster.broadcast_json(payload.session_id, {
            "type": "chat.message",
            "session_id": payload.session_id,
            "message": gm_serialized,
        })

    return serialized


def _gm_acknowledge(player_message: str) -> str:
    """Generate a brief, deterministic GM acknowledgement for an @GM mention.

    This is intentionally simple so it works without an LLM.  A richer
    LLM-backed response can replace this body when an API key is configured.
    """
    lower = player_message.lower()
    if any(word in lower for word in _QUESTION_KEYWORDS):
        return "[GM] That's a fair question. Let me consider the situation — I'll rule on it shortly."
    if any(word in lower for word in _COMBAT_KEYWORDS):
        return "[GM] Roll for initiative! Describe your action and we'll resolve it."
    if any(word in lower for word in _INVESTIGATION_KEYWORDS):
        return "[GM] Roll Perception or Investigation and tell me what you're searching for."
    return "[GM] Noted. The GM is watching — carry on or describe your action."


@router.get("/pinned", response_model=list[ChatMessageOut])
def list_pinned(session_id: str = Query(...), current_user=Depends(get_current_user)):
    """Return all pinned messages for a session, in pin-order (oldest pin first)."""
    msgs = db.list_pinned_messages(session_id)
    return [_serialize_chat_message(m, pinned=True) for m in msgs]


@router.post("/{message_id}/pin", response_model=ChatMessageOut)
async def pin_message(message_id: int, session_id: str = Query(...), current_user=Depends(get_current_user)):
    """Pin a message in the session. Idempotent."""
    pin = db.pin_message(session_id=session_id, message_id=message_id, pinned_by_id=getattr(current_user, "id", None))
    if not pin:
        raise HTTPException(status_code=404, detail="Message not found in this session.")
    msg = db.list_pinned_messages(session_id)
    target = next((m for m in msg if m.id == message_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Message not found.")
    serialized = _serialize_chat_message(target, pinned=True)
    await broadcaster.broadcast_json(session_id, {
        "type": "chat.pin",
        "session_id": session_id,
        "message": serialized.model_dump(),
    })
    return serialized


@router.delete("/{message_id}/pin", status_code=204)
async def unpin_message(message_id: int, session_id: str = Query(...), current_user=Depends(get_current_user)):
    """Remove a pin from a message."""
    removed = db.unpin_message(session_id=session_id, message_id=message_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Pin not found.")
    await broadcaster.broadcast_json(session_id, {
        "type": "chat.unpin",
        "session_id": session_id,
        "message_id": message_id,
    })


@router.delete("/{message_id}", status_code=204)
async def delete_message(message_id: int, session_id: str = Query(...), current_user=Depends(get_current_user)):
    """Delete a chat message. Only the sender may delete their own messages."""
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=400, detail="User ID missing.")
    deleted = db.delete_chat_message(message_id=message_id, sender_id=user_id)
    if not deleted:
        raise HTTPException(status_code=403, detail="Message not found or you are not the sender.")
    await broadcaster.broadcast_json(session_id, {
        "type": "chat.delete",
        "session_id": session_id,
        "message_id": message_id,
    })

