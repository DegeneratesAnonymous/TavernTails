"""
WO-008: Integration tests for campaign→session flow determinism.

Covers:
- Creating a campaign with create_session=True returns session in response
- create_session_from_campaign returns session_id and meta
- Validate endpoint confirms session belongs to campaign
- Validate endpoint rejects sessions from another campaign (404)
- Validate endpoint is host-only (403 for unrelated user)
"""
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


def _auth(email: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(email)}"}


# ---------------------------------------------------------------------------
# Campaign creation includes first session in response
# ---------------------------------------------------------------------------

def test_create_campaign_with_session_includes_session_in_response():
    client = _client()
    user = _ensure_user("wo008-create@example.com")
    assert user.id is not None

    res = client.post(
        "/campaigns",
        headers=_auth(user.email),
        json={"name": "WO008 Test Campaign", "create_session": True},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    campaign = data.get("campaign", {})
    sessions = campaign.get("sessions", [])
    assert len(sessions) >= 1, "Expected at least one session in response"
    assert sessions[0].get("id"), "Session must have an id"


def test_create_campaign_without_session_returns_empty_sessions():
    client = _client()
    user = _ensure_user("wo008-nosession@example.com")
    assert user.id is not None

    res = client.post(
        "/campaigns",
        headers=_auth(user.email),
        json={"name": "WO008 No Session Campaign", "create_session": False},
    )
    assert res.status_code == 201, res.text
    sessions = res.json().get("campaign", {}).get("sessions", [])
    assert sessions == [], f"Expected empty sessions list, got {sessions}"


# ---------------------------------------------------------------------------
# create_session_from_campaign returns session_id + meta
# ---------------------------------------------------------------------------

def test_create_session_from_campaign_returns_session_id_and_meta():
    client = _client()
    user = _ensure_user("wo008-newsession@example.com")
    assert user.id is not None

    camp = db.create_campaign(owner_id=user.id, name="WO008 Session Create", description="")
    assert camp.id is not None

    res = client.post(
        f"/campaigns/{camp.id}/create_session",
        headers=_auth(user.email),
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data.get("session_id"), "Response must include session_id"
    assert isinstance(data.get("meta"), dict), "Response must include meta dict"


def test_create_session_from_campaign_forbidden_for_other_user():
    client = _client()
    owner = _ensure_user("wo008-owner-sec@example.com")
    other = _ensure_user("wo008-other-sec@example.com")
    assert owner.id is not None

    camp = db.create_campaign(owner_id=owner.id, name="WO008 Forbidden Session", description="")
    assert camp.id is not None

    res = client.post(
        f"/campaigns/{camp.id}/create_session",
        headers=_auth(other.email),
    )
    assert res.status_code == 403, res.text


# ---------------------------------------------------------------------------
# Validate endpoint: session belongs to campaign
# ---------------------------------------------------------------------------

def test_validate_session_belongs_to_campaign_ok():
    client = _client()
    user = _ensure_user("wo008-validate-ok@example.com")
    assert user.id is not None

    # Create campaign + session via the API so DB linkage is correct
    create_res = client.post(
        "/campaigns",
        headers=_auth(user.email),
        json={"name": "WO008 Validate Campaign", "create_session": True},
    )
    assert create_res.status_code == 201, create_res.text
    campaign = create_res.json()["campaign"]
    campaign_id = str(campaign["id"])
    session_id = str(campaign["sessions"][0]["id"])

    res = client.get(
        f"/campaigns/{campaign_id}/sessions/{session_id}/validate",
        headers=_auth(user.email),
    )
    assert res.status_code == 200, res.text
    assert res.json().get("ok") is True


def test_validate_session_wrong_campaign_returns_404():
    client = _client()
    user = _ensure_user("wo008-validate-wrong@example.com")
    assert user.id is not None

    camp1_res = client.post(
        "/campaigns",
        headers=_auth(user.email),
        json={"name": "WO008 Camp A", "create_session": True},
    )
    camp2_res = client.post(
        "/campaigns",
        headers=_auth(user.email),
        json={"name": "WO008 Camp B", "create_session": True},
    )
    assert camp1_res.status_code == 201
    assert camp2_res.status_code == 201

    camp1_id = str(camp1_res.json()["campaign"]["id"])
    camp2_session_id = str(camp2_res.json()["campaign"]["sessions"][0]["id"])

    # Camp B's session should NOT validate against Camp A
    res = client.get(
        f"/campaigns/{camp1_id}/sessions/{camp2_session_id}/validate",
        headers=_auth(user.email),
    )
    assert res.status_code == 404, res.text


def test_validate_session_forbidden_for_non_owner():
    client = _client()
    owner = _ensure_user("wo008-validate-owner@example.com")
    other = _ensure_user("wo008-validate-nonowner@example.com")
    assert owner.id is not None

    create_res = client.post(
        "/campaigns",
        headers=_auth(owner.email),
        json={"name": "WO008 Validate Auth Camp", "create_session": True},
    )
    assert create_res.status_code == 201
    campaign_id = str(create_res.json()["campaign"]["id"])
    session_id = str(create_res.json()["campaign"]["sessions"][0]["id"])

    res = client.get(
        f"/campaigns/{campaign_id}/sessions/{session_id}/validate",
        headers=_auth(other.email),
    )
    assert res.status_code == 403, res.text
