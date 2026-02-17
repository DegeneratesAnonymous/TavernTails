from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.auth import create_access_token


def _client() -> TestClient:
    return TestClient(main.app)


def _ensure_user(email: str) -> None:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return
    user = db.create_user(
        email=email,
        password="secret",
        username=email.split("@")[0],
        profile={"name": email.split("@")[0], "email": email},
    )
    assert user.verification_token
    db.verify_user(email, user.verification_token)


def test_beyond20_relay_token_get_and_rotate():
    client = _client()
    email = "relay-owner@example.com"
    _ensure_user(email)
    token = create_access_token(email)
    auth_headers = {"Authorization": f"Bearer {token}"}

    r1 = client.get("/player/beyond20/relay-token", headers=auth_headers)
    assert r1.status_code == 200, r1.text
    t1 = r1.json().get("relay_token")
    assert isinstance(t1, str) and len(t1) >= 16

    r2 = client.get("/player/beyond20/relay-token", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json().get("relay_token") == t1

    r3 = client.post("/player/beyond20/relay-token/rotate", headers=auth_headers)
    assert r3.status_code == 200, r3.text
    t2 = r3.json().get("relay_token")
    assert isinstance(t2, str) and len(t2) >= 16
    assert t2 != t1


def test_beyond20_relay_ingest_requires_token():
    client = _client()

    r = client.post(
        "/integrations/beyond20/roll/relay",
        json={"session_id": "test-session", "beyond20": {"action": "roll"}},
    )
    assert r.status_code == 401


def test_beyond20_relay_ingest_accepts_dom_payload():
    client = _client()
    email = "relay-ingest@example.com"
    _ensure_user(email)

    # Ensure a relay token exists for this user
    user = db.get_user_by_identifier(email)
    assert user and user.id is not None
    relay_token = db.ensure_beyond20_relay_token_for_user_id(user.id)
    assert relay_token

    payload = {
        "session_id": "test-session",
        "beyond20": {
            "action": "rendered-roll",
            "title": "Attack Roll",
            "character": {"name": "Sir Relay"},
            "attack_rolls": [
                {
                    "formula": "1d20+5",
                    "parts": [{"rolls": [{"roll": 12}]}, "+", 5],
                    "total": 17,
                }
            ],
        },
    }

    r = client.post(
        "/integrations/beyond20/roll/relay",
        headers={"X-Relay-Token": relay_token},
        json=payload,
    )
    assert r.status_code == 200, r.text
    data = r.json().get("result")
    assert data
    assert data["total"] == 17
    assert data["by"] == "Sir Relay"
    assert data["source"] == "beyond20"
