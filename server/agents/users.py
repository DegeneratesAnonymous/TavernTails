from fastapi import APIRouter, Depends, Query

from .. import db
from ..auth import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search")
def search_users(
    q: str = Query("", description="Username or email substring"),
    limit: int = Query(10, ge=1, le=25),
    current_user=Depends(get_current_user),
):
    query = (q or "").strip()
    if len(query) < 2:
        return {"results": []}

    results = []
    users = db.search_users(query, limit=limit)
    current_id = getattr(current_user, "id", None)
    for user in users:
        if current_id is not None and user.id == current_id:
            continue
        profile = db._profile_with_identity(user)
        results.append(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "name": profile.get("name") or user.username or user.email,
            }
        )

    return {"results": results}
