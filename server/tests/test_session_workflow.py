"""Tests for the New Session and Returning Session workflow orchestration endpoints."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents import sessions as sessions_module
from server.agents import simulation as simulation_agent
from server.agents.scene_validator import validate_scene_quality
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
    assert isinstance(parsed["current_situation"], dict)
    assert parsed["current_situation"]["current_objective"]
    assert "[Character:" not in parsed["current_situation"]["current_objective"]
    assert isinstance(parsed["world_moves"], list)
    assert len(parsed["world_moves"]) >= 2
    assert parsed["experience_mode"]


def test_scene_presentation_repairs_generic_prompt_for_active_player():
    scene = {
        "narrative_body": "Torvin drops a cracked lantern on the table.",
        "player_prompt": "What does the party do?",
        "active_player": "Arin Quickstep",
        "location": "The Wayward Lantern Inn",
    }

    normalized = simulation_agent.normalize_scene_presentation(
        scene,
        simulation_agent.default_world_state(),
        {},
    )

    assert normalized["player_prompt"] == "What does Arin Quickstep do?"
    assert normalized["text"].endswith("What does Arin Quickstep do?")


def test_scene_validator_rejects_placeholder_narrative():
    score, issues = validate_scene_quality(
        "At The Wayward Lantern Inn, the moment holds — waiting for what comes next.\n\nWhat does Yungmin do?",
        location_name="The Wayward Lantern Inn",
        player_name="Yungmin",
    )

    assert score == 0
    assert any("Placeholder narrative" in issue for issue in issues)


def test_action_response_scene_uses_latest_action():
    response = sessions_module._action_response_scene(
        player_name="Yungmin",
        location_name="The Wayward Lantern Inn",
        latest_action="I cast Detect Magic on the cracked lantern.",
        action_count=1,
    )

    assert "Yungmin" in response["narrative"]
    assert "blue-white thread" in response["narrative"]
    assert "arcane" in response["objective"].lower()
    assert response["suggested_actions"]


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
    assert parsed["scene_templates"]
    assert parsed["simulation_delta"]["time_changes"]
    assert isinstance(parsed["current_situation"], dict)
    assert parsed["current_situation"]["current_objective"]
    assert "[Character:" not in parsed["current_situation"]["current_objective"]
    assert isinstance(parsed["world_clock"], dict)
    assert parsed["world_clock"]["campaign_day"] >= 1
    assert parsed["experience_mode"]
    assert isinstance(parsed["memory_updates"], dict)
    assert isinstance(parsed["image"], dict)

    folder = Path(sessions_module.BASE) / sid
    assert (folder / "world_state.json").exists()
    assert (folder / "last_simulation_delta.json").exists()
    assert (folder / "last_memory_delta.json").exists()
    assert (folder / "canon_memory.json").exists()

    world_state = json.loads((folder / "world_state.json").read_text())
    assert world_state["campaign_day"] >= 1
    assert world_state["time_of_day"]
    assert world_state["weather"]


def test_advance_scene_active_lock_returns_generation_status():
    client = _client()
    owner = "advance-scene-lock-owner@example.com"
    _ensure_user(owner)
    sid, _ = sessions_module.create_session_folder("Advance Scene Lock Test", owner)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    folder = Path(sessions_module.BASE) / sid
    active_lock = {
        "generation_id": "existing-generation",
        "session_id": sid,
        "status": "running",
        "started_at": "2099-01-01T00:00:00+00:00",
        "expires_at": "2099-01-01T00:10:00+00:00",
    }
    (folder / "advance_scene_lock.json").write_text(json.dumps(active_lock))

    resp = client.post(f"/sessions/{sid}/advance-scene", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["generation"]["generation_id"] == "existing-generation"
    assert body["status"] == "running"


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


# ---------------------------------------------------------------------------
# CampaignSettings typed model — agent data flow
# ---------------------------------------------------------------------------

def test_campaign_settings_typed_fields_roundtrip():
    """PUT /campaigns/{id}/settings accepts and persists all agent-relevant typed fields."""
    client = _client()
    owner = "settings-typed-owner@example.com"
    _ensure_user(owner)
    user = db.get_user_by_identifier(owner)
    campaign = db.create_campaign(owner_id=user.id, name="Typed Settings Campaign")
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    payload = {
        "genre": "horror",
        "tone": "gritty realism",
        "setting_summary": "A crumbling Victorian city haunted by ancient evils.",
        "world_name": "Grimhaven",
        "ruleset": "Call of Cthulhu 7e",
        "starting_level": 1,
        "house_rules": "Sanity loss is doubled.",
        "player_run_mode": False,
    }
    put = client.put(f"/campaigns/{campaign.id}/settings", headers=headers, json=payload)
    assert put.status_code == 200, put.text
    settings = put.json()["settings"]
    assert settings["genre"] == "horror"
    assert settings["tone"] == "gritty realism"
    assert settings["setting_summary"] == "A crumbling Victorian city haunted by ancient evils."
    assert settings["world_name"] == "Grimhaven"
    assert settings["ruleset"] == "Call of Cthulhu 7e"
    assert settings["starting_level"] == 1
    assert settings["house_rules"] == "Sanity loss is doubled."
    assert settings["player_run_mode"] is False

    get = client.get(f"/campaigns/{campaign.id}/settings", headers=headers)
    assert get.status_code == 200
    assert get.json()["settings"]["genre"] == "horror"


def test_campaign_settings_extra_fields_preserved():
    """Extra/custom fields beyond the typed schema are still persisted (backward compat)."""
    client = _client()
    owner = "settings-extra-owner@example.com"
    _ensure_user(owner)
    user = db.get_user_by_identifier(owner)
    campaign = db.create_campaign(owner_id=user.id, name="Extra Fields Campaign")
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    payload = {"world_name": "Eldervale", "custom_key": "custom_value", "starting_level": 3}
    put = client.put(f"/campaigns/{campaign.id}/settings", headers=headers, json=payload)
    assert put.status_code == 200, put.text
    settings = put.json()["settings"]
    assert settings["world_name"] == "Eldervale"
    assert settings["custom_key"] == "custom_value"
    assert settings["starting_level"] == 3


def test_storyboard_variables_themes_become_hooks():
    """Campaign variables themes flow into storyboard hooks."""
    client = _client()
    resp = client.post("/storyboard/generate", json={
        "players": ["Theron"],
        "campaign_settings": {"genre": "western", "world_name": "Dustfield"},
        "campaign_variables": {
            "themes": ["revenge", "survival"],
            "narrative_style": "gritty realism",
            "pacing": "fast",
        },
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # themes from campaign_variables must appear as hooks
    assert "revenge" in data["hooks"]
    assert "survival" in data["hooks"]
    # genre and world_name appear in the plot
    assert "western" in data["plot"]
    assert "Dustfield" in data["plot"]
    # narrative_style is used as tone
    assert "gritty realism" in data["plot"]


def test_storyboard_variables_factions_appear_in_plot():
    """Faction goals from campaign variables are woven into the plot text."""
    client = _client()
    resp = client.post("/storyboard/generate", json={
        "campaign_variables": {
            "factions": [
                {
                    "name": "Iron Council",
                    "alignment": "lawful evil",
                    "goals": ["seize the mines"],
                    "members": ["Warden Krix"],
                }
            ],
        },
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "Iron Council" in data["plot"]
    # Faction goal must also appear in the plot
    assert "seize the mines" in data["plot"]
    # Faction member should appear in npcs_mentioned
    assert "Warden Krix" in data["npcs_mentioned"]


def test_storyboard_variables_tone_fallback():
    """narrative_style from campaign_variables is used as tone when settings.tone is absent."""
    client = _client()
    resp = client.post("/storyboard/generate", json={
        "campaign_settings": {"genre": "fantasy"},
        "campaign_variables": {"narrative_style": "cinematic heroism"},
    })
    assert resp.status_code == 200, resp.text
    assert "cinematic heroism" in resp.json()["plot"]


def test_start_session_reads_campaign_variables():
    """start_session derives narrative style from campaign variables and passes it to storyboard."""
    client = _client()
    owner = "start-vars-owner@example.com"
    _ensure_user(owner)
    user = db.get_user_by_identifier(owner)
    campaign = db.create_campaign(owner_id=user.id, name="Variables Session Campaign")

    # Set campaign settings + variables
    db.set_campaign_settings(campaign.id, campaign.owner_id, {
        "genre": "space opera",
        "tone": "cinematic heroism",
        "world_name": "Starfall Nexus",
    })
    db.set_campaign_variables(campaign.id, campaign.owner_id, {
        "themes": ["sacrifice", "exploration"],
        "narrative_style": "cinematic heroism",
        "factions": [
            {"name": "Void Syndicate", "goals": ["control the jump gates"], "members": ["Admiral Ryn"]},
        ],
    })

    sid, _ = sessions_module.create_session_folder("Variables Session", owner, campaign_id=campaign.id)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    resp = client.post(f"/sessions/{sid}/start", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    # The plot and hooks from storyboard should include campaign context
    assert isinstance(body["hooks"], list)
    # Faction member Admiral Ryn should surface as an NPC profile
    npc_names = [p.get("name") for p in body["npc_profiles"]]
    assert "Admiral Ryn" in npc_names
