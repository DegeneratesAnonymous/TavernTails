from fastapi.testclient import TestClient

import server.main as main
from server import db


def _create_and_verify(email: str, password: str, username: str):
    user = db.create_user(email=email, password=password, username=username, profile={"name": username, "email": email})
    token = user.verification_token
    db.verify_user(email, token)
    return user


def test_user_search_and_invite_by_username():
    client = TestClient(main.app)

    _create_and_verify('owner@example.com', 'secret', 'owner')
    _create_and_verify('bob@example.com', 'secret', 'bob')

    login = client.post('/player/login', json={'email': 'owner@example.com', 'password': 'secret'})
    assert login.status_code == 200
    token = login.json()['access_token']

    # Search by username
    search = client.get('/users/search?q=bo', headers={'Authorization': f'Bearer {token}'})
    assert search.status_code == 200
    results = search.json().get('results')
    assert isinstance(results, list)
    assert any(r.get('username') == 'bob' for r in results)

    # Create a session
    created = client.post('/sessions', json={'name': 'Invite Test'}, headers={'Authorization': f'Bearer {token}'})
    assert created.status_code == 201
    sid = created.json()['id']

    # Invite by username
    invited = client.post(
        f'/sessions/{sid}/invite',
        json={'identifier': 'bob', 'note': 'join us'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert invited.status_code == 200
    payload = invited.json()
    invites = payload.get('invites')
    assert isinstance(invites, list)
    assert any(i.get('email') == 'bob@example.com' for i in invites)

    # Party endpoint should show bob in invites and owner in members.
    party = client.get(f'/sessions/{sid}/party', headers={'Authorization': f'Bearer {token}'})
    assert party.status_code == 200
    pdata = party.json()
    assert any(m.get('email') == 'owner@example.com' for m in pdata.get('members', []))
    assert any(i.get('email') == 'bob@example.com' for i in pdata.get('invites', []))
