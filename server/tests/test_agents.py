"""Contract tests for lightweight agent stubs."""

import pytest
from fastapi.testclient import TestClient

import server.main as main

from . import agent_payloads as payloads


@pytest.fixture()
def client() -> TestClient:
    return TestClient(main.app)


def test_narrative_agent_contract(client: TestClient):
    resp = client.post("/narrative/generate", json=payloads.NARRATIVE_REQUEST)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert payloads.NARRATIVE_REQUEST["scene"] in data["narrative"]
    assert data["prompt"].startswith(payloads.NARRATIVE_REQUEST["player"])
    assert data["tone"] == payloads.NARRATIVE_REQUEST["style"].lower()


def test_storyboard_agent_contract(client: TestClient):
    resp = client.post("/storyboard/update", json=payloads.STORYBOARD_REQUEST)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["storyboard"]["scene"] == payloads.STORYBOARD_REQUEST["scene"]
    assert data["storyboard"]["choices"] == payloads.STORYBOARD_REQUEST["choices"]
    assert data["storyboard"]["completed"] == payloads.STORYBOARD_REQUEST["completed"]
    assert data["next_focus"]


def test_notes_agent_contract(client: TestClient):
    resp = client.post("/notes/log", json=payloads.NOTES_REQUEST)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["session_id"] == payloads.NOTES_REQUEST["session_id"]
    assert data["notes_logged"] == len(payloads.NOTES_REQUEST["notes"])
    # Recap is deterministic and should reference the submitted notes.
    recap = data["recap"]
    assert isinstance(recap, str)
    assert payloads.NOTES_REQUEST["notes"][-1] in recap


def test_image_agent_contract(client: TestClient):
    resp = client.post("/image/generate", json=payloads.IMAGE_REQUEST)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["prompt"] == payloads.IMAGE_REQUEST["prompt"]
    assert data["style"] == payloads.IMAGE_REQUEST["style"]
    assert data["image_url"].startswith("https://placeholder.image/")
    assert "placeholder" in data["guidance"].lower()


def test_scene_agent_roll_prompts(client: TestClient):
    resp = client.post("/scene/analyze", json=payloads.SCENE_REQUEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert any(roll["skill"] == "Persuasion" for roll in body["dice_rolls"])
    assert any("Roll a d20" in prompt for prompt in body["prompts"])


def test_npc_agent_initiative_hint(client: TestClient):
    resp = client.post("/npc/manage", json=payloads.NPC_REQUEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["npc_profile"]["name"] == payloads.NPC_REQUEST["name"]
    assert "d20" in body["initiative_hint"]
