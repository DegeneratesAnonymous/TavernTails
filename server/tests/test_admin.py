"""Tests for the admin API endpoints."""

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

ADMIN_EMAIL = "admin_test@example.local"
ADMIN_PASS = "adminpass123"
USER_EMAIL = "regular_test@example.local"
USER_PASS = "userpass123"

admin_token: str = ""
user_token: str = ""
user_id: int = 0


def _login(email: str, password: str) -> str:
    # ensure verified
    u = db.get_user_by_identifier(email)
    if u and not u.verified and u.verification_token:
        db.verify_user(email, u.verification_token)
    r = client.post("/player/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_setup_users():
    global admin_token, user_token, user_id
    # create admin user
    r = client.post("/player/signup", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS, "name": "AdminUser"})
    assert r.status_code == 200
    token = r.json()["verification_token"]
    client.post("/player/verify-email", json={"email": ADMIN_EMAIL, "token": token})
    # grant admin via db directly
    adm = db.get_user_by_identifier(ADMIN_EMAIL)
    assert adm is not None
    p = dict(adm.profile or {})
    p["admin"] = True
    adm.profile = p
    from sqlmodel import Session
    with Session(db.engine) as sess:
        sess.add(adm)
        sess.commit()

    admin_token = _login(ADMIN_EMAIL, ADMIN_PASS)

    # create regular user
    r = client.post("/player/signup", json={"email": USER_EMAIL, "password": USER_PASS, "name": "RegularUser"})
    assert r.status_code == 200
    token = r.json()["verification_token"]
    client.post("/player/verify-email", json={"email": USER_EMAIL, "token": token})
    user_token = _login(USER_EMAIL, USER_PASS)
    u = db.get_user_by_identifier(USER_EMAIL)
    assert u is not None
    user_id = u.id  # type: ignore[assignment]


def test_stats_requires_admin():
    r = client.get("/admin/stats", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 403


def test_stats_admin_ok():
    r = client.get("/admin/stats", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    data = r.json()
    assert "total_users" in data
    assert data["total_users"] >= 2
    assert "total_campaigns" in data


def test_list_users():
    r = client.get("/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    data = r.json()
    assert "users" in data
    emails = [u["email"] for u in data["users"]]
    assert ADMIN_EMAIL in emails
    assert USER_EMAIL in emails


def test_list_users_forbidden_for_non_admin():
    r = client.get("/admin/users", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 403


def test_get_user():
    r = client.get(f"/admin/users/{user_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == user_id
    assert data["email"] == USER_EMAIL


def test_get_user_not_found():
    r = client.get("/admin/users/99999", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 404


def test_warn_user():
    r = client.post(
        f"/admin/users/{user_id}/warn",
        json={"message": "Please follow the rules."},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert r.json()["warned"] is True
    # notification should appear in user profile
    u = db.admin_get_user(user_id)
    assert u is not None
    notifs = (u.profile or {}).get("notifications", [])
    assert any("Warning" in n.get("title", "") for n in notifs)


def test_message_user():
    r = client.post(
        f"/admin/users/{user_id}/message",
        json={"title": "Hello!", "body": "Important info from admin."},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert r.json()["sent"] is True


def test_reset_password():
    new_pass = "NewSecure456"
    r = client.post(
        f"/admin/users/{user_id}/reset-password",
        json={"new_password": new_pass},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert r.json()["reset"] is True
    # user should be able to login with new password
    r2 = client.post("/player/login", json={"email": USER_EMAIL, "password": new_pass})
    assert r2.status_code == 200


def test_reset_password_too_short():
    r = client.post(
        f"/admin/users/{user_id}/reset-password",
        json={"new_password": "short"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400


def test_list_campaigns():
    r = client.get("/admin/campaigns", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    data = r.json()
    assert "campaigns" in data


def test_archive_campaign_not_found():
    r = client.post("/admin/campaigns/nonexistent/archive", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 404


def test_global_search():
    r = client.get("/admin/search?q=Regular", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    data = r.json()
    assert "users" in data
    assert any("Regular" in (u.get("name") or "") or "regular" in (u.get("email") or "").lower() for u in data["users"])


def test_global_search_short_query():
    r = client.get("/admin/search?q=a", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["users"] == []
    assert data["campaigns"] == []
