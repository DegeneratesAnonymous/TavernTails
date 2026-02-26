"""Direct messages — user-to-user inbox outside of sessions."""

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from .. import db
from ..auth import get_current_user

router = APIRouter(prefix="/messages", tags=["messages"])


def _dm_dict(msg: db.DirectMessage, sender_name: str | None = None, recipient_name: str | None = None) -> dict:
    return {
        "id": msg.id,
        "sender_id": msg.sender_id,
        "recipient_id": msg.recipient_id,
        "body": msg.body,
        "read": msg.read,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "sender_name": sender_name,
        "recipient_name": recipient_name,
    }


def _resolve_name(user_id: int | None) -> str | None:
    if not user_id:
        return None
    u = db.admin_get_user(user_id)
    if not u:
        return None
    return (u.profile or {}).get("name") or u.username or u.email


# ---------------------------------------------------------------------------
# Send a message
# ---------------------------------------------------------------------------


@router.post("/send")
def send_message(
    recipient_id: int = Body(..., embed=True),
    body: str = Body(..., embed=True, min_length=1, max_length=5000),
    current_user=Depends(get_current_user),
):
    """Send a direct message to another user.

    Both users must be friends (see /player/friends).  Blocked relationships
    also prevent messaging (if the sender has blocked the recipient or vice
    versa).
    """
    body = body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message body cannot be empty")
    if recipient_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot send a message to yourself")

    target = db.admin_get_user(recipient_id)
    if not target:
        raise HTTPException(status_code=404, detail="Recipient not found")

    # Friends-only DMs.
    if not db.are_friends(current_user.id, recipient_id):
        raise HTTPException(status_code=403, detail="You can only message users who are your friends")

    # Block check (bidirectional).
    if db.is_blocked(current_user.id, recipient_id) or db.is_blocked(recipient_id, current_user.id):
        raise HTTPException(status_code=403, detail="Unable to send message due to a block")

    msg = db.send_direct_message(sender_id=current_user.id, recipient_id=recipient_id, body=body)
    return {
        "message": _dm_dict(
            msg,
            sender_name=_resolve_name(current_user.id),
            recipient_name=_resolve_name(recipient_id),
        )
    }


# ---------------------------------------------------------------------------
# Inbox / Sent
# ---------------------------------------------------------------------------


@router.get("/inbox")
def get_inbox(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
):
    """Return messages received by the current user, newest first."""
    messages = db.get_inbox(current_user.id, limit=limit, offset=offset)
    unread = db.count_unread_messages(current_user.id)
    return {
        "messages": [
            _dm_dict(m, sender_name=_resolve_name(m.sender_id))
            for m in messages
        ],
        "unread": unread,
    }


@router.get("/sent")
def get_sent(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
):
    """Return messages sent by the current user, newest first."""
    messages = db.get_sent_messages(current_user.id, limit=limit, offset=offset)
    return {
        "messages": [
            _dm_dict(m, recipient_name=_resolve_name(m.recipient_id))
            for m in messages
        ]
    }


@router.post("/{message_id}/read")
def mark_read(message_id: int, current_user=Depends(get_current_user)):
    """Mark a received message as read."""
    ok = db.mark_message_read(message_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"read": True, "message_id": message_id}


@router.delete("/{message_id}")
def delete_message(message_id: int, current_user=Depends(get_current_user)):
    """Delete a message (sender or recipient may delete it from their view)."""
    ok = db.delete_direct_message(message_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"deleted": True, "message_id": message_id}
