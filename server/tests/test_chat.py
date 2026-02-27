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


# ---------------------------------------------------------------------------
# Pin / unpin / delete
# ---------------------------------------------------------------------------

def test_pin_and_unpin_message():
    client = TestClient(main.app)
    headers = _login_dev(client)
    session_id = 'pin-session'

    # post a message then pin it
    create = client.post('/chat', json={'session_id': session_id, 'message': 'Important announcement'}, headers=headers)
    assert create.status_code == 201, create.text
    msg_id = create.json()['id']

    pin = client.post(f'/chat/{msg_id}/pin', params={'session_id': session_id}, headers=headers)
    assert pin.status_code == 200, pin.text
    assert pin.json()['pinned'] is True

    # list pinned — should contain the message
    pinned = client.get('/chat/pinned', params={'session_id': session_id}, headers=headers)
    assert pinned.status_code == 200, pinned.text
    pinned_ids = [m['id'] for m in pinned.json()]
    assert msg_id in pinned_ids

    # idempotent pin (second call should succeed too)
    pin2 = client.post(f'/chat/{msg_id}/pin', params={'session_id': session_id}, headers=headers)
    assert pin2.status_code == 200

    # unpin
    unpin = client.delete(f'/chat/{msg_id}/pin', params={'session_id': session_id}, headers=headers)
    assert unpin.status_code == 204

    # list pinned — should be empty now
    pinned2 = client.get('/chat/pinned', params={'session_id': session_id}, headers=headers)
    assert pinned2.status_code == 200
    assert msg_id not in [m['id'] for m in pinned2.json()]


def test_pin_wrong_session_404():
    client = TestClient(main.app)
    headers = _login_dev(client)

    create = client.post('/chat', json={'session_id': 'real-session', 'message': 'test'}, headers=headers)
    assert create.status_code == 201
    msg_id = create.json()['id']

    # attempt to pin under a different session_id → 404
    pin = client.post(f'/chat/{msg_id}/pin', params={'session_id': 'wrong-session'}, headers=headers)
    assert pin.status_code == 404


def test_unpin_not_found_404():
    client = TestClient(main.app)
    headers = _login_dev(client)
    unpin = client.delete('/chat/99999/pin', params={'session_id': 'no-session'}, headers=headers)
    assert unpin.status_code == 404


def test_delete_own_message():
    client = TestClient(main.app)
    headers = _login_dev(client)
    session_id = 'delete-session'

    create = client.post('/chat', json={'session_id': session_id, 'message': 'To be deleted'}, headers=headers)
    assert create.status_code == 201
    msg_id = create.json()['id']

    delete = client.delete(f'/chat/{msg_id}', params={'session_id': session_id}, headers=headers)
    assert delete.status_code == 204

    # message should no longer appear in listing
    listing = client.get('/chat', params={'session_id': session_id}, headers=headers)
    assert listing.status_code == 200
    assert msg_id not in [m['id'] for m in listing.json()]


def test_delete_nonexistent_message_403():
    client = TestClient(main.app)
    headers = _login_dev(client)
    resp = client.delete('/chat/99999', params={'session_id': 'any-session'}, headers=headers)
    assert resp.status_code == 403


def test_sender_id_exposed_in_message():
    """Each message response should include the sender_id field."""
    client = TestClient(main.app)
    headers = _login_dev(client)
    resp = client.post('/chat', json={'session_id': 'sid-session', 'message': 'check sender'}, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert 'sender_id' in data
    assert data['sender_id'] is not None

