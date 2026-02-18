"""Tests for GM assignment and player-led campaign features."""

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


def test_assign_gm_ai_mode():
    """Test assigning AI as GM (default mode)."""
    client = _client()
    email = "gm-test-owner@example.com"
    user = _ensure_user(email)
    assert user.id is not None

    token = create_access_token(email)
    headers = {"Authorization": f"Bearer {token}"}

    # Create campaign
    camp = db.create_campaign(owner_id=user.id, name="GM Test Campaign", description="")
    assert camp.id
    assert camp.gm_mode == "ai"  # Default
    assert camp.gm_user_id is None  # Default

    # Assign AI as GM (explicitly)
    response = client.put(
        f"/campaigns/{camp.id}/gm",
        headers=headers,
        json={"gm_user_id": None}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["gm_mode"] == "ai"
    assert data["gm_user_id"] is None


def test_assign_gm_player_mode():
    """Test assigning a player as GM."""
    client = _client()
    owner_email = "gm-test-owner2@example.com"
    owner = _ensure_user(owner_email)
    assert owner.id is not None

    token = create_access_token(owner_email)
    headers = {"Authorization": f"Bearer {token}"}

    # Create campaign
    camp = db.create_campaign(owner_id=owner.id, name="Player GM Test", description="")
    assert camp.id

    # Assign owner as GM
    response = client.put(
        f"/campaigns/{camp.id}/gm",
        headers=headers,
        json={"gm_user_id": owner.id}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["gm_mode"] == "player"
    assert data["gm_user_id"] == owner.id


def test_get_gm_assignment():
    """Test retrieving GM assignment."""
    client = _client()
    email = "gm-test-owner3@example.com"
    user = _ensure_user(email)
    assert user.id is not None

    token = create_access_token(email)
    headers = {"Authorization": f"Bearer {token}"}

    # Create campaign and assign player as GM
    camp = db.create_campaign(owner_id=user.id, name="GM Get Test", description="")
    assert camp.id

    client.put(
        f"/campaigns/{camp.id}/gm",
        headers=headers,
        json={"gm_user_id": user.id}
    )

    # Get GM assignment
    response = client.get(f"/campaigns/{camp.id}/gm", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["gm_mode"] == "player"
    assert data["gm_user_id"] == user.id


def test_get_campaign_players():
    """Test retrieving campaign players."""
    client = _client()
    email = "gm-test-owner4@example.com"
    user = _ensure_user(email)
    assert user.id is not None

    token = create_access_token(email)
    headers = {"Authorization": f"Bearer {token}"}

    # Create campaign
    camp = db.create_campaign(owner_id=user.id, name="Players Test", description="")
    assert camp.id

    # Get players
    response = client.get(f"/campaigns/{camp.id}/players", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "players" in data
    assert len(data["players"]) >= 1
    # Owner should be in the list
    owner_in_list = any(p["id"] == user.id for p in data["players"])
    assert owner_in_list


def test_gm_assignment_forbidden_for_other_user():
    """Test that non-owners cannot assign GM."""
    client = _client()
    owner = _ensure_user("gm-test-owner5@example.com")
    other = _ensure_user("gm-test-other@example.com")
    assert owner.id is not None
    assert other.id is not None

    # Create campaign as owner
    camp = db.create_campaign(owner_id=owner.id, name="Forbidden Test", description="")
    assert camp.id

    # Try to assign GM as other user
    token_other = create_access_token(other.email or "")
    headers_other = {"Authorization": f"Bearer {token_other}"}

    response = client.put(
        f"/campaigns/{camp.id}/gm",
        headers=headers_other,
        json={"gm_user_id": other.id}
    )
    assert response.status_code == 403, response.text
