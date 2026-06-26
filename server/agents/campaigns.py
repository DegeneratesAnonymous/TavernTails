import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .. import db
from ..auth import get_current_user
from . import sessions as sessions_agent

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CampaignSettings(BaseModel):
    """Structured settings that generative agents read when producing story content.

    These are the inputs users provide when creating or configuring a campaign.
    Each field is consumed by at least one Session Agent:

    - genre / tone / setting_summary / world_name → Storyboard Agent (plot seed),
      Narrative Agent (style hint)
    - ruleset / starting_level / house_rules → Scene Analysis Agent (rule checks),
      NPC Manager (stat scaling)
    - player_run_mode → all agents (disables AI narration when True)

    Extra / unknown fields are preserved for forward-compatibility.
    """

    # ── Story framing (Storyboard + Narrative agents) ─────────────────────
    genre: str = Field(
        default="fantasy",
        description="Campaign genre, e.g. 'fantasy', 'sci-fi', 'horror', 'western'",
    )
    tone: str = Field(
        default="balanced",
        description=(
            "Narrative tone used by the Narrative Agent: "
            "'gritty realism' | 'cinematic heroism' | 'balanced'"
        ),
    )
    setting_summary: str = Field(
        default="",
        description=(
            "Short paragraph describing the campaign world/setting. "
            "Storyboard Agent weaves this into the opening plot."
        ),
    )
    world_name: str = Field(
        default="",
        description="Name of the campaign world or region, e.g. 'Faerûn', 'The Shattered Isles'",
    )

    # ── Rules context (Scene Analysis + NPC agents) ────────────────────────
    ruleset: str = Field(
        default="",
        description="TTRPG ruleset; users enter their own system name, e.g. '5th Edition SRD', 'OSR', 'custom homebrew'",
    )
    starting_level: int = Field(
        default=1,
        ge=1,
        description="Starting character level; NPC Manager uses this for stat scaling",
    )
    house_rules: str = Field(
        default="",
        description="Free-text house rules that Scene Analysis should respect",
    )

    # ── AI control ────────────────────────────────────────────────────────
    player_run_mode: bool = Field(
        default=False,
        description="When True, AI narration is disabled; players run the session manually",
    )

    model_config = ConfigDict(extra="allow")  # preserve any additional free-form fields


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
    out = camp.model_dump()
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
        item = r.model_dump()
        sessions_list = (r.metadata_json or {}).get('sessions', [])
        item['sessions'] = [{'id': s, 'meta': f'/sessions/{s}/meta', 'files': f'/sessions/{s}/files'} for s in sessions_list]
        campaigns.append(item)
    return {'campaigns': campaigns}


@router.get('/as-gm', summary='List campaigns where current user is the assigned GM')
def list_campaigns_as_gm(current_user=Depends(get_current_user)):
    """Return campaigns owned by others where the current user is assigned as GM."""
    user_id = _require_user_id(current_user)
    rows = db.list_campaigns_as_gm(user_id)
    campaigns = []
    for r in rows:
        item = r.model_dump()
        sessions_list = (r.metadata_json or {}).get('sessions', [])
        item['sessions'] = [{'id': s, 'meta': f'/sessions/{s}/meta', 'files': f'/sessions/{s}/files'} for s in sessions_list]
        # Include pending GM invite info
        meta = r.metadata_json or {}
        pending = meta.get('pending_gm_invite')
        item['gm_invite_pending'] = pending is not None
        campaigns.append(item)
    return {'campaigns': campaigns}


@router.get('/{campaign_id}')
def get_campaign(campaign_id: str, current_user=Depends(get_current_user)):
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != _require_user_id(current_user):
        raise HTTPException(status_code=403, detail='Forbidden')
    out = c.model_dump()
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
    updates = req.model_dump(exclude_unset=True)
    c = db.update_campaign(campaign_id, owner_id, updates)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found or forbidden')
    return {'campaign': c.model_dump()}


@router.delete('/{campaign_id}')
def delete_campaign(campaign_id: str, current_user=Depends(get_current_user)):
    import shutil
    from pathlib import Path

    owner_id = _require_user_id(current_user)
    camp = db.get_campaign_by_id(campaign_id)
    if not camp or camp.owner_id != owner_id:
        raise HTTPException(status_code=404, detail='Campaign not found or forbidden')

    # Collect session IDs before deleting the campaign record
    session_ids: List[str] = (camp.metadata_json or {}).get('sessions', [])

    ok = db.delete_campaign(campaign_id, owner_id)
    if not ok:
        raise HTTPException(status_code=404, detail='Campaign not found or forbidden')

    # Delete session folders from disk
    sessions_base = Path(sessions_agent.BASE)
    for sid in session_ids:
        folder = sessions_base / str(sid)
        if folder.exists() and folder.is_dir():
            try:
                shutil.rmtree(folder)
            except Exception:
                pass

    # Delete campaign-level file storage (story_state, etc.)
    campaigns_base = Path(__file__).resolve().parents[1] / 'campaigns'
    camp_dir = campaigns_base / campaign_id
    if camp_dir.exists() and camp_dir.is_dir():
        try:
            shutil.rmtree(camp_dir)
        except Exception:
            pass

    # Delete orphaned DB records tied to this campaign
    db.delete_campaign_memory(campaign_id)

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


