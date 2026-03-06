"""Tests for LLM integration in generative endpoints (NPC, Location, Loot).

These tests exercise the LLM code paths by injecting a fake openai module via
sys.modules so no real API key is required.  The fallback (no API key) path is
also covered.
"""
import json
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.auth import create_access_token


@pytest.fixture()
def client() -> TestClient:
    return TestClient(main.app)


def _ensure_user(email: str) -> db.User:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return existing
    user = db.create_user(
        email=email,
        password="secret",
        username=email.split("@")[0],
        profile={"name": email.split("@")[0], "email": email},
    )
    assert user.verification_token
    db.verify_user(email, user.verification_token)
    return user


def _make_campaign(user_id: int, name: str) -> str:
    camp = db.create_campaign(owner_id=user_id, name=name, description="")
    db.set_campaign_settings(
        camp.id,
        user_id,
        {"world_name": "Testworld", "tone": "grim", "ruleset": "5e"},
    )
    return camp.id


def _make_fake_openai(response_content: dict, captured: dict | None = None):
    """Return a fake openai module whose ChatCompletion.create returns response_content as JSON."""

    class DummyChat:
        @staticmethod
        def create(*args, **kwargs):
            if captured is not None:
                captured["last"] = {"args": args, "kwargs": kwargs}
            return {"choices": [{"message": {"content": json.dumps(response_content)}}]}

    fake = SimpleNamespace()
    fake.api_key = None
    fake.ChatCompletion = DummyChat
    return fake


def _make_fake_openai_error():
    """Return a fake openai module whose ChatCompletion.create raises an exception."""

    class FailingChat:
        @staticmethod
        def create(*args, **kwargs):
            raise Exception("Simulated LLM network error")

    fake = SimpleNamespace()
    fake.api_key = None
    fake.ChatCompletion = FailingChat
    return fake


# ---------------------------------------------------------------------------
# NPC generation — LLM path
# ---------------------------------------------------------------------------


