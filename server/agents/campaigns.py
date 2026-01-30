from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..auth import get_current_user
from . import sessions as sessions_agent

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _require_user_id(current_user) -> int:
    owner_id = getattr(current_user, 'id', None)
    if not isinstance(owner_id, int):
        raise HTTPException(status_code=401, detail='Invalid authentication credentials')
    return owner_id


def _require_user_identifier(current_user) -> str:
    identifier = getattr(current_user, 'email', None) or getattr(current_user, 'username', None)
    if not isinstance(identifier, str) or not identifier.strip():
        raise HTTPException(status_code=401, detail='Invalid authentication credentials')
    return identifier


class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    invites: Optional[List[str]] = None
    create_session: Optional[bool] = True


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    archived: Optional[bool] = None


@router.post('', status_code=201)
def create_campaign(req: CampaignCreate, current_user=Depends(get_current_user)):
    owner_id = _require_user_id(current_user)
    camp = db.create_campaign(owner_id=owner_id, name=req.name, description=req.description)
    campaign_id = camp.id
    if campaign_id is None:
        raise HTTPException(status_code=500, detail='Failed to create campaign')
    # Optionally create an initial linked session and persist that link to campaign.metadata
    created_session = None
    try:
        owner_email = _require_user_identifier(current_user)
        if req.create_session:
            sid, meta = sessions_agent.create_session_folder(req.name, owner_email, invites=req.invites, campaign_id=str(campaign_id))
            db.add_session_to_campaign(campaign_id, owner_id, sid)
            created_session = sid
    except Exception:
        # non-fatal: campaign created but session creation failed
        created_session = None
    out = camp.dict()
    # include enriched session links
    sessions_list = (camp.metadata_json or {}).get('sessions', [])
    out['sessions'] = [{'id': s, 'meta': f'/sessions/{s}/meta', 'files': f'/sessions/{s}/files'} for s in sessions_list]
    if created_session and created_session not in sessions_list:
        out['sessions'].append({'id': created_session, 'meta': f'/sessions/{created_session}/meta', 'files': f'/sessions/{created_session}/files'})
    return {'campaign': out}


@router.get('', summary='List campaigns visible to current user')
def list_campaigns(current_user=Depends(get_current_user)):
    owner_id = _require_user_id(current_user)
    rows = db.list_campaigns_for_owner(owner_id)
    campaigns = []
    for r in rows:
        item = r.dict()
        sessions_list = (r.metadata_json or {}).get('sessions', [])
        item['sessions'] = [{'id': s, 'meta': f'/sessions/{s}/meta', 'files': f'/sessions/{s}/files'} for s in sessions_list]
        campaigns.append(item)
    return {'campaigns': campaigns}


@router.get('/{campaign_id}')
def get_campaign(campaign_id: str, current_user=Depends(get_current_user)):
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != _require_user_id(current_user):
        raise HTTPException(status_code=403, detail='Forbidden')
    out = c.dict()
    sessions_list = (c.metadata_json or {}).get('sessions', [])
    out['sessions'] = [{'id': s, 'meta': f'/sessions/{s}/meta', 'files': f'/sessions/{s}/files'} for s in sessions_list]
    return {'campaign': out}


@router.post('/{campaign_id}/create_session', status_code=201)
def create_session_from_campaign(campaign_id: str, current_user=Depends(get_current_user)):
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != _require_user_id(current_user):
        raise HTTPException(status_code=403, detail='Forbidden')
    owner_email = _require_user_identifier(current_user)
    invites = (c.metadata_json or {}).get('invites', [])
    try:
        sid, meta = sessions_agent.create_session_folder(c.name, owner_email, invites=invites, campaign_id=str(campaign_id))
        db.add_session_to_campaign(campaign_id, c.owner_id, sid)
        return {'session_id': sid, 'meta': meta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put('/{campaign_id}')
def update_campaign(campaign_id: str, req: CampaignUpdate, current_user=Depends(get_current_user)):
    owner_id = _require_user_id(current_user)
    updates = req.dict(exclude_unset=True)
    c = db.update_campaign(campaign_id, owner_id, updates)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found or forbidden')
    return {'campaign': c.dict()}


@router.delete('/{campaign_id}')
def delete_campaign(campaign_id: str, current_user=Depends(get_current_user)):
    owner_id = _require_user_id(current_user)
    ok = db.delete_campaign(campaign_id, owner_id)
    if not ok:
        raise HTTPException(status_code=404, detail='Campaign not found or forbidden')
    return {'ok': True}


@router.get('/{campaign_id}/settings')
def get_campaign_settings(campaign_id: str, current_user=Depends(get_current_user)):
    owner_id = _require_user_id(current_user)
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != owner_id:
        raise HTTPException(status_code=403, detail='Forbidden')
    settings = db.get_campaign_settings(campaign_id, owner_id)
    if settings is None:
        raise HTTPException(status_code=404, detail='Campaign not found or forbidden')
    return {'settings': settings}


@router.put('/{campaign_id}/settings')
def put_campaign_settings(
    campaign_id: str,
    settings: Dict[str, Any] = Body(...),
    current_user=Depends(get_current_user),
):
    owner_id = _require_user_id(current_user)
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != owner_id:
        raise HTTPException(status_code=403, detail='Forbidden')
    if not isinstance(settings, dict):
        raise HTTPException(status_code=400, detail='Settings must be an object')
    updated = db.set_campaign_settings(campaign_id, owner_id, settings)
    if not updated:
        raise HTTPException(status_code=404, detail='Campaign not found or forbidden')
    meta = updated.metadata_json or {}
    out = meta.get('settings') if isinstance(meta, dict) else {}
    return {'settings': out if isinstance(out, dict) else {}}
