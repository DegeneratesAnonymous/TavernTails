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
    """List all registered users."""
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
    return {"users": result, "total": len(result), "offset": offset}


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
