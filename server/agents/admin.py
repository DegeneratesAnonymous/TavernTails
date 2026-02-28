"""Admin agent — admin-only endpoints for site management."""

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from .. import db
from ..auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(current_user=Depends(get_current_user)):
    if not db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


# ---------------------------------------------------------------------------
# Site statistics
# ---------------------------------------------------------------------------


@router.get("/stats")
def get_site_stats(current_user=Depends(_require_admin)):
    """Return aggregate site statistics."""
    return db.admin_site_stats()


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


@router.get("/users")
def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(_require_admin),
):
    """List all registered users sorted alphabetically."""
    users = db.admin_list_users(limit=limit, offset=offset)
    result = []
    for u in users:
        profile = db._profile_with_identity(u)
        result.append(
            {
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "verified": u.verified,
                "name": profile.get("name") or u.username or u.email,
                "admin": db.is_admin_user(u),
            }
        )
    # Also return total count so the frontend can paginate correctly
    total = db.admin_count_users()
    return {"users": result, "total": total, "offset": offset}


@router.get("/users/{user_id}")
def get_user(user_id: int, current_user=Depends(_require_admin)):
    """Get details for a specific user."""
    u = db.admin_get_user(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    profile = db._profile_with_identity(u)
    campaigns = db.list_campaigns_for_owner(user_id)
    return {
        "id": u.id,
        "email": u.email,
        "username": u.username,
        "verified": u.verified,
        "name": profile.get("name") or u.username or u.email,
        "admin": db.is_admin_user(u),
        "campaigns": [{"id": c.id, "name": c.name, "archived": c.archived} for c in campaigns],
    }


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    new_password: str = Body(..., embed=True),
    current_user=Depends(_require_admin),
):
    """Reset a user's password (admin generates a new one or provides one)."""
    if not new_password or len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    ok = db.admin_reset_password(user_id, new_password)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"reset": True, "user_id": user_id}


@router.post("/users/{user_id}/warn")
def warn_user(
    user_id: int,
    message: str = Body(..., embed=True),
    current_user=Depends(_require_admin),
):
    """Send a warning notification to a user."""
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="Warning message required")
    ok = db.admin_send_notification(user_id, title="⚠️ Warning from Admin", body=message.strip())
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"warned": True, "user_id": user_id}


@router.post("/users/{user_id}/message")
def message_user(
    user_id: int,
    title: str = Body(..., embed=True),
    body: str = Body("", embed=True),
    current_user=Depends(_require_admin),
):
    """Send an admin message/notification to a user."""
    if not title or not title.strip():
        raise HTTPException(status_code=400, detail="Message title required")
    ok = db.admin_send_notification(user_id, title=title.strip(), body=(body or "").strip())
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"sent": True, "user_id": user_id}


# ---------------------------------------------------------------------------
# Campaign management
# ---------------------------------------------------------------------------


@router.get("/campaigns")
def list_all_campaigns(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(_require_admin),
):
    """List all campaigns across all users."""
    campaigns = db.admin_list_all_campaigns(limit=limit, offset=offset)
    result = []
    for c in campaigns:
        owner = db.admin_get_user(c.owner_id)
        result.append(
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "archived": c.archived,
                "created_at": c.created_at,
                "owner_id": c.owner_id,
                "owner_name": (owner.username or owner.email) if owner else None,
            }
        )
    return {"campaigns": result, "total": len(result), "offset": offset}


@router.post("/campaigns/{campaign_id}/archive")
def archive_campaign(campaign_id: str, current_user=Depends(_require_admin)):
    """Archive a campaign by ID (rollback / deactivate)."""
    ok = db.admin_archive_campaign(campaign_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"archived": True, "campaign_id": campaign_id}


@router.delete("/campaigns/{campaign_id}")
def delete_campaign(campaign_id: str, current_user=Depends(_require_admin)):
    """Permanently delete a campaign and its data."""
    ok = db.admin_delete_campaign(campaign_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"deleted": True, "campaign_id": campaign_id}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@router.get("/search")
