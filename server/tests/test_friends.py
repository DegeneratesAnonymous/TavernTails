from fastapi.testclient import TestClient

import server.main as main
from server import db


def _create_and_verify(email, password, name=None):
    user = db.create_user(email=email, password=password, username=name)
    # verify token
    token = user.verification_token
    db.verify_user(email, token)
    return user


def test_friend_request_flow():
    client = TestClient(main.app)
    # create two users
    _create_and_verify('alice@example.com', 'secret', 'alice')
    _create_and_verify('bob@example.com', 'secret', 'bob')

    # login both
    r1 = client.post('/player/login', json={'email': 'alice@example.com', 'password': 'secret'})
    assert r1.status_code == 200
    t1 = r1.json()['access_token']

    r2 = client.post('/player/login', json={'email': 'bob@example.com', 'password': 'secret'})
    assert r2.status_code == 200
    t2 = r2.json()['access_token']

    # Alice sends friend request to Bob
    send = client.post('/player/friends', json={'identifier': 'bob@example.com'}, headers={'Authorization': f'Bearer {t1}'})
    assert send.status_code == 200
    assert send.json().get('sent') is True

    # Bob lists friends -> should see pending
    listing = client.get('/player/friends', headers={'Authorization': f'Bearer {t2}'})
    assert listing.status_code == 200
    data = listing.json()
    assert 'pending' in data
    assert any(p['from_profile']['email'] == 'alice@example.com' for p in data['pending'])

    # Bob accepts
    accept = client.post('/player/friends/accept', json={'from_identifier': 'alice@example.com'}, headers={'Authorization': f'Bearer {t2}'})
    assert accept.status_code == 200
    assert accept.json().get('accepted') is True

    # Now both list friends and see each other
    la = client.get('/player/friends', headers={'Authorization': f'Bearer {t1}'})
    lb = client.get('/player/friends', headers={'Authorization': f'Bearer {t2}'})
    assert any(f['email'] == 'bob@example.com' for f in la.json().get('friends', []))
    assert any(f['email'] == 'alice@example.com' for f in lb.json().get('friends', []))
