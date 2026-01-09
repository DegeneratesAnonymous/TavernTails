from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..auth import get_current_user
from . import sessions as sessions_agent

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


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
    owner_id = getattr(current_user, 'id', None)
    camp = db.create_campaign(owner_id=owner_id, name=req.name, description=req.description)
    # Optionally create an initial linked session and persist that link to campaign.metadata
    created_session = None
    try:
        owner_email = getattr(current_user, 'email', None) or getattr(current_user, 'username', None)
        if req.create_session:
            sid, meta = sessions_agent.create_session_folder(req.name, owner_email, invites=req.invites)
            db.add_session_to_campaign(camp.id, owner_id, sid)
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
    owner_id = getattr(current_user, 'id', None)
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
    if c.owner_id != getattr(current_user, 'id', None):
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
    if c.owner_id != getattr(current_user, 'id', None):
        raise HTTPException(status_code=403, detail='Forbidden')
    owner_email = getattr(current_user, 'email', None) or getattr(current_user, 'username', None)
    invites = (c.metadata_json or {}).get('invites', [])
    try:
        sid, meta = sessions_agent.create_session_folder(c.name, owner_email, invites=invites)
        db.add_session_to_campaign(campaign_id, c.owner_id, sid)
        return {'session_id': sid, 'meta': meta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put('/{campaign_id}')
def update_campaign(campaign_id: str, req: CampaignUpdate, current_user=Depends(get_current_user)):
    owner_id = getattr(current_user, 'id', None)
    updates = req.dict(exclude_unset=True)
    c = db.update_campaign(campaign_id, owner_id, updates)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found or forbidden')
    return {'campaign': c.dict()}


@router.delete('/{campaign_id}')
def delete_campaign(campaign_id: str, current_user=Depends(get_current_user)):
    owner_id = getattr(current_user, 'id', None)
    ok = db.delete_campaign(campaign_id, owner_id)
    if not ok:
        raise HTTPException(status_code=404, detail='Campaign not found or forbidden')
    return {'ok': True}