def admin_search(
    q: str = Query("", description="Search query for users, campaigns, or characters"),
    current_user=Depends(_require_admin),
):
    """Global search across users and campaigns."""
    query = (q or "").strip()
    if len(query) < 2:
        return {"users": [], "campaigns": []}

    users = db.search_users(query, limit=10)
    user_results = [
        {
            "id": u.id,
            "email": u.email,
            "username": u.username,
            "name": db._profile_with_identity(u).get("name") or u.username or u.email,
        }
        for u in users
    ]

    matching_campaigns = db.admin_search_campaigns(query, limit=10)
    campaign_results = [
        {"id": c.id, "name": c.name, "owner_id": c.owner_id, "archived": c.archived}
        for c in matching_campaigns
    ]

    return {"users": user_results, "campaigns": campaign_results}


# ---------------------------------------------------------------------------
# Per-user reports and tickets
# ---------------------------------------------------------------------------


@router.get("/users/{user_id}/reports")
def get_reports_about_user(
    user_id: int,
    current_user=Depends(_require_admin),
):
    """Return all user reports filed against a specific user."""
    u = db.admin_get_user(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    reports = db.list_reports_about_user(user_id)
    return {
        "user_id": user_id,
        "reports": [
            {
                "id": r.id,
                "reporter_id": r.reporter_id,
                "reason": r.reason,
                "details": r.details,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            }
            for r in reports
        ],
    }


@router.get("/users/{user_id}/tickets")
def get_tickets_by_user(
    user_id: int,
    current_user=Depends(_require_admin),
):
    """Return all support tickets submitted by a specific user."""
    u = db.admin_get_user(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    tickets = db.list_tickets_by_user(user_id)
    return {
        "user_id": user_id,
        "tickets": [
            {
                "id": t.id,
                "subject": t.subject,
                "body": t.body,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in tickets
        ],
    }


# ---------------------------------------------------------------------------
# Impersonation ("Login As")
# ---------------------------------------------------------------------------


@router.post("/users/{user_id}/impersonate")
def impersonate_user(user_id: int, current_user=Depends(_require_admin)):
    """Return a short-lived JWT that grants access as the target user.

    The token expires after 15 minutes.  This action should be audited.
    """
    token = db.admin_get_impersonation_token(current_user, user_id)
    if not token:
        raise HTTPException(status_code=404, detail="User not found")
    return {"access_token": token, "token_type": "bearer", "expires_in": 900, "impersonated_user_id": user_id}


# ---------------------------------------------------------------------------
# Email bans and suspensions
# ---------------------------------------------------------------------------


def _ban_dict(ban: db.BannedEmail) -> dict:
    return {
        "id": ban.id,
        "email": ban.email,
        "reason": ban.reason,
        "ban_type": ban.ban_type,
        "suspended_until": ban.suspended_until.isoformat() if ban.suspended_until else None,
        "created_at": ban.created_at.isoformat() if ban.created_at else None,
        "created_by_id": ban.created_by_id,
    }


@router.get("/bans")
def list_bans(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user=Depends(_require_admin),
):
    """List all banned / suspended email records."""
    bans = db.list_banned_emails(limit=limit, offset=offset)
    return {"bans": [_ban_dict(b) for b in bans], "total": len(bans)}


@router.post("/bans")
def create_ban(
    email: str = Body(..., embed=True),
    reason: str = Body("", embed=True),
    ban_type: str = Body("ban", embed=True),
    suspended_until: str | None = Body(None, embed=True),
    current_user=Depends(_require_admin),
):
    """Ban or suspend an email address or @domain.com pattern."""
    from datetime import datetime, timezone

    email = (email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email or pattern required")
    if ban_type not in ("ban", "suspend"):
        raise HTTPException(status_code=400, detail="ban_type must be 'ban' or 'suspend'")

    until: datetime | None = None
    if ban_type == "suspend" and suspended_until:
        try:
            until = datetime.fromisoformat(suspended_until.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError as err:
            raise HTTPException(status_code=400, detail="Invalid suspended_until format. Use ISO-8601.") from err

    record = db.ban_email(
        email=email,
        reason=reason.strip(),
        ban_type=ban_type,
        suspended_until=until,
        created_by_id=current_user.id,
    )
    return {"ban": _ban_dict(record)}


@router.delete("/bans/{email}")
def remove_ban(email: str, current_user=Depends(_require_admin)):
    """Remove a ban or suspension record for the given email / pattern."""
    from urllib.parse import unquote
    email = unquote(email).lower().strip()
    ok = db.unban_email(email)
    if not ok:
        raise HTTPException(status_code=404, detail="No ban record found for that email")
    return {"removed": True, "email": email}
