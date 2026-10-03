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


def test_get_scene_repairs_recycled_first_crossroads_fixture():
    client = _client()
    owner = "repair-recycled-opening@example.com"
    _ensure_user(owner)
    user = db.get_user_by_identifier(owner)
    assert user.id is not None
    campaign = db.create_campaign(
        owner_id=user.id,
        name="Salt, Steel, and Sorcery",
        description="A grim and grounded campaign where dangerous choices matter.",
    )
    db.set_campaign_metadata_keys(campaign.id, user.id, {
        "settings": {
            "genre": "fantasy",
            "tone": "grim",
            "setting_summary": "A dangerous salt-road frontier where rival houses hire steel to settle old debts.",
        },
        "campaign_contract": {
            "campaign_name": "Salt, Steel, and Sorcery",
            "campaign_pitch": "Mercenary survivors are drawn into a salt-road dispute between rival houses.",
        },
    })
    sid, _meta = sessions_module.create_session_folder("Salt, Steel, and Sorcery", owner, campaign_id=campaign.id)
    scene_path = Path(sessions_module.BASE) / sid / "scene.json"
    scene_path.write_text(json.dumps({
        "id": "opening",
        "title": "The First Crossroads",
        "text": "Mira Vale arrives visibly shaken with a sealed packet.",
        "narrative_body": "The air feels too still at The First Crossroads. Mira Vale carries a sealed packet.",
        "scene_director_data": {"source": "deterministic", "central_conflict": "[Campaign Contract]"},
    }))

    resp = client.get(f"/sessions/{sid}/file/scene.json", headers=_auth(owner))
    assert resp.status_code == 200, resp.text
    repaired = resp.json()
    repaired_text = json.dumps(repaired).lower()
    assert "first crossroads" not in repaired_text
    assert "mira vale" not in repaired_text
    assert "sealed packet" not in repaired_text
    assert repaired["scene_director_data"]["source"] == "recycled_fixture_repair"
    assert repaired.get("content_bundle", {}).get("content_gate_passed") is True


def test_get_scene_repairs_outer_court_deterministic_fixture():
    client = _client()
    owner = "repair-outer-court@example.com"
    _ensure_user(owner)
    user = db.get_user_by_identifier(owner)
    assert user and user.id is not None
    campaign = db.create_campaign(
        owner_id=user.id,
        name="Ashes of the Fallen Throne",
        description="A political fantasy campaign about a broken royal line and rival claimants.",
    )
    db.set_campaign_metadata_keys(campaign.id, user.id, {
        "settings": {
            "genre": "fantasy",
            "tone": "grim",
            "setting_summary": "A broken royal line leaves rival claimants fighting through spies, debts, and public ceremonies.",
        },
        "campaign_contract": {
            "campaign_name": "Ashes of the Fallen Throne",
            "campaign_pitch": "A fresh court intrigue about rival claimants and dangerous public loyalties.",
        },
    })
    sid, _meta = sessions_module.create_session_folder(campaign.name, owner, campaign_id=campaign.id)
    scene_path = Path(sessions_module.BASE) / sid / "scene.json"
    scene_path.write_text(json.dumps({
        "id": "opening",
        "title": "Opening — The Outer Court",
        "text": "Dry grit catches in the throat at The Outer Court; conversation falters as attention turns toward the same point of trouble.",
        "narrative_body": (
            "Envoy Marrec arrives visibly shaken, and sets down a scorched ledger page curled around a brass token. "
            "This was not supposed to reach us like this."
        ),
        "scene_director_data": {"source": "deterministic", "location": {"name": "The Outer Court"}},
    }))

    resp = client.get(f"/sessions/{sid}/file/scene.json", headers=_auth(owner))
    assert resp.status_code == 200, resp.text
    repaired = resp.json()
    repaired_text = json.dumps(repaired).lower()
    assert "the outer court" not in repaired_text
    assert "envoy marrec" not in repaired_text
    assert "conversation falters as attention turns toward the same point of trouble" not in repaired_text
    assert repaired["scene_director_data"]["source"] == "recycled_fixture_repair"
    assert repaired["location"] != {"name": "The Outer Court"}
    assert isinstance(repaired["location"], str)


