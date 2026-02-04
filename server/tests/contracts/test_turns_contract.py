from fastapi.testclient import TestClient

import server.main as main
from server import auth, db
from server.agents import sessions as sessions_agent


def _make_user_and_token():
    user = db.create_user(email="turns-qa@example.com", password="pw", username="turnsqa")
    token = auth.create_access_token(user.email)
    return user, token


def test_turns_contract_create_and_read():
    client = TestClient(main.app)
    user, token = _make_user_and_token()
    # create a session folder owned by this user so the membership checks pass
    sid, _meta = sessions_agent.create_session_folder(name="QA Session", owner_email=user.email)
    headers = {"Authorization": f"Bearer {token}"}
    # read turns (should return a TurnState shape)
    resp = client.get(f"/turns/{sid}", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "session_id" in data and data["session_id"] == sid
    assert "order" in data and isinstance(data["order"], list)
