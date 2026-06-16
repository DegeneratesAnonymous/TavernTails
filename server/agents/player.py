"""Player agent (DB-backed).

Minimal, single implementation of the player router. Supports signup, login
and profile updates. Login returns a dev JWT in `access_token`.
"""

from datetime import timezone
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from .. import db
from ..auth import create_access_token, get_current_user

router = APIRouter()

STEWARD_VALIDATE_URL = "http://localhost:5555/api/games/taverntails/validate-sso"


@router.post("/player/steward-sso")
def steward_sso_login(sso_token: str = Body(..., embed=True)):
    """Exchange a Steward Dashboard SSO token for a TavernTails JWT."""
    try:
        resp = httpx.get(STEWARD_VALIDATE_URL, params={"token": sso_token}, timeout=3.0)
        data = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Steward SSO validation unavailable") from exc
    if not data.get("valid"):
        raise HTTPException(status_code=401, detail="Invalid or expired SSO token")
    user = db.get_or_create_steward_user(data["profile_id"], data["display_name"])
    token = create_access_token(subject=user.email)
    return {"access_token": token, "token_type": "bearer", "profile": db._profile_with_identity(user)}


@router.post("/player/friends")
def player_send_friend_request(identifier: str = Body(..., embed=True), current_user=Depends(get_current_user)):
    try:
        req = db.send_friend_request(current_user.email or current_user.username, identifier)
        return {"sent": True, "request_id": req.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/player/friends")
def player_list_friends(current_user=Depends(get_current_user)):
    return db.list_friends_and_requests(current_user.email or current_user.username)


@router.post("/player/friends/accept")
def player_accept_friend(from_identifier: str = Body(..., embed=True), current_user=Depends(get_current_user)):
    ok = db.accept_friend_request(current_user.email or current_user.username, from_identifier)
    if not ok:
        raise HTTPException(status_code=400, detail="No pending request or user not found")
    return {"accepted": True}


@router.post("/player/signup")
def player_signup(
    email: str = Body(...),
    password: str = Body(...),
    name: str = Body(...),
    age: int | None = Body(None),
    character: dict[str, Any] | None = Body(None),
):
    email = email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email required")
    username = name.strip() if isinstance(name, str) else None
    if not username:
        raise HTTPException(status_code=400, detail="Display name required")
    if db.get_user_by_identifier(email):
        raise HTTPException(status_code=409, detail="User exists")
    profile: dict[str, Any] = {"name": username or email.split("@")[0], "email": email, "preferences": {}}
    if character:
        profile["character"] = character
    if age is not None:
        prefs = profile.setdefault("preferences", {})
        if isinstance(prefs, dict):
            prefs["age"] = age
    user = db.create_user(email=email, password=password, username=username, profile=profile)
    return {"profile": user.profile, "verification_token": user.verification_token}


@router.post("/player/login")
def player_login(email: str | None = Body(None), name: str | None = Body(None), password: str = Body(...)):
    identifier = (email or name or "").strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="Email or username required")
    user = db.authenticate_user(identifier, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.verified:
        raise HTTPException(status_code=403, detail="Email not verified")
    # Check for active email ban / suspension
    user_email = (user.email or "").lower().strip()
    if user_email:
        ban = db._email_is_banned_or_suspended(user_email)
        if ban:
            if ban.ban_type == "suspend":
                su = ban.suspended_until
                if su is not None and su.tzinfo is None:
                    su = su.replace(tzinfo=timezone.utc)
                until = su.strftime("%Y-%m-%d") if su else "an unspecified date"
                raise HTTPException(status_code=403, detail=f"Account suspended until {until}.")
            raise HTTPException(status_code=403, detail="Account banned. Contact support if you believe this is an error.")
    subject = user.email or user.username or identifier
    token = create_access_token(subject)
    return {"profile": user.profile, "access_token": token, "token_type": "bearer"}


@router.post("/player/verify-email")
def verify_email(email: str = Body(...), token: str = Body(...)):
    ok = db.verify_user(email, token)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid token or user not found")
    return {"verified": True}


@router.post("/player/resend-verification")
def resend_verification(email: str = Body(...)):
    user = db.get_user_by_identifier(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    token = __import__("uuid").uuid4().hex
    db.set_verification_token(email, token)
    return {"verification_token": token}


@router.post("/player/profile")
def player_profile(
    identifier: str = Body(...),
    name: str | None = Body(None),
    character: dict[str, Any] | None = Body(None),
    preferences: dict[str, Any] | None = Body(None),
):
    user = db.get_user_by_identifier(identifier.strip())
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    updates: dict[str, Any] = {}
    if name is not None:
        updates["name"] = name
    if character is not None:
        updates["character"] = character
    if preferences is not None:
        updates.setdefault("preferences", {}).update(preferences)
    updated = db.update_profile(identifier, updates)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update profile")
    return {"player_profile": updated.profile}


@router.post("/player/dndbeyond")
def import_dndbeyond_character(text: str | None = Body(None), url: str | None = Body(None), export: dict[str, Any] | None = Body(None)):
    import re

    import httpx

    if text:
        m = re.search(r"Name[:\\s]+(.+)", text, re.I)
        name = m.group(1).strip() if m else None
        return {"dndbeyond_character": {"imported": bool(name), "character": {"name": name}}}
    if export:
        name = export.get("name") or export.get("character", {}).get("name")
        return {"dndbeyond_character": {"imported": bool(name), "character": {"name": name}}}
    if url:
        try:
            resp = httpx.get(url, timeout=10.0)
            body = resp.text
            m = re.search(r"Name[:\\s]+(.+)", body, re.I)
            name = m.group(1).strip() if m else None
            return {"dndbeyond_character": {"imported": bool(name), "character": {"name": name}}}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}") from e
    return {"dndbeyond_character": {"imported": False, "character": {}}}


@router.get("/player/beyond20")
def get_beyond20_domains(identifier: str = Query(...)):
    domains = db.get_beyond20_domains_for(identifier.strip())
    if domains is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"domains": domains}


