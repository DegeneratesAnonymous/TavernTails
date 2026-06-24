import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator

from .. import db
from ..auth import get_current_user
from ..realtime import broadcaster
from ..storage import documents as doc_storage
from . import image as image_agent
from . import narrative as narrative_agent
from . import notes as notes_agent
from . import npc as npc_agent
from . import scene as scene_agent
from . import scene_director as scene_director_agent
from . import storyboard as storyboard_agent
from . import suggestions as suggestions_agent
from .entity_schemas import EntityAssociation, PlayerEntityCard
from .narrative_director import DirectorOutput
from .narrative_director import direct_scene as narrative_direct_scene
from .scene_director import SceneDirectorOutput, SceneDirectorRequest, build_image_prompt
from .scene_validator import (
    MINIMUM_SCORE,
    build_fallback_scene,
    build_retry_feedback,
    validate_scene_quality,
)
from .story_state import (
    derive_campaign_dna,
    load_story_state,
    save_story_state,
    story_dashboard_payload,
    sync_threads_from_entities,
    update_state_after_scene,
)
from .story_validator import validate_story_quality as validate_story_structure
from .visual_director import run_visual_pipeline
from .visual_state import load_visual_state, save_visual_state

router = APIRouter(prefix="/sessions")

BASE = Path(__file__).resolve().parents[1] / 'sessions'


def is_player_run_mode(session_id: str) -> bool:
    """Return True if the session's campaign has player-run mode enabled."""
    if not session_id:
        return False
    meta_path = BASE / session_id / 'meta.json'
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        return False
    campaign_id = meta.get('campaign_id')
    if not campaign_id:
        return False
    campaign = db.get_campaign_by_id(str(campaign_id))
    if not campaign:
        return False
    settings = (campaign.metadata_json or {}).get('settings') if isinstance(campaign.metadata_json, dict) else {}
    if not isinstance(settings, dict):
        return False
    return bool(settings.get('player_run_mode'))
BASE.mkdir(exist_ok=True)

_doc_store = doc_storage.get_document_store()


def _identifier_for_user(user) -> str:
    value = (getattr(user, 'email', None) or getattr(user, 'username', '') or '').strip()
    return value.lower()


def _normalize_email(value: str | None) -> str:
    return (value or '').strip().lower()


def _normalize_invites(raw):
    normalized = []
    for entry in raw or []:
        if isinstance(entry, str):
            normalized.append({
                'email': _normalize_email(entry),
                'min_level': 1,
                'accepted': False,
                'character_id': None,
                'character_name': None,
            })
        elif isinstance(entry, dict):
            normalized.append({
                'email': _normalize_email(entry.get('email')),
                'min_level': max(1, int(entry.get('min_level', 1))),
                'accepted': bool(entry.get('accepted', False)),
                'character_id': entry.get('character_id'),
                'character_name': entry.get('character_name'),
                'note': entry.get('note'),
                'accepted_at': entry.get('accepted_at'),
            })
    return normalized


def create_session_folder(name: str, owner_email: str, invites=None, campaign_id: str | None = None):
    """Create a session folder programmatically and return the session id and meta."""
    sid = uuid.uuid4().hex[:8]
    folder = BASE / sid
    if folder.exists():
        raise Exception('Session id collision')
    folder.mkdir(parents=True)
    meta = {
        'id': sid,
        'name': name,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'owner': owner_email,
        'campaign_id': campaign_id,
        'invites': _normalize_invites(invites or []),
        'members': [
            {
                'email': owner_email,
                'character_id': None,
                'role': 'owner'
            }
        ]
    }
    (folder / 'meta.json').write_text(json.dumps(meta))
    (folder / 'notes.md').write_text(f'# Notes for {name}\n')
    (folder / 'npcs.json').write_text('[]')
    (folder / 'pcs.json').write_text('[]')
    (folder / 'associations.json').write_text('[]')
    (folder / 'story.json').write_text(json.dumps([{'type': 'meta', 'text': 'The session begins.'}]))
    (folder / 'scene.json').write_text(json.dumps({
        'id': 'opening',
        'title': f"{name} — Opening Scene",
        'image': None,
        'text': 'Your adventure is about to begin. Choose an approach to set the tone.',
        'choices': [
            {'id': 'scout', 'label': 'Scout ahead cautiously'},
            {'id': 'parley', 'label': 'Seek conversation first'},
            {'id': 'press_on', 'label': 'Press forward decisively'},
        ],
    }))

    # Default documents:
    # - Some are player-visible (shared)
    # - Some are AI-GM private (category=gm + visibility=hidden) and are hidden from the UI.
    try:
        _doc_store.save_document(
            session_id=sid,
            name='Session Notes',
            content='# Session Notes\n\n- ',
            category='core',
            visibility='shared',
        )
        _doc_store.save_document(
            session_id=sid,
            name='GM Scratchpad',
            content='(AI GM private)\n\nUse this for behind-the-scenes state, secrets, and internal tracking.',
            category='gm',
            visibility='hidden',
        )
        _doc_store.save_document(
            session_id=sid,
            name='GM World State',
            content='(AI GM private)\n\n- Open threads:\n- Secrets:\n- NPC motives:\n',
            category='gm',
            visibility='hidden',
        )
    except Exception:
        # Documents are best-effort; session creation must still succeed.
        pass
    return sid, meta


def _user_is_member(meta: dict, identifier: str) -> bool:
    owner = _normalize_email(meta.get('owner'))
    if identifier == owner:
        return True
    invites = _normalize_invites(meta.get('invites'))
    if any(inv['email'] == identifier for inv in invites):
        return True
    for member in meta.get('members', []) or []:
        if _normalize_email(member.get('email')) == identifier:
            return True
    return False


class CreateSessionRequest(BaseModel):
    name: str
    owner: str | None = None


@router.post('', status_code=201)
def create_session(req: CreateSessionRequest, current_user=Depends(get_current_user)):
    try:
        owner_email = current_user.email or current_user.username
        sid, meta = create_session_folder(req.name, owner_email, invites=[])
        return {'id': sid, 'name': req.name, 'owner': owner_email}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get('', response_model=list[dict])
def list_sessions(current_user=Depends(get_current_user)):
    out = []
    identifier = _identifier_for_user(current_user)
    for p in BASE.iterdir():
        if p.is_dir():
            meta = p / 'meta.json'
            if meta.exists():
                try:
                    d = json.loads(meta.read_text())
                except Exception:
                    d = {'id': p.name, 'name': p.name}
            else:
                d = {'id': p.name, 'name': p.name}
            # filter to sessions where the current user is owner, invited, or already a member
            if _user_is_member(d, identifier):
                d['invites'] = _normalize_invites(d.get('invites'))
                d['members'] = d.get('members', []) or []
                out.append(d)
    return out


