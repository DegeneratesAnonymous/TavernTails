from fastapi.testclient import TestClient

import server.main as main
from server.tests import agent_payloads as payloads


def test_npc_manage_contract():
    client = TestClient(main.app)
    resp = client.post("/npc/manage", json=payloads.NPC_REQUEST)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "npc_profile" in data and isinstance(data["npc_profile"], dict)
    assert "initiative_hint" in data and isinstance(data["initiative_hint"], str)
