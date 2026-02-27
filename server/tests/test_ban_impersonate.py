"""Tests for email ban / suspension and admin impersonation endpoints."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

import server.db as db
from server.agents.admin import router as admin_router
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
app.include_router(admin_router)
client = TestClient(app)

ADMIN_EMAIL = "admin_ban@example.local"
ADMIN_PASS = "adminpass999"
USER_EMAIL = "targetuser_ban@example.local"
USER_PASS = "userpass999"

admin_token: str = ""
user_token: str = ""
user_id: int = 0


def _signup_and_login(email: str, password: str, admin: bool = False) -> str:
    r = client.post("/player/signup", json={"email": email, "password": password, "name": email.split("@")[0]})
    assert r.status_code == 200, r.text
    tok = r.json()["verification_token"]
    client.post("/player/verify-email", json={"email": email, "token": tok})
    if admin:
        from sqlmodel import Session
        u = db.get_user_by_identifier(email)
        p = dict(u.profile or {})
        p["admin"] = True
        u.profile = p
        with Session(db.engine) as sess:
            sess.add(u)
            sess.commit()
    r2 = client.post("/player/login", json={"email": email, "password": password})
    assert r2.status_code == 200, r2.text
    return r2.json()["access_token"]


def test_setup():
    global admin_token, user_token, user_id
    admin_token = _signup_and_login(ADMIN_EMAIL, ADMIN_PASS, admin=True)
    user_token = _signup_and_login(USER_EMAIL, USER_PASS)
    user_id = db.get_user_by_identifier(USER_EMAIL).id


# ---------------------------------------------------------------------------
# Email ban
# ---------------------------------------------------------------------------


def test_list_bans_empty():
    r = client.get("/admin/bans", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    assert r.json()["bans"] == []


def test_create_ban():
    r = client.post(
        "/admin/bans",
        json={"email": USER_EMAIL, "reason": "spammer", "ban_type": "ban"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ban"]["email"] == USER_EMAIL
    assert r.json()["ban"]["ban_type"] == "ban"


def test_banned_user_cannot_login():
    r = client.post("/player/login", json={"email": USER_EMAIL, "password": USER_PASS})
    assert r.status_code == 403, r.text
    assert "banned" in r.json()["detail"].lower()


def test_list_bans_contains_ban():
    r = client.get("/admin/bans", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    emails = [b["email"] for b in r.json()["bans"]]
    assert USER_EMAIL in emails


def test_remove_ban():
    from urllib.parse import quote
    r = client.delete(f"/admin/bans/{quote(USER_EMAIL, safe='')}", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    assert r.json()["removed"] is True


def test_unbanned_user_can_login():
    r = client.post("/player/login", json={"email": USER_EMAIL, "password": USER_PASS})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Suspension
# ---------------------------------------------------------------------------


def test_create_suspension():
    future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    r = client.post(
        "/admin/bans",
        json={"email": USER_EMAIL, "reason": "temp suspension", "ban_type": "suspend", "suspended_until": future},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ban"]["ban_type"] == "suspend"


def test_suspended_user_cannot_login():
    r = client.post("/player/login", json={"email": USER_EMAIL, "password": USER_PASS})
    assert r.status_code == 403, r.text
    assert "suspended" in r.json()["detail"].lower()


def test_remove_suspension():
    from urllib.parse import quote
    client.delete(f"/admin/bans/{quote(USER_EMAIL, safe='')}", headers={"Authorization": f"Bearer {admin_token}"})
    r = client.post("/player/login", json={"email": USER_EMAIL, "password": USER_PASS})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Impersonation
# ---------------------------------------------------------------------------


def test_impersonate_user():
    r = client.post(f"/admin/users/{user_id}/impersonate", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert data["impersonated_user_id"] == user_id
    assert data["expires_in"] == 900  # 15 minutes


def test_non_admin_cannot_impersonate():
    r = client.post(f"/admin/users/{user_id}/impersonate", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 403


def test_impersonation_token_is_functional():
    """Token obtained via impersonate should be a valid JWT for the target user."""
    r = client.post(f"/admin/users/{user_id}/impersonate", headers={"Authorization": f"Bearer {admin_token}"})
    token = r.json()["access_token"]
    from server.auth import decode_access_token
    payload = decode_access_token(token)
    assert payload is not None
    assert payload.get("sub") == USER_EMAIL


# ---------------------------------------------------------------------------
# Per-user reports and tickets
# ---------------------------------------------------------------------------


def test_get_reports_about_user_empty():
    r = client.get(f"/admin/users/{user_id}/reports", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["reports"] == []


def test_get_tickets_by_user_empty():
    r = client.get(f"/admin/users/{user_id}/tickets", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["tickets"] == []
