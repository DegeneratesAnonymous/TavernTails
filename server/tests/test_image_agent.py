"""Tests for the image agent — caching and gallery endpoints."""

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents import sessions as sessions_module
from server.auth import create_access_token


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


def _client_and_headers():
    email = "image-test@example.com"
    _ensure_user(email)
    client = TestClient(main.app)
    headers = {"Authorization": f"Bearer {create_access_token(email)}"}
    return client, headers


def test_generate_no_session():
    """Generate without session_id returns a response but does not cache."""
    client, headers = _client_and_headers()
    resp = client.post("/image/generate", json={"prompt": "A dark tower", "style": "comic"}, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["image_url"].startswith("https://placeholder.image/")
    assert data["cached"] is False
    assert "id" in data
    assert "generated_at" in data


def test_generate_with_session_is_cached_on_repeat(tmp_path):
    """Generating the same prompt+style twice for a session returns cached=True the second time."""
    client, headers = _client_and_headers()
    owner = "image-session-host@example.com"
    _ensure_user(owner)
    session_id, _ = sessions_module.create_session_folder("Image Cache Test", owner)

    payload = {"prompt": "Goblin ambush at dusk", "style": "watercolour", "session_id": session_id}

    resp1 = client.post("/image/generate", json=payload, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["cached"] is False

    resp2 = client.post("/image/generate", json=payload, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["cached"] is True
    assert data2["id"] == data1["id"]
    assert data2["image_url"] == data1["image_url"]


def test_gallery_contains_generated_images():
    """Gallery endpoint returns images generated for the session."""
    client, headers = _client_and_headers()
    owner = "image-gallery-host@example.com"
    _ensure_user(owner)
    session_id, _ = sessions_module.create_session_folder("Image Gallery Test", owner)

    prompts = ["Dragon over the keep", "Haunted crypt entrance"]
    for prompt in prompts:
        resp = client.post(
            "/image/generate", json={"prompt": prompt, "style": "realistic", "session_id": session_id}, headers=headers
        )
        assert resp.status_code == 200

    gallery = client.get(f"/image/gallery/{session_id}", headers=headers)
    assert gallery.status_code == 200, gallery.text
    data = gallery.json()
    assert data["session_id"] == session_id
    gallery_prompts = [img["prompt"] for img in data["images"]]
    for prompt in prompts:
        assert prompt in gallery_prompts


def test_gallery_empty_session():
    """Gallery for a session with no images returns an empty list."""
    client, headers = _client_and_headers()
    owner = "image-empty-host@example.com"
    _ensure_user(owner)
    session_id, _ = sessions_module.create_session_folder("Empty Gallery Session", owner)

    gallery = client.get(f"/image/gallery/{session_id}", headers=headers)
    assert gallery.status_code == 200
    assert gallery.json()["images"] == []


def test_different_styles_not_cached_as_same():
    """Different styles for the same prompt generate distinct cache entries."""
    client, headers = _client_and_headers()
    owner = "image-style-host@example.com"
    _ensure_user(owner)
    session_id, _ = sessions_module.create_session_folder("Style Distinction Test", owner)

    prompt = "Bridge battle at midnight"
    resp_a = client.post(
        "/image/generate", json={"prompt": prompt, "style": "comic", "session_id": session_id}, headers=headers
    )
    resp_b = client.post(
        "/image/generate", json={"prompt": prompt, "style": "watercolour", "session_id": session_id}, headers=headers
    )
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    assert resp_a.json()["id"] != resp_b.json()["id"]


def test_clear_gallery():
    """DELETE /image/gallery/{session_id} empties the gallery."""
    client, headers = _client_and_headers()
    owner = "image-clear-host@example.com"
    _ensure_user(owner)
    session_id, _ = sessions_module.create_session_folder("Clear Gallery Session", owner)

    client.post(
        "/image/generate", json={"prompt": "Something to delete", "style": "realistic", "session_id": session_id},
        headers=headers,
    )

    delete = client.delete(f"/image/gallery/{session_id}", headers=headers)
    assert delete.status_code == 204

    gallery = client.get(f"/image/gallery/{session_id}", headers=headers)
    assert gallery.json()["images"] == []
