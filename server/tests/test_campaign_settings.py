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


def test_campaign_settings_roundtrip():
    client = _client()
    email = "campaign-settings-owner@example.com"
    user = _ensure_user(email)
    assert user.id is not None

    token = create_access_token(email)
    headers = {"Authorization": f"Bearer {token}"}

    camp = db.create_campaign(owner_id=user.id, name="Settings Test", description="")
    assert camp.id

    payload = {
        "world_name": "Eldervale",
        "tone": "dark-fantasy",
        "ruleset": "5e",
        "starting_level": 3,
        "house_rules": "No flanking.",
    }

    put = client.put(f"/campaigns/{camp.id}/settings", headers=headers, json=payload)
    assert put.status_code == 200, put.text
    assert put.json().get("settings", {}).get("world_name") == "Eldervale"

    get = client.get(f"/campaigns/{camp.id}/settings", headers=headers)
    assert get.status_code == 200, get.text
    settings = get.json().get("settings")
    assert isinstance(settings, dict)
    assert settings.get("starting_level") == 3


def test_campaign_settings_forbidden_for_other_user():
    client = _client()
    owner = _ensure_user("campaign-settings-owner2@example.com")
    other = _ensure_user("campaign-settings-other@example.com")
    assert owner.id is not None

    camp = db.create_campaign(owner_id=owner.id, name="Settings Test 2", description="")
    assert camp.id

    token_other = create_access_token(other.email or "")
    headers_other = {"Authorization": f"Bearer {token_other}"}

    r = client.get(f"/campaigns/{camp.id}/settings", headers=headers_other)
    assert r.status_code == 403, r.text
