"""Tests for PUT /player/me and POST /player/me/change-password (self-service)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

import server.db as db
from server.agents.player import router as player_router


def setup_module(module):
    db.engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db.create_db_and_tables()


app = FastAPI()
app.include_router(player_router)
client = TestClient(app)

USER_EMAIL = "selfedit@example.local"
USER_PASS = "password123"

user_token: str = ""


def _login(email: str, password: str) -> str:
    u = db.get_user_by_identifier(email)
    if u and not u.verified and u.verification_token:
        db.verify_user(email, u.verification_token)
    r = client.post("/player/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def test_setup_user():
    global user_token
    r = client.post("/player/signup", json={"email": USER_EMAIL, "password": USER_PASS, "name": "Self Edit User"})
    assert r.status_code == 200
    token = r.json()["verification_token"]
    client.post("/player/verify-email", json={"email": USER_EMAIL, "token": token})
    user_token = _login(USER_EMAIL, USER_PASS)
    assert user_token


# ---------------------------------------------------------------------------
# PUT /player/me
# ---------------------------------------------------------------------------

def test_update_display_name():
    r = client.put("/player/me", json={"name": "New Name"}, headers=_auth(user_token))
    assert r.status_code == 200
    profile = r.json()["profile"]
    assert profile["name"] == "New Name"


def test_update_username():
    r = client.put("/player/me", json={"username": "cool_handle"}, headers=_auth(user_token))
    assert r.status_code == 200
    profile = r.json()["profile"]
    assert profile.get("username") == "cool_handle"


def test_update_email_returns_new_token():
    """When email changes the response includes a fresh access_token so the client can re-auth."""
    global user_token
    r = client.put("/player/me", json={"email": "newemail@example.local"}, headers=_auth(user_token))
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data, "fresh token must be returned on email change"
    # Use the new token for all subsequent tests
    user_token = data["access_token"]


def test_update_name_empty_rejected():
    r = client.put("/player/me", json={"name": "   "}, headers=_auth(user_token))
    assert r.status_code == 400


def test_update_email_invalid_rejected():
    r = client.put("/player/me", json={"email": "not-an-email"}, headers=_auth(user_token))
    assert r.status_code == 400


def test_update_no_fields_rejected():
    r = client.put("/player/me", json={}, headers=_auth(user_token))
    assert r.status_code == 400


def test_update_me_requires_auth():
    r = client.put("/player/me", json={"name": "Hacker"})
    assert r.status_code == 401


def test_duplicate_email_rejected():
    # Create a second user, try to take the first user's email
    r = client.post("/player/signup", json={"email": "other@example.local", "password": "other123", "name": "Other User"})
    assert r.status_code == 200
    tok2 = r.json()["verification_token"]
    client.post("/player/verify-email", json={"email": "other@example.local", "token": tok2})
    other_token = _login("other@example.local", "other123")
    # try to steal newemail@example.local (already taken by user 1)
    r = client.put("/player/me", json={"email": "newemail@example.local"}, headers=_auth(other_token))
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# POST /player/me/change-password
# ---------------------------------------------------------------------------

def test_change_password_success():
    r = client.post(
        "/player/me/change-password",
        json={"current_password": USER_PASS, "new_password": "newpassword99"},
        headers=_auth(user_token),
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True
    # verify can log in with new password
    new_tok = _login("newemail@example.local", "newpassword99")
    assert new_tok


def test_change_password_wrong_current():
    tok = _login("newemail@example.local", "newpassword99")
    r = client.post(
        "/player/me/change-password",
        json={"current_password": "wrongpassword", "new_password": "anything99"},
        headers=_auth(tok),
    )
    assert r.status_code == 400
    assert "incorrect" in r.json()["detail"].lower()


def test_change_password_too_short():
    tok = _login("newemail@example.local", "newpassword99")
    r = client.post(
        "/player/me/change-password",
        json={"current_password": "newpassword99", "new_password": "short"},
        headers=_auth(tok),
    )
    assert r.status_code == 400
    assert "8 characters" in r.json()["detail"]


def test_change_password_requires_auth():
    r = client.post(
        "/player/me/change-password",
        json={"current_password": "anything", "new_password": "anything99"},
    )
    assert r.status_code == 401
