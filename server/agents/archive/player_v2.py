"""Player Agent (DB-backed) - v2

Clean, single-file DB-backed player router. Use this while `player.py` is being repaired.
"""

from fastapi import APIRouter, Body, HTTPException, Query
from typing import Dict, Any, Optional, List
import re
import httpx
import uuid

from .. import db


router = APIRouter()


def _parse_domains_text(text: str) -> List[str]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    valid = []
    for ln in lines:
        if not re.match(r'^https?://', ln):
            raise ValueError(f"Domain must start with http:// or https://: {ln}")
        if ' ' in ln:
            raise ValueError(f"Invalid domain (contains spaces): {ln}")
        valid.append(ln)
    return valid


@router.post("/player/signup")
def player_signup(email: str = Body(...), password: str = Body(...), name: Optional[str] = Body(None), character: Dict[str, Any] = Body({})):
    if db.get_user_by_identifier(email):
        raise HTTPException(status_code=409, detail="User exists")
    profile = {"name": name or email.split('@')[0], "email": email, "character": character, "preferences": {}}
    user = db.create_user(email=email, password=password, username=name, profile=profile)
    return {"profile": user.profile, "verification_token": user.verification_token}


@router.post("/player/login")
def player_login(email: Optional[str] = Body(None), name: Optional[str] = Body(None), password: str = Body(...)):
    identifier = email or name
    user = db.authenticate_user(identifier, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.verified:
        raise HTTPException(status_code=403, detail="Email not verified")
    return {"profile": user.profile}


@router.post('/player/verify-email')
def verify_email(email: str = Body(...), token: str = Body(...)):
    ok = db.verify_user(email, token)
    if not ok:
        raise HTTPException(status_code=400, detail='Invalid token or user not found')
    return {'verified': True}


@router.post('/player/resend-verification')
def resend_verification(email: str = Body(...)):
    user = db.get_user_by_identifier(email)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    token = uuid.uuid4().hex
    db.set_verification_token(email, token)
    return {'verification_token': token}


@router.post("/player/profile")
def player_profile(identifier: str = Body(...), name: Optional[str] = Body(None), character: Optional[Dict[str, Any]] = Body(None), preferences: Optional[Dict[str, Any]] = Body(None)):
    user = db.get_user_by_identifier(identifier)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    updates = {}
    if name is not None:
        updates['name'] = name
    if character is not None:
        updates['character'] = character
    if preferences is not None:
        updates.setdefault('preferences', {}).update(preferences)
    updated = db.update_profile(identifier, updates)
    if not updated:
        raise HTTPException(status_code=500, detail='Failed to update profile')
    return {"player_profile": updated.profile}


@router.post("/player/dndbeyond")
def import_dndbeyond_character(text: Optional[str] = Body(None), url: Optional[str] = Body(None), export: Optional[Dict[str, Any]] = Body(None)):
    if text:
        m = re.search(r"Name[:\s]+(.+)", text, re.I)
        name = m.group(1).strip() if m else None
        return {"dndbeyond_character": {"imported": bool(name), "character": {"name": name}}}
    if export:
        name = export.get('name') or export.get('character', {}).get('name')
        return {"dndbeyond_character": {"imported": bool(name), "character": {"name": name}}}
    if url:
        try:
            resp = httpx.get(url, timeout=10.0)
            body = resp.text
            m = re.search(r"Name[:\s]+(.+)", body, re.I)
            name = m.group(1).strip() if m else None
            return {"dndbeyond_character": {"imported": bool(name), "character": {"name": name}}}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}")
    return {"dndbeyond_character": {"imported": False, "character": {}}}


@router.get("/player/beyond20")
def get_beyond20_domains(identifier: str = Query(...)):
    domains = db.get_beyond20_domains_for(identifier)
    if domains is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"domains": domains}


@router.post("/player/beyond20")
def set_beyond20_domains(identifier: str = Body(...), domains_text: Optional[str] = Body(None), domains_list: Optional[List[str]] = Body(None)):
    if domains_list is not None:
        parsed = [d.strip() for d in domains_list]
    elif domains_text is not None:
        parsed = _parse_domains_text(domains_text)
    else:
        raise HTTPException(status_code=400, detail="Provide domains")
    saved = db.set_beyond20_domains_for(identifier, parsed)
    if saved is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"domains": saved}