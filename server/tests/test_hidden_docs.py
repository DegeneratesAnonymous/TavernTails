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


def test_hidden_doc_delete_rbac():
    """Host can delete hidden docs; non-host members cannot."""
    client = _client()
    owner = "del-host@example.com"
    other = "del-nonhost@example.com"
    _ensure_user(owner)
    _ensure_user(other)

    sid, _ = sessions_module.create_session_folder("Delete RBAC Session", owner)
    import json as _json
    meta_path = sessions_module.BASE / sid / "meta.json"
    data = _json.loads(meta_path.read_text())
    data["invites"] = [other]
    meta_path.write_text(_json.dumps(data))

    owner_headers = {"Authorization": f"Bearer {create_access_token(owner)}"}
    other_headers = {"Authorization": f"Bearer {create_access_token(other)}"}

    # create a hidden doc as host
    resp = client.post(
        f"/documents/{sid}",
        headers=owner_headers,
        json={"name": "Deletable", "content": "bye", "visibility": "hidden"},
    )
    assert resp.status_code == 201, resp.text
    doc_id = resp.json()["id"]

    # non-host cannot delete it
    resp = client.delete(f"/documents/{sid}/{doc_id}", headers=other_headers)
    assert resp.status_code == 403, resp.text

    # host can delete it
    resp = client.delete(f"/documents/{sid}/{doc_id}", headers=owner_headers)
    assert resp.status_code == 200, resp.text


def test_audit_entries_contain_expected_fields():
    """Audit entries have ok, action, actor, ts; denied actions also logged."""
    client = _client()
    owner = "audit-fields-host@example.com"
    other = "audit-fields-nonhost@example.com"
    _ensure_user(owner)
    _ensure_user(other)

    sid, _ = sessions_module.create_session_folder("Audit Fields Session", owner)
    import json as _json
    meta_path = sessions_module.BASE / sid / "meta.json"
    data = _json.loads(meta_path.read_text())
    data["invites"] = [other]
    meta_path.write_text(_json.dumps(data))

    owner_headers = {"Authorization": f"Bearer {create_access_token(owner)}"}
    other_headers = {"Authorization": f"Bearer {create_access_token(other)}"}

    # host creates hidden doc
    resp = client.post(
        f"/documents/{sid}",
        headers=owner_headers,
        json={"name": "AuditDoc", "content": "x", "visibility": "hidden"},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    # non-host tries to read it (should be denied)
    client.get(f"/documents/{sid}/{doc_id}", headers=other_headers)

    # read audit log as host
    resp = client.get(f"/documents/{sid}/audit", headers=owner_headers)
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) > 0
    actions = {e["action"] for e in entries}
    # should have at least one create and one denied-read
    assert "documents.create" in actions
    assert "documents.read" in actions or "documents.hidden_denied" in actions
    for entry in entries:
        assert "ok" in entry
        assert isinstance(entry["ok"], bool)
        assert "ts" in entry
        assert "actor" in entry
        assert "action" in entry


def test_audit_endpoint_host_only():
    """GET /documents/{session_id}/audit is host-only."""
    client = _client()
    owner = "audit-host@example.com"
    other = "audit-nonhost@example.com"
    _ensure_user(owner)
    _ensure_user(other)

    sid, _meta = sessions_module.create_session_folder("Audit Test Session", owner)
    # Add other user as a non-host member
    import json as _json
    meta_path = sessions_module.BASE / sid / "meta.json"
    data = _json.loads(meta_path.read_text())
    data["invites"] = [other]
    meta_path.write_text(_json.dumps(data))

    owner_headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    # Create a hidden doc so there's something in the audit trail
    resp = client.post(
        f"/documents/{sid}",
        headers=owner_headers,
        json={"name": "Secret", "content": "x", "visibility": "hidden"},
    )
    assert resp.status_code == 201, resp.text

    # Host can read audit log
    resp = client.get(f"/documents/{sid}/audit", headers=owner_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "entries" in data
    assert isinstance(data["entries"], list)
    assert len(data["entries"]) > 0
    # Every entry should have at minimum ts, actor, action
    for entry in data["entries"]:
        assert "ts" in entry
        assert "actor" in entry
        assert "action" in entry


def test_audit_endpoint_non_host_forbidden():
    """Non-host session members must receive 403 from the audit endpoint."""
    client = _client()
    owner = "audit-host2@example.com"
    other = "audit-nonhost2@example.com"
    _ensure_user(owner)
    _ensure_user(other)

    sid, _meta = sessions_module.create_session_folder("Audit RBAC Session", owner)
    import json as _json
    meta_path = sessions_module.BASE / sid / "meta.json"
    data = _json.loads(meta_path.read_text())
    data["invites"] = [other]
    meta_path.write_text(_json.dumps(data))

    other_headers = {"Authorization": f"Bearer {create_access_token(other)}"}
    resp = client.get(f"/documents/{sid}/audit", headers=other_headers)
    assert resp.status_code == 403, resp.text


def test_audit_endpoint_non_member_forbidden():
    """Users not in the session must receive 403 from the audit endpoint."""
    client = _client()
    owner = "audit-host3@example.com"
    stranger = "audit-stranger@example.com"
    _ensure_user(owner)
    _ensure_user(stranger)

    sid, _meta = sessions_module.create_session_folder("Audit Stranger Session", owner)

    stranger_headers = {"Authorization": f"Bearer {create_access_token(stranger)}"}
    resp = client.get(f"/documents/{sid}/audit", headers=stranger_headers)
    assert resp.status_code == 403, resp.text
