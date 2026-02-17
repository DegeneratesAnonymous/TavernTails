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


def test_preview_import_character_from_pasted_json_does_not_create_character():
    client = _client()
    email = "import-preview-owner@example.com"
    _ensure_user(email)
    token = create_access_token(email)
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Preview
    res = client.post(
        "/characters/import/preview",
        headers=auth_headers,
        json={
            "raw_json": '{"name": "Preview One", "level": 4, "class_name": "Cleric"}',
            "ddb_url": "https://www.dndbeyond.com/characters/999",
            "source": "paste",
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["preview"]["name"] == "Preview One"
    assert data["preview"]["level"] == 4
    assert data["preview"]["class_name"] == "Cleric"
    assert data["preview"]["sheet"]["import"]["source"] == "paste"

    # No new character should exist unless we explicitly create one.
    list_res = client.get("/characters", headers=auth_headers)
    assert list_res.status_code == 200, list_res.text
    names = [c["name"] for c in list_res.json().get("characters", [])]
    assert "Preview One" not in names


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


def test_preview_import_character_from_pdf_upload_best_effort():
    client = _client()
    email = "import-preview-owner-pdf@example.com"
    _ensure_user(email)
    token = create_access_token(email)
    auth_headers = {"Authorization": f"Bearer {token}"}

    payload = b"Minsc\nLevel 3\nRanger\n"
    res = client.post(
        "/characters/import/pdf/preview?source=pdf",
        headers=auth_headers,
        files={"file": ("character.pdf", io.BytesIO(payload), "application/pdf")},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["preview"]["name"] == "Minsc"
    assert data["preview"]["level"] == 3
    assert data["preview"]["class_name"] == "Ranger"
    assert "raw_text" in data["preview"]["sheet"]


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
    add_widget("STR", "15", y=640.0)
    add_widget("DEX", "14", y=610.0)
    add_widget("Armor Class", "17", y=595.0)
    add_widget("Current Hit Points", "21", y=575.0)
    add_widget("Hit Point Maximum", "28", y=555.0)
    add_widget("Passive Perception", "14", y=540.0)
    add_widget("Passive Insight", "12", y=525.0)
    add_widget("Passive Investigation", "13", y=510.0)
    add_widget("Race", "Elf", y=495.0)
    add_widget("Background", "Acolyte", y=480.0)
    add_widget("Weight Carried", "120", y=465.0)
    add_widget("Encumbered", "150", y=450.0)
    add_widget("Heavily Encumbered", "200", y=435.0)
    add_widget("Personality Traits", "Curious", y=420.0)
    add_widget("Ideals", "Justice", y=405.0)
    add_widget("Bonds", "Temple", y=390.0)
    add_widget("Flaws", "Stubborn", y=375.0)
    add_widget("Allies & Organizations", "Harpers", y=360.0)
    add_widget("Features & Traits", "Darkvision\nSecond Wind", y=535.0)
    add_widget("spellName0", "Magic Missile", y=515.0)
    add_widget("spellComponents0", "V,S", y=495.0)

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
    assert data["character"]["sheet"]["stats"]["str"] == 15
    assert data["character"]["sheet"]["stats"]["dex"] == 14
    assert data["character"]["sheet"]["ac"] == 17
    assert data["character"]["sheet"]["hp"]["current"] == 21
    assert data["character"]["sheet"]["hp"]["max"] == 28
    assert data["character"]["sheet"]["passives"]["perception"] == 14
    assert data["character"]["sheet"]["passives"]["insight"] == 12
    assert data["character"]["sheet"]["passives"]["investigation"] == 13
    assert data["character"]["sheet"]["species"] == "Elf"
    assert data["character"]["sheet"]["background"] == "Acolyte"
    assert data["character"]["sheet"]["carry"]["weight_current"] == 120
    assert data["character"]["sheet"]["carry"]["encumbered_at"] == 150
    assert data["character"]["sheet"]["carry"]["heavily_encumbered_at"] == 200
    assert data["character"]["sheet"]["story"]["personality_traits"] == "Curious"
    assert data["character"]["sheet"]["story"]["ideals"] == "Justice"
    assert data["character"]["sheet"]["story"]["bonds"] == "Temple"
    assert data["character"]["sheet"]["story"]["flaws"] == "Stubborn"
    assert data["character"]["sheet"]["story"]["allies"] == "Harpers"
    assert any(entry.get("class_name") == "Druid" and entry.get("level") == 4 for entry in data["character"]["sheet"]["multiclass"])
    assert any(entry.get("class_name") == "Cleric" and entry.get("level") == 2 for entry in data["character"]["sheet"]["multiclass"])
    assert "Darkvision" in data["character"]["sheet"]["features"]
    assert "Magic Missile" in data["character"]["sheet"]["spells"]
    assert "V,S" not in data["character"]["sheet"]["spells"]

    def test_spell_table_text_parsing():
        from server.agents.characters import _extract_spellbook_from_text

        text = """
        PREP SPELL NAME        SOURCE   SAVE/ATK   TIME   RANGE   COMP   DURATION   PAGE REF   NOTES
        O Shillelagh           Druid    +6         1BA    Touch   V,S,M  1 minute   PHB 275    D: 1m, V/S/M
        O Shape Water          Druid    --         1A     30 ft.  V,S    Instant    EE 164     5 ft. Cube, V/S
        === 1ST LEVEL ===
        O Cure Wounds          Druid    --         1A     Touch   V,S    Instant    PHB 230    V/S
        """

        entries = _extract_spellbook_from_text(text)
        assert len(entries) >= 3
        assert entries[0]["name"] == "Shillelagh"
        assert entries[0]["source"] == "Druid"
        assert entries[0]["time"] == "1BA"
        assert entries[0]["range"] == "Touch"
        assert entries[0]["components"] == "V,S,M"
        assert entries[0]["duration"] == "1 minute"
        assert entries[0]["page"] == "PHB 275"
        assert "D: 1m" in (entries[0]["notes"] or "")


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
