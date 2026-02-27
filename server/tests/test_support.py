"""Tests for the support / contact-us endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

import server.db as db
from server.agents.player import router as player_router
from server.agents.support import router as support_router


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
app.include_router(support_router)
client = TestClient(app)

USER_EMAIL = "user_support@example.local"
USER_PASS = "userpass123"
ADMIN_EMAIL = "admin_support@example.local"
ADMIN_PASS = "adminpass123"

user_token: str = ""
admin_token: str = ""
ticket_id: int = 0


def _signup_and_login(email: str, password: str) -> str:
    r = client.post("/player/signup", json={"email": email, "password": password, "name": "TestUser"})
    assert r.status_code == 200, r.text
    token = r.json()["verification_token"]
    client.post("/player/verify-email", json={"email": email, "token": token})
    r2 = client.post("/player/login", json={"email": email, "password": password})
    assert r2.status_code == 200, r2.text
    return r2.json()["access_token"]


def test_setup():
    global user_token, admin_token
    user_token = _signup_and_login(USER_EMAIL, USER_PASS)
    admin_token = _signup_and_login(ADMIN_EMAIL, ADMIN_PASS)
    # Grant admin
    adm = db.get_user_by_identifier(ADMIN_EMAIL)
    assert adm is not None
    p = dict(adm.profile or {})
    p["admin"] = True
    from sqlmodel import Session, select

    with Session(db.engine) as session:
        u = session.exec(select(db.User).where(db.User.id == adm.id)).first()
        assert u is not None
        u.profile = p
        session.add(u)
        session.commit()


def test_submit_ticket():
    global ticket_id
    r = client.post(
        "/support/contact",
        json={"subject": "Test subject", "body": "This is a test message body for the ticket."},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "ticket" in data
    ticket = data["ticket"]
    assert ticket["subject"] == "Test subject"
    assert ticket["status"] == "open"
    assert ticket["user_id"] is not None
    ticket_id = ticket["id"]


def test_submit_ticket_too_short_body():
    r = client.post(
        "/support/contact",
        json={"subject": "Hi", "body": "short"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert r.status_code == 422  # FastAPI validation error for min_length


def test_submit_ticket_requires_auth():
    r = client.post(
        "/support/contact",
        json={"subject": "No auth", "body": "This should fail without a token."},
    )
    assert r.status_code in (401, 403)


def test_my_tickets():
    r = client.get("/support/my-tickets", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "tickets" in data
    assert len(data["tickets"]) >= 1
    assert data["tickets"][0]["subject"] == "Test subject"


def test_my_ticket_by_id():
    r = client.get(f"/support/my-tickets/{ticket_id}", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200, r.text
    assert r.json()["ticket"]["id"] == ticket_id


def test_my_ticket_not_found():
    r = client.get("/support/my-tickets/99999", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 404


def test_admin_list_tickets():
    r = client.get("/support/tickets", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "tickets" in data
    assert len(data["tickets"]) >= 1
    # Admin view includes user metadata
    assert "user_email" in data["tickets"][0]


def test_admin_list_tickets_filter_by_status():
    r = client.get("/support/tickets?status=open", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert all(t["status"] == "open" for t in data["tickets"])


def test_admin_get_ticket():
    r = client.get(f"/support/tickets/{ticket_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    assert r.json()["ticket"]["id"] == ticket_id


def test_admin_update_ticket_status():
    r = client.patch(
        f"/support/tickets/{ticket_id}/status",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ticket"]["status"] == "in_progress"


def test_admin_update_ticket_invalid_status():
    r = client.patch(
        f"/support/tickets/{ticket_id}/status",
        json={"status": "banana"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400


def test_non_admin_cannot_list_all_tickets():
    r = client.get("/support/tickets", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 403


def test_non_admin_cannot_update_ticket_status():
    r = client.patch(
        f"/support/tickets/{ticket_id}/status",
        json={"status": "resolved"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert r.status_code == 403
