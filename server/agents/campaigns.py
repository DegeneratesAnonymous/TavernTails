from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

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
    description: str | None = ""
    invites: list[str] | None = None
    create_session: bool | None = True


class CampaignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    archived: bool | None = None


class GMAssignment(BaseModel):
    gm_user_id: int | None = None  # None or user ID for player GM, treated as "AI" if None


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
    # Build enriched session list from persisted metadata.
    sessions_list = (camp.metadata_json or {}).get('sessions', [])
    out['sessions'] = [{'id': s, 'meta': f'/sessions/{s}/meta', 'files': f'/sessions/{s}/files'} for s in sessions_list]
    # Ensure the newly created session is always present in the response even if
    # add_session_to_campaign hasn't refreshed camp in-process yet.
    if created_session:
        existing_ids = {s['id'] for s in out['sessions']}
        if created_session not in existing_ids:
            out['sessions'].append({
                'id': created_session,
                'meta': f'/sessions/{created_session}/meta',
                'files': f'/sessions/{created_session}/files',
            })
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


@router.get('/{campaign_id}/sessions/{session_id}/validate')
def validate_session_belongs_to_campaign(campaign_id: str, session_id: str, current_user=Depends(get_current_user)):
    """Return 200 if session_id belongs to campaign_id, 404 otherwise.
    Useful for defensive UI checks before bootstrapping gameplay."""
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != _require_user_id(current_user):
        raise HTTPException(status_code=403, detail='Forbidden')
    sessions_list = (c.metadata_json or {}).get('sessions', [])
    if session_id not in sessions_list:
        raise HTTPException(status_code=404, detail='Session does not belong to this campaign')
    return {'ok': True, 'campaign_id': campaign_id, 'session_id': session_id}


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


@router.delete('/purge')
def purge_campaigns(name_like: str | None = None, current_user=Depends(get_current_user)):
    if not db.is_admin_user(current_user):
        raise HTTPException(status_code=403, detail='Admin privileges required')
    owner_id = _require_user_id(current_user)
    tokens: List[str] = []
    if name_like:
        tokens = [part.strip() for part in name_like.split(',') if part.strip()]
    deleted = db.purge_campaigns(owner_id=owner_id, name_tokens=tokens)
    return {'deleted': deleted}


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


@router.put('/{campaign_id}/gm')
def assign_gm(
    campaign_id: str,
    assignment: GMAssignment,
    current_user=Depends(get_current_user),
):
    """Assign a GM to the campaign. Pass gm_user_id=null for AI GM, or a user ID for player GM."""
    owner_id = _require_user_id(current_user)
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != owner_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    # Update GM assignment in database
    from sqlmodel import Session
    with Session(db.engine) as session:
        from sqlmodel import select
        stmt = select(db.Campaign).where(db.Campaign.id == campaign_id)
        camp = session.exec(stmt).first()
        if not camp:
            raise HTTPException(status_code=404, detail='Campaign not found')

        camp.gm_user_id = assignment.gm_user_id
        camp.gm_mode = "player" if assignment.gm_user_id else "ai"

        session.add(camp)
        session.commit()
        session.refresh(camp)

        return {
            'campaign_id': campaign_id,
            'gm_user_id': camp.gm_user_id,
            'gm_mode': camp.gm_mode,
        }


@router.get('/{campaign_id}/gm')
def get_gm_assignment(campaign_id: str, current_user=Depends(get_current_user)):
    """Get the current GM assignment for a campaign."""
    owner_id = _require_user_id(current_user)
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != owner_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    return {
        'campaign_id': campaign_id,
        'gm_user_id': c.gm_user_id,
        'gm_mode': c.gm_mode,
    }


@router.get('/{campaign_id}/players')
def get_campaign_players(campaign_id: str, current_user=Depends(get_current_user)):
    """Get list of players in a campaign (owner + invites for now)."""
    owner_id = _require_user_id(current_user)
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != owner_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    # For now, return owner as the only player
    # In the future, this should include invited players from metadata
    from sqlmodel import Session, select
    with Session(db.engine) as session:
        stmt = select(db.User).where(db.User.id == c.owner_id)
        owner = session.exec(stmt).first()
        if not owner:
            return {'players': []}

        players = [{
            'id': owner.id,
            'username': owner.username,
            'email': owner.email,
        }]

        return {'players': players}


class CampaignVariables(BaseModel):
    """Structured variables that generative agents factor in when producing
    story content, NPC profiles, location descriptions, dialogue, and scenes."""

    # ── Narrative / Story ──────────────────────────────────────────────────
    themes: List[str] = Field(
        default_factory=list,
        description="Recurring story themes, e.g. ['redemption', 'betrayal', 'survival']",
    )
    pacing: str = Field(
        default="moderate",
        description="Overall story pacing: 'slow' | 'moderate' | 'fast'",
    )
    narrative_style: str = Field(
        default="balanced",
        description="Narrative register: 'epic', 'intimate', 'gritty', 'lighthearted', 'balanced'",
    )

    # ── NPCs / Characters ──────────────────────────────────────────────────
    factions: List[str] = Field(
        default_factory=list,
        description="Named factions or groups present in the world, e.g. ['Thieves Guild', 'Royal Guard']",
    )
    npc_archetypes: List[str] = Field(
        default_factory=list,
        description="Dominant NPC archetypes agents should favour, e.g. ['grizzled veteran', 'trickster merchant']",
    )
    naming_style: str = Field(
        default="",
        description="Naming convention hint for NPCs/places, e.g. 'Norse', 'Elvish', 'Latin-inspired'",
    )

    # ── Locations / World ─────────────────────────────────────────────────
    primary_environment: str = Field(
        default="",
        description="Dominant environment type, e.g. 'arctic tundra', 'tropical jungle', 'underground caverns'",
    )
    location_tags: List[str] = Field(
        default_factory=list,
        description="Descriptive location tags, e.g. ['dangerous', 'mystical', 'urban', 'ruined']",
    )

    # ── Dialogue / Voice ──────────────────────────────────────────────────
    dialogue_style: str = Field(
        default="",
        description="Preferred dialogue register: 'formal', 'archaic', 'modern', 'regional slang'",
    )
    content_rating: str = Field(
        default="pg-13",
        description="Content maturity level: 'family', 'pg-13', 'mature'",
    )


@router.get('/{campaign_id}/variables')
def get_campaign_variables(campaign_id: str, current_user=Depends(get_current_user)):
    """Return the campaign variables used by generative agents."""
    owner_id = _require_user_id(current_user)
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != owner_id:
        raise HTTPException(status_code=403, detail='Forbidden')
    variables = db.get_campaign_variables(campaign_id, owner_id)
    if variables is None:
        raise HTTPException(status_code=404, detail='Campaign not found or forbidden')
    return {'variables': variables}


@router.put('/{campaign_id}/variables')
def put_campaign_variables(
    campaign_id: str,
    variables: CampaignVariables,
    current_user=Depends(get_current_user),
):
    """Save campaign variables used by generative agents."""
    owner_id = _require_user_id(current_user)
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != owner_id:
        raise HTTPException(status_code=403, detail='Forbidden')
    updated = db.set_campaign_variables(campaign_id, owner_id, variables.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail='Campaign not found or forbidden')
    meta = updated.metadata_json or {}
    out = meta.get('variables') if isinstance(meta, dict) else {}
    return {'variables': out if isinstance(out, dict) else {}}
