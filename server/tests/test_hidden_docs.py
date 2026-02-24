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


# ---------------------------------------------------------------------------
# Category-driven default visibility (player information isolation model)
# ---------------------------------------------------------------------------

def test_gm_category_auto_hidden_without_explicit_visibility():
    """GM document categories must default to hidden even when visibility is not supplied."""
    client = _client()
    owner = "cat-gm-owner@example.com"
    _ensure_user(owner)
    sid, _ = sessions_module.create_session_folder("Cat GM Session", owner)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    for cat in ("gm_plot", "gm_npc", "gm_location", "gm_quest", "gm_notes"):
        resp = client.post(
            f"/documents/{sid}",
            headers=headers,
            json={"name": f"Test {cat}", "content": "secret", "category": cat},
            # NOTE: visibility is deliberately omitted — must auto-infer "hidden"
        )
        assert resp.status_code == 201, f"create {cat}: {resp.text}"
        assert resp.json()["visibility"] == "hidden", (
            f"Category '{cat}' should default to hidden, got {resp.json()['visibility']}"
        )


def test_player_category_auto_shared_without_explicit_visibility():
    """Player and world document categories must default to shared."""
    client = _client()
    owner = "cat-player-owner@example.com"
    _ensure_user(owner)
    sid, _ = sessions_module.create_session_folder("Cat Player Session", owner)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    for cat in ("player_npc", "player_location", "player_quest_log", "player_journal", "world_lore", "core"):
        resp = client.post(
            f"/documents/{sid}",
            headers=headers,
            json={"name": f"Test {cat}", "content": "visible", "category": cat},
        )
        assert resp.status_code == 201, f"create {cat}: {resp.text}"
        assert resp.json()["visibility"] == "shared", (
            f"Category '{cat}' should default to shared, got {resp.json()['visibility']}"
        )


def test_player_cannot_read_gm_category_docs():
    """Non-host players cannot read documents in GM categories, even without explicit hidden flag."""
    import json as _json

    client = _client()
    host = "isolation-host@example.com"
    player = "isolation-player@example.com"
    _ensure_user(host)
    _ensure_user(player)

    sid, _ = sessions_module.create_session_folder("Isolation Session", host)
    meta_path = sessions_module.BASE / sid / "meta.json"
    data = _json.loads(meta_path.read_text())
    data["invites"] = [player]
    meta_path.write_text(_json.dumps(data))

    host_headers = {"Authorization": f"Bearer {create_access_token(host)}"}
    player_headers = {"Authorization": f"Bearer {create_access_token(player)}"}

    # Host creates a full NPC profile (gm_npc — should auto-hide)
    resp = client.post(
        f"/documents/{sid}",
        headers=host_headers,
        json={"name": "Warlord Vrak — Full Profile", "content": "HP:120, motivation:revenge", "category": "gm_npc"},
    )
    assert resp.status_code == 201, resp.text
    gm_doc_id = resp.json()["id"]
    assert resp.json()["visibility"] == "hidden"

    # Host also creates a player-facing NPC card (player_npc — shared)
    resp = client.post(
        f"/documents/{sid}",
        headers=host_headers,
        json={"name": "Warlord Vrak — Appearance", "content": "Tall, scarred face, speaks in riddles.", "category": "player_npc"},
    )
    assert resp.status_code == 201, resp.text
    player_doc_id = resp.json()["id"]
    assert resp.json()["visibility"] == "shared"

    # Player can list documents — gm_npc is absent, player_npc is present
    list_resp = client.get(f"/documents/{sid}", headers=player_headers)
    assert list_resp.status_code == 200
    ids = [d["id"] for d in list_resp.json()]
    assert gm_doc_id not in ids, "Player should NOT see gm_npc document in list"
    assert player_doc_id in ids, "Player SHOULD see player_npc document in list"

    # Player cannot read the gm_npc document directly
    read_resp = client.get(f"/documents/{sid}/{gm_doc_id}", headers=player_headers)
    assert read_resp.status_code == 403, "Player must be denied reading gm_npc document"

    # Player can read the player_npc document
    read_resp = client.get(f"/documents/{sid}/{player_doc_id}", headers=player_headers)
    assert read_resp.status_code == 200
    assert "HP:120" not in read_resp.json()["content"], "Player NPC card must NOT contain GM stats"


def test_explicit_visibility_overrides_category_default():
    """Callers can explicitly override the category default in either direction."""
    client = _client()
    owner = "override-vis-owner@example.com"
    _ensure_user(owner)
    sid, _ = sessions_module.create_session_folder("Override Vis Session", owner)
    headers = {"Authorization": f"Bearer {create_access_token(owner)}"}

    # Force a core (normally shared) document to be hidden
    resp = client.post(
        f"/documents/{sid}",
        headers=headers,
        json={"name": "Private Core Doc", "content": "x", "category": "core", "visibility": "hidden"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["visibility"] == "hidden"

    # Force a gm_notes (normally hidden) document to be shared
    resp = client.post(
        f"/documents/{sid}",
        headers=headers,
        json={"name": "Public GM Note", "content": "y", "category": "gm_notes", "visibility": "shared"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["visibility"] == "shared"
