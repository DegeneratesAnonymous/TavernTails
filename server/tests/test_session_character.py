from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents import sessions as sessions_module
from server.auth import create_access_token


def _client():
    return TestClient(main.app)


def _ensure_user(email: str) -> None:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return
    user = db.create_user(email=email, password="secret", username=email.split("@")[0], profile={"name": email.split("@")[0], "email": email})
    db.verify_user(email, user.verification_token)


def test_assign_character_to_session_member():
    client = _client()
    owner = "char-owner@example.com"
    _ensure_user(owner)

    owner_user = db.get_user_by_identifier(owner)
    assert owner_user is not None

    character = db.create_character(owner_id=owner_user.id, name="Sir Test", level=3, class_name="Fighter", sheet={})

    sid, _meta = sessions_module.create_session_folder("Character Session", owner)

    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(f"/sessions/{sid}/character", headers=headers, json={"character_id": character.id})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["character_id"] == character.id
    assert payload["character_name"] == "Sir Test"

    meta = client.get(f"/sessions/{sid}/meta", headers=headers).json()
    members = meta.get("members", [])
    assert any(m.get("character_id") == character.id for m in members)


def test_clear_character_assignment():
    client = _client()
    owner = "char-clear@example.com"
    _ensure_user(owner)

    sid, _meta = sessions_module.create_session_folder("Character Clear Session", owner)

    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(f"/sessions/{sid}/character", headers=headers, json={"character_id": None})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["character_id"] is None
    assert payload["character_name"] is None


def test_session_player_names_fall_back_to_meta_character_name():
    owner = "char-meta-name@example.com"
    _ensure_user(owner)
    sid, _meta = sessions_module.create_session_folder("Meta Character Session", owner)
    folder = sessions_module.BASE / sid
    meta_path = folder / "meta.json"
    meta = {
        "id": sid,
        "name": "Meta Character Session",
        "owner": owner,
        "members": [{"email": owner, "character_id": 123, "role": "owner", "character_name": "Yungmin"}],
    }
    meta_path.write_text(__import__("json").dumps(meta))
    (folder / "pcs.json").write_text("[]")

    assert sessions_module._session_player_names(folder, meta) == ["Yungmin"]


def test_invited_player_joins_with_character_and_can_join_again_with_other_character():
    client = _client()
    owner = "join-owner@example.com"
    player = "join-player@example.com"
    _ensure_user(owner)
    _ensure_user(player)

    player_user = db.get_user_by_identifier(player)
    assert player_user and player_user.id is not None
    first = db.create_character(owner_id=player_user.id, name="First Hero", level=2, class_name="Ranger", sheet={})
    second = db.create_character(owner_id=player_user.id, name="Second Hero", level=2, class_name="Wizard", sheet={})

    sid, _meta = sessions_module.create_session_folder("Join Character Session", owner, invites=[player])
    owner_headers = {"Authorization": f"Bearer {create_access_token(owner)}"}
    player_headers = {"Authorization": f"Bearer {create_access_token(player)}"}

    joined = client.post(f"/sessions/{sid}/join", headers=player_headers, json={"character_id": first.id})
    assert joined.status_code == 200, joined.text
    assert joined.json()["character_name"] == "First Hero"

    # A later invite to the same player should be accepted as an additional character.
    reinvite = client.post(f"/sessions/{sid}/invite", headers=owner_headers, json={"identifier": player})
    assert reinvite.status_code == 200, reinvite.text
    joined_again = client.post(f"/sessions/{sid}/join", headers=player_headers, json={"character_id": second.id})
    assert joined_again.status_code == 200, joined_again.text

    meta = client.get(f"/sessions/{sid}/meta", headers=owner_headers).json()
    player_members = [m for m in meta.get("members", []) if m.get("email") == player]
    assert {m.get("character_name") for m in player_members} >= {"First Hero", "Second Hero"}
    accepted = [i for i in meta.get("invites", []) if i.get("email") == player and i.get("accepted")]
    assert len(accepted) == 2