@router.get('/{campaign_id}/settings', response_model=Dict[str, Any])
def get_campaign_settings(campaign_id: str, current_user=Depends(get_current_user)):
    user_id = _require_user_id(current_user)
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    # Allow owner OR the assigned GM to read settings
    if c.owner_id != user_id and c.gm_user_id != user_id:
        raise HTTPException(status_code=403, detail='Forbidden')
    settings = db.get_campaign_settings(campaign_id, c.owner_id)
    if settings is None:
        raise HTTPException(status_code=404, detail='Campaign not found or forbidden')
    return {'settings': settings, 'is_owner': c.owner_id == user_id}


@router.put('/{campaign_id}/settings', response_model=Dict[str, Any])
def put_campaign_settings(
    campaign_id: str,
    settings: CampaignSettings,
    current_user=Depends(get_current_user),
):
    """Save campaign settings.

    Accepts all :class:`CampaignSettings` fields plus any additional free-form
    keys (e.g. ``world_name``, ``house_rules``).  The values stored here are
    read by the Session Agents during gameplay:

    - ``genre`` / ``tone`` / ``setting_summary`` → Storyboard + Narrative
    - ``ruleset`` / ``starting_level`` / ``house_rules`` → Scene Analysis + NPC Manager
    - ``player_run_mode`` → disables AI narration across all agents
    """
    owner_id = _require_user_id(current_user)
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != owner_id:
        raise HTTPException(status_code=403, detail='Forbidden')
    updated = db.set_campaign_settings(campaign_id, owner_id, settings.model_dump())
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
    user_id = _require_user_id(current_user)
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    # Allow owner OR GM to read the assignment
    if c.owner_id != user_id and c.gm_user_id != user_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    meta = c.metadata_json or {}
    pending_invite = meta.get('pending_gm_invite')
    result: Dict[str, Any] = {
        'campaign_id': campaign_id,
        'gm_user_id': c.gm_user_id,
        'gm_mode': c.gm_mode,
    }
    if pending_invite:
        result['pending_invite'] = {
            'user_id': pending_invite.get('user_id'),
            'token': pending_invite.get('token'),
        }
    return result


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


class GMInviteRequest(BaseModel):
    identifier: str  # email or username of the user to invite as GM


class GMInviteResponse(BaseModel):
    token: str
    accept: bool  # True = accept, False = decline


@router.post('/{campaign_id}/gm/invite')
def send_gm_invite(
    campaign_id: str,
    req: GMInviteRequest,
    current_user=Depends(get_current_user),
):
    """Send a GM invite request to another user.  The invited user receives an in-app
    notification and must accept before they become the GM."""
    owner_id = _require_user_id(current_user)
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != owner_id:
        raise HTTPException(status_code=403, detail='Only the campaign owner can invite a GM')

    # Resolve user by email or username
    from sqlmodel import Session, select
    identifier = req.identifier.strip().lower()
    with Session(db.engine) as session:
        stmt = select(db.User).where(
            (db.User.email == identifier) | (db.User.username == identifier)
        )
        target_user = session.exec(stmt).first()
        if not target_user:
            raise HTTPException(status_code=404, detail='User not found')
        if target_user.id == owner_id:
            raise HTTPException(status_code=400, detail='You cannot invite yourself as GM')

        target_id = target_user.id
        target_display = target_user.username or target_user.email or str(target_id)

    # Generate a unique invite token
    token = uuid.uuid4().hex

    # Store pending invite in campaign metadata
    from sqlmodel import Session as DBSession
    with DBSession(db.engine) as session:
        stmt = select(db.Campaign).where(db.Campaign.id == campaign_id)
        camp = session.exec(stmt).first()
        if not camp:
            raise HTTPException(status_code=404, detail='Campaign not found')
        meta = dict(camp.metadata_json or {})
        settings = meta.get('settings', {})
        meta['pending_gm_invite'] = {
            'token': token,
            'user_id': target_id,
            'invited_by_id': owner_id,
        }
        camp.metadata_json = meta
        session.add(camp)
        session.commit()

    # Look up inviter display name
    with DBSession(db.engine) as session:
        stmt = select(db.User).where(db.User.id == owner_id)
        inviter = session.exec(stmt).first()
        inviter_name = (inviter.username or inviter.email or str(owner_id)) if inviter else str(owner_id)

    # Send in-app notification to the invited user
    s = settings if isinstance(settings, dict) else {}
    world_name = s.get('world_name', '')
    setting_summary = s.get('setting_summary', '')
    genre = s.get('genre', '')
    tone = s.get('tone', '')
    summary_parts = [p for p in [genre, tone, setting_summary] if p]
    summary_text = ' · '.join(summary_parts[:2]) + (f' — {setting_summary[:80]}' if setting_summary else '')

    notification_body = (
        f'{inviter_name} has invited you to be the Game Master for '
        f'"{c.name}"'
        f'{(" (" + world_name + ")") if world_name else ""}. '
        f'{summary_text} '
        f'Use invite token: {token}'
    )
    db.admin_send_notification(
        target_id,
        title=f'GM Invite: {c.name}',
        body=notification_body,
    )

    return {
        'ok': True,
        'invited_user_id': target_id,
        'invited_display': target_display,
        'token': token,
    }


