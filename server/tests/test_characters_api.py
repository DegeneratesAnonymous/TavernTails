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


def test_characters_update_allows_owner_changes():
    client = _client()
    owner = "chars-update-owner@example.com"
    _ensure_user(owner)

    owner_token = create_access_token(owner)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    resp_create = client.post(
        "/characters",
        headers=owner_headers,
        json={"name": "Update Me", "level": 1, "class_name": "Fighter"},
    )
    assert resp_create.status_code == 201, resp_create.text
    created = resp_create.json()["character"]
    created_id = created["id"]

    update_payload = {
        "name": "Updated Name",
        "level": 4,
        "class_name": "Rogue",
        "sheet": {"ac": 15, "hp": {"current": 20, "max": 20}},
    }
    resp_update = client.put(
        f"/characters/{created_id}",
        headers=owner_headers,
        json=update_payload,
    )
    assert resp_update.status_code == 200, resp_update.text
    updated = resp_update.json()["character"]
    assert updated["name"] == "Updated Name"
    assert updated["level"] == 4
    assert updated["class_name"] == "Rogue"
    assert updated["sheet"]["ac"] == 15

    resp_get = client.get(f"/characters/{created_id}", headers=owner_headers)
    assert resp_get.status_code == 200, resp_get.text
    body = resp_get.json()["character"]
    assert body["name"] == "Updated Name"
    assert body["level"] == 4


def test_characters_update_requires_ownership():
    client = _client()
    owner = "chars-update-owner2@example.com"
    other = "chars-update-other@example.com"
    _ensure_user(owner)
    _ensure_user(other)

    owner_token = create_access_token(owner)
    other_token = create_access_token(other)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    resp_create = client.post(
        "/characters",
        headers=owner_headers,
        json={"name": "Owner Character", "level": 2, "class_name": "Wizard"},
    )
    assert resp_create.status_code == 201, resp_create.text
    created_id = resp_create.json()["character"]["id"]

    resp_update_other = client.put(
        f"/characters/{created_id}",
        headers=other_headers,
        json={"name": "Hacked", "level": 5},
    )
    assert resp_update_other.status_code == 404, resp_update_other.text


def test_character_delete_unassigns_from_session():
    """Deleting a character automatically removes it from active sessions."""
    import json
    import pathlib
    import uuid

    client = _client()
    owner = "chars-delete-active@example.com"
    _ensure_user(owner)

    owner_token = create_access_token(owner)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # Create a character
    resp = client.post(
        "/characters",
        headers=owner_headers,
        json={"name": "Active Hero", "level": 1, "class_name": "Fighter"},
    )
    assert resp.status_code == 201, resp.text
    char_id = resp.json()["character"]["id"]

    # Simulate the character being active in a session by writing a meta.json
    sessions_base = pathlib.Path(__file__).resolve().parents[1] / "sessions"
    sessions_base.mkdir(exist_ok=True)
    fake_session_id = f"test-{uuid.uuid4().hex[:6]}"
    fake_session_dir = sessions_base / fake_session_id
    fake_session_dir.mkdir()
    meta = {
        "id": fake_session_id,
        "name": "Test Session",
        "owner": owner,
        "members": [{"email": owner, "character_id": char_id, "role": "owner"}],
    }
    (fake_session_dir / "meta.json").write_text(json.dumps(meta))

    try:
        # Deletion should now succeed — character is unassigned from sessions first
        resp_delete = client.delete(f"/characters/{char_id}", headers=owner_headers)
        assert resp_delete.status_code == 200, resp_delete.text
        assert resp_delete.json().get("ok") is True

        # The session meta should have the character_id cleared
        updated_meta = json.loads((fake_session_dir / "meta.json").read_text())
        assert updated_meta["members"][0]["character_id"] is None
    finally:
        import shutil
        shutil.rmtree(fake_session_dir, ignore_errors=True)
