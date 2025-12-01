from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from pathlib import Path
import uuid
import json
import os
from datetime import datetime

from ..auth import get_current_user
from .. import db

router = APIRouter(prefix="/sessions")

BASE = Path(__file__).resolve().parents[1] / 'sessions'
BASE.mkdir(exist_ok=True)


def _identifier_for_user(user) -> str:
    value = (getattr(user, 'email', None) or getattr(user, 'username', '') or '').strip()
    return value.lower()


def _normalize_email(value: str) -> str:
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
                'accepted_at': entry.get('accepted_at'),
            })
    return normalized


def create_session_folder(name: str, owner_email: str, invites=None):
    """Create a session folder programmatically and return the session id and meta."""
    sid = uuid.uuid4().hex[:8]
    folder = BASE / sid
    if folder.exists():
        raise Exception('Session id collision')
    folder.mkdir(parents=True)
    meta = {
        'id': sid,
        'name': name,
        'created_at': datetime.utcnow().isoformat(),
        'owner': owner_email,
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
    owner: str = None


@router.post('', status_code=201)
def create_session(req: CreateSessionRequest, current_user=Depends(get_current_user)):
    try:
        owner_email = current_user.email or current_user.username
        sid, meta = create_session_folder(req.name, owner_email, invites=[])
        return {'id': sid, 'name': req.name, 'owner': owner_email}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('', response_model=List[dict])
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
    except Exception:
        raise HTTPException(status_code=500, detail='Failed to read meta')


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
    except Exception:
        raise HTTPException(status_code=500, detail='Failed to delete file')


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
    email: str


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
    invites = data.get('invites', [])
    if req.email in invites:
        return {'ok': True, 'invites': invites}
    invites.append(req.email)
    data['invites'] = invites
    meta.write_text(json.dumps(data))
    return {'ok': True, 'invites': invites}
