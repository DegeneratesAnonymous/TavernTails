"""Tests for generative endpoints (NPC, Location, Loot generation)."""

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.auth import create_access_token


def _client() -> TestClient:
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


def test_generate_npc():
    """Test NPC generation endpoint."""
    client = _client()
    email = "gen-npc-owner@example.com"
    user = _ensure_user(email)
    assert user.id is not None

    token = create_access_token(email)
    headers = {"Authorization": f"Bearer {token}"}

    # Create campaign with settings
    camp = db.create_campaign(owner_id=user.id, name="NPC Gen Test", description="")
    assert camp.id

    # Set campaign settings
    settings = {
        "world_name": "Eldervale",
        "setting_summary": "A dark fantasy world",
        "tone": "grim",
        "ruleset": "5e",
    }
    db.set_campaign_settings(camp.id, user.id, settings)

    # Generate NPC
    response = client.post(
        "/generate/npc",
        headers=headers,
        json={
            "campaign_id": camp.id,
            "npc_type": "merchant",
            "setting": "tavern",
        }
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "npc" in data
    assert data["campaign_id"] == camp.id
    assert "name" in data["npc"]
    assert "description" in data["npc"]


def test_generate_location():
    """Test location generation endpoint."""
    client = _client()
    email = "gen-location-owner@example.com"
    user = _ensure_user(email)
    assert user.id is not None

    token = create_access_token(email)
    headers = {"Authorization": f"Bearer {token}"}

    # Create campaign with settings
    camp = db.create_campaign(owner_id=user.id, name="Location Gen Test", description="")
    assert camp.id

    settings = {
        "world_name": "Mythara",
        "setting_summary": "High fantasy realm",
        "tone": "heroic",
    }
    db.set_campaign_settings(camp.id, user.id, settings)

    # Generate location
    response = client.post(
        "/generate/location",
        headers=headers,
        json={
            "campaign_id": camp.id,
            "location_type": "dungeon",
            "mood": "mysterious",
        }
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "location" in data
    assert data["campaign_id"] == camp.id
    assert "name" in data["location"]
    assert "description" in data["location"]


def test_generate_loot():
    """Test loot generation endpoint."""
    client = _client()
    email = "gen-loot-owner@example.com"
    user = _ensure_user(email)
    assert user.id is not None

    token = create_access_token(email)
    headers = {"Authorization": f"Bearer {token}"}

    # Create campaign with settings
    camp = db.create_campaign(owner_id=user.id, name="Loot Gen Test", description="")
    assert camp.id

    settings = {
        "world_name": "Dungeon World",
        "ruleset": "5e",
        "starting_level": 5,
    }
    db.set_campaign_settings(camp.id, user.id, settings)

    # Generate loot
    response = client.post(
        "/generate/loot",
        headers=headers,
        json={
            "campaign_id": camp.id,
            "challenge_rating": 5,
            "loot_type": "magic_item",
        }
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "loot" in data
    assert data["campaign_id"] == camp.id
    assert "name" in data["loot"]
    assert "items" in data["loot"]


def test_generate_forbidden_for_other_user():
    """Test that non-owners cannot use generative endpoints."""
    client = _client()
    owner = _ensure_user("gen-forbidden-owner@example.com")
    other = _ensure_user("gen-forbidden-other@example.com")
    assert owner.id is not None

    # Create campaign as owner
    camp = db.create_campaign(owner_id=owner.id, name="Forbidden Gen Test", description="")
    assert camp.id

    # Try to generate as other user
    token_other = create_access_token(other.email or "")
    headers_other = {"Authorization": f"Bearer {token_other}"}

    response = client.post(
        "/generate/npc",
        headers=headers_other,
        json={
            "campaign_id": camp.id,
            "npc_type": "guard",
        }
    )
    assert response.status_code == 403, response.text
