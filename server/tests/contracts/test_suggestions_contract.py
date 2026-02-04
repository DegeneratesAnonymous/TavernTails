from fastapi.testclient import TestClient

import server.main as main
from server import db, auth


def _make_user_and_token():
    user = db.create_user(email="qa2@example.com", password="pw", username="qa2")
    token = auth.create_access_token(user.email)
    return user, token


def test_suggestions_contract():
    client = TestClient(main.app)
    _, token = _make_user_and_token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/suggestions?limit=3", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "suggestions" in data and isinstance(data["suggestions"], list)
    assert "source" in data and isinstance(data["source"], str)
