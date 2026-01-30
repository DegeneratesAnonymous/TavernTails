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
    db.verify_user(email, user.verification_token)


def test_characters_create_list_delete_and_isolation():
    client = _client()
    owner = "chars-owner@example.com"
    other = "chars-other@example.com"
    _ensure_user(owner)
    _ensure_user(other)

    owner_token = create_access_token(owner)
    other_token = create_access_token(other)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # Other user creates a character (should not show up for owner)
    resp_other_create = client.post(
        "/characters",
        headers=other_headers,
        json={"name": "Other Guy", "level": 2, "class_name": "Rogue"},
    )
    assert resp_other_create.status_code == 201, resp_other_create.text

    # Owner creates a character
    resp_create = client.post(
        "/characters",
        headers=owner_headers,
        json={"name": "Owner Hero", "level": 3, "class_name": "Fighter"},
    )
    assert resp_create.status_code == 201, resp_create.text
    created = resp_create.json().get("character")
    assert created and isinstance(created.get("id"), int)
    created_id = created["id"]

    # Owner lists characters, should include only owner's char
    resp_list = client.get("/characters", headers=owner_headers)
    assert resp_list.status_code == 200, resp_list.text
    chars = resp_list.json().get("characters")
    assert isinstance(chars, list)
    assert any(c.get("id") == created_id for c in chars)
    assert all(c.get("name") != "Other Guy" for c in chars)

    # Owner can delete their own character
    resp_delete = client.delete(f"/characters/{created_id}", headers=owner_headers)
    assert resp_delete.status_code == 200, resp_delete.text
    assert resp_delete.json().get("ok") is True

    # Owner deleting other user's character should 404
    other_created_id = resp_other_create.json()["character"]["id"]
    resp_delete_other = client.delete(f"/characters/{other_created_id}", headers=owner_headers)
    assert resp_delete_other.status_code == 404, resp_delete_other.text


def test_characters_get_requires_ownership():
    client = _client()
    owner = "chars-get-owner@example.com"
    other = "chars-get-other@example.com"
    _ensure_user(owner)
    _ensure_user(other)

    owner_token = create_access_token(owner)
    other_token = create_access_token(other)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    resp_create = client.post(
        "/characters",
        headers=owner_headers,
        json={"name": "Owner Sheet", "level": 2, "class_name": "Wizard", "sheet": {"import": {"source": "test"}}},
    )
    assert resp_create.status_code == 201, resp_create.text
    created_id = resp_create.json()["character"]["id"]

    resp_get_owner = client.get(f"/characters/{created_id}", headers=owner_headers)
    assert resp_get_owner.status_code == 200, resp_get_owner.text
    body = resp_get_owner.json().get("character")
    assert body and body.get("id") == created_id
    assert body.get("name") == "Owner Sheet"

    resp_get_other = client.get(f"/characters/{created_id}", headers=other_headers)
    assert resp_get_other.status_code == 404, resp_get_other.text
