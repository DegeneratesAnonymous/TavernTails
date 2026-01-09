import json
from typing import Any, Dict

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents import sessions as sessions_module
from server.auth import create_access_token


def _ensure_user(email: str) -> None:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return
    user = db.create_user(email=email, password="secret", username=email.split("@")[0], profile={"name": email.split("@")[0], "email": email})
    db.verify_user(email, user.verification_token)


def _recv_until(ws, expected_type: str, max_messages: int = 10) -> Dict[str, Any]:
    last = None
    for _ in range(max_messages):
        raw = ws.receive_text()
        last = json.loads(raw)
        if last.get("type") == expected_type:
            return last
    raise AssertionError(f"Did not receive type={expected_type}. Last={last}")


def test_ws_event_contracts_for_session():
    client = TestClient(main.app)
    owner = "ws-owner@example.com"
    _ensure_user(owner)

    sid, _meta = sessions_module.create_session_folder("WS Contract Session", owner)

    token = create_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    with client.websocket_connect(f"/ws/sessions/{sid}?token={token}") as ws:
        # chat.message
        r = client.post("/chat", headers=headers, json={"message": "Hello @party", "session_id": sid, "role": "player"})
        assert r.status_code == 201, r.text
        msg = _recv_until(ws, "chat.message")
        assert msg["session_id"] == sid
        assert isinstance(msg.get("message"), dict)
        assert msg["message"].get("message") == "Hello @party"
        assert "id" in msg["message"]
        assert isinstance(msg["message"].get("mentions"), list)

        # rolls.result
        r = client.post("/rolls", headers=headers, json={"expression": "1d20", "reason": "test", "session_id": sid})
        assert r.status_code == 200, r.text
        roll_evt = _recv_until(ws, "rolls.result")
        assert roll_evt["session_id"] == sid
        assert isinstance(roll_evt.get("result"), dict)
        assert roll_evt["result"].get("expression") == "1d20"
        assert isinstance(roll_evt["result"].get("rolls"), list)
        assert isinstance(roll_evt["result"].get("total"), int)

        # turns.update
        r = client.post(f"/turns/{sid}", headers=headers, json={"order": ["A", "B"], "active_index": 0})
        assert r.status_code == 200, r.text
        turns_evt = _recv_until(ws, "turns.update")
        assert turns_evt["session_id"] == sid
        assert turns_evt.get("order") == ["A", "B"]
        assert isinstance(turns_evt.get("active_index"), int)

        # suggestions.update
        r = client.get("/suggestions", headers=headers, params={"session_id": sid, "limit": 4})
        assert r.status_code == 200, r.text
        sugg_evt = _recv_until(ws, "suggestions.update")
        assert sugg_evt["session_id"] == sid
        assert isinstance(sugg_evt.get("suggestions"), list)
        assert isinstance(sugg_evt.get("source"), str)

        # scene.cues
        r = client.post("/scene/analyze", json={"scene": "A tense standoff", "actions": ["attack"], "session_id": sid})
        assert r.status_code == 200, r.text
        scene_evt = _recv_until(ws, "scene.cues")
        assert scene_evt["session_id"] == sid
        assert isinstance(scene_evt.get("dice_rolls"), list)
        assert isinstance(scene_evt.get("prompts"), list)

        # npc.profile
        r = client.post("/npc/manage", json={"name": "Goblin", "traits": {}, "motivations": [], "stats": {"initiative": 2}, "quirks": [], "session_id": sid})
        assert r.status_code == 200, r.text
        npc_evt = _recv_until(ws, "npc.profile")
        assert npc_evt["session_id"] == sid
        assert isinstance(npc_evt.get("profile"), dict)
        assert npc_evt["profile"].get("name") == "Goblin"
        assert isinstance(npc_evt.get("initiative_hint"), str)
