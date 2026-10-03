import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.agents import narrative


def make_fake_chat_complete(response_text: str, captured: dict | None = None):
    def _fake(messages, **kwargs):
        if captured is not None:
            captured['last'] = {'kwargs': {'messages': messages, **kwargs}}
        return response_text
    return _fake


def test_generate_narrative_uses_openai(monkeypatch):
    captured = {}
    monkeypatch.setattr(narrative, 'chat_complete', make_fake_chat_complete('FAKE LLM SCENE OUTPUT. Ask: What do you do?', captured))

    req = narrative.NarrativeRequest(scene='A dark road', player='Alice')
    resp = narrative.generate_narrative(req)
    assert isinstance(resp.narrative, str)
    assert 'FAKE LLM SCENE OUTPUT' in resp.narrative
    # Ensure chat_complete was called with messages containing our scene
    assert 'last' in captured
    msgs = captured['last']['kwargs'].get('messages')
    assert msgs and any('A dark road' in (m.get('content') or '') for m in msgs)


def test_generate_narrative_parses_json_response(monkeypatch):
    captured = {}
    json_body = '\nSome intro text\n```json\n{\n  "narrative": "You enter a hall lit by sconces.",\n  "prompt": "What do you examine?",\n  "citations": [{"source_id":"PHB","page":77,"snippet":"Light sources"}]\n}\n```\n'
    monkeypatch.setattr(narrative, 'chat_complete', make_fake_chat_complete(json_body, captured))

    req = narrative.NarrativeRequest(scene='Hall', player='Bryn')
    resp = narrative.generate_narrative(req)
    assert isinstance(resp.narrative, str)
    assert 'You enter a hall lit by sconces.' in resp.narrative
    assert 'Citations:' in resp.narrative


def test_continue_narrative_includes_references(monkeypatch, tmp_path):
    # create a fake session folder with story/pcs/npcs
    session_id = 'testsess123'
    folder = tmp_path / 'sessions' / session_id
    folder.mkdir(parents=True)
    # Write story.json with a narration entry
    story = [
        {'type': 'narration', 'text': 'The party entered a ruined tower.'}
    ]
    (folder / 'story.json').write_text(json.dumps(story))
    (folder / 'meta.json').write_text(json.dumps({
        'id': session_id,
        'name': 'Test Session',
        'owner': 'rog@example.com',
        'invites': [],
        'members': [{'email': 'rog@example.com', 'role': 'owner'}],
    }))
    (folder / 'pcs.json').write_text(json.dumps([{'name': 'Rog'}, {'name': 'Mira'}]))
    (folder / 'npcs.json').write_text(json.dumps([{'name': 'Keeper'}]))

    captured = {}
    monkeypatch.setattr(narrative, 'chat_complete', make_fake_chat_complete('FAKE LLM SCENE OUTPUT. Ask: What do you do?', captured))

    # Monkeypatch the sessions folder used by narrative.continue_narrative
    monkeypatch.setattr(narrative, 'Path', Path)

    # Monkeypatch search_query to return a sample hit
    monkeypatch.setattr(narrative, 'search_query', lambda q, top_k=3, **_kw: [{'source_id': 'PHB', 'page': 123, 'snippet': 'Fireball deals 8d6 fire damage', 'score': 0.9}])

    # Ensure the session folder is in the actual sessions location used by narrative
    real_sessions_dir = Path(__file__).resolve().parents[1] / 'sessions'
    target = real_sessions_dir / session_id
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    # Copy our tmp folder contents into the repo sessions folder for the duration of the test
    for f in folder.iterdir():
        dest = target / f.name
        dest.write_text(f.read_text())

    try:
        req = narrative.ContinueRequest(session_id=session_id, player='Rog')
        current_user = SimpleNamespace(email='rog@example.com', username='rog')
        res = narrative.continue_narrative(req, current_user=current_user)
        assert isinstance(res.narrative, str)
        # Our fake LLM output should be used
        assert 'FAKE LLM SCENE OUTPUT' in res.narrative
        # Verify the captured messages contained the relevant rule snippet via search_query
        assert 'last' in captured
        messages = captured['last']['kwargs'].get('messages')
        assert messages and any('Fireball deals' in (m.get('content') or '') or 'PHB' in (m.get('content') or '') for m in messages)
    finally:
        # cleanup the temporary session folder we wrote into repo
        try:
            for f in target.iterdir():
                f.unlink()
            target.rmdir()
        except Exception:
            pass


def test_regenerate_narrative_skips_story_history(monkeypatch, tmp_path):
    """Regenerate should produce a narrative without using recent story history."""
    session_id = 'regentest456'
    folder = tmp_path / 'sessions' / session_id
    folder.mkdir(parents=True)
    # Write story.json – regenerate should NOT include this in the scene
    story = [
        {'type': 'narration', 'text': 'Secret story that must not appear in regeneration.'}
    ]
    (folder / 'story.json').write_text(json.dumps(story))
    (folder / 'meta.json').write_text(json.dumps({
        'id': session_id,
        'name': 'Regen Session',
        'owner': 'hero@example.com',
        'invites': [],
        'members': [{'email': 'hero@example.com', 'role': 'owner'}],
    }))
    (folder / 'pcs.json').write_text(json.dumps([{'name': 'Arion'}]))
    (folder / 'npcs.json').write_text(json.dumps([]))

    captured = {}
    monkeypatch.setattr(narrative, 'chat_complete', make_fake_chat_complete('FAKE LLM SCENE OUTPUT. Ask: What do you do?', captured))

    real_sessions_dir = Path(__file__).resolve().parents[1] / 'sessions'
    target = real_sessions_dir / session_id
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    for f in folder.iterdir():
        dest = target / f.name
        dest.write_text(f.read_text())

    try:
        req = narrative.RegenerateRequest(session_id=session_id, player='Arion')
        current_user = SimpleNamespace(email='hero@example.com', username='hero')
        res = narrative.regenerate_narrative(req, current_user=current_user)
        assert isinstance(res.narrative, str)
        # Our fake LLM output should be used
        assert 'FAKE LLM SCENE OUTPUT' in res.narrative
        # The story history text must NOT be passed to the LLM
        messages = captured['last']['kwargs'].get('messages')
        assert messages
        combined = ' '.join(m.get('content') or '' for m in messages)
        assert 'Secret story that must not appear in regeneration' not in combined
    finally:
        try:
            for f in target.iterdir():
                f.unlink()
            target.rmdir()
        except Exception:
            pass
