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


def _auth(email: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(email)}"}


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
    # The deterministic narration prefix for the "investigate" choice is always present
    assert "You follow the strongest lead" in parsed["text"]


def test_player_run_mode_bootstrap_skips_ai():
    client = _client()
    owner = "bootstrap-player-run@example.com"
    _ensure_user(owner)

    campaign = db.create_campaign(owner_id=db.get_user_by_identifier(owner).id, name="Player Run Campaign")
    db.set_campaign_settings(campaign.id, campaign.owner_id, {"player_run_mode": True})

    sid, _meta = sessions_module.create_session_folder("Player Run Session", owner, campaign_id=campaign.id)

    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(f"/sessions/{sid}/bootstrap", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    scene = body["scene"]
    assert "Player-run mode" in scene["text"]


def test_start_session_uses_campaign_contract_not_wayward_lantern_fallback():
    client = _client()
    owner = "bootstrap-contract-start@example.com"
    _ensure_user(owner)
    user = db.get_user_by_identifier(owner)
    assert user and user.id is not None

    campaign = db.create_campaign(
        owner_id=user.id,
        name="Stars Over Glass Harbor",
        description="A political sci-fi mystery about smugglers, missing diplomats, and an orbital harbor.",
    )
    assert campaign.id is not None
    db.set_campaign_settings(campaign.id, user.id, {
        "genre": "sci-fi mystery",
        "tone": "political thriller",
        "setting_summary": "Glass Harbor is an orbital trade station full of sabotage and faction intrigue.",
        "world_name": "Glass Harbor",
        "ruleset": "starfinder",
        "starting_level": 3,
        "creation_posture": "guided_builder",
    })
    sid, _meta = sessions_module.create_session_folder(campaign.name, owner, campaign_id=campaign.id)

    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(f"/sessions/{sid}/start", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    scene = resp.json()["scene"]
    scene_blob = json.dumps(scene).lower()

    assert scene["location"] == "Glass Harbor"
    assert "glass harbor" in scene_blob
    assert "wayward" not in scene_blob
    assert "torven" not in scene_blob
    assert "mara vell" not in scene_blob
    assert "cracked lantern" not in scene_blob
    assert "harness leather" not in scene_blob
    assert "fantasy environment art" not in scene_blob


def test_start_session_uses_create_description_for_opening_premise():
    client = _client()
    owner = "bootstrap-northern-march@example.com"
    _ensure_user(owner)

    description = (
        "Apart of a slave army - you've been marching north for months. "
        "You've found an opportunity to escape and you've taken it and seem to have slipped away "
        "entirely unnoticed. Having hidden out in the woods for weeks with no sign of pursuit."
    )
    create = client.post(
        "/campaigns",
        headers=_auth(owner),
        json={
            "name": "Northern March",
            "description": description,
            "create_session": True,
            "preferences": {
                "genre": "fantasy",
                "tone": "balanced",
                "setting_summary": description,
            },
        },
    )
    assert create.status_code == 201, create.text
    campaign = create.json()["campaign"]
    sid = str(campaign["sessions"][0]["id"])

    resp = client.post(f"/sessions/{sid}/start", headers=_auth(owner), json={})
    assert resp.status_code == 200, resp.text
    scene = resp.json()["scene"]
    scene_blob = json.dumps(scene).lower()

    assert scene["location"] == "The Northwood Hiding Place"
    assert "northwood" in scene_blob
    assert any(term in scene_blob for term in ("escape", "pursuit", "army", "hiding"))
    assert "wayward" not in scene_blob
    assert "lantern inn" not in scene_blob
    assert "torven" not in scene_blob
    assert "cracked lantern" not in scene_blob


def test_player_run_mode_content_advance_skips_ai():
    client = _client()
    owner = "advance-player-run@example.com"
    _ensure_user(owner)

    campaign = db.create_campaign(owner_id=db.get_user_by_identifier(owner).id, name="Player Run Campaign 2")
    db.set_campaign_settings(campaign.id, campaign.owner_id, {"player_run_mode": True})

    sid, _meta = sessions_module.create_session_folder("Player Run Advance", owner, campaign_id=campaign.id)

    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(f"/sessions/{sid}/bootstrap", headers=headers, json={})
    assert resp.status_code == 200, resp.text

    advance = client.post(
        "/content/advance",
        headers=headers,
        json={"sceneId": "opening", "choiceId": "investigate", "sessionId": sid},
    )
    assert advance.status_code == 200, advance.text
    data = advance.json()
    next_scene = data["nextScene"]
    assert next_scene is not None
    assert "You follow the strongest lead" in next_scene.get("text", "")
    assert "Paths branch ahead" not in next_scene.get("text", "")
