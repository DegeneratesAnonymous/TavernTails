from __future__ import annotations

import json
from pathlib import Path

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
    assert user.verification_token
    db.verify_user(email, user.verification_token)


def test_session_bootstrap_writes_scene_file():
    client = _client()
    owner = "bootstrap-owner@example.com"
    _ensure_user(owner)

    sid, _meta = sessions_module.create_session_folder("Bootstrap Session", owner)

    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(f"/sessions/{sid}/bootstrap", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    scene = body["scene"]
    assert scene["id"] == "opening"
    assert isinstance(scene["text"], str)
    assert isinstance(scene["choices"], list)
    assert len(scene["choices"]) >= 2

    scene_path = Path(sessions_module.BASE) / sid / "scene.json"
    assert scene_path.exists()
    parsed = json.loads(scene_path.read_text())
    assert parsed["id"] == "opening"

    # Suggestions should be available even without chat messages, via scene fallback.
    sugg = client.get(f"/suggestions?session_id={sid}", headers=headers)
    assert sugg.status_code == 200, sugg.text
    sugg_body = sugg.json()
    assert sugg_body["session_id"] == sid
    assert isinstance(sugg_body["suggestions"], list)
    assert len(sugg_body["suggestions"]) >= 1


def test_content_advance_persists_next_scene():
    client = _client()
    owner = "advance-owner@example.com"
    _ensure_user(owner)

    sid, _meta = sessions_module.create_session_folder("Advance Session", owner)

    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    # Ensure we have an opening scene
    resp = client.post(f"/sessions/{sid}/bootstrap", headers=headers, json={})
    assert resp.status_code == 200, resp.text

    advance = client.post(
        "/content/advance",
        headers=headers,
        json={"sceneId": "opening", "choiceId": "investigate", "sessionId": sid},
    )
    assert advance.status_code == 200, advance.text
    data = advance.json()
    assert "narration" in data
    assert data["nextScene"] is not None
    assert isinstance(data["nextScene"].get("text"), str)

    scene_path = Path(sessions_module.BASE) / sid / "scene.json"
    parsed = json.loads(scene_path.read_text())
    assert parsed["id"].startswith("scene-")
    assert "Investigate" in parsed["text"] or "investigate" in parsed["text"].lower()