@router.get('/{session_id}/files')
def get_files(session_id: str, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_file = folder / 'meta.json'
    if meta_file.exists():
        data = json.loads(meta_file.read_text())
        identifier = _identifier_for_user(current_user)
        if not _user_is_member(data, identifier):
            raise HTTPException(status_code=403, detail='Not a member of this session')
    files = [p.name for p in folder.iterdir() if p.is_file()]
    return {'files': files}


@router.get('/{session_id}/meta')
def get_meta(session_id: str, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta = folder / 'meta.json'
    if not meta.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        data = json.loads(meta.read_text())
        identifier = _identifier_for_user(current_user)
        if not _user_is_member(data, identifier):
            raise HTTPException(status_code=403, detail='Not a member of this session')
        data['invites'] = _normalize_invites(data.get('invites'))
        data['members'] = data.get('members', []) or []
        return data
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err


class SetCharacterRequest(BaseModel):
    character_id: int | None = None


@router.post('/{session_id}/character')
def set_character_for_session(session_id: str, req: SetCharacterRequest, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')

    try:
        data = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err

    identifier = _identifier_for_user(current_user)
    if not _user_is_member(data, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    owner_id = getattr(current_user, 'id', None)
    if not isinstance(owner_id, int):
        raise HTTPException(status_code=401, detail='Invalid authentication credentials')

    character_name = None
    if req.character_id is not None:
        character = db.get_character_for_owner(req.character_id, owner_id)
        if not character:
            raise HTTPException(status_code=404, detail='Character not found')
        character_name = character.name

    members = data.get('members', []) or []
    owner_normalized = _normalize_email(data.get('owner'))
    role = 'owner' if identifier == owner_normalized else 'member'

    found = False
    for member in members:
        if _normalize_email(member.get('email')) == identifier:
            member['character_id'] = req.character_id
            member['character_name'] = character_name
            member.setdefault('role', role)
            found = True
            break

    if not found:
        members.append({
            'email': identifier,
            'character_id': req.character_id,
            'character_name': character_name,
            'role': role,
        })

    data['members'] = members
    meta_path.write_text(json.dumps(data))
    return {'ok': True, 'session_id': session_id, 'character_id': req.character_id, 'character_name': character_name}


@router.delete('/{session_id}/file/{filename}')
def delete_file(session_id: str, filename: str, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    target = folder / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail='File not found')
    try:
        # membership check
        meta = folder / 'meta.json'
        if meta.exists():
            data = json.loads(meta.read_text())
            identifier = _identifier_for_user(current_user)
            if not _user_is_member(data, identifier):
                raise HTTPException(status_code=403, detail='Not a member of this session')
        target.unlink()
        return {'ok': True}
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to delete file') from err


@router.get('/{session_id}/file/{filename}')
def get_file(session_id: str, filename: str, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    target = folder / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail='File not found')
    # membership check
    meta = folder / 'meta.json'
    if meta.exists():
        data = json.loads(meta.read_text())
        identifier = _identifier_for_user(current_user)
        if not _user_is_member(data, identifier):
            raise HTTPException(status_code=403, detail='Not a member of this session')

    text = target.read_text()
    # try to return json if parseable
    try:
        return json.loads(text)
    except Exception:
        return {'content': text}


class SaveFileRequest(BaseModel):
    content: str


@router.post('/{session_id}/file/{filename}')
def save_file(session_id: str, filename: str, req: SaveFileRequest, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    # membership check
    meta = folder / 'meta.json'
    if meta.exists():
        data = json.loads(meta.read_text())
        identifier = _identifier_for_user(current_user)
        if not _user_is_member(data, identifier):
            raise HTTPException(status_code=403, detail='Not a member of this session')
    target = folder / filename
    target.write_text(req.content)
    return {'ok': True}


class InviteRequest(BaseModel):
    identifier: str | None = None
    email: str | None = None
    note: str | None = None

    @model_validator(mode='after')
    def _ensure_identifier(self):
        if not (self.identifier or self.email):
            raise ValueError('identifier required')
        if not self.identifier:
            self.identifier = self.email
        return self


class BootstrapRequest(BaseModel):
    style: str | None = None
    weather: str | None = None
    time_of_day: str | None = None


@router.post('/{session_id}/invite')
def invite_user(session_id: str, req: InviteRequest, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta = folder / 'meta.json'
    if not meta.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    data = json.loads(meta.read_text())
    # only owner may invite
    owner = data.get('owner')
    identifier = current_user.email or current_user.username
    if identifier != owner:
        raise HTTPException(status_code=403, detail='Only owner may invite users')

    raw_identifier = (req.identifier or '').strip()
    if not raw_identifier:
        raise HTTPException(status_code=400, detail='identifier required')

    invite_email = None
    if '@' in raw_identifier:
        invite_email = _normalize_email(raw_identifier)
    else:
        user = db.get_user_by_identifier(raw_identifier)
        if not user or not user.email:
            raise HTTPException(status_code=404, detail='User not found')
        invite_email = _normalize_email(user.email)

    invites = _normalize_invites(data.get('invites'))
    if any(inv.get('email') == invite_email for inv in invites):
        data['invites'] = invites
        meta.write_text(json.dumps(data))
        return {'ok': True, 'invites': invites}

    invites.append({
        'email': invite_email,
        'min_level': 1,
        'accepted': False,
        'character_id': None,
        'character_name': None,
        'note': (req.note or None),
    })
    data['invites'] = invites
    meta.write_text(json.dumps(data))
    return {'ok': True, 'invites': invites}


@router.get('/{session_id}/party')
def get_party(session_id: str, current_user=Depends(get_current_user)):
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err

    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    members = meta.get('members', []) or []
    invites = _normalize_invites(meta.get('invites'))

    out_members = []
    for member in members:
        email = _normalize_email(member.get('email'))
        user = db.get_user_by_identifier(email) if email else None
        username = user.username if user else None
        name = None
        if user:
            profile = db._profile_with_identity(user)
            name = profile.get('name')

        character_id = member.get('character_id')
        character = None
        if isinstance(character_id, int):
            ch = db.get_character_by_id(character_id)
            if ch:
                character = {
                    'id': ch.id,
                    'name': ch.name,
                    'level': ch.level,
                    'class_name': ch.class_name,
                    'sheet': ch.sheet,
                }

        out_members.append({
            'email': email,
            'username': username,
            'name': name or username or email,
            'role': member.get('role') or 'member',
            'character_id': character_id,
            'character_name': member.get('character_name'),
            'character': character,
        })

    out_invites = []
    for inv in invites:
        email = _normalize_email(inv.get('email'))
        user = db.get_user_by_identifier(email) if email else None
        username = user.username if user else None
        name = None
        if user:
            profile = db._profile_with_identity(user)
            name = profile.get('name')
        out_invites.append({
            **inv,
            'email': email,
            'username': username,
            'name': name or username or email,
        })

    npcs = []
    try:
        npcs_path = folder / 'npcs.json'
        if npcs_path.exists():
            raw = json.loads(npcs_path.read_text())
            if isinstance(raw, list):
                npcs = raw
    except Exception:
        npcs = []

    return {
        'session_id': session_id,
        'members': out_members,
        'invites': out_invites,
        'npcs': npcs,
    }


@router.post('/{session_id}/bootstrap')
async def bootstrap_session(session_id: str, payload: BootstrapRequest, current_user=Depends(get_current_user)):
    """Create/refresh an opening scene for a session.

    This is intentionally deterministic and offline-friendly: it uses the Narrative agent's
    deterministic generator and writes the current scene to `scene.json`.
    """
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err

    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    session_name = (meta.get('name') or session_id)
    owner = (meta.get('owner') or 'GM')
    style = (payload.style or 'balanced')
    weather = (payload.weather or 'clear')
    time_of_day = (payload.time_of_day or 'day')

    if is_player_run_mode(session_id):
        scene = {
            'id': 'opening',
            'title': f"{session_name} — Player-Run Session",
            'image': None,
            'text': "Player-run mode is enabled. Use chat, notes, and documents to run the session without AI narration.",
            'choices': [],
        }
        (folder / 'scene.json').write_text(json.dumps(scene))
        return {'ok': True, 'scene': scene}

    scene_seed = f"the first scene of the campaign '{session_name}', as the party arrives and the hook is revealed"
    narrative = narrative_agent.generate_narrative(narrative_agent.NarrativeRequest(
        scene=scene_seed,
        player='party',
        style=style,
        weather=weather,
        time_of_day=time_of_day,
    ))

    scene = {
        'id': 'opening',
        'title': f"{session_name} — Opening Scene",
        'image': None,
        'text': f"{narrative.narrative}\n\n{narrative.prompt}",
        'choices': [
            {'id': 'investigate', 'label': 'Investigate the most immediate clue'},
            {'id': 'talk', 'label': 'Talk to someone nearby'},
            {'id': 'press_on', 'label': 'Press on toward the obvious destination'},
            {'id': 'plan', 'label': 'Huddle and make a plan'},
        ],
    }

    (folder / 'scene.json').write_text(json.dumps(scene))

    # append a log entry for history
    story_path = folder / 'story.json'
    try:
        cur = json.loads(story_path.read_text()) if story_path.exists() else []
    except Exception:
        cur = []
    if not isinstance(cur, list):
        cur = [cur]
    cur.append({
        'type': 'narration',
        'ts': datetime.now(timezone.utc).isoformat(),
        'text': scene['text'],
    })
    story_path.write_text(json.dumps(cur))

    await broadcaster.broadcast_json(session_id, {
        'type': 'narrative.scene',
        'session_id': session_id,
        'scene': scene,
    })

    # Best-effort: emit cues + suggestions so the UI feels reactive immediately.
    try:
        await scene_agent.analyze_scene(scene_agent.SceneAnalysisRequest(
            scene=scene['text'],
            actions=[c.get('label', '') for c in (scene.get('choices') or []) if isinstance(c, dict)],
            session_id=session_id,
        ))
    except Exception:
        pass

    try:
        await suggestions_agent.get_suggestions(session_id=session_id, limit=4, current_user=current_user)
    except Exception:
        pass

    return {'ok': True, 'scene': scene, 'owner': owner}


# ---------------------------------------------------------------------------
# New Session Workflow (Steps 1–5)
# ---------------------------------------------------------------------------

class StartSessionRequest(BaseModel):
    style: str | None = None
    weather: str | None = None
    time_of_day: str | None = None


@router.post('/{session_id}/start')
async def start_session(session_id: str, payload: StartSessionRequest, current_user=Depends(get_current_user)):
    """Orchestrate the New Session Workflow (Steps 1–5).

    Step 1 – Storyboard Agent builds a story plot from players, campaign settings, and docs.
    Step 2 – Narrative Agent creates the opening scene from the storyboard output.
    Step 3 – Scene Analysis Agent checks for dice-roll opportunities.
    Step 4 – NPC Manager initialises profiles for NPCs mentioned in the plot.
    Step 5 – Scene is broadcast to all session members.
    """
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err

    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    session_name = meta.get('name') or session_id
    style = payload.style or 'balanced'
    weather = payload.weather or 'clear'
    time_of_day = payload.time_of_day or 'day'

    if is_player_run_mode(session_id):
        scene = {
            'id': 'opening',
            'title': f"{session_name} — Player-Run Session",
            'image': None,
            'text': "Player-run mode is enabled. Use chat, notes, and documents to run the session without AI narration.",
            'choices': [],
        }
        (folder / 'scene.json').write_text(json.dumps(scene))
        await broadcaster.broadcast_json(session_id, {'type': 'narrative.scene', 'session_id': session_id, 'scene': scene})
        return {'ok': True, 'scene': scene}

    # --- Step 1: Storyboard Agent ---
    players: list[str] = []
    try:
        pcs_file = folder / 'pcs.json'
        if pcs_file.exists():
            pcs = json.loads(pcs_file.read_text()) or []
            players = [str(p.get('name') or p.get('character_name') or '') for p in pcs if p]
            players = [n for n in players if n]
    except Exception:
        players = []
    for member in meta.get('members', []) or []:
        name = member.get('character_name') or member.get('email') or ''
        if name and name not in players:
            players.append(name)

    campaign_settings: dict = {}
    campaign_variables: dict = {}
    campaign_docs: list[str] = []
    campaign_id = meta.get('campaign_id')
    if campaign_id:
        try:
            campaign = db.get_campaign_by_id(str(campaign_id))
            if campaign and isinstance(campaign.metadata_json, dict):
                campaign_settings = campaign.metadata_json.get('settings') or {}
                if not isinstance(campaign_settings, dict):
                    campaign_settings = {}
                campaign_variables = campaign.metadata_json.get('variables') or {}
                if not isinstance(campaign_variables, dict):
                    campaign_variables = {}
        except Exception:
            pass
        try:
            docs = _doc_store.list_documents(session_id=session_id)
            for doc in docs or []:
                content = doc.get('content') or ''
                if content:
                    campaign_docs.append(content)
        except Exception:
            pass

    # Derive narrative style: campaign_variables.narrative_style →
    # campaign_settings.tone → request payload style → default 'balanced'
    derived_style = (
        str(campaign_variables.get('narrative_style') or '').strip()
        or str(campaign_settings.get('tone') or '').strip()
        or style
    )

    # --- Context Orchestrator: assemble ranked context packet ---
    from .context_collector import summarize_active_threads, summarize_recent_world_changes
    from .context_orchestrator import ContextPacket, orchestrate

    context_packet: ContextPacket | None = None
    world_ctx: dict = {}

    if campaign_id:
        try:
            context_packet = orchestrate(
                campaign_id=str(campaign_id),
                session_id=session_id,
                player_name=players[0] if players else "",
                player_actions=[],
                use_cache=False,
            )
            # Normalize NPC/thread/location format to what Scene Director and downstream code expect
            def _npc_to_old_format(n) -> dict:
                return {
                    "name": n.name, "goal": n.goal, "fear": n.fear,
                    "emotional_state": n.current_emotional_state,
                    "next_action": n.likely_next_action,
                    "faction": n.faction, "relevance_score": n.relevance_score,
                    "known_information": n.known_information,
                }
            def _thread_to_old_format(t) -> dict:
                return {
                    "name": t.title, "situation": t.current_state, "stakes": t.stakes,
                    "next_beat": t.next_escalation, "ticking_clock": t.ticking_clock,
                    "relevance_score": t.relevance_score,
                }
            def _loc_to_old_format(loc) -> dict:
                return {
                    "name": loc.name, "current_tension": loc.current_tensions[0] if loc.current_tensions else "",
                    "description": loc.description, "atmosphere": loc.atmosphere,
                }

            world_ctx = {
                "relevant_npcs": [_npc_to_old_format(n) for n in context_packet.active_npcs],
                "locations": [_loc_to_old_format(context_packet.location)] if context_packet.location.name else [],
                "active_threads": [_thread_to_old_format(t) for t in context_packet.story_threads],
                "open_hooks": [{"title": t.title, "description": t.ticking_clock} for t in context_packet.story_threads if t.ticking_clock],
                "recent_changes": [],
                "prompt_block": context_packet.for_narrative(),
            }
            # Inject story thread / hook summary into campaign_docs for Storyboard LLM
            memory_parts = []
            if context_packet.story_threads:
                memory_parts.append(summarize_active_threads(str(campaign_id)))
            if context_packet.clues.available_clues:
                hook_lines = [f"Hook: {c}" for c in context_packet.clues.available_clues[:4]]
                memory_parts.append("\n".join(hook_lines))
            if memory_parts:
                campaign_docs.append("[Campaign Memory]\n" + "\n\n".join(memory_parts))
        except Exception:
            # Fallback to legacy context_collector
            try:
                from .context_collector import collect_context
                world_ctx = collect_context(str(campaign_id), session_id=session_id)
                memory_parts = []
                if world_ctx.get("active_threads"):
                    memory_parts.append(summarize_active_threads(str(campaign_id)))
                if world_ctx.get("recent_changes"):
                    memory_parts.append(summarize_recent_world_changes(str(campaign_id)))
                if world_ctx.get("open_hooks"):
                    hook_lines = [f"Hook: {h['title']}" for h in world_ctx["open_hooks"][:5]]
                    memory_parts.append("\n".join(hook_lines))
                if memory_parts:
                    campaign_docs.append("[Campaign Memory]\n" + "\n\n".join(memory_parts))
            except Exception:
                pass

    # --- Steps 1 + Director: run in parallel (they don't depend on each other) ---
    # Storyboard generates raw plot material; Narrative Director sets story guidance.
    # Both are synchronous LLM calls — run them in a thread pool concurrently.
    import asyncio
    import concurrent.futures as _cf

    _loop = asyncio.get_event_loop()

    def _run_storyboard():
        return storyboard_agent.generate_plot(storyboard_agent.StoryboardPlotRequest(
            session_id=session_id,
            players=players,
            campaign_settings=campaign_settings,
            campaign_variables=campaign_variables,
            campaign_docs=campaign_docs,
        ))

    # Prepare story state for narrative director (pure data ops, no I/O)
    story_state = load_story_state(str(campaign_id)) if campaign_id else None
    mem_threads_raw: list[dict] = world_ctx.get('active_threads') or []
    if story_state is not None:
        try:
            story_state = sync_threads_from_entities(story_state, mem_threads_raw)
            if not story_state.campaign_dna.themes:
                story_state.campaign_dna = derive_campaign_dna(campaign_settings, campaign_variables)
        except Exception:
            pass

    def _run_director():
        if story_state is None:
            return None
        try:
            return narrative_direct_scene(
                state=story_state,
                player_name=player_name if players else "",
                player_actions=[],
            )
        except Exception:
            return None

    with _cf.ThreadPoolExecutor(max_workers=2) as _pool:
        fut_plot = _loop.run_in_executor(_pool, _run_storyboard)
        fut_director = _loop.run_in_executor(_pool, _run_director)
        plot_result, narrative_director_output = await asyncio.gather(fut_plot, fut_director)

    narrative_director_output: DirectorOutput | None = narrative_director_output  # type annotation

    # --- Step 1b: Merge campaign memory into Scene Director candidates ---
    mem_npc_details: list[dict] = world_ctx.get('relevant_npcs') or []
    mem_loc_details: list[dict] = world_ctx.get('locations') or []
    mem_threads: list[dict] = mem_threads_raw
    mem_hooks: list[dict] = world_ctx.get('open_hooks') or []
    mem_changes: list[dict] = world_ctx.get('recent_changes') or []

    # Flatten to strings for candidate lists, prefer memory-sourced (more structured) over doc-sourced
    mem_npc_names = [n['name'] for n in mem_npc_details if n.get('name')]
    mem_loc_names = [loc['name'] for loc in mem_loc_details if loc.get('name')]
    mem_thread_texts = [
        t.get('situation') or t.get('name') or ''
        for t in mem_threads if t.get('situation') or t.get('name')
    ]
    mem_hook_texts = [h.get('title', '') for h in mem_hooks if h.get('title')]
    mem_event_texts = [c.get('summary', '') for c in mem_changes if c.get('summary')]

    candidate_npcs = (mem_npc_names or plot_result.candidate_npcs)
    candidate_locations = (mem_loc_names or plot_result.candidate_locations)
    candidate_threads = (mem_thread_texts or plot_result.candidate_story_threads)
    open_hooks = (mem_hook_texts or plot_result.open_hooks)
    recent_events = (mem_event_texts or plot_result.recent_events)

    # All known entity names for quality validator
    all_campaign_entities = list({*candidate_npcs, *candidate_locations, *candidate_threads})

    # --- Step 2: Scene Director Agent — converts raw material into a concrete scene plan ---
    director_output: SceneDirectorOutput = scene_director_agent.direct_scene(SceneDirectorRequest(
        campaign_settings=campaign_settings,
        campaign_variables=campaign_variables,
        players=players,
        plot_seed=plot_result.plot,
        candidate_npcs=candidate_npcs[:6],
        candidate_npc_details=mem_npc_details[:6],
        candidate_locations=candidate_locations[:4],
        candidate_location_details=mem_loc_details[:4],
        candidate_factions=plot_result.candidate_factions,
        candidate_story_threads=candidate_threads[:4],
        candidate_thread_details=mem_threads[:4],
        open_hooks=open_hooks[:4],
        recent_events=recent_events[:4],
        world_context_block=world_ctx.get('prompt_block') or '',
        director_guidance=narrative_director_output.model_dump() if narrative_director_output else None,
    ))

    player_name = players[0] if players else 'the party'
    loc_name = director_output.location.name or ''
    npc_name = director_output.primary_npc.name or ''

    # --- Step 3: Narrative Agent — first attempt ---
    narrative = narrative_agent.generate_narrative(narrative_agent.NarrativeRequest(
        scene=plot_result.plot,
        player=player_name,
        style=derived_style,
        weather=weather,
        time_of_day=time_of_day,
        scene_director_data=director_output.model_dump(),
    ))

    # --- Step 3b: Quality validation + retry/fallback ---
    quality_score, quality_issues = validate_scene_quality(
        narrative_text=f"{narrative.narrative}\n\n{narrative.prompt}",
        location_name=loc_name,
        npc_name=npc_name,
        player_name=player_name,
        conflict=director_output.central_conflict,
        campaign_entities=all_campaign_entities,
    )
    retry_used = False
    fallback_used = False

    if quality_score < MINIMUM_SCORE:
        retry_used = True
        feedback = build_retry_feedback(quality_issues, quality_score, loc_name, npc_name, player_name)
        narrative = narrative_agent.generate_narrative(narrative_agent.NarrativeRequest(
            scene=plot_result.plot,
            player=player_name,
            style=derived_style,
            weather=weather,
            time_of_day=time_of_day,
            scene_director_data=director_output.model_dump(),
            validator_feedback=feedback,
        ))
        quality_score, quality_issues = validate_scene_quality(
            narrative_text=f"{narrative.narrative}\n\n{narrative.prompt}",
            location_name=loc_name,
            npc_name=npc_name,
            player_name=player_name,
            conflict=director_output.central_conflict,
            campaign_entities=all_campaign_entities,
        )

    if quality_score < MINIMUM_SCORE:
        fallback_used = True
        sensory = (director_output.location.sensory_details[:1] or [''])[0]
        fallback_text = build_fallback_scene(
            location_name=loc_name or 'the settlement',
            npc_name=npc_name,
            player_name=player_name,
            emotional_state=director_output.primary_npc.current_emotional_state or 'grim-faced',
            inciting_incident=director_output.inciting_incident or director_output.central_conflict,
            central_conflict=director_output.central_conflict,
            immediate_stakes=director_output.immediate_stakes,
            sensory_detail=sensory,
        )
        narrative = narrative_agent.NarrativeResponse(
            narrative=fallback_text,
            prompt=f"What does {player_name} do?",
            tone=derived_style,
        )

    # --- Step 4: Build scene object ---
    # Choices from Scene Director possible_actions if available
    if director_output.possible_actions:
        choices = [
            {'id': f'action_{i}', 'label': a}
            for i, a in enumerate(director_output.possible_actions[:4])
        ]
    else:
        choices = [
            {'id': 'investigate', 'label': 'Investigate the most immediate clue'},
            {'id': 'talk', 'label': 'Talk to someone nearby'},
            {'id': 'press_on', 'label': 'Press on toward the obvious destination'},
            {'id': 'plan', 'label': 'Huddle and make a plan'},
        ]

    scene = {
        'id': 'opening',
        'title': director_output.scene_title or f"{session_name} — Opening Scene",
        'image': None,
        'text': f"{narrative.narrative}\n\n{narrative.prompt}",
        'choices': choices,
        'hooks': plot_result.hooks,
    }
    (folder / 'scene.json').write_text(json.dumps(scene))

    # --- Step 4b: Visual Director + Image generation ---
    loc_type = director_output.location.type if director_output.location else ""
    vd_elements = director_output.visual_prompt_elements or []
    try:
        visual_state, image_prompt, _ = run_visual_pipeline(
            session_id=session_id,
            scene_text=scene['text'],
            location_name=loc_name,
            location_type=loc_type,
            weather=weather,
            time_of_day=time_of_day,
            season="",
            region="",
            visual_prompt_elements=vd_elements,
            previous_visual_state=None,
        )
        save_visual_state(session_id, visual_state)
        scene['visual_state'] = visual_state.model_dump()
    except Exception:
        visual_state = None
        image_prompt = build_image_prompt(director_output, style=derived_style, weather=weather, time_of_day=time_of_day)

    try:
        img = image_agent.generate_image(image_agent.ImageRequest(
            prompt=image_prompt,
            style='realistic',
            session_id=session_id,
        ))
        scene['image'] = img.image_url
        (folder / 'scene.json').write_text(json.dumps(scene))
    except Exception:
        pass

    story_path = folder / 'story.json'
    try:
        cur = json.loads(story_path.read_text()) if story_path.exists() else []
    except Exception:
        cur = []
    if not isinstance(cur, list):
        cur = [cur]
    cur.append({'type': 'narration', 'ts': datetime.now(timezone.utc).isoformat(), 'text': scene['text']})
    story_path.write_text(json.dumps(cur))

    # --- Step 5: Scene Analysis ---
    dice_rolls: list[dict] = []
    try:
        cues = await scene_agent.analyze_scene(scene_agent.SceneAnalysisRequest(
            scene=scene['text'],
            actions=[c.get('label', '') for c in scene.get('choices', []) if isinstance(c, dict)],
            session_id=session_id,
        ))
        dice_rolls = [r.model_dump() for r in cues.dice_rolls]
    except Exception:
        pass

    # --- Step 6: NPC Manager — enrich profiles from Scene Director data ---
    npc_profiles: list[dict] = []

    def _make_npc_from_director(blueprint: dict, scene_id: str, sid: str) -> dict:
        """Build an enriched NPC profile dict from a Scene Director NPC blueprint."""
        existing_detail = next(
            (n for n in mem_npc_details if n.get('name') == blueprint.get('name')), {}
        )
        return {
            'name': blueprint.get('name', ''),
            'role': blueprint.get('role', ''),
            'emotional_state': blueprint.get('current_emotional_state', ''),
            'motivations': [blueprint.get('what_they_want', '')] if blueprint.get('what_they_want') else [],
            'secrets': [],
            'first_seen_scene_id': scene_id,
            'associated_location': loc_name,
            'associated_thread': candidate_threads[0] if candidate_threads else '',
            'current_goal': existing_detail.get('goal') or blueprint.get('what_they_want', ''),
            'known_information': [blueprint.get('what_they_know', '')] if blueprint.get('what_they_know') else [],
            'relationship_to_player': director_output.why_player_is_involved[:120] if director_output.why_player_is_involved else '',
            'source': director_output.source,
        }

    # Primary NPC from Scene Director
    if npc_name:
        try:
            blueprint = director_output.primary_npc.model_dump()
            enriched = _make_npc_from_director(blueprint, 'opening', session_id)
            result = await npc_agent.manage_npc(npc_agent.NPCManageRequest(
                name=npc_name,
                motivations=enriched['motivations'],
                personality=enriched.get('emotional_state', ''),
                appearance='',
                backstory='',
                session_id=session_id,
                traits=enriched,
            ))
            npc_profiles.append(result.npc_profile)
        except Exception:
            pass

    # Secondary entities (name-only) from Scene Director
    for secondary_name in director_output.secondary_entities[:3]:
        if secondary_name and secondary_name != npc_name:
            try:
                result = await npc_agent.manage_npc(npc_agent.NPCManageRequest(
                    name=secondary_name,
                    session_id=session_id,
                    traits={'source': 'scene_director', 'first_seen_scene_id': 'opening'},
                ))
                npc_profiles.append(result.npc_profile)
            except Exception:
                pass

    # Any additional NPCs mentioned in storyboard but not yet profiled
    existing_names = {p.get('name') for p in npc_profiles}
    for extra_name in plot_result.npcs_mentioned:
        if extra_name and extra_name not in existing_names:
            try:
                result = await npc_agent.manage_npc(npc_agent.NPCManageRequest(
                    name=extra_name,
                    session_id=session_id,
                    traits={'source': 'storyboard', 'first_seen_scene_id': 'opening'},
                ))
                npc_profiles.append(result.npc_profile)
                existing_names.add(extra_name)
            except Exception:
                pass

    # --- Step 7: Broadcast scene to players ---
    await broadcaster.broadcast_json(session_id, {
        'type': 'narrative.scene',
        'session_id': session_id,
        'scene': scene,
    })

    ready_path = folder / 'ready.json'
    ready_path.write_text(json.dumps({}))

    # --- Story Validator + State Update ---
    story_validator_result = None
    story_debug: dict | None = None
    if story_state is not None and narrative_director_output is not None:
        try:
            story_validator_result = validate_story_structure(
                scene_text=scene.get('text', ''),
                director=narrative_director_output,
                state=story_state,
                scene_type=narrative_director_output.recommended_scene_type,
                npc_names=candidate_npcs[:10],
                location_names=candidate_locations[:6],
            )
            story_state = update_state_after_scene(
                state=story_state,
                scene_type=narrative_director_output.recommended_scene_type,
                scene_purpose=narrative_director_output.scene_purpose,
                scene_id=scene.get('id', session_id),
                location=loc_name,
                npcs_featured=[n for n in candidate_npcs[:5] if n.lower() in scene.get('text', '').lower()],
                threads_advanced=narrative_director_output.threads_to_advance,
                threads_resolved=narrative_director_output.threads_to_resolve,
                emotional_target=narrative_director_output.emotional_target,
                director_tension_target=narrative_director_output.target_tension,
                story_score=story_validator_result.score,
                director_recommendation_followed=True,
            )
            save_story_state(story_state)
            story_debug = {
                'director': narrative_director_output.model_dump(),
                'story_state': story_dashboard_payload(story_state),
                'story_validator': story_validator_result.to_dict(),
            }
        except Exception:
            pass

    scene_debug = {
        'storyboard_plot': plot_result.plot,
        'storyboard_hooks': plot_result.hooks,
        'scene_director_source': director_output.source,
        'scene_director': {
            'location': loc_name,
            'primary_npc': npc_name,
            'central_conflict': director_output.central_conflict,
            'inciting_incident': director_output.inciting_incident,
            'immediate_stakes': director_output.immediate_stakes,
        },
        'quality_score': quality_score,
        'quality_issues': quality_issues,
        'retry_used': retry_used,
        'fallback_used': fallback_used,
        'image_prompt': image_prompt,
    }

    context_debug = context_packet.debug_payload() if context_packet else None

    return {
        'ok': True,
        'scene': scene,
        'plot': plot_result.plot,
        'hooks': plot_result.hooks,
        'dice_rolls': dice_rolls,
        'npc_profiles': npc_profiles,
        'scene_debug': scene_debug,
        'context_debug': context_debug,
        'story_debug': story_debug,
    }


# ---------------------------------------------------------------------------
# Returning Session Workflow – Step 1: Player "Done" Signal
# ---------------------------------------------------------------------------

class PlayerReadyRequest(BaseModel):
    done: bool = True


@router.post('/{session_id}/player-ready')
async def player_ready(session_id: str, payload: PlayerReadyRequest, current_user=Depends(get_current_user)):
    """Mark the current player as done contributing to chat (Returning Session Workflow, Step 1).

    When all session members have signalled ready, the response includes
    ``all_ready: true`` so the frontend knows it can trigger ``/advance-scene``.
    """
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err

    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    # Load/update ready state
    ready_path = folder / 'ready.json'
    try:
        ready: dict = json.loads(ready_path.read_text()) if ready_path.exists() else {}
    except Exception:
        ready = {}

    ready[identifier] = payload.done
    ready_path.write_text(json.dumps(ready))

    # Determine all_ready: every member who has an entry must be done.
    members = meta.get('members', []) or []
    member_ids = [_normalize_email(m.get('email')) for m in members if m.get('email')]
    if not member_ids:
        member_ids = [_normalize_email(meta.get('owner') or '')]
    all_ready = bool(member_ids) and all(ready.get(mid) for mid in member_ids)

    await broadcaster.broadcast_json(session_id, {
        'type': 'player.ready',
        'session_id': session_id,
        'player': identifier,
        'done': payload.done,
        'all_ready': all_ready,
    })

    return {'ok': True, 'player': identifier, 'done': payload.done, 'all_ready': all_ready}


# ---------------------------------------------------------------------------
# Returning Session Workflow – Steps 2–5: Advance Scene
# ---------------------------------------------------------------------------

class AdvanceSceneRequest(BaseModel):
    style: str | None = None
    weather: str | None = None
    time_of_day: str | None = None


@router.post('/{session_id}/advance-scene')
async def advance_scene(session_id: str, payload: AdvanceSceneRequest, current_user=Depends(get_current_user)):
    """Orchestrate the Returning Session Workflow (Steps 2–5).

    Step 2 – Narrative Agent analyses recent chat; Scene Analysis checks for dice rolls.
    Step 3 – Notes Agent logs session notes; Storyboard is updated with player choices.
    Step 4 – Narrative Agent creates the new scene; Image Generation kicks off.
    Step 5 – New scene is broadcast to all session members.
    """
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err

    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    style = payload.style or 'balanced'
    weather = payload.weather or 'clear'
    time_of_day = payload.time_of_day or 'day'
    campaign_id = meta.get('campaign_id')

    if is_player_run_mode(session_id):
        raise HTTPException(status_code=400, detail='advance-scene is not available in player-run mode')

    # --- Step 2: Collect recent player chat and analyse for dice rolls ---
    recent_messages = db.list_chat_messages(session_id=session_id, limit=20)
    player_actions = [
        m.message for m in recent_messages
        if m.role not in ('gm', 'narrator', 'system') and m.message
    ]

    # Load current scene for context
    scene_text = ''
    try:
        scene_path = folder / 'scene.json'
        if scene_path.exists():
            scene_text = json.loads(scene_path.read_text()).get('text', '')
    except Exception:
        pass

    dice_rolls: list[dict] = []
    try:
        cues = await scene_agent.analyze_scene(scene_agent.SceneAnalysisRequest(
            scene=scene_text,
            actions=player_actions,
            session_id=session_id,
        ))
        dice_rolls = [r.model_dump() for r in cues.dice_rolls]
    except Exception:
        pass

    # --- Step 3: Notes Agent logs the interaction; Storyboard is updated ---
    notes_to_log = [f"[player] {a}" for a in player_actions[:10]]
    try:
        notes_agent._ensure_notes_member(session_id, current_user)
        notes_agent._append_to_session_notes(
            session_id,
            notes_to_log,
            notes_agent._generate_recap(notes_to_log),
        )
    except Exception:
        pass

    # Update storyboard with player choices as new story beats
    storyboard_choices = player_actions[:5]
    try:
        storyboard_agent.update_storyboard(storyboard_agent.StoryboardRequest(
            scene=scene_text,
            choices=storyboard_choices,
            unresolved=[],
            completed=[],
        ))
    except Exception:
        pass

    # --- Step 4: Context Orchestrator + Narrative Agent ---
    adv_context_packet = None
    world_context_block = ""
    adv_player_name = "the party"

    # Resolve player name from session PC list for richer context
    try:
        pcs_path = folder / 'pcs.json'
        if pcs_path.exists():
            pcs_raw = json.loads(pcs_path.read_text()) or []
            if pcs_raw:
                adv_player_name = str(pcs_raw[0].get('name') or pcs_raw[0].get('character_name') or 'the party')
    except Exception:
        pass

    if campaign_id:
        try:
            from .context_orchestrator import orchestrate
            adv_context_packet = orchestrate(
                campaign_id=str(campaign_id),
                session_id=session_id,
                player_name=adv_player_name,
                player_actions=player_actions,
                use_cache=False,
            )
            world_context_block = adv_context_packet.for_narrative()
        except Exception:
            try:
                from .context_collector import collect_context
                ctx = collect_context(
                    campaign_id=str(campaign_id),
                    session_id=session_id,
                    recent_chat=player_actions,
                )
                world_context_block = ctx.get("prompt_block") or ""
            except Exception:
                pass

    # --- Narrative Director: scene-level story guidance ---
    adv_story_state = load_story_state(str(campaign_id)) if campaign_id else None
    adv_director_output: DirectorOutput | None = None
    if adv_story_state is not None:
        try:
            adv_director_output = narrative_direct_scene(
                state=adv_story_state,
                player_name=adv_player_name,
                player_actions=player_actions,
            )
        except Exception:
            adv_director_output = None

    scene_summary = ' '.join(player_actions[:3]) if player_actions else 'The party deliberates their next move.'
    if world_context_block:
        scene_summary = f"{scene_summary}\n\n{world_context_block}"

    # Inject director pacing guidance into narrative prompt
    if adv_director_output:
        director_lines = [f"[STORY DIRECTOR] Scene purpose: {adv_director_output.scene_purpose}",
                          f"Scene type: {adv_director_output.recommended_scene_type}"]
        if adv_director_output.threads_to_advance:
            director_lines.append(f"Advance threads: {', '.join(adv_director_output.threads_to_advance)}")
        if adv_director_output.recommended_consequence:
            director_lines.append(f"Consequence to surface: {adv_director_output.recommended_consequence}")
        if adv_director_output.spotlight_target:
            director_lines.append(f"Spotlight: {adv_director_output.spotlight_target}")
        if adv_director_output.next_story_beat:
            director_lines.append(f"Target beat: {adv_director_output.next_story_beat}")
        scene_summary = "\n".join(director_lines) + "\n\n" + scene_summary

    narrative = narrative_agent.generate_narrative(narrative_agent.NarrativeRequest(
        scene=scene_summary,
        player=adv_player_name,
        style=style,
        weather=weather,
        time_of_day=time_of_day,
        player_actions=player_actions,
    ))

    now = datetime.now(timezone.utc)
    scene_index = f"scene-{uuid.uuid4().hex[:8]}"
    new_scene = {
        'id': scene_index,
        'title': f"Scene — {now.strftime('%Y-%m-%d %H:%M')} UTC",
        'image': None,
        'text': f"{narrative.narrative}\n\n{narrative.prompt}",
        'choices': [
            {'id': 'investigate', 'label': 'Investigate the most immediate clue'},
            {'id': 'talk', 'label': 'Talk to someone nearby'},
            {'id': 'press_on', 'label': 'Press on toward the obvious destination'},
            {'id': 'plan', 'label': 'Huddle and make a plan'},
        ],
    }

    # --- Visual Director: determine atmosphere + image refresh decision ---
    image_url = None
    prev_vs = load_visual_state(session_id)

    # Extract location hint from previous scene.json if available
    adv_loc_name = ""
    adv_loc_type = ""
    try:
        prev_scene_raw = folder / 'scene.json'
        if prev_scene_raw.exists():
            prev_scene_data = json.loads(prev_scene_raw.read_text())
            prev_vs_data = prev_scene_data.get('visual_state') or {}
            adv_loc_name = prev_vs_data.get('location_name', '')
            adv_loc_type = prev_vs_data.get('location_type', '')
    except Exception:
        pass

    try:
        adv_vs, adv_img_prompt, do_refresh = run_visual_pipeline(
            session_id=session_id,
            scene_text=new_scene['text'],
            location_name=adv_loc_name,
            location_type=adv_loc_type,
            weather=weather,
            time_of_day=time_of_day,
            previous_visual_state=prev_vs,
        )
        save_visual_state(session_id, adv_vs)
        new_scene['visual_state'] = adv_vs.model_dump()
    except Exception:
        do_refresh = True
        adv_img_prompt = narrative.narrative[:200]

    if do_refresh:
        try:
            img = image_agent.generate_image(image_agent.ImageRequest(
                prompt=adv_img_prompt,
                style='realistic',
            ))
            image_url = img.image_url
            new_scene['image'] = image_url
        except Exception:
            pass
    elif prev_vs:
        # Reuse prior image — copy from previous scene.json if available
        try:
            prev_scene_raw2 = folder / 'scene.json'
            if prev_scene_raw2.exists():
                prev_img = json.loads(prev_scene_raw2.read_text()).get('image')
                if prev_img:
                    image_url = prev_img
                    new_scene['image'] = prev_img
        except Exception:
            pass

    (folder / 'scene.json').write_text(json.dumps(new_scene))

    story_path = folder / 'story.json'
    try:
        cur = json.loads(story_path.read_text()) if story_path.exists() else []
    except Exception:
        cur = []
    if not isinstance(cur, list):
        cur = [cur]
    cur.append({'type': 'narration', 'ts': now.isoformat(), 'text': new_scene['text']})
    story_path.write_text(json.dumps(cur))

    # Reset player-ready state for the next round
    ready_path = folder / 'ready.json'
    ready_path.write_text(json.dumps({}))

    # --- Step 5: Broadcast the new scene ---
    await broadcaster.broadcast_json(session_id, {
        'type': 'narrative.scene',
        'session_id': session_id,
        'scene': new_scene,
    })

    adv_context_debug = adv_context_packet.debug_payload() if adv_context_packet else None

    # --- Story Validator + State Update (advance scene) ---
    adv_story_debug: dict | None = None
    if adv_story_state is not None and adv_director_output is not None:
        try:
            adv_story_result = validate_story_structure(
                scene_text=new_scene.get('text', ''),
                director=adv_director_output,
                state=adv_story_state,
                scene_type=adv_director_output.recommended_scene_type,
            )
            adv_story_state = update_state_after_scene(
                state=adv_story_state,
                scene_type=adv_director_output.recommended_scene_type,
                scene_purpose=adv_director_output.scene_purpose,
                scene_id=new_scene.get('id', session_id),
                location=new_scene.get('title', ''),
                npcs_featured=[],
                threads_advanced=adv_director_output.threads_to_advance,
                threads_resolved=adv_director_output.threads_to_resolve,
                emotional_target=adv_director_output.emotional_target,
                director_tension_target=adv_director_output.target_tension,
                story_score=adv_story_result.score,
                director_recommendation_followed=True,
            )
            save_story_state(adv_story_state)
            adv_story_debug = {
                'director': adv_director_output.model_dump(),
                'story_state': story_dashboard_payload(adv_story_state),
                'story_validator': adv_story_result.to_dict(),
            }
        except Exception:
            pass

    return {
        'ok': True,
        'scene': new_scene,
        'dice_rolls': dice_rolls,
        'image_url': image_url,
        'context_debug': adv_context_debug,
        'story_debug': adv_story_debug,
    }


# ---------------------------------------------------------------------------
# Entity associations + in-chat hyperlink lookup
# ---------------------------------------------------------------------------

def _associations_path(session_id: str) -> Path:
    return BASE / session_id / 'associations.json'


def _load_associations(session_id: str) -> list[dict]:
    path = _associations_path(session_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_associations(session_id: str, associations: list[dict]) -> None:
    path = _associations_path(session_id)
    path.write_text(json.dumps(associations, indent=2))


@router.post('/{session_id}/entities/associate', status_code=201)
def add_association(session_id: str, payload: EntityAssociation, current_user=Depends(get_current_user)):
    """Record a link between two entities (NPC ↔ Location, NPC ↔ Quest, etc.).

    Associations are stored in ``associations.json`` inside the session folder.
    They power in-chat hyperlinks: when a player clicks an entity name in the
    chat transcript the UI resolves it to the player-visible card via
    ``GET /sessions/{id}/entity/{name}``.

    Only session members may call this endpoint.
    """
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err
    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    existing = _load_associations(session_id)
    # Upsert: replace any existing link that shares the same ordered (entity_a, entity_b) pair.
    # Associations are directional by default — "NPC guards Location" and "Location is guarded
    # by NPC" are treated as distinct entries.  If you want to replace in both directions,
    # submit a second association with the entities swapped.
    new_entry = payload.model_dump()
    updated = [
        e for e in existing
        if not (
            e.get('entity_a') == payload.entity_a and e.get('entity_b') == payload.entity_b
        )
    ]
    updated.append(new_entry)
    _save_associations(session_id, updated)
    return {'ok': True, 'association': new_entry}


@router.get('/{session_id}/entities/associations')
def list_associations(session_id: str, current_user=Depends(get_current_user)):
    """Return all entity associations for the session.  All session members may read."""
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err
    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')
    return {'session_id': session_id, 'associations': _load_associations(session_id)}


@router.get('/{session_id}/entity/{entity_name}', response_model=PlayerEntityCard)
def get_entity_card(session_id: str, entity_name: str, current_user=Depends(get_current_user)):
    """Return the player-visible card for a named entity (NPC, location, or quest).

    This endpoint powers in-chat hyperlinks.  When a player clicks an entity
    name in the chat transcript the frontend calls this endpoint and displays
    the returned card in a pop-up.

    The card contains **only** information the players have gathered:
    - For NPCs: appearance, observable attitude, dialogue/relationships —
      never stats, motivations, or secrets.
    - For locations: shops, contacts, explored layout — never hidden areas or traps.
    - For quests: current objective, completed stages — never hidden complications.

    Returns ``404`` if no player-visible information exists for the name yet.
    """
    folder = BASE / session_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    meta_path = folder / 'meta.json'
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail='Meta not found')
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as err:
        raise HTTPException(status_code=500, detail='Failed to read meta') from err
    identifier = _identifier_for_user(current_user)
    if not _user_is_member(meta, identifier):
        raise HTTPException(status_code=403, detail='Not a member of this session')

    name_lower = entity_name.strip().lower()

    # Load associations once; reused by all branches below.
    assoc = _load_associations(session_id)

    def _known_for(name_lc: str) -> list[str]:
        return [
            f"{a['entity_b']} ({a.get('relationship', '')})"
            for a in assoc
            if (a.get('entity_a') or '').strip().lower() == name_lc
        ] + [
            f"{a['entity_a']} ({a.get('relationship', '')})"
            for a in assoc
            if (a.get('entity_b') or '').strip().lower() == name_lc
        ]

    # --- 1. Try the session npcs.json (player-visible NPC profiles) ---
    npcs_path = folder / 'npcs.json'
    if npcs_path.exists():
        try:
            npcs = json.loads(npcs_path.read_text()) or []
            for npc in npcs:
                if (npc.get('name') or '').strip().lower() == name_lower:
                    # Canonical appearance lives at the top level (written by the updated
                    # manage_npc endpoint).  Fall back to traits['appearance'] for profiles
                    # written by older code.
                    appearance = npc.get('appearance') or ''
                    if not appearance:
                        traits = npc.get('traits') or {}
                        appearance = traits.get('appearance', '') if isinstance(traits, dict) else ''
                    return PlayerEntityCard(
                        name=npc.get('name', entity_name),
                        entity_type='npc',
                        summary=appearance or f"You have encountered {npc.get('name', entity_name)}.",
                        appearance=appearance,
                        relationship_notes=npc.get('personality', '') or ', '.join(npc.get('quirks') or []),
                        known_associations=_known_for(name_lower),
                    )
        except Exception:
            pass

    # --- 2. Try player-visible documents (player_npc, player_location, player_quest_log) ---
    docs = _doc_store.list_documents(session_id)
    player_cats = {'player_npc', 'player_location', 'player_quest_log'}
    for doc_meta in docs:
        if doc_meta.visibility == 'hidden':
            continue
        if doc_meta.category not in player_cats:
            continue
        if (doc_meta.name or '').strip().lower() != name_lower:
            continue
        record = _doc_store.read_document(session_id, doc_meta.id)
        if not record:
            continue
        _, content = record
        entity_type_map = {
            'player_npc': 'npc',
            'player_location': 'location',
            'player_quest_log': 'quest',
        }
        return PlayerEntityCard(
            name=doc_meta.name,
            entity_type=entity_type_map.get(doc_meta.category, 'npc'),  # type: ignore[arg-type]
            summary=content[:500] if content else '',
            known_associations=_known_for(name_lower),
        )

    raise HTTPException(status_code=404, detail=f"No player-visible information found for '{entity_name}'")
