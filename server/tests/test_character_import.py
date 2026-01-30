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


def test_import_character_from_pdf_uses_filename_fallback_and_allows_overrides():
    client = _client()
    email = "import-owner-pdf-filename@example.com"
    _ensure_user(email)
    token = create_access_token(email)
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Template-like content should NOT become the character name.
    payload = b"CLASS & LEVEL PLAYER NAME\nCHARACTER NAME SPECIES BACKGROUND\n"
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=auth_headers,
        files={"file": ("spaceman_wil_91460971.pdf", io.BytesIO(payload), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["character"]["name"] == "Spaceman Wil"
    assert data["character"]["level"] == 1

    # Overrides should win even when extraction is poor.
    res2 = client.post(
        "/characters/import/pdf?source=pdf",
        headers=auth_headers,
        data={"name": "Custom Name", "level": "5", "class_name": "Wizard"},
        files={"file": ("blank.pdf", io.BytesIO(payload), "application/pdf")},
    )
    assert res2.status_code == 201, res2.text
    data2 = res2.json()
    assert data2["character"]["name"] == "Custom Name"
    assert data2["character"]["level"] == 5
    assert data2["character"]["class_name"] == "Wizard"


def test_import_character_from_pdf_extracts_widget_values():
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

    client = _client()
    email = "import-owner-pdf-widgets@example.com"
    _ensure_user(email)
    token = create_access_token(email)
    auth_headers = {"Authorization": f"Bearer {token}"}

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    def add_widget(field_name: str, value: str, y: float) -> None:
        annot = DictionaryObject()
        annot.update(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/T"): TextStringObject(field_name),
                NameObject("/V"): TextStringObject(value),
                NameObject("/Rect"): ArrayObject(
                    [FloatObject(50.0), FloatObject(y), FloatObject(300.0), FloatObject(y + 20.0)]
                ),
            }
        )
        ref = writer._add_object(annot)  # noqa: SLF001
        annots = page.get("/Annots")
        if annots is None:
            page[NameObject("/Annots")] = ArrayObject([ref])
        else:
            annots.append(ref)

    add_widget("CharacterName", "Launk", y=700.0)
    add_widget("CLASS  LEVEL", "Druid 4 / Cleric 2", y=670.0)

    bio = io.BytesIO()
    writer.write(bio)
    bio.seek(0)

    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=auth_headers,
        files={"file": ("ddb.pdf", bio, "application/pdf")},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["character"]["name"] == "Launk"
    assert data["character"]["level"] == 6
    assert data["character"]["class_name"] == "Druid / Cleric"


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
