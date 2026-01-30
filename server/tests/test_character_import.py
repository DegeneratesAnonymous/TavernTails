import io

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.auth import create_access_token


def _client() -> TestClient:
    return TestClient(main.app)


def _ensure_user(email: str) -> None:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return
    user = db.create_user(
        email=email,
        password="secret",
        username=email.split("@")[0],
        profile={"name": email.split("@")[0], "email": email},
    )
    db.verify_user(email, user.verification_token)


def test_import_character_from_pasted_json():
    client = _client()
    email = "import-owner@example.com"
    _ensure_user(email)
    token = create_access_token(email)
    auth_headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/characters/import",
        headers=auth_headers,
        json={
            "raw_json": '{"name": "Imported One", "level": 3, "class_name": "Wizard"}',
            "ddb_url": "https://www.dndbeyond.com/characters/123456",
            "source": "paste",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["character"]["name"] == "Imported One"
    assert data["character"]["level"] == 3
    assert data["character"]["class_name"] == "Wizard"
    assert data["character"]["sheet"]["import"]["source"] == "paste"
    assert data["character"]["sheet"]["import"]["ddb_url"].endswith("/123456")


def test_import_character_from_file():
    client = _client()
    email = "import-owner-file@example.com"
    _ensure_user(email)
    token = create_access_token(email)
    auth_headers = {"Authorization": f"Bearer {token}"}

    payload = b'{"name":"File Import","level":2,"class":"Rogue"}'
    res = client.post(
        "/characters/import/file?source=file",
        headers=auth_headers,
        files={"file": ("character.json", io.BytesIO(payload), "application/json")},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["character"]["name"] == "File Import"
    assert data["character"]["level"] == 2
    assert data["character"]["class_name"] == "Rogue"
    assert data["character"]["sheet"]["import"]["source"] == "file"


def test_import_character_from_pdf_upload_best_effort():
    client = _client()
    email = "import-owner-pdf@example.com"
    _ensure_user(email)
    token = create_access_token(email)
    auth_headers = {"Authorization": f"Bearer {token}"}

    # We intentionally upload bytes that are NOT a real PDF.
    # The endpoint should still behave safely (best-effort) and create a character,
    # because it falls back to decoding bytes as text if PDF parsing fails.
    payload = b"Minsc\nLevel 3\nRanger\n"
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=auth_headers,
        files={"file": ("character.pdf", io.BytesIO(payload), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["character"]["name"] == "Minsc"
    assert data["character"]["level"] == 3
    assert data["character"]["class_name"] == "Ranger"
    assert data["character"]["sheet"]["import"]["source"] == "pdf"
    assert "raw_text" in data["character"]["sheet"]


def test_import_character_from_nested_classes_shape():
    client = _client()
    email = "import-owner-ddb@example.com"
    _ensure_user(email)
    token = create_access_token(email)
    auth_headers = {"Authorization": f"Bearer {token}"}

    raw = {
        "data": {
            "name": "DDB Nested",
            "classes": [
                {"name": "Fighter", "level": 5},
                {"name": "Wizard", "level": 1},
            ],
        }
    }

    res = client.post(
        "/characters/import",
        headers=auth_headers,
        json={
            "raw_json": __import__("json").dumps(raw),
            "source": "paste",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["character"]["name"] == "DDB Nested"
    assert data["character"]["level"] == 6
    assert data["character"]["class_name"] == "Fighter / Wizard"
