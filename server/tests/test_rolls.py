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
    user = db.create_user(
        email=email,
        password="secret",
        username=email.split("@")[0],
        profile={"name": email.split("@")[0], "email": email},
    )
    db.verify_user(email, user.verification_token)


def test_beyond20_uses_payload_totals(monkeypatch):
    client = _client()
    payload = {
        "session_id": "sess-123",
        "player": "Aria",
        "expression": "1d20+5",
        "rolls": [12],
        "modifier": 5,
        "total": 17,
    }
    resp = client.post("/integrations/beyond20/roll", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json().get("result", {})
    assert data["total"] == 17
    assert data["rolls"] == [12]
    assert data["mod"] == 5
    assert data["by"] == "Aria"
    assert data["source"] == "beyond20"


def test_beyond20_falls_back_to_parser(monkeypatch):
    client = _client()
    from server.agents import rolls as rolls_agent

    def fake_roll(_, __):
        return [3, 4]

    monkeypatch.setattr(rolls_agent, "_roll", fake_roll)
    resp = client.post("/integrations/beyond20/roll", json={"session_id": "sess-abc", "expression": "2d6+1"})
    assert resp.status_code == 200, resp.text
    data = resp.json().get("result", {})
    assert data["total"] == 8  # 3 + 4 + 1
    assert data["rolls"] == [3, 4]
    assert data["mod"] == 1
    assert data["source"] == "beyond20"


def test_roll_persists_with_session_campaign(monkeypatch):
    client = _client()
    owner = "roll-campaign-owner@example.com"
    _ensure_user(owner)
    user = db.get_user_by_identifier(owner)
    assert user is not None
    campaign = db.create_campaign(owner_id=user.id, name="Roll Campaign")
    sid, _meta = sessions_module.create_session_folder("Roll Session", owner, campaign_id=campaign.id)

    from server.agents import rolls as rolls_agent

    def fake_roll(_, __):
        return [12]

    monkeypatch.setattr(rolls_agent, "_roll", fake_roll)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    resp = client.post(
        "/rolls",
        headers=headers,
        json={"session_id": sid, "expression": "1d20+4", "reason": "Arcana"},
    )

    assert resp.status_code == 200, resp.text
    stored = db.list_rolls_for_campaign(campaign.id)
    assert any(r.expression == "1d20+4" and r.total == 16 for r in stored)
