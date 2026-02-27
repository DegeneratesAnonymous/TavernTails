"""Support agent — contact form and ticket management endpoints."""

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from .. import db
from ..auth import get_current_user

router = APIRouter(prefix="/support", tags=["support"])


def _require_admin(current_user=Depends(get_current_user)):
    if not db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


def _ticket_dict(ticket: db.SupportTicket, include_user: bool = False) -> dict:
    data = {
        "id": ticket.id,
        "user_id": ticket.user_id,
        "subject": ticket.subject,
        "body": ticket.body,
        "status": ticket.status,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
    }
    if include_user:
        user = db.admin_get_user(ticket.user_id)
        if user:
            data["user_email"] = user.email
            data["user_name"] = (user.profile or {}).get("name") or user.username or user.email
    return data


# ---------------------------------------------------------------------------
# Player endpoints
# ---------------------------------------------------------------------------


@router.post("/contact")
def submit_ticket(
    subject: str = Body(..., embed=True, min_length=3, max_length=200),
    body: str = Body(..., embed=True, min_length=10, max_length=5000),
    current_user=Depends(get_current_user),
):
    """Submit a support / contact-us ticket."""
    subject = subject.strip()
    body = body.strip()
    if not subject:
        raise HTTPException(status_code=400, detail="Subject is required")
    if not body:
        raise HTTPException(status_code=400, detail="Message body is required")
    ticket = db.create_support_ticket(user_id=current_user.id, subject=subject, body=body)
    return {"ticket": _ticket_dict(ticket)}


@router.get("/my-tickets")
def my_tickets(current_user=Depends(get_current_user)):
    """Return all support tickets submitted by the current user."""
    tickets = db.list_user_support_tickets(current_user.id)
    return {"tickets": [_ticket_dict(t) for t in tickets]}


@router.get("/my-tickets/{ticket_id}")
def get_my_ticket(ticket_id: int, current_user=Depends(get_current_user)):
    """Get a specific support ticket belonging to the current user."""
    ticket = db.get_support_ticket(ticket_id)
    if not ticket or ticket.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ticket": _ticket_dict(ticket)}


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.get("/tickets")
def list_tickets(
    status: str | None = Query(None, description="Filter by status: open, in_progress, resolved, closed"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(_require_admin),
):
    """List all support tickets (admin only)."""
    tickets = db.list_support_tickets(status=status, limit=limit, offset=offset)
    return {"tickets": [_ticket_dict(t, include_user=True) for t in tickets], "total": len(tickets), "offset": offset}


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, current_user=Depends(_require_admin)):
    """Get a specific support ticket by ID (admin only)."""
    ticket = db.get_support_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ticket": _ticket_dict(ticket, include_user=True)}


@router.patch("/tickets/{ticket_id}/status")
def update_ticket_status(
    ticket_id: int,
    status: str = Body(..., embed=True),
    current_user=Depends(_require_admin),
):
    """Update the status of a support ticket (admin only)."""
    if status not in db._VALID_TICKET_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(sorted(db._VALID_TICKET_STATUSES))}")
    ticket = db.update_ticket_status(ticket_id, status)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ticket": _ticket_dict(ticket, include_user=True)}
