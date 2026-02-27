"""Tests for the direct messaging (inbox) endpoints."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

import server.db as db
from server.agents.messages import router as messages_router
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
app.include_router(messages_router)
client = TestClient(app)

EMAIL_A = "alice_msg@example.local"
PASS_A = "alicepass123"
EMAIL_B = "bob_msg@example.local"
PASS_B = "bobpass123"
EMAIL_C = "carol_msg@example.local"
PASS_C = "carolpass123"

token_a: str = ""
token_b: str = ""
token_c: str = ""
user_a_id: int = 0
user_b_id: int = 0
message_id: int = 0


def _signup_and_login(email: str, password: str) -> str:
    r = client.post("/player/signup", json={"email": email, "password": password, "name": email.split("@")[0]})
    assert r.status_code == 200, r.text
    token = r.json()["verification_token"]
    client.post("/player/verify-email", json={"email": email, "token": token})
    r2 = client.post("/player/login", json={"email": email, "password": password})
    assert r2.status_code == 200, r2.text
    return r2.json()["access_token"]


def test_setup():
    global token_a, token_b, token_c, user_a_id, user_b_id
    token_a = _signup_and_login(EMAIL_A, PASS_A)
    token_b = _signup_and_login(EMAIL_B, PASS_B)
    token_c = _signup_and_login(EMAIL_C, PASS_C)
    user_a_id = db.get_user_by_identifier(EMAIL_A).id
    user_b_id = db.get_user_by_identifier(EMAIL_B).id


def test_send_message_requires_friendship():
    """Cannot send a message to a non-friend."""
    r = client.post(
        "/messages/send",
        json={"recipient_id": user_b_id, "body": "Hello!"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 403, r.text
    assert "friend" in r.json()["detail"].lower()


def test_send_message_after_becoming_friends():
    """Can send a message once friendship is accepted."""
    global message_id

    # Make A and B friends
    db.send_friend_request(EMAIL_A, EMAIL_B)
    db.accept_friend_request(EMAIL_B, EMAIL_A)

    r = client.post(
        "/messages/send",
        json={"recipient_id": user_b_id, "body": "Hey Bob!"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 200, r.text
    msg = r.json()["message"]
    assert msg["body"] == "Hey Bob!"
    assert msg["sender_id"] == user_a_id
    assert msg["recipient_id"] == user_b_id
    assert msg["read"] is False
    message_id = msg["id"]


def test_inbox_contains_message():
    """B's inbox should contain A's message."""
    r = client.get("/messages/inbox", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200, r.text
    data = r.json()
    bodies = [m["body"] for m in data["messages"]]
    assert "Hey Bob!" in bodies
    assert data["unread"] >= 1


def test_inbox_empty_for_sender():
    """A's inbox should not contain the message (it's in sent)."""
    r = client.get("/messages/inbox", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200
    bodies = [m["body"] for m in r.json()["messages"]]
    assert "Hey Bob!" not in bodies


def test_sent_contains_message():
    """A's sent box should contain the message."""
    r = client.get("/messages/sent", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200
    bodies = [m["body"] for m in r.json()["messages"]]
    assert "Hey Bob!" in bodies


def test_mark_read():
    """Marking the message as read should work for the recipient."""
    r = client.post(f"/messages/{message_id}/read", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200, r.text
    assert r.json()["read"] is True


def test_mark_read_wrong_user_404():
    """Sender cannot mark the message as read (they are not the recipient)."""
    r = client.post(f"/messages/{message_id}/read", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 404


def test_send_message_to_self_400():
    r = client.post(
        "/messages/send",
        json={"recipient_id": user_a_id, "body": "Talking to myself"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 400


def test_delete_message():
    """Sender or recipient can delete the message."""
    r = client.delete(f"/messages/{message_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True


def test_send_blocked_user_rejected():
    """A blocks C before they are friends — even if C tries to send, it should fail."""
    user_c_id = db.get_user_by_identifier(EMAIL_C).id
    db.block_user(blocker_id=user_a_id, blocked_id=user_c_id)
    # Make them friends first to bypass the friendship check
    db.send_friend_request(EMAIL_A, EMAIL_C)
    db.accept_friend_request(EMAIL_C, EMAIL_A)
    r = client.post(
        "/messages/send",
        json={"recipient_id": user_a_id, "body": "Hi Alice"},
        headers={"Authorization": f"Bearer {token_c}"},
    )
    assert r.status_code == 403, r.text
    assert "block" in r.json()["detail"].lower()
