import os
import sys
import json
from pathlib import Path

import pytest

from server.agents import narrative


def make_fake_openai_module(captured):
    class DummyChat:
        @staticmethod
        def create(*args, **kwargs):
            # capture call for assertions
            captured['last'] = {'args': args, 'kwargs': kwargs}
            # Default fake returns raw text
            return {'choices': [{'message': {'content': 'FAKE LLM SCENE OUTPUT. Ask: What do you do?'}}]}

    fake = type('m', (), {})()
    fake.ChatCompletion = DummyChat
    return fake


def test_generate_narrative_uses_openai(monkeypatch):
    # Ensure OPENAI key appears set so code path imports openai
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    captured = {}
    fake = make_fake_openai_module(captured)
    sys.modules['openai'] = fake

    req = narrative.NarrativeRequest(scene='A dark road', player='Alice')
    resp = narrative.generate_narrative(req)
    assert isinstance(resp.narrative, str)
    assert 'FAKE LLM SCENE OUTPUT' in resp.narrative
    # Ensure ChatCompletion.create was called with messages containing our scene
    assert 'last' in captured
    msgs = captured['last']['kwargs'].get('messages') or captured['last']['kwargs'].get('messages')
    assert msgs and any('A dark road' in (m.get('content') or '') for m in msgs)


def test_generate_narrative_parses_json_response(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    captured = {}

    class JSONDummy:
        @staticmethod
        def create(*args, **kwargs):
            captured['last'] = {'args': args, 'kwargs': kwargs}
            # Model returns markdown with embedded JSON
            body = '\nSome intro text\n```json\n{\n  "narrative": "You enter a hall lit by sconces.",\n  "prompt": "What do you examine?",\n  "citations": [{"source_id":"PHB","page":77,"snippet":"Light sources"}]\n}\n```\n'
            return {'choices': [{'message': {'content': body}}]}

    sys.modules['openai'] = type('m', (), {'ChatCompletion': JSONDummy})()

    req = narrative.NarrativeRequest(scene='Hall', player='Bryn')
    resp = narrative.generate_narrative(req)
    assert isinstance(resp.narrative, str)
    assert 'You enter a hall lit by sconces.' in resp.narrative
    assert 'Citations:' in resp.narrative


def test_continue_narrative_includes_references(monkeypatch, tmp_path):
    # create a fake session folder with story/pcs/npcs
    sessions_root = Path(__file__).resolve().parents[2] / 'sessions'
    session_id = 'testsess123'
    folder = tmp_path / 'sessions' / session_id
    folder.mkdir(parents=True)
    # Write story.json with a narration entry
    story = [
        {'type': 'narration', 'text': 'The party entered a ruined tower.'}
    ]
    (folder / 'story.json').write_text(json.dumps(story))
    (folder / 'pcs.json').write_text(json.dumps([{'name': 'Rog'}, {'name': 'Mira'}]))
    (folder / 'npcs.json').write_text(json.dumps([{'name': 'Keeper'}]))

    # Monkeypatch narrative sessions dir resolution to use our tmp sessions folder
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    captured = {}
    fake = make_fake_openai_module(captured)
    sys.modules['openai'] = fake

    # Monkeypatch the sessions folder used by narrative.continue_narrative
    orig_base = Path(__file__).resolve().parents[1] / 'sessions'
    monkeypatch.setattr(narrative, 'Path', Path)

    # Monkeypatch search_query to return a sample hit
    monkeypatch.setattr(narrative, 'search_query', lambda q, top_k=3: [{'source_id': 'PHB', 'page': 123, 'snippet': 'Fireball deals 8d6 fire damage', 'score': 0.9}])

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
        res = narrative.continue_narrative(req)
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
