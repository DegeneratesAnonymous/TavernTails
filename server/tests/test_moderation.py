"""Tests for the moderation (user blocking + reporting) endpoints."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

import server.db as db
from server.agents.moderation import router as moderation_router
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
app.include_router(moderation_router)
client = TestClient(app)

USER_A_EMAIL = "user_a_mod@example.local"
USER_A_PASS = "passA1234"
USER_B_EMAIL = "user_b_mod@example.local"
USER_B_PASS = "passB1234"
ADMIN_EMAIL = "admin_mod@example.local"
ADMIN_PASS = "adminpass1234"

token_a: str = ""
token_b: str = ""
token_admin: str = ""
user_a_id: int = 0
user_b_id: int = 0
report_id: int = 0


def _signup_and_login(email: str, password: str) -> tuple:
    r = client.post("/player/signup", json={"email": email, "password": password, "name": "TestUser"})
    assert r.status_code == 200, r.text
    vtoken = r.json()["verification_token"]
    r3 = client.post("/player/verify-email", json={"email": email, "token": vtoken})
    assert r3.status_code == 200, r3.text
    r2 = client.post("/player/login", json={"email": email, "password": password})
    assert r2.status_code == 200, r2.text
    access_token = r2.json()["access_token"]
    user = db.get_user_by_identifier(email)
    assert user is not None
    return access_token, user.id


def _auth(tok):
    return {"Authorization": "Bearer " + tok}


def test_setup():
    global token_a, token_b, token_admin, user_a_id, user_b_id
    token_a, user_a_id = _signup_and_login(USER_A_EMAIL, USER_A_PASS)
    token_b, user_b_id = _signup_and_login(USER_B_EMAIL, USER_B_PASS)
    token_admin, _ = _signup_and_login(ADMIN_EMAIL, ADMIN_PASS)
    # Grant admin role
    adm = db.get_user_by_identifier(ADMIN_EMAIL)
    assert adm is not None
    with Session(db.engine) as session:
        u = session.exec(select(db.User).where(db.User.id == adm.id)).first()
        assert u is not None
        u.profile = {**(u.profile or {}), "admin": True}
        session.add(u)
        session.commit()


# ---------------------------------------------------------------------------
# Blocking
# ---------------------------------------------------------------------------

def test_block_user():
    r = client.post("/moderation/block/" + str(user_b_id), headers=_auth(token_a))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["blocked"] is True
    assert data["block"]["blocker_id"] == user_a_id
    assert data["block"]["blocked_id"] == user_b_id


def test_block_idempotent():
    r = client.post("/moderation/block/" + str(user_b_id), headers=_auth(token_a))
    assert r.status_code == 200
    assert r.json()["blocked"] is True


def test_block_self_fails():
    r = client.post("/moderation/block/" + str(user_a_id), headers=_auth(token_a))
    assert r.status_code == 400


def test_block_status_is_blocked():
    r = client.get("/moderation/block/" + str(user_b_id) + "/status", headers=_auth(token_a))
    assert r.status_code == 200
    assert r.json()["is_blocked"] is True


def test_block_status_not_blocked():
    r = client.get("/moderation/block/" + str(user_a_id) + "/status", headers=_auth(token_b))
    assert r.status_code == 200
    assert r.json()["is_blocked"] is False


def test_list_my_blocks():
    r = client.get("/moderation/blocks", headers=_auth(token_a))
    assert r.status_code == 200
    data = r.json()
    assert len(data["blocks"]) >= 1
    assert data["blocks"][0]["blocked_id"] == user_b_id
    assert "blocked_name" in data["blocks"][0]


def test_unblock_user():
    r = client.delete("/moderation/block/" + str(user_b_id), headers=_auth(token_a))
    assert r.status_code == 200
    assert r.json()["unblocked"] is True


def test_unblock_nonexistent_returns_false():
    r = client.delete("/moderation/block/" + str(user_b_id), headers=_auth(token_a))
    assert r.status_code == 200
    assert r.json()["unblocked"] is False


def test_block_requires_auth():
    r = client.post("/moderation/block/" + str(user_b_id))
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def test_report_user():
    global report_id
    r = client.post(
        "/moderation/report/" + str(user_b_id),
        json={"reason": "harassment", "details": "They sent me threatening messages."},
        headers=_auth(token_a),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reported"] is True
    report_id = data["report"]["id"]
    assert data["report"]["reason"] == "harassment"
    assert data["report"]["status"] == "open"


def test_report_idempotent():
    r = client.post(
        "/moderation/report/" + str(user_b_id),
        json={"reason": "harassment", "details": "Duplicate report."},
        headers=_auth(token_a),
    )
    assert r.status_code == 200
    assert r.json()["report"]["id"] == report_id  # same record returned


def test_report_invalid_reason():
    r = client.post(
        "/moderation/report/" + str(user_b_id),
        json={"reason": "wrong_reason"},
        headers=_auth(token_a),
    )
    assert r.status_code == 400


def test_report_self_fails():
    r = client.post(
        "/moderation/report/" + str(user_a_id),
        json={"reason": "spam"},
        headers=_auth(token_a),
    )
    assert r.status_code == 400


def test_report_requires_auth():
    r = client.post("/moderation/report/" + str(user_b_id), json={"reason": "spam"})
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Admin — reports queue
# ---------------------------------------------------------------------------

def test_admin_list_reports():
    r = client.get("/moderation/reports", headers=_auth(token_admin))
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["reports"]) >= 1
    assert "reporter_name" in data["reports"][0]
    assert "reported_name" in data["reports"][0]


def test_admin_list_reports_filter_by_status():
    r = client.get("/moderation/reports?status=open", headers=_auth(token_admin))
    assert r.status_code == 200
    assert all(rep["status"] == "open" for rep in r.json()["reports"])


def test_admin_get_report():
    r = client.get("/moderation/reports/" + str(report_id), headers=_auth(token_admin))
    assert r.status_code == 200
    assert r.json()["report"]["id"] == report_id


def test_admin_update_report_status():
    r = client.patch(
        "/moderation/reports/" + str(report_id) + "/status",
        json={"status": "reviewed"},
        headers=_auth(token_admin),
    )
    assert r.status_code == 200, r.text
    assert r.json()["report"]["status"] == "reviewed"
    assert r.json()["report"]["reviewed_at"] is not None


def test_admin_update_report_invalid_status():
    r = client.patch(
        "/moderation/reports/" + str(report_id) + "/status",
        json={"status": "banana"},
        headers=_auth(token_admin),
    )
    assert r.status_code == 400


def test_non_admin_cannot_list_reports():
    r = client.get("/moderation/reports", headers=_auth(token_b))
    assert r.status_code == 403


def test_non_admin_cannot_update_report_status():
    r = client.patch(
        "/moderation/reports/" + str(report_id) + "/status",
        json={"status": "dismissed"},
        headers=_auth(token_b),
    )
    assert r.status_code == 403
