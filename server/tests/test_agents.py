"""Contract tests for lightweight agent stubs."""

import json

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents import narrative as narrative_module
from server.agents import sessions as sessions_module
from server.auth import create_access_token

from . import agent_payloads as payloads


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


@pytest.fixture()
def client() -> TestClient:
    return TestClient(main.app)


def test_narrative_agent_contract(monkeypatch, client: TestClient):
    fake_llm = json.dumps({
        "narrative": "Rain lashes the watchtower parapet as Aria rushes through the door.",
        "prompt": "Aria, what do you do?",
    })
    monkeypatch.setattr(narrative_module, "chat_complete", lambda *a, **kw: fake_llm)

    resp = client.post("/narrative/generate", json=payloads.NARRATIVE_REQUEST)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data["narrative"], str) and len(data["narrative"]) > 10
    assert isinstance(data["prompt"], str) and len(data["prompt"]) > 0
    assert data["tone"] == payloads.NARRATIVE_REQUEST["style"].lower()
    assert isinstance(data["scene_score"], int)
    assert isinstance(data["score_passed"], bool)


def test_storyboard_agent_contract(client: TestClient):
    resp = client.post("/storyboard/update", json=payloads.STORYBOARD_REQUEST)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["storyboard"]["scene"] == payloads.STORYBOARD_REQUEST["scene"]
    assert data["storyboard"]["choices"] == payloads.STORYBOARD_REQUEST["choices"]
    assert data["storyboard"]["completed"] == payloads.STORYBOARD_REQUEST["completed"]
    assert data["next_focus"]


def test_notes_agent_contract(client: TestClient):
    owner = "contract-notes-host@example.com"
    _ensure_user(owner)
    sid, _ = sessions_module.create_session_folder("Contract Notes Session", owner)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}
    payload = {**payloads.NOTES_REQUEST, "session_id": sid}
    resp = client.post("/notes/log", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["session_id"] == sid
    assert data["notes_logged"] == len(payload["notes"])
    # Recap is deterministic and should reference the submitted notes.
    recap = data["recap"]
    assert isinstance(recap, str)
    assert payload["notes"][-1] in recap


def test_image_agent_contract(client: TestClient):
    owner = "contract-image-host@example.com"
    _ensure_user(owner)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}
    resp = client.post("/image/generate", json=payloads.IMAGE_REQUEST, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["prompt"] == payloads.IMAGE_REQUEST["prompt"]
    assert data["style"] == payloads.IMAGE_REQUEST["style"]
    assert isinstance(data["image_url"], str) and data["image_url"].startswith("https://")
    assert isinstance(data["guidance"], str)
    assert "id" in data
    assert "generated_at" in data
    assert data["cached"] is False


def test_scene_agent_roll_prompts(client: TestClient):
    resp = client.post("/scene/analyze", json=payloads.SCENE_REQUEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert any(roll["skill"] == "Persuasion" for roll in body["dice_rolls"])
    assert any("d20" in prompt for prompt in body["prompts"])


def test_npc_agent_initiative_hint(client: TestClient):
    resp = client.post("/npc/manage", json=payloads.NPC_REQUEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["npc_profile"]["name"] == payloads.NPC_REQUEST["name"]
    assert "d20" in body["initiative_hint"]
