"""The brief a player answers and the scene they start in come from one seed; /player/me names the caller."""
from __future__ import annotations

import json

from server.agents import sessions
from server.tests.test_opening_setup import _auth, _client, _create_campaign_session


def test_opening_questionnaire_keeps_the_seed_its_brief_was_built_from():
    client = _client()
    email = "opening-seed@example.com"
    session_id, _ = _create_campaign_session(client, email, "Seed Scout")
    response = client.get(f"/sessions/{session_id}/opening-setup", headers=_auth(email))
    assert response.status_code == 200, response.text
    meta = json.loads((sessions.BASE / session_id / "meta.json").read_text())
    seed = meta["opening_setup"].get("seed")
    assert isinstance(seed, dict) and seed.get("starting_location")
    brief = response.json()["questionnaire"]["campaign_brief"]
    assert brief["location_name"] == seed["starting_location"]

    # Asking again must not draw a different place.
    again = client.get(f"/sessions/{session_id}/opening-setup", headers=_auth(email)).json()["questionnaire"]["campaign_brief"]
    assert again["location_name"] == brief["location_name"]


def test_submitting_the_setup_keeps_the_seed_for_session_start():
    client = _client()
    email = "opening-seed-submit@example.com"
    session_id, _ = _create_campaign_session(client, email, "Seed Submitter")
    headers = _auth(email)
    questionnaire = client.get(f"/sessions/{session_id}/opening-setup", headers=headers).json()["questionnaire"]
    seed_before = json.loads((sessions.BASE / session_id / "meta.json").read_text())["opening_setup"]["seed"]
    done = client.post(f"/sessions/{session_id}/opening-setup/skip", headers=headers, json={})
    assert done.status_code == 200, done.text
    meta = json.loads((sessions.BASE / session_id / "meta.json").read_text())
    assert meta["opening_setup"]["completed"] is True
    assert meta["opening_setup"]["seed"] == seed_before
    assert meta["session_start_context"]["campaign_brief"]["location_name"] == questionnaire["campaign_brief"]["location_name"]


def test_player_me_includes_the_identity_clients_match_party_members_on():
    client = _client()
    email = "who-am-i@example.com"
    _create_campaign_session(client, email, "Identity Scout")
    profile = client.get("/player/me", headers=_auth(email)).json()["profile"]
    assert profile["email"] == email and profile["username"] == "who-am-i"


def test_session_start_opens_where_the_brief_said(monkeypatch):
    """Every fresh draw of the opening seed names a different place; start must not make a second draw."""
    from server import steward_llm
    from server.agents import content_bundles

    real = content_bundles.generate_starter_seed
    draws: list[str] = []

    def drifting(*args, **kwargs):
        seed = dict(real(*args, **kwargs))
        place = f"Drifting Hollow {len(draws)}"
        draws.append(place)
        seed["starting_location"] = place
        return seed

    monkeypatch.setattr(content_bundles, "generate_starter_seed", drifting)
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: None)  # deterministic opening path
    client = _client()
    email = "opening-start@example.com"
    session_id, _ = _create_campaign_session(client, email, "Start Scout")
    headers = _auth(email)
    questionnaire = client.get(f"/sessions/{session_id}/opening-setup", headers=headers).json()["questionnaire"]
    seeded = draws[0]
    assert client.post(f"/sessions/{session_id}/opening-setup/skip", headers=headers, json={}).status_code == 200
    started = client.post(f"/sessions/{session_id}/start", headers=headers, json={})
    assert started.status_code == 200, started.text
    assert draws == [seeded], f"start drew the opening seed again: {draws}"
    assert seeded in json.dumps(started.json()["scene"])
    assert seeded in json.dumps(questionnaire["campaign_brief"])