def test_get_scene_repairs_docking_concourse_fixture_family():
    client = _client()
    owner = "repair-docking-concourse@example.com"
    _ensure_user(owner)
    user = db.get_user_by_identifier(owner)
    assert user and user.id is not None
    campaign = db.create_campaign(
        owner_id=user.id,
        name="Star Orchard",
        description="An orbital orchard mystery about gravity fruit, corporate guards, and a contested harvest.",
    )
    db.set_campaign_settings(campaign.id, user.id, {
        "genre": "science fantasy mystery",
        "tone": "tense",
        "setting_summary": "An orbital orchard where gravity fruit are failing before a corporate harvest.",
    })
    sid, _meta = sessions_module.create_session_folder(campaign.name, owner, campaign_id=campaign.id)
    scene_path = Path(sessions_module.BASE) / sid / "scene.json"
    scene_path.write_text(json.dumps({
        "id": "opening",
        "title": "The Docking Concourse",
        "text": (
            "The air is tense with held breath at The Docking Concourse; conversation falters as attention turns "
            "toward the same point of trouble. Quartermaster Vale arrives visibly shaken."
        ),
        "narrative_body": "Quartermaster Vale sets down a sealed packet. This was not supposed to reach us like this.",
        "scene_director_data": {"source": "deterministic", "location": {"name": "The Docking Concourse"}},
    }))

    resp = client.get(f"/sessions/{sid}/file/scene.json", headers=_auth(owner))
    assert resp.status_code == 200, resp.text
    repaired_blob = json.dumps(resp.json()).lower()
    assert "docking concourse" not in repaired_blob
    assert "quartermaster vale" not in repaired_blob
    assert "conversation falters as attention turns toward the same point of trouble" not in repaired_blob
    assert any(term in repaired_blob for term in ("orchard", "gravity fruit", "helix"))


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

    skip = client.post(f"/sessions/{sid}/opening-setup/skip", headers=_auth(owner))
    assert skip.status_code == 200, skip.text
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


def test_quickstart_setup_required_session_advances_to_real_scene():
    client = _client()
    owner = "bootstrap-quickstart-regression@example.com"
    _ensure_user(owner)

    description = (
        "A coastal clockwork mystery where a lighthouse lens sings at midnight, "
        "dock crews are blaming a retired artificer, and the first witness keeps changing their story."
    )
    create = client.post(
        "/campaigns",
        headers=_auth(owner),
        json={
            "name": "Quickstart Lens Regression",
            "description": description,
            "create_session": True,
            "preferences": {
                "genre": "clockwork mystery",
                "tone": "tense",
                "setting_summary": description,
            },
        },
    )
    assert create.status_code == 201, create.text
    sid = str(create.json()["campaign"]["sessions"][0]["id"])

    placeholder = client.get(f"/sessions/{sid}/file/scene.json", headers=_auth(owner))
    assert placeholder.status_code == 200, placeholder.text
    assert placeholder.json()["title"].endswith("Setup Pending")

    bootstrap = client.post(f"/sessions/{sid}/bootstrap", headers=_auth(owner), json={})
    assert bootstrap.status_code == 200, bootstrap.text
    assert bootstrap.json()["requires_opening_setup"] is True

    skip = client.post(f"/sessions/{sid}/opening-setup/skip", headers=_auth(owner))
    assert skip.status_code == 200, skip.text
    started = client.post(f"/sessions/{sid}/start", headers=_auth(owner), json={})
    assert started.status_code == 200, started.text

    scene = started.json()["scene"]
    scene_blob = json.dumps(scene).lower()
    assert not str(scene.get("title", "")).endswith("Setup Pending")
    assert "complete the campaign brief" not in scene_blob
    assert any(term in scene_blob for term in ("lighthouse", "lens", "clockwork", "dock", "artificer"))


