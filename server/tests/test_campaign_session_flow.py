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


def test_create_campaign_owner_can_join_as_character():
    client = _client()
    user = _ensure_user("wo008-owner-character@example.com")
    assert user.id is not None
    character = db.create_character(owner_id=user.id, name="Owner Hero", level=4, class_name="Paladin", sheet={})

    res = client.post(
        "/campaigns",
        headers=_auth(user.email),
        json={
            "name": "WO008 Owner Character Campaign",
            "create_session": True,
            "owner_role": "player",
            "owner_character_id": character.id,
        },
    )
    assert res.status_code == 201, res.text
    campaign = res.json()["campaign"]
    assert campaign["metadata_json"]["owner_participation"]["character_id"] == character.id

    session_id = campaign["sessions"][0]["id"]
    meta = client.get(f"/sessions/{session_id}/meta", headers=_auth(user.email)).json()
    owner_member = next(m for m in meta["members"] if m["email"] == user.email)
    assert owner_member["character_id"] == character.id
    assert owner_member["character_name"] == "Owner Hero"


def test_create_campaign_uses_selected_owner_character_not_first_character():
    client = _client()
    user = _ensure_user("wo008-selected-character@example.com")
    assert user.id is not None
    first = db.create_character(owner_id=user.id, name="Yungmin", level=5, class_name="Wizard", sheet={})
    selected = db.create_character(owner_id=user.id, name="Chosen Ranger", level=3, class_name="Ranger", sheet={})

    res = client.post(
        "/campaigns",
        headers=_auth(user.email),
        json={
            "name": "WO008 Selected Character Campaign",
            "create_session": True,
            "owner_role": "player",
            "owner_character_id": selected.id,
        },
    )

    assert res.status_code == 201, res.text
    campaign = res.json()["campaign"]
    assert campaign["metadata_json"]["owner_participation"]["character_id"] == selected.id
    assert campaign["metadata_json"]["owner_participation"]["character_id"] != first.id

    session_id = campaign["sessions"][0]["id"]
    meta = client.get(f"/sessions/{session_id}/meta", headers=_auth(user.email)).json()
    owner_member = next(m for m in meta["members"] if m["email"] == user.email)
    assert owner_member["character_id"] == selected.id
    assert owner_member["character_name"] == "Chosen Ranger"


def test_partial_settings_update_preserves_setting_summary_for_opening_context():
    client = _client()
    user = _ensure_user("wo008-settings-merge@example.com")
    assert user.id is not None

    res = client.post(
        "/campaigns",
        headers=_auth(user.email),
        json={
            "name": "WO008 Setting Preserve",
            "description": "A crystal desert where glass storms expose buried cities.",
            "create_session": True,
            "preferences": {
                "genre": "fantasy",
                "tone": "mystery",
                "setting_summary": "A crystal desert where glass storms expose buried cities.",
            },
        },
    )
    assert res.status_code == 201, res.text
    campaign_id = res.json()["campaign"]["id"]

    settings_res = client.put(
        f"/campaigns/{campaign_id}/settings",
        headers=_auth(user.email),
        json={"genre": "fantasy", "tone": "mystery"},
    )

    assert settings_res.status_code == 200, settings_res.text
    settings = settings_res.json()["settings"]
    assert settings["setting_summary"] == "A crystal desert where glass storms expose buried cities."


def test_create_campaign_owner_can_designate_self_dm():
    client = _client()
    user = _ensure_user("wo008-owner-dm@example.com")
    assert user.id is not None

    res = client.post(
        "/campaigns",
        headers=_auth(user.email),
        json={
            "name": "WO008 Owner DM Campaign",
            "create_session": True,
            "owner_role": "dm",
        },
    )
    assert res.status_code == 201, res.text
    campaign = res.json()["campaign"]
    assert campaign["metadata_json"]["owner_participation"]["role"] == "dm"

    session_id = campaign["sessions"][0]["id"]
    meta = client.get(f"/sessions/{session_id}/meta", headers=_auth(user.email)).json()
    owner_member = next(m for m in meta["members"] if m["email"] == user.email)
    assert owner_member["role"] == "dm"
    assert owner_member["character_id"] is None


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


def test_create_session_from_campaign_inherits_owner_character():
    client = _client()
    user = _ensure_user("wo008-newsession-owner-character@example.com")
    assert user.id is not None
    character = db.create_character(owner_id=user.id, name="Chosen Later", level=2, class_name="Bard", sheet={})

    res = client.post(
        "/campaigns",
        headers=_auth(user.email),
        json={
            "name": "WO008 Later Session Character Campaign",
            "create_session": False,
            "owner_role": "player",
            "owner_character_id": character.id,
        },
    )
    assert res.status_code == 201, res.text
    campaign_id = res.json()["campaign"]["id"]

    session_res = client.post(
        f"/campaigns/{campaign_id}/create_session",
        headers=_auth(user.email),
    )
    assert session_res.status_code == 201, session_res.text
    meta = session_res.json()["meta"]
    owner_member = next(m for m in meta["members"] if m["email"] == user.email)
    assert owner_member["character_id"] == character.id
    assert owner_member["character_name"] == "Chosen Later"


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