@router.post('/{campaign_id}/gm/invite/respond')
def respond_gm_invite(
    campaign_id: str,
    req: GMInviteResponse,
    current_user=Depends(get_current_user),
):
    """Accept or decline a GM invite.  The responding user must match the invite token."""
    user_id = _require_user_id(current_user)
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')

    meta = dict(c.metadata_json or {})
    invite = meta.get('pending_gm_invite')
    if not invite or invite.get('token') != req.token:
        raise HTTPException(status_code=404, detail='No matching GM invite found')
    if invite.get('user_id') != user_id:
        raise HTTPException(status_code=403, detail='This invite is not for your account')

    from sqlmodel import Session, select
    with Session(db.engine) as session:
        stmt = select(db.Campaign).where(db.Campaign.id == campaign_id)
        camp = session.exec(stmt).first()
        if not camp:
            raise HTTPException(status_code=404, detail='Campaign not found')
        camp_meta = dict(camp.metadata_json or {})
        # Remove pending invite regardless of outcome
        camp_meta.pop('pending_gm_invite', None)

        if req.accept:
            camp.gm_user_id = user_id
            camp.gm_mode = 'player'
        else:
            # On decline, revert to AI GM if this user was already set
            if camp.gm_user_id == user_id:
                camp.gm_user_id = None
                camp.gm_mode = 'ai'

        camp.metadata_json = camp_meta
        session.add(camp)
        session.commit()
        session.refresh(camp)

    return {
        'ok': True,
        'accepted': req.accept,
        'campaign_id': campaign_id,
        'gm_user_id': camp.gm_user_id,
        'gm_mode': camp.gm_mode,
    }


class FactionEntry(BaseModel):
    """A named faction with membership, alignment, and goals for agent context."""

    name: str = Field(..., description="Faction name, e.g. 'Thieves Guild'")
    alignment: str = Field(
        default="",
        description="Faction alignment, e.g. 'chaotic neutral', 'lawful evil'",
    )
    goals: List[str] = Field(
        default_factory=list,
        description="Primary faction goals, e.g. ['control the spice trade', 'overthrow the king']",
    )
    members: List[str] = Field(
        default_factory=list,
        description="Key member names, e.g. ['Guildmaster Varro', 'Shade the Informant']",
    )


class CampaignVariables(BaseModel):
    """Structured variables that generative agents factor in when producing
    story content, NPC profiles, location descriptions, dialogue, and scenes.

    Fields that the narrator infers automatically from user preferences (such as
    environment details or dialogue register) are intentionally omitted; agents
    derive those from the setting_summary and tone in campaign settings.
    """

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

    # ── Factions ───────────────────────────────────────────────────────────
    factions: List[FactionEntry] = Field(
        default_factory=list,
        description="Named factions with alignment, goals, and key members",
    )

    # ── NPCs / Characters ──────────────────────────────────────────────────
    npc_archetypes: List[str] = Field(
        default_factory=list,
        description="Dominant NPC archetypes agents should favour; motivations are goal-based and derived from faction membership, e.g. ['grizzled veteran', 'trickster merchant']",
    )
    naming_style: str = Field(
        default="",
        description="Naming convention hint for NPCs/places, e.g. 'Norse', 'Elvish', 'Latin-inspired'",
    )

    # ── Dialogue / Voice ──────────────────────────────────────────────────
    content_rating: str = Field(
        default="pg-13",
        description="Content maturity level: 'family', 'pg-13', 'mature'",
    )


@router.get('/{campaign_id}/variables')
def get_campaign_variables(campaign_id: str, current_user=Depends(get_current_user)):
    """Return the campaign variables used by generative agents."""
    user_id = _require_user_id(current_user)
    c = db.get_campaign_by_id(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if c.owner_id != user_id and c.gm_user_id != user_id:
        raise HTTPException(status_code=403, detail='Forbidden')
    variables = db.get_campaign_variables(campaign_id, c.owner_id)
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
