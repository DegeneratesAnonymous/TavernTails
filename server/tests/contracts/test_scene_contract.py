import json

from fastapi.testclient import TestClient

import server.main as main
from server.tests import agent_payloads as payloads


def test_scene_analyze_contract():
    client = TestClient(main.app)
    resp = client.post("/scene/analyze", json=payloads.SCENE_REQUEST)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "dice_rolls" in data and isinstance(data["dice_rolls"], list)
    assert "prompts" in data and isinstance(data["prompts"], list)
