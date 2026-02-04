import json

from fastapi.testclient import TestClient

import server.main as main
from server.tests import agent_payloads as payloads


def test_narrative_contract():
    client = TestClient(main.app)
    resp = client.post("/narrative/generate", json=payloads.NARRATIVE_REQUEST)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Basic contract expectations
    assert "narrative" in data
    assert isinstance(data["narrative"], str)
    assert "prompt" in data
    assert "tone" in data
