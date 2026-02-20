"""Tests for campaign variables API (GET / PUT /campaigns/{id}/variables)."""
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


def test_campaign_variables_roundtrip():
    """Variables can be saved and retrieved correctly."""
    client = _client()
    email = "campaign-vars-owner@example.com"
    user = _ensure_user(email)
    assert user.id is not None

    token = create_access_token(email)
    headers = {"Authorization": f"Bearer {token}"}

    camp = db.create_campaign(owner_id=user.id, name="Variables Test", description="")
    assert camp.id

    payload = {
        "themes": ["redemption", "betrayal"],
        "pacing": "fast",
        "narrative_style": "gritty",
        "factions": [
            {
                "name": "Thieves Guild",
                "alignment": "chaotic neutral",
                "goals": ["control the spice trade", "bribe city officials"],
                "members": ["Guildmaster Varro", "Shade the Informant"],
            },
            {
                "name": "Royal Guard",
                "alignment": "lawful neutral",
                "goals": ["protect the crown"],
                "members": ["Captain Aldric"],
            },
        ],
        "npc_archetypes": ["grizzled veteran", "cunning spy"],
        "naming_style": "Norse",
        "content_rating": "pg-13",
    }

    put = client.put(f"/campaigns/{camp.id}/variables", headers=headers, json=payload)
    assert put.status_code == 200, put.text
    assert put.json()["variables"]["pacing"] == "fast"
    assert put.json()["variables"]["themes"] == ["redemption", "betrayal"]
    factions = put.json()["variables"]["factions"]
    assert len(factions) == 2
    assert factions[0]["name"] == "Thieves Guild"
    assert factions[0]["alignment"] == "chaotic neutral"
    assert "control the spice trade" in factions[0]["goals"]
    assert "Guildmaster Varro" in factions[0]["members"]

    get = client.get(f"/campaigns/{camp.id}/variables", headers=headers)
    assert get.status_code == 200, get.text
    variables = get.json()["variables"]
    assert isinstance(variables, dict)
    assert variables["naming_style"] == "Norse"
    assert variables["content_rating"] == "pg-13"
    assert len(variables["factions"]) == 2


def test_campaign_variables_defaults_when_unset():
    """Fetching variables before any PUT returns an empty dict (not 404)."""
    client = _client()
    email = "campaign-vars-defaults@example.com"
    user = _ensure_user(email)
    assert user.id is not None

    token = create_access_token(email)
    headers = {"Authorization": f"Bearer {token}"}

    camp = db.create_campaign(owner_id=user.id, name="Variables Defaults Test", description="")
    assert camp.id

    get = client.get(f"/campaigns/{camp.id}/variables", headers=headers)
    assert get.status_code == 200, get.text
    variables = get.json()["variables"]
    assert isinstance(variables, dict)


def test_campaign_variables_forbidden_for_other_user():
    """A user cannot read or write another user's campaign variables."""
    client = _client()
    owner = _ensure_user("campaign-vars-owner2@example.com")
    other = _ensure_user("campaign-vars-other@example.com")
    assert owner.id is not None

    camp = db.create_campaign(owner_id=owner.id, name="Variables Forbidden Test", description="")
    assert camp.id

    token_other = create_access_token(other.email or "")
    headers_other = {"Authorization": f"Bearer {token_other}"}

    get = client.get(f"/campaigns/{camp.id}/variables", headers=headers_other)
    assert get.status_code == 403, get.text

    put = client.put(
        f"/campaigns/{camp.id}/variables",
        headers=headers_other,
        json={"themes": ["test"]},
    )
    assert put.status_code == 403, put.text


def test_campaign_variables_in_generate_npc_context():
    """Campaign variables are included in the generate/npc context."""
    client = _client()
    email = "campaign-vars-gen@example.com"
    user = _ensure_user(email)
    assert user.id is not None

    token = create_access_token(email)
    headers = {"Authorization": f"Bearer {token}"}

    camp = db.create_campaign(owner_id=user.id, name="Variables Generate Test", description="")
    assert camp.id

    # Save variables with rich faction data
    vars_payload = {
        "themes": ["survival"],
        "pacing": "slow",
        "narrative_style": "intimate",
        "factions": [
            {
                "name": "Desert Wanderers",
                "alignment": "neutral good",
                "goals": ["find the lost oasis", "protect the caravan routes"],
                "members": ["Elder Rashid", "Scout Lena"],
            }
        ],
        "npc_archetypes": ["wise elder"],
        "naming_style": "Arabic-inspired",
        "content_rating": "family",
    }
    client.put(f"/campaigns/{camp.id}/variables", headers=headers, json=vars_payload)

    # Generate NPC and check variables appear in context
    gen_res = client.post(
        "/generate/npc",
        headers=headers,
        json={"campaign_id": camp.id, "npc_type": "merchant"},
    )
    assert gen_res.status_code == 200, gen_res.text
    npc_data = gen_res.json()
    context = npc_data["npc"]["context"]
    assert context["themes"] == ["survival"]
    assert context["pacing"] == "slow"
    # faction data includes goals for goal-based NPC motivations
    assert len(context["factions"]) == 1
    assert context["factions"][0]["name"] == "Desert Wanderers"
    assert "find the lost oasis" in context["factions"][0]["goals"]
    assert context["naming_style"] == "Arabic-inspired"
