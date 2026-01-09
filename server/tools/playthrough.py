"""Automated backend playthrough for signup -> verify -> login -> create session -> invite."""
import json
import time

from fastapi.testclient import TestClient

from server.main import app


def pretty(label: str, response):
    print(f"\n=== {label} ===")
    print("status:", response.status_code)
    try:
        payload = response.json()
    except Exception:
        payload = response.text
    print(json.dumps(payload, indent=2) if isinstance(payload, (dict, list)) else payload)
    return payload


def main():
    client = TestClient(app)
    ts = int(time.time())
    email = f"play{ts}@example.com"
    password = "secret123"
    name = "Play Tester"

    signup = client.post(
        "/player/signup",
        json={"email": email, "password": password, "name": name},
    )
    data = pretty("signup", signup)
    if signup.status_code != 200:
        return
    token = data.get("verification_token")
    verify = client.post("/player/verify-email", json={"email": email, "token": token})
    pretty("verify", verify)

    login = client.post("/player/login", json={"email": email, "password": password})
    login_data = pretty("login", login)
    if login.status_code != 200:
        return
    owner_token = login_data.get("access_token")
    headers = {"Authorization": f"Bearer {owner_token}"}

    session_name = f"Automated Session {ts}"
    create_session = client.post("/sessions", json={"name": session_name}, headers=headers)
    session_payload = pretty("create_session", create_session)
    if create_session.status_code != 201:
        return
    session_id = session_payload.get("id")

    invite = client.post(
        f"/sessions/{session_id}/invite",
        json={"email": "test@example.com"},
        headers=headers,
    )
    pretty("invite_dev", invite)

    dev_login = client.post(
        "/player/login", json={"email": "test@example.com", "password": "secret"}
    )
    dev_data = pretty("dev_login", dev_login)
    if dev_login.status_code != 200:
        return
    dev_headers = {"Authorization": f"Bearer {dev_data.get('access_token')}"}

    list_owner = client.get("/sessions", headers=headers)
    pretty("owner_sessions", list_owner)

    list_dev = client.get("/sessions", headers=dev_headers)
    pretty("dev_sessions", list_dev)


if __name__ == "__main__":
    main()
