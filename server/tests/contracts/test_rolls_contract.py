from fastapi.testclient import TestClient

import server.main as main
from server import auth, db


def _make_user_and_token():
    # create a simple dev user and token
    user = db.create_user(email="qa@example.com", password="pw", username="qa")
    token = auth.create_access_token(user.email)
    return user, token


def test_rolls_contract():
    client = TestClient(main.app)
    _, token = _make_user_and_token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/rolls", json={"expression": "1d6", "reason": "contract test"}, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "result" in data
    r = data["result"]
    assert r.get("expression") == "1d6"
    assert isinstance(r.get("rolls"), list)
    assert isinstance(r.get("total"), int)