@router.post("/player/beyond20")
def set_beyond20_domains(identifier: str = Body(...), domains_text: str | None = Body(None), domains_list: list[str] | None = Body(None)):
    def _parse_domains_text(text: str) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        valid: list[str] = []
        for ln in lines:
            if not ln.startswith("http://") and not ln.startswith("https://"):
                raise ValueError(f"Domain must start with http:// or https://: {ln}")
            if " " in ln:
                raise ValueError(f"Invalid domain (contains spaces): {ln}")
            valid.append(ln)
        return valid

    if domains_list is not None:
        parsed = [d.strip() for d in domains_list]
    elif domains_text is not None:
        parsed = _parse_domains_text(domains_text)
    else:
        raise HTTPException(status_code=400, detail="Provide domains")
    saved = db.set_beyond20_domains_for(identifier.strip(), parsed)
    if saved is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"domains": saved}


@router.get("/player/me")
def player_me(current_user=Depends(get_current_user)):
    return {"profile": current_user.profile}


@router.put("/player/me")
def update_player_me(
    name: str | None = Body(None),
    email: str | None = Body(None),
    username: str | None = Body(None),
    current_user=Depends(get_current_user),
):
    """Update the current user's own display name, email, and/or username."""
    if name is not None:
        name = name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Display name cannot be empty.")
    if email is not None:
        email = email.strip().lower()
        if not email or "@" not in email:
            raise HTTPException(status_code=400, detail="A valid email address is required.")
    if username is not None:
        username = username.strip()
    if name is None and email is None and username is None:
        raise HTTPException(status_code=400, detail="No fields to update.")
    try:
        updated = db.update_user_self(current_user.id, name=name, email=email, username=username)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")
    response: dict = {"profile": db._profile_with_identity(updated)}
    # If the email actually changed, the JWT subject (email) is now stale — issue a fresh token.
    old_email = (current_user.email or "").lower()
    new_email = (updated.email or "").lower()
    if email is not None and new_email and new_email != old_email:
        response["access_token"] = create_access_token(subject=new_email)
    return response


@router.post("/player/me/change-password")
def change_player_password(
    current_password: str = Body(...),
    new_password: str = Body(...),
    current_user=Depends(get_current_user),
):
    """Change the current user's own password (requires current password for verification)."""
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")
    ok = db.change_user_password(current_user.id, current_password, new_password)
    if not ok:
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    return {"ok": True}


@router.post("/player/admin-mode")
def set_admin_mode(enabled: bool = Body(..., embed=True), current_user=Depends(get_current_user)):
    if not db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    updated = db.set_admin_mode(current_user.id, bool(enabled))
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update admin mode")
    return {"profile": updated.profile}


@router.get("/player/beyond20/relay-token")
def get_beyond20_relay_token(current_user=Depends(get_current_user)):
    if current_user.id is None:
        raise HTTPException(status_code=400, detail="User missing id")
    token = db.ensure_beyond20_relay_token_for_user_id(current_user.id)
    if not token:
        raise HTTPException(status_code=500, detail="Unable to create relay token")
    return {"relay_token": token}


@router.post("/player/beyond20/relay-token/rotate")
def rotate_beyond20_relay_token(current_user=Depends(get_current_user)):
    if current_user.id is None:
        raise HTTPException(status_code=400, detail="User missing id")
    token = db.rotate_beyond20_relay_token_for_user_id(current_user.id)
    if not token:
        raise HTTPException(status_code=500, detail="Unable to rotate relay token")
    return {"relay_token": token}
