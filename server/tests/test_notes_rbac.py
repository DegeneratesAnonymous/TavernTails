"""RBAC tests for the /notes/log endpoint.

WO-009: verify that notes logging enforces session membership.
"""
from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents import sessions as sessions_module
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
    db.verify_user(email, user.verification_token)


def test_notes_log_requires_auth():
    """Unauthenticated requests to /notes/log return 401 or 403."""
    client = _client()
    owner = "notes-anon-host@example.com"
    _ensure_user(owner)
    sid, _ = sessions_module.create_session_folder("Notes Anon Session", owner)

    resp = client.post(
        "/notes/log",
        json={"session_id": sid, "notes": ["something happened"]},
        # no Authorization header
    )
    assert resp.status_code in (401, 403), resp.text


def test_notes_log_non_member_forbidden():
    """A valid user who is not a session member gets 403."""
    client = _client()
    owner = "notes-host@example.com"
    stranger = "notes-stranger@example.com"
    _ensure_user(owner)
    _ensure_user(stranger)

    sid, _ = sessions_module.create_session_folder("Notes RBAC Session", owner)

    stranger_headers = {"Authorization": f"Bearer {create_access_token(stranger)}"}
    resp = client.post(
        "/notes/log",
        headers=stranger_headers,
        json={"session_id": sid, "notes": ["I should not be here"]},
    )
    assert resp.status_code == 403, resp.text


def test_notes_log_member_can_log():
    """A session member (non-host) can log notes successfully."""
    client = _client()
    owner = "notes-host2@example.com"
    member = "notes-member@example.com"
    _ensure_user(owner)
    _ensure_user(member)

    import json as _json

    sid, _ = sessions_module.create_session_folder("Notes Member Session", owner)
    meta_path = sessions_module.BASE / sid / "meta.json"
    data = _json.loads(meta_path.read_text())
    data["invites"] = [member]
    meta_path.write_text(_json.dumps(data))

    member_headers = {"Authorization": f"Bearer {create_access_token(member)}"}
    resp = client.post(
        "/notes/log",
        headers=member_headers,
        json={"session_id": sid, "notes": ["The party entered the dungeon", "A goblin appeared"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["notes_logged"] == 2
    assert body["session_id"] == sid
    assert body["recap"]


def test_notes_log_host_can_log():
    """The session host can log notes successfully."""
    client = _client()
    owner = "notes-host3@example.com"
    _ensure_user(owner)

    sid, _ = sessions_module.create_session_folder("Notes Host Session", owner)

    owner_headers = {"Authorization": f"Bearer {create_access_token(owner)}"}
    resp = client.post(
        "/notes/log",
        headers=owner_headers,
        json={"session_id": sid, "notes": ["Session started", "Players chose to go north"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["notes_logged"] == 2


def test_notes_log_unknown_session_returns_error():
    """Logging notes for a nonexistent session returns 404."""
    client = _client()
    owner = "notes-host4@example.com"
    _ensure_user(owner)

    owner_headers = {"Authorization": f"Bearer {create_access_token(owner)}"}
    resp = client.post(
        "/notes/log",
        headers=owner_headers,
        json={"session_id": "nonexistent-session-xyz", "notes": ["test"]},
    )
    assert resp.status_code == 404, resp.text
