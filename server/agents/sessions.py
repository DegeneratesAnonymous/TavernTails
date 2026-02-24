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
from . import storyboard as storyboard_agent
from . import suggestions as suggestions_agent
from .entity_schemas import EntityAssociation, PlayerEntityCard

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

    plot_result = storyboard_agent.generate_plot(storyboard_agent.StoryboardPlotRequest(
        session_id=session_id,
        players=players,
        campaign_settings=campaign_settings,
        campaign_variables=campaign_variables,
        campaign_docs=campaign_docs,
    ))

    # --- Step 2: Narrative Agent creates the opening scene ---
    narrative = narrative_agent.generate_narrative(narrative_agent.NarrativeRequest(
        scene=plot_result.plot,
        player='party',
        style=derived_style,
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
        'hooks': plot_result.hooks,
    }
    (folder / 'scene.json').write_text(json.dumps(scene))

    story_path = folder / 'story.json'
    try:
        cur = json.loads(story_path.read_text()) if story_path.exists() else []
    except Exception:
        cur = []
    if not isinstance(cur, list):
        cur = [cur]
    cur.append({'type': 'narration', 'ts': datetime.now(timezone.utc).isoformat(), 'text': scene['text']})
    story_path.write_text(json.dumps(cur))

    # --- Step 3: Scene Analysis ---
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

    # --- Step 4: NPC Manager initialises profiles for mentioned NPCs ---
    npc_profiles: list[dict] = []
    for npc_name in plot_result.npcs_mentioned:
        try:
            result = await npc_agent.manage_npc(npc_agent.NPCManageRequest(
                name=npc_name,
                session_id=session_id,
            ))
            npc_profiles.append(result.npc_profile)
        except Exception:
            pass

    # --- Step 5: Broadcast scene to players ---
    await broadcaster.broadcast_json(session_id, {
        'type': 'narrative.scene',
        'session_id': session_id,
        'scene': scene,
    })

    # Reset player-ready state for the new session
    ready_path = folder / 'ready.json'
    ready_path.write_text(json.dumps({}))

    return {
        'ok': True,
        'scene': scene,
        'plot': plot_result.plot,
        'hooks': plot_result.hooks,
        'dice_rolls': dice_rolls,
        'npc_profiles': npc_profiles,
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

    # --- Step 4: Narrative Agent creates the new scene ---
    scene_summary = ' '.join(player_actions[:3]) if player_actions else 'The party deliberates their next move.'
    narrative = narrative_agent.generate_narrative(narrative_agent.NarrativeRequest(
        scene=scene_summary,
        player='party',
        style=style,
        weather=weather,
        time_of_day=time_of_day,
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

    # Kick off image generation for the new scene (best-effort)
    image_url = None
    try:
        img = image_agent.generate_image(image_agent.ImageRequest(
            prompt=narrative.narrative[:200],
            style='realistic',
        ))
        image_url = img.image_url
        new_scene['image'] = image_url
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

    return {
        'ok': True,
        'scene': new_scene,
        'dice_rolls': dice_rolls,
        'image_url': image_url,
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

    # --- 1. Try the session npcs.json (player-visible NPC profiles) ---
    npcs_path = folder / 'npcs.json'
    if npcs_path.exists():
        try:
            npcs = json.loads(npcs_path.read_text()) or []
            for npc in npcs:
                if (npc.get('name') or '').strip().lower() == name_lower:
                    # Build a PlayerEntityCard from the NPC profile.
                    # Only expose appearance + traits that are player-safe.
                    traits = npc.get('traits') or {}
                    appearance = traits.get('appearance', '') if isinstance(traits, dict) else ''
                    assoc = _load_associations(session_id)
                    known = [
                        f"{a['entity_b']} ({a.get('relationship', '')})"
                        for a in assoc
                        if (a.get('entity_a') or '').strip().lower() == name_lower
                    ] + [
                        f"{a['entity_a']} ({a.get('relationship', '')})"
                        for a in assoc
                        if (a.get('entity_b') or '').strip().lower() == name_lower
                    ]
                    return PlayerEntityCard(
                        name=npc.get('name', entity_name),
                        entity_type='npc',
                        summary=appearance or f"You have encountered {npc.get('name', entity_name)}.",
                        appearance=appearance,
                        relationship_notes=', '.join(npc.get('quirks') or []),
                        known_associations=known,
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
        assoc = _load_associations(session_id)
        known = [
            f"{a['entity_b']} ({a.get('relationship', '')})"
            for a in assoc
            if (a.get('entity_a') or '').strip().lower() == name_lower
        ] + [
            f"{a['entity_a']} ({a.get('relationship', '')})"
            for a in assoc
            if (a.get('entity_b') or '').strip().lower() == name_lower
        ]
        return PlayerEntityCard(
            name=doc_meta.name,
            entity_type=entity_type_map.get(doc_meta.category, 'npc'),  # type: ignore[arg-type]
            summary=content[:500] if content else '',
            known_associations=known,
        )

    raise HTTPException(status_code=404, detail=f"No player-visible information found for '{entity_name}'")
