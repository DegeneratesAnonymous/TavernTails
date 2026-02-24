"""Tests for the New Session and Returning Session workflow orchestration endpoints."""

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


# ---------------------------------------------------------------------------
# /storyboard/generate
# ---------------------------------------------------------------------------

def test_storyboard_generate_basic():
    client = _client()
    resp = client.post("/storyboard/generate", json={
        "players": ["Aria", "Brom"],
        "campaign_settings": {"genre": "dark fantasy", "tone": "gritty realism"},
        "campaign_docs": ["The city of Ashenvale has long been ruled by shadow."],
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "plot" in data
    assert isinstance(data["plot"], str)
    assert "dark fantasy" in data["plot"]
    assert isinstance(data["hooks"], list)
    assert len(data["hooks"]) >= 1
    assert isinstance(data["npcs_mentioned"], list)


def test_storyboard_generate_defaults():
    """generate_plot works with no inputs (all defaults)."""
    client = _client()
    resp = client.post("/storyboard/generate", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["plot"]
    assert isinstance(data["hooks"], list)


def test_storyboard_generate_npc_extraction():
    """NPCs mentioned via 'NPC:' prefix in campaign docs are extracted."""
    client = _client()
    resp = client.post("/storyboard/generate", json={
        "campaign_docs": ["NPC: Lord Vex, the tyrant king."],
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "Lord Vex" in data["npcs_mentioned"]


# ---------------------------------------------------------------------------
# /sessions/{session_id}/start  (New Session Workflow)
# ---------------------------------------------------------------------------

def test_start_session_creates_opening_scene():
    client = _client()
    owner = "start-session-owner@example.com"
    _ensure_user(owner)
    sid, _ = sessions_module.create_session_folder("Start Session Test", owner)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    resp = client.post(f"/sessions/{sid}/start", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert isinstance(body["scene"]["text"], str)
    assert isinstance(body["hooks"], list)
    assert isinstance(body["dice_rolls"], list)
    assert isinstance(body["npc_profiles"], list)

    # scene.json must be written
    scene_path = Path(sessions_module.BASE) / sid / "scene.json"
    assert scene_path.exists()
    parsed = json.loads(scene_path.read_text())
    assert parsed["id"] == "opening"


def test_start_session_player_run_skips_ai():
    client = _client()
    owner = "start-player-run@example.com"
    _ensure_user(owner)
    campaign = db.create_campaign(owner_id=db.get_user_by_identifier(owner).id, name="PR Campaign Start")
    db.set_campaign_settings(campaign.id, campaign.owner_id, {"player_run_mode": True})
    sid, _ = sessions_module.create_session_folder("Player Run Start", owner, campaign_id=campaign.id)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    resp = client.post(f"/sessions/{sid}/start", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "Player-run mode" in body["scene"]["text"]


def test_start_session_non_member_forbidden():
    client = _client()
    owner = "start-owner-forbidden@example.com"
    _ensure_user(owner)
    other = "start-other-forbidden@example.com"
    _ensure_user(other)
    sid, _ = sessions_module.create_session_folder("Forbidden Start", owner)
    headers = {"Authorization": f"Bearer {create_access_token(other)}"}

    resp = client.post(f"/sessions/{sid}/start", headers=headers, json={})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# /sessions/{session_id}/player-ready  (Returning Session, Step 1)
# ---------------------------------------------------------------------------

def test_player_ready_marks_single_member():
    client = _client()
    owner = "player-ready-owner@example.com"
    _ensure_user(owner)
    sid, _ = sessions_module.create_session_folder("Player Ready Test", owner)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    resp = client.post(f"/sessions/{sid}/player-ready", headers=headers, json={"done": True})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["done"] is True
    # Single-member session → owner is the only member → all_ready should be True
    assert body["all_ready"] is True


def test_player_ready_not_all_ready_until_everyone_done():
    client = _client()
    owner = "ready-owner2@example.com"
    invitee = "ready-invitee2@example.com"
    _ensure_user(owner)
    _ensure_user(invitee)
    sid, _ = sessions_module.create_session_folder("Multi-Player Ready", owner)
    # Register invitee as a member manually via meta
    meta_path = Path(sessions_module.BASE) / sid / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["members"].append({"email": invitee, "role": "member"})
    meta_path.write_text(json.dumps(meta))

    owner_headers = {"Authorization": f"Bearer {create_access_token(owner)}"}
    invitee_headers = {"Authorization": f"Bearer {create_access_token(invitee)}"}

    # Owner marks ready
    r1 = client.post(f"/sessions/{sid}/player-ready", headers=owner_headers, json={"done": True})
    assert r1.status_code == 200
    assert r1.json()["all_ready"] is False  # invitee not yet done

    # Invitee marks ready
    r2 = client.post(f"/sessions/{sid}/player-ready", headers=invitee_headers, json={"done": True})
    assert r2.status_code == 200
    assert r2.json()["all_ready"] is True


def test_player_ready_non_member_forbidden():
    client = _client()
    owner = "ready-forbidden-owner@example.com"
    _ensure_user(owner)
    other = "ready-forbidden-other@example.com"
    _ensure_user(other)
    sid, _ = sessions_module.create_session_folder("Ready Forbidden", owner)
    headers = {"Authorization": f"Bearer {create_access_token(other)}"}

    resp = client.post(f"/sessions/{sid}/player-ready", headers=headers, json={"done": True})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# /sessions/{session_id}/advance-scene  (Returning Session, Steps 2–5)
# ---------------------------------------------------------------------------

def test_advance_scene_creates_new_scene():
    client = _client()
    owner = "advance-scene-owner@example.com"
    _ensure_user(owner)
    sid, _ = sessions_module.create_session_folder("Advance Scene Test", owner)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    # Bootstrap first so scene.json exists
    client.post(f"/sessions/{sid}/bootstrap", headers=headers, json={})

    # Post a player message to give the advance endpoint something to work with
    client.post("/chat", headers=headers, json={
        "message": "I search for traps near the door",
        "session_id": sid,
        "role": "player",
    })

    resp = client.post(f"/sessions/{sid}/advance-scene", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert isinstance(body["scene"]["text"], str)
    assert isinstance(body["dice_rolls"], list)

    scene_path = Path(sessions_module.BASE) / sid / "scene.json"
    parsed = json.loads(scene_path.read_text())
    assert parsed["id"].startswith("scene-")


def test_advance_scene_player_run_mode_rejected():
    client = _client()
    owner = "advance-scene-pr@example.com"
    _ensure_user(owner)
    campaign = db.create_campaign(owner_id=db.get_user_by_identifier(owner).id, name="PR Advance")
    db.set_campaign_settings(campaign.id, campaign.owner_id, {"player_run_mode": True})
    sid, _ = sessions_module.create_session_folder("PR Advance Session", owner, campaign_id=campaign.id)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    resp = client.post(f"/sessions/{sid}/advance-scene", headers=headers, json={})
    assert resp.status_code == 400


def test_advance_scene_non_member_forbidden():
    client = _client()
    owner = "advance-scene-forbidden-owner@example.com"
    _ensure_user(owner)
    other = "advance-scene-forbidden-other@example.com"
    _ensure_user(other)
    sid, _ = sessions_module.create_session_folder("Advance Forbidden", owner)
    headers = {"Authorization": f"Bearer {create_access_token(other)}"}

    resp = client.post(f"/sessions/{sid}/advance-scene", headers=headers, json={})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# @GM mention in chat
# ---------------------------------------------------------------------------

def test_gm_mention_triggers_gm_response():
    client = _client()
    owner = "gm-mention-owner@example.com"
    _ensure_user(owner)
    sid, _ = sessions_module.create_session_folder("GM Mention Test", owner)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    resp = client.post("/chat", headers=headers, json={
        "message": "@GM can I pick the lock?",
        "session_id": sid,
        "role": "player",
    })
    assert resp.status_code == 201, resp.text

    # Retrieve chat — there should be a gm-role response following the player message
    msgs = client.get(f"/chat?session_id={sid}", headers=headers)
    assert msgs.status_code == 200
    roles = [m["role"] for m in msgs.json()]
    assert "gm" in roles, f"Expected a 'gm' role message, got roles: {roles}"

    gm_msg = next(m for m in msgs.json() if m["role"] == "gm")
    assert gm_msg["message"].startswith("[GM]")


def test_no_gm_response_without_mention():
    client = _client()
    owner = "no-gm-mention-owner@example.com"
    _ensure_user(owner)
    sid, _ = sessions_module.create_session_folder("No GM Mention", owner)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    resp = client.post("/chat", headers=headers, json={
        "message": "I move towards the door.",
        "session_id": sid,
        "role": "player",
    })
    assert resp.status_code == 201

    msgs = client.get(f"/chat?session_id={sid}", headers=headers)
    assert msgs.status_code == 200
    roles = [m["role"] for m in msgs.json()]
    assert "gm" not in roles
