from fastapi.testclient import TestClient
import server.main as main

def _client():
    return TestClient(main.app)


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
