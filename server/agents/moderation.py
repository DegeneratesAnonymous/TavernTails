"""Moderation agent — user blocking and reporting endpoints."""

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from .. import db
from ..auth import get_current_user

router = APIRouter(prefix="/moderation", tags=["moderation"])


def _require_admin(current_user=Depends(get_current_user)):
    if not db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


def _block_dict(block: db.UserBlock) -> dict:
    return {
        "id": block.id,
        "blocker_id": block.blocker_id,
        "blocked_id": block.blocked_id,
        "created_at": block.created_at.isoformat() if block.created_at else None,
    }


def _report_dict(report: db.UserReport, include_users: bool = False) -> dict:
    data: dict = {
        "id": report.id,
        "reporter_id": report.reporter_id,
        "reported_id": report.reported_id,
        "reason": report.reason,
        "details": report.details,
        "status": report.status,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "reviewed_at": report.reviewed_at.isoformat() if report.reviewed_at else None,
    }
    if include_users:
        reporter = db.admin_get_user(report.reporter_id)
        reported = db.admin_get_user(report.reported_id)
        if reporter:
            data["reporter_name"] = (reporter.profile or {}).get("name") or reporter.username or reporter.email
        if reported:
            data["reported_name"] = (reported.profile or {}).get("name") or reported.username or reported.email
    return data


# ---------------------------------------------------------------------------
# Blocking
# ---------------------------------------------------------------------------


@router.post("/block/{user_id}")
def block_user(user_id: int, current_user=Depends(get_current_user)):
    """Block another user. Idempotent."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot block yourself")
    target = db.admin_get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    block = db.block_user(blocker_id=current_user.id, blocked_id=user_id)
    return {"blocked": True, "block": _block_dict(block)}


@router.delete("/block/{user_id}")
def unblock_user(user_id: int, current_user=Depends(get_current_user)):
    """Unblock a previously blocked user."""
    removed = db.unblock_user(blocker_id=current_user.id, blocked_id=user_id)
    return {"unblocked": removed}


@router.get("/blocks")
def list_my_blocks(current_user=Depends(get_current_user)):
    """Return the list of users the current user has blocked."""
    blocks = db.list_blocks(current_user.id)
    result = []
    for b in blocks:
        entry = _block_dict(b)
        target = db.admin_get_user(b.blocked_id)
        if target:
            profile = db._profile_with_identity(target)
            entry["blocked_name"] = profile.get("name") or target.username or target.email
        result.append(entry)
    return {"blocks": result}


@router.get("/block/{user_id}/status")
def block_status(user_id: int, current_user=Depends(get_current_user)):
    """Check whether the current user has blocked a given user."""
    blocked = db.is_blocked(blocker_id=current_user.id, blocked_id=user_id)
    return {"user_id": user_id, "is_blocked": blocked}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


@router.post("/report/{user_id}")
def report_user(
    user_id: int,
    reason: str = Body(..., embed=True),
    details: str = Body("", embed=True),
    current_user=Depends(get_current_user),
):
    """Report another user for bad behaviour."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot report yourself")
    if reason not in db._VALID_REPORT_REASONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid reason. Must be one of: {', '.join(sorted(db._VALID_REPORT_REASONS))}",
        )
    target = db.admin_get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    report = db.create_user_report(
        reporter_id=current_user.id,
        reported_id=user_id,
        reason=reason,
        details=details,
    )
    return {"reported": True, "report": _report_dict(report)}


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.get("/reports")
def list_reports(
    status: str | None = Query(None, description="Filter by status: open, reviewed, dismissed"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(_require_admin),
):
    """List all user reports (admin only)."""
    reports = db.list_user_reports(status=status, limit=limit, offset=offset)
    return {
        "reports": [_report_dict(r, include_users=True) for r in reports],
        "total": len(reports),
        "offset": offset,
    }


@router.get("/reports/{report_id}")
def get_report(report_id: int, current_user=Depends(_require_admin)):
    """Get details of a specific user report (admin only)."""
    report = db.get_user_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"report": _report_dict(report, include_users=True)}


@router.patch("/reports/{report_id}/status")
def update_report_status(
    report_id: int,
    status: str = Body(..., embed=True),
    current_user=Depends(_require_admin),
):
    """Update the status of a user report (admin only)."""
    if status not in db._VALID_REPORT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(db._VALID_REPORT_STATUSES))}",
        )
    report = db.update_report_status(report_id, status)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"report": _report_dict(report, include_users=True)}