def test_premise_seed_visual_prompt_matches_non_forest_premise():
    client = _client()
    owner = "bootstrap-orchard-visual@example.com"
    _ensure_user(owner)

    description = (
        "A science fantasy mystery in an orbital orchard where gravity fruit are failing, "
        "corporate guards are sealing the gantries, and a harvest engineer asks for help."
    )
    create = client.post(
        "/campaigns",
        headers=_auth(owner),
        json={
            "name": "Star Orchard Visual",
            "description": description,
            "create_session": True,
            "preferences": {
                "genre": "science fantasy mystery",
                "tone": "tense",
                "setting_summary": description,
            },
        },
    )
    assert create.status_code == 201, create.text
    sid = str(create.json()["campaign"]["sessions"][0]["id"])

    skip = client.post(f"/sessions/{sid}/opening-setup/skip", headers=_auth(owner))
    assert skip.status_code == 200, skip.text
    resp = client.post(f"/sessions/{sid}/start", headers=_auth(owner), json={})
    assert resp.status_code == 200, resp.text
    scene = resp.json()["scene"]
    scene_blob = json.dumps(scene).lower()
    image_prompt = json.dumps((scene.get("visual_state") or {}).get("image_prompt") or scene.get("image") or "").lower()

    assert "helix orchard" in scene_blob or "gravity fruit" in scene_blob
    assert "concealed forest camp" not in image_prompt
    assert "army road" not in image_prompt
    assert any(term in image_prompt for term in ("orchard", "gravity fruit", "gantry"))


def test_start_session_rejects_recycled_first_crossroads_opening(monkeypatch):
    client = _client()
    owner = "bootstrap-crossroads-guard@example.com"
    _ensure_user(owner)
    user = db.get_user_by_identifier(owner)
    assert user and user.id is not None

    campaign = db.create_campaign(
        owner_id=user.id,
        name="Crystal Desert",
        description="A survival mystery about caravans vanishing under glass dunes and sun-buried ruins.",
    )
    assert campaign.id is not None
    db.set_campaign_settings(campaign.id, user.id, {
        "genre": "fantasy survival mystery",
        "tone": "tense",
        "setting_summary": "Caravans vanish under glass dunes near sun-buried ruins. Water and shade are precious.",
        "creation_posture": "guided_builder",
        "playstyle_profile": "survival exploration",
    })
    sid, _meta = sessions_module.create_session_folder(campaign.name, owner, campaign_id=campaign.id)

    def stock_crossroads_response(_req):
        return sessions_module.narrative_agent.NarrativeResponse(
            narrative=(
                "Rain ticks against every hard surface at The First Crossroads; "
                "Mira Vale arrives visibly shaken and sets down a sealed packet."
            ),
            prompt="What does the party do?",
            tone="balanced",
            scene_score=90,
            score_passed=True,
        )

    monkeypatch.setattr(sessions_module.narrative_agent, "generate_narrative", stock_crossroads_response)

    resp = client.post(f"/sessions/{sid}/start", headers=_auth(owner), json={})
    assert resp.status_code == 200, resp.text
    scene = resp.json()["scene"]
    scene_blob = json.dumps(scene).lower()

    assert "first crossroads" not in scene_blob
    assert "mira vale" not in scene_blob
    assert "sealed packet" not in scene_blob
    assert any(term in scene_blob for term in ("crystal", "desert", "dune", "water", "shade"))


def test_bootstrap_rejects_recycled_first_crossroads_opening(monkeypatch):
    client = _client()
    owner = "bootstrap-crossroads-simple@example.com"
    _ensure_user(owner)
    user = db.get_user_by_identifier(owner)
    assert user and user.id is not None

    campaign = db.create_campaign(
        owner_id=user.id,
        name="Skyrail Sabotage",
        description="A science-fantasy investigation aboard a lightning-powered rail line.",
    )
    assert campaign.id is not None
    db.set_campaign_settings(campaign.id, user.id, {
        "genre": "science fantasy mystery",
        "tone": "thriller",
        "setting_summary": "A lightning-powered skyrail is sabotaged above a storm canyon.",
    })
    sid, _meta = sessions_module.create_session_folder(campaign.name, owner, campaign_id=campaign.id)

    def stock_crossroads_response(_req):
        return sessions_module.narrative_agent.NarrativeResponse(
            narrative="Something has gone very wrong at The First Crossroads. Mira Vale clutches a sealed packet.",
            prompt="What does the party do?",
            tone="balanced",
            scene_score=90,
            score_passed=True,
        )

    monkeypatch.setattr(sessions_module.narrative_agent, "generate_narrative", stock_crossroads_response)

    resp = client.post(f"/sessions/{sid}/bootstrap", headers=_auth(owner), json={})
    assert resp.status_code == 200, resp.text
    scene_blob = json.dumps(resp.json()["scene"]).lower()

    assert "first crossroads" not in scene_blob
    assert "mira vale" not in scene_blob
    assert "sealed packet" not in scene_blob
    assert any(term in scene_blob for term in ("skyrail", "lightning", "storm", "sabotage"))


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
