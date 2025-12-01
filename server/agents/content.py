from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel
from pathlib import Path
import json


class AdvanceRequest(BaseModel):
    sceneId: Optional[str] = None
    choiceId: Optional[str] = None
    sessionId: Optional[str] = None

router = APIRouter(prefix="/content")
SESSIONS_DIR = Path(__file__).resolve().parents[1] / 'sessions'
from ..auth import get_current_user


@router.get('/campaigns/seed')
def get_seed_campaign():
    # Minimal seed scene returned for the frontend NarrativeView
    return {
        "id": "seed",
        "title": "The Abandoned Mill",
        "image": None,
        "text": "The wind howls as you step into the mill. Broken gears and faded banners tell a story of a sudden evacuation...",
        "choices": [
            {"id": "search", "label": "Search the sacks"},
            {"id": "listen", "label": "Listen at the door"}
        ]
    }


@router.post('/advance')
def advance_scene(req: AdvanceRequest, current_user=Depends(get_current_user)):
    # Very small state machine for choices to demonstrate interaction
    choiceId = req.choiceId
    if choiceId == 'search':
        res = {"narration":"You rummage through the sacks and find a small silver key.", "nextScene": None}
        if req.sessionId:
            folder = SESSIONS_DIR / req.sessionId
            if folder.exists():
                meta = folder / 'meta.json'
                if meta.exists():
                    data = json.loads(meta.read_text())
                    owner = data.get('owner')
                    invites = data.get('invites', [])
                    identifier = current_user.email or current_user.username
                    if identifier != owner and identifier not in invites:
                        raise HTTPException(status_code=403, detail='Not a member of this session')
                story = folder / 'story.json'
                try:
                    cur = json.loads(story.read_text())
                except Exception:
                    cur = []
                # append event
                if isinstance(cur, list):
                    cur.append({'type':'narration','text':res['narration']})
                else:
                    cur = [cur, {'type':'narration','text':res['narration']}]
                story.write_text(json.dumps(cur))
        return res
    if choiceId == 'listen':
        res = {"narration":"You press your ear to the door and hear muffled voices on the other side.", "nextScene": None}
        if req.sessionId:
            folder = SESSIONS_DIR / req.sessionId
            if folder.exists():
                story = folder / 'story.json'
                try:
                    cur = json.loads(story.read_text())
                except Exception:
                    cur = []
                if isinstance(cur, list):
                    cur.append({'type':'narration','text':res['narration']})
                else:
                    cur = [cur, {'type':'narration','text':res['narration']}]
                story.write_text(json.dumps(cur))
        return res
    res = {"narration":"Nothing notable happens.", "nextScene": None}
    if req.sessionId:
        folder = SESSIONS_DIR / req.sessionId
        if folder.exists():
            story = folder / 'story.json'
            try:
                cur = json.loads(story.read_text())
            except Exception:
                cur = []
            if isinstance(cur, list):
                cur.append({'type':'narration','text':res['narration']})
            else:
                cur = [cur, {'type':'narration','text':res['narration']}]
            story.write_text(json.dumps(cur))
    return res