def test_generate_npc_with_llm(client: TestClient, monkeypatch):
    """When OPENAI_API_KEY is set, NPC endpoint returns LLM-generated fields."""
    user = _ensure_user("llm-npc-test@example.com")
    assert user.id is not None
    camp_id = _make_campaign(user.id, "LLM NPC Test")
    headers = {"Authorization": f"Bearer {create_access_token(user.email or '')}"}

    npc_payload = {
        "name": "Mira the Merchant",
        "description": "A shrewd trader from the eastern docks.",
        "personality": "Cautious but fair",
        "motivation": "Accumulate enough wealth to retire",
        "appearance": "Middle-aged woman with sharp eyes",
        "faction_affiliation": "Traders Guild",
    }

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    captured: dict = {}
    sys.modules["openai"] = _make_fake_openai(npc_payload, captured)

    try:
        resp = client.post(
            "/generate/npc",
            headers=headers,
            json={"campaign_id": camp_id, "npc_type": "merchant"},
        )
    finally:
        sys.modules.pop("openai", None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    npc = data["npc"]
    assert npc["name"] == npc_payload["name"]
    assert npc["motivation"] == npc_payload["motivation"]
    assert npc["faction_affiliation"] == npc_payload["faction_affiliation"]
    assert "last" in captured, "ChatCompletion.create was never called"


# ---------------------------------------------------------------------------
# Location generation — LLM path
# ---------------------------------------------------------------------------


def test_generate_location_with_llm(client: TestClient, monkeypatch):
    """When OPENAI_API_KEY is set, location endpoint returns LLM-generated fields."""
    user = _ensure_user("llm-location-test@example.com")
    assert user.id is not None
    camp_id = _make_campaign(user.id, "LLM Location Test")
    headers = {"Authorization": f"Bearer {create_access_token(user.email or '')}"}

    location_payload = {
        "name": "The Sunken Archive",
        "description": "An ancient library half-submerged in brackish water.",
        "atmosphere": "Damp, dimly lit, smells of old parchment and decay.",
        "points_of_interest": ["Flooded reading room", "The Archivist's sealed vault"],
        "rumors": ["A ghost haunts the east wing"],
        "connections_to_factions": "Contested by the Scholar's Circle and the Undercity Thieves",
    }

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    sys.modules["openai"] = _make_fake_openai(location_payload)

    try:
        resp = client.post(
            "/generate/location",
            headers=headers,
            json={"campaign_id": camp_id, "location_type": "dungeon", "mood": "eerie"},
        )
    finally:
        sys.modules.pop("openai", None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    loc = data["location"]
    assert loc["name"] == location_payload["name"]
    assert loc["atmosphere"] == location_payload["atmosphere"]
    assert isinstance(loc["points_of_interest"], list)
    assert len(loc["points_of_interest"]) == 2


# ---------------------------------------------------------------------------
# Loot generation — LLM path
# ---------------------------------------------------------------------------


def test_generate_loot_with_llm(client: TestClient, monkeypatch):
    """When OPENAI_API_KEY is set, loot endpoint returns LLM-generated item list."""
    user = _ensure_user("llm-loot-test@example.com")
    assert user.id is not None
    camp_id = _make_campaign(user.id, "LLM Loot Test")
    headers = {"Authorization": f"Bearer {create_access_token(user.email or '')}"}

    loot_payload = {
        "name": "Dragon Hoard Fragment",
        "description": "A small portion of a dragon's personal treasury.",
        "items": [
            {"name": "Gold Pieces", "quantity": 500, "type": "currency", "rarity": "common", "description": ""},
            {"name": "Ruby Amulet", "quantity": 1, "type": "magic", "rarity": "rare", "description": "Glows faintly red"},
        ],
        "total_value_gp": 650,
    }

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    sys.modules["openai"] = _make_fake_openai(loot_payload)

    try:
        resp = client.post(
            "/generate/loot",
            headers=headers,
            json={"campaign_id": camp_id, "challenge_rating": 8, "loot_type": "treasure"},
        )
    finally:
        sys.modules.pop("openai", None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    loot = data["loot"]
    assert loot["name"] == loot_payload["name"]
    assert loot["total_value_gp"] == 650
    assert len(loot["items"]) == 2


# ---------------------------------------------------------------------------
# Fallback path — no API key
# ---------------------------------------------------------------------------


def test_generate_npc_fallback_no_key(client: TestClient, monkeypatch):
    """Without OPENAI_API_KEY, NPC endpoint returns placeholder data."""
    user = _ensure_user("llm-npc-nokey@example.com")
    assert user.id is not None
    camp_id = _make_campaign(user.id, "LLM NPC NoKey Test")
    headers = {"Authorization": f"Bearer {create_access_token(user.email or '')}"}

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    resp = client.post(
        "/generate/npc",
        headers=headers,
        json={"campaign_id": camp_id, "npc_type": "guard"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "npc" in data
    assert "name" in data["npc"]
    # Placeholder name contains the npc_type
    assert "guard" in data["npc"]["name"].lower()


def test_generate_location_fallback_no_key(client: TestClient, monkeypatch):
    """Without OPENAI_API_KEY, location endpoint returns placeholder data."""
    user = _ensure_user("llm-loc-nokey@example.com")
    assert user.id is not None
    camp_id = _make_campaign(user.id, "LLM Location NoKey Test")
    headers = {"Authorization": f"Bearer {create_access_token(user.email or '')}"}

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    resp = client.post(
        "/generate/location",
        headers=headers,
        json={"campaign_id": camp_id, "location_type": "tavern"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "location" in data
    assert "name" in data["location"]
    assert "tavern" in data["location"]["name"].lower()


def test_generate_loot_fallback_no_key(client: TestClient, monkeypatch):
    """Without OPENAI_API_KEY, loot endpoint returns placeholder data with items."""
    user = _ensure_user("llm-loot-nokey@example.com")
    assert user.id is not None
    camp_id = _make_campaign(user.id, "LLM Loot NoKey Test")
    headers = {"Authorization": f"Bearer {create_access_token(user.email or '')}"}

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    resp = client.post(
        "/generate/loot",
        headers=headers,
        json={"campaign_id": camp_id, "loot_type": "equipment"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "loot" in data
    assert isinstance(data["loot"]["items"], list)
    assert len(data["loot"]["items"]) > 0


# ---------------------------------------------------------------------------
# LLM error resilience — exception during LLM call falls back gracefully
# ---------------------------------------------------------------------------


def test_generate_npc_llm_exception_falls_back(client: TestClient, monkeypatch):
    """If the LLM call raises an exception, the endpoint falls back to placeholder."""
    user = _ensure_user("llm-npc-exc@example.com")
    assert user.id is not None
    camp_id = _make_campaign(user.id, "LLM NPC Exception Test")
    headers = {"Authorization": f"Bearer {create_access_token(user.email or '')}"}

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    sys.modules["openai"] = _make_fake_openai_error()

    try:
        resp = client.post(
            "/generate/npc",
            headers=headers,
            json={"campaign_id": camp_id, "npc_type": "villain"},
        )
    finally:
        sys.modules.pop("openai", None)

    # Should still return 200 with placeholder data
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "npc" in data
    assert "name" in data["npc"]


# ---------------------------------------------------------------------------
# Campaign-level model override (_get_model)
# ---------------------------------------------------------------------------


def test_campaign_model_override_used_in_llm_call(monkeypatch):
    """_get_model() returns campaign ai_model setting when present."""
    from server.agents.generate import _get_model

    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    # Without campaign override, use env var
    assert _get_model({}) == "gpt-4o-mini"

    # With campaign override, use that instead
    assert _get_model({"ai_model": "gpt-4o"}) == "gpt-4o"
    assert _get_model({"ai_model": "gpt-4.1"}) == "gpt-4.1"

    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    # Without env var and without campaign setting, fall back to built-in default
    assert _get_model({}) == "gpt-4o"

