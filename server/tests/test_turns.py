from fastapi.testclient import TestClient

import server.main as main


def _login(client: TestClient):
    resp = client.post('/player/login', json={'email': 'test@example.com', 'password': 'secret'})
    assert resp.status_code == 200
    token = resp.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_turn_lifecycle(tmp_path, monkeypatch):
    client = TestClient(main.app)
    headers = _login(client)

    # bootstrap session via API to create folder
    session = client.post('/sessions', json={'name': 'Test Session'}, headers=headers)
    assert session.status_code == 201, session.text
    session_id = session.json()['id']

    state = client.post(f'/turns/{session_id}', json={'order': ['a', 'b', 'c'], 'active_index': 0}, headers=headers)
    assert state.status_code == 200, state.text
    data = state.json()
    assert data['order'][0] == 'a'
    assert data['active_index'] == 0
    assert data['active'] == 'a'

    advanced = client.post(f'/turns/{session_id}/advance', json={'steps': 1}, headers=headers)
    assert advanced.status_code == 200
    adv_data = advanced.json()
    assert adv_data['active_index'] == 1
    assert adv_data['active'] == 'b'

    fetched = client.get(f'/turns/{session_id}', headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()['active_index'] == adv_data['active_index']
