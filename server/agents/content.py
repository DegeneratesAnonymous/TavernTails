import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..realtime import broadcaster
from . import narrative as narrative_agent
from . import scene as scene_agent
from . import sessions as sessions_agent
from . import suggestions as suggestions_agent


class AdvanceRequest(BaseModel):
    sceneId: str | None = None
    choiceId: str | None = None
    sessionId: str | None = None

router = APIRouter(prefix="/content")
SESSIONS_DIR = Path(__file__).resolve().parents[1] / "sessions"


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
    # Very small state machine for choices to demonstrate interaction.
    # When session_id is provided, we persist an evolving `scene.json` and append entries into `story.json`.
    choice_id = req.choice_id

    def _ensure_member(session_id: str) -> None:
        folder = SESSIONS_DIR / session_id
        if not folder.exists():
            raise HTTPException(status_code=404, detail='Session not found')
        meta = folder / 'meta.json'
        if meta.exists():
            try:
                data = json.loads(meta.read_text())
            except Exception as err:
                raise HTTPException(status_code=500, detail='Failed to read meta') from err
            identifier = sessions_agent._identifier_for_user(current_user)
            if not sessions_agent._user_is_member(data, identifier):
                raise HTTPException(status_code=403, detail='Not a member of this session')

    def _load_current_scene(session_id: str) -> dict:
        folder = SESSIONS_DIR / session_id
        scene_path = folder / 'scene.json'
        if not scene_path.exists():
            return {
                'id': 'opening',
                'title': 'Opening Scene',
                'image': None,
                'text': 'The adventure begins.',
                'choices': [],
            }
        try:
            raw = json.loads(scene_path.read_text())
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _write_scene(session_id: str, scene: dict) -> None:
        folder = SESSIONS_DIR / session_id
        (folder / 'scene.json').write_text(json.dumps(scene))

    def _append_story(session_id: str, entry: dict) -> None:
        folder = SESSIONS_DIR / session_id
        story = folder / 'story.json'
        try:
            cur = json.loads(story.read_text()) if story.exists() else []
        except Exception:
            cur = []
        if not isinstance(cur, list):
            cur = [cur]
        cur.append(entry)
        story.write_text(json.dumps(cur))
    narration_map = {
        'search': 'You rummage through the sacks and find a small silver key.',
        'listen': 'You press your ear to the door and hear muffled voices on the other side.',
        'scout': 'You move quietly, taking stock of threats and exits before committing the party.',
        'parley': 'You approach with open hands, looking for the safest words to earn trust.',
        'investigate': 'You follow the strongest lead, examining the scene for what others missed.',
        'talk': 'You strike up a conversation to test motives and gather rumors.',
        'press_on': 'You push forward, choosing momentum over caution.',
        'plan': 'You huddle up, define roles, and agree on a clear next step.',
    }

    narration = narration_map.get(choice_id or '', 'Nothing notable happens.')
    res = {"narration": narration, "nextScene": None}

    if req.session_id:
        _ensure_member(req.session_id)
        current = _load_current_scene(req.session_id)
        prev_title = (current.get('title') or 'Scene')
        prev_text = (current.get('text') or '')
        player_run = sessions_agent.is_player_run_mode(req.session_id)
        if player_run:
            next_scene = {
                'id': f"scene-{int(datetime.now(timezone.utc).timestamp())}",
                'title': prev_title,
                'image': None,
                'text': f"{narration}",
                'choices': [
                    {'id': 'investigate', 'label': 'Investigate further'},
                    {'id': 'talk', 'label': 'Talk / negotiate'},
                    {'id': 'press_on', 'label': 'Move to the next area'},
                    {'id': 'rest', 'label': 'Take a breather and regroup'},
                ],
            }
        else:
            seed = f"After choosing '{choice_id}', continue the scene: {prev_title}. Context: {prev_text}"
            generated = narrative_agent.generate_narrative(narrative_agent.NarrativeRequest(
                scene=seed,
                player='party',
                style='balanced',
                weather='clear',
                time_of_day='day',
            ))
            next_scene = {
                'id': f"scene-{int(datetime.now(timezone.utc).timestamp())}",
                'title': prev_title,
                'image': None,
                'text': f"{narration}\n\n{generated.narrative}\n\n{generated.prompt}",
                'choices': [
                    {'id': 'investigate', 'label': 'Investigate further'},
                    {'id': 'talk', 'label': 'Talk / negotiate'},
                    {'id': 'press_on', 'label': 'Move to the next area'},
                    {'id': 'rest', 'label': 'Take a breather and regroup'},
                ],
            }

        _write_scene(req.session_id, next_scene)
        _append_story(req.session_id, {
            'type': 'choice',
            'ts': datetime.now(timezone.utc).isoformat(),
            'choice_id': choice_id,
        })
        _append_story(req.session_id, {
            'type': 'narration',
            'ts': datetime.now(timezone.utc).isoformat(),
            'text': next_scene['text'],
        })

        res['nextScene'] = next_scene
        try:
            # broadcast_json is async; content.advance is sync. Run best-effort.
            import anyio

            anyio.from_thread.run(
                broadcaster.broadcast_json,
                req.session_id,
                {
                    'type': 'narrative.scene',
                    'session_id': req.session_id,
                    'scene': next_scene,
                },
            )
        except Exception:
            pass

        if not player_run:
            try:
                import anyio

                anyio.from_thread.run(
                    scene_agent.analyze_scene,
                    scene_agent.SceneAnalysisRequest(
                        scene=next_scene['text'],
                        actions=[c.get('label', '') for c in (next_scene.get('choices') or []) if isinstance(c, dict)],
                        session_id=req.session_id,
                    ),
                )
            except Exception:
                pass

            try:
                import anyio

                anyio.from_thread.run(
                    suggestions_agent.get_suggestions,
                    session_id=req.session_id,
                    limit=4,
                    current_user=current_user,
                )
            except Exception:
                pass

    return res
