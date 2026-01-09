from pathlib import Path

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
            # make sure tests don't fail due to unverified user
            db.verify_user(email, existing.verification_token or "")
        return
    user = db.create_user(email=email, password="secret", username=email.split("@")[0], profile={"name": email.split("@")[0], "email": email})
    db.verify_user(email, user.verification_token)


def test_hidden_docs_are_host_only(tmp_path):
    client = _client()
    owner = "test@example.com"
    other = "friend@example.com"
    _ensure_user(other)

    sid, meta = sessions_module.create_session_folder("Hidden Doc Session", owner)
    # invite other user so they're a session member but not a host
    meta_path = sessions_module.BASE / sid / "meta.json"
    data = __import__("json").loads(meta_path.read_text())
    data["invites"] = [other]
    meta_path.write_text(__import__("json").dumps(data))

    owner_token = create_access_token(owner)
    other_token = create_access_token(other)

    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # owner can create hidden doc
    resp = client.post(
        f"/documents/{sid}",
        headers=owner_headers,
        json={"name": "GM Secrets", "content": "Top secret", "category": "core", "visibility": "hidden"},
    )
    assert resp.status_code == 201, resp.text
    saved = resp.json()
    assert saved["visibility"] == "hidden"

    # non-host cannot list hidden docs
    resp = client.get(f"/documents/{sid}", headers=other_headers)
    assert resp.status_code == 200, resp.text
    docs = resp.json()
    assert all(d.get("visibility") != "hidden" for d in docs)

    # non-host cannot read hidden doc
    resp = client.get(f"/documents/{sid}/{saved['id']}", headers=other_headers)
    assert resp.status_code == 403

    # non-host cannot create hidden doc
    resp = client.post(
        f"/documents/{sid}",
        headers=other_headers,
        json={"name": "Bad", "content": "nope", "visibility": "hidden"},
    )
    assert resp.status_code == 403

    # audit file exists and has at least one record
    audit_path = sessions_module.BASE / sid / "document_access.jsonl"
    assert audit_path.exists()
    assert audit_path.read_text(encoding="utf-8").strip()
