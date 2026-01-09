from fastapi.testclient import TestClient
import server.main as main


def _login_dev(client: TestClient) -> dict:
    resp = client.post('/player/login', json={'email': 'test@example.com', 'password': 'secret'})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return {'Authorization': f"Bearer {body['access_token']}"}


def test_chat_message_roundtrip(tmp_path, monkeypatch):
    client = TestClient(main.app)
    headers = _login_dev(client)

    create = client.post('/chat', json={'session_id': 'testsession', 'message': 'Hello from test'}, headers=headers)
    assert create.status_code == 201, create.text
    created = create.json()
    assert created['message'] == 'Hello from test'
    assert created['mentions'] == []

    listing = client.get('/chat', params={'session_id': 'testsession'}, headers=headers)
    assert listing.status_code == 200
    items = listing.json()
    assert any(msg['message'] == 'Hello from test' for msg in items)


def test_chat_mentions_are_detected():
    client = TestClient(main.app)
    headers = _login_dev(client)
    resp = client.post('/chat', json={'session_id': 'mention-session', 'message': '@Aria please scout ahead'}, headers=headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert 'aria' in data['mentions']


def test_suggestions_default_pool():
    client = TestClient(main.app)
    headers = _login_dev(client)
    resp = client.get('/suggestions', headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data['source'] == 'default'
    assert len(data['suggestions']) >= 1


def test_suggestions_respond_to_combat_language():
    client = TestClient(main.app)
    headers = _login_dev(client)
    session_id = 'combat-session'
    payloads = [
        {'session_id': session_id, 'message': 'I attack the goblin with my sword'},
        {'session_id': session_id, 'message': 'Strike while they are staggered!'},
    ]
    for body in payloads:
        resp = client.post('/chat', json=body, headers=headers)
        assert resp.status_code == 201, resp.text

    resp = client.get('/suggestions', params={'session_id': session_id}, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data['source'].startswith('chat:')
    assert any('cover' in s.lower() or 'attack' in s.lower() for s in data['suggestions'])
