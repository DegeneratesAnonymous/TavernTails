"""Tests for Starfinder PDF character sheet import.

Covers the Starfinder-specific import path in ``server/agents/characters.py``
using synthetic PDFs built with pypdf widget annotations so the test suite can
run in CI without the real Paizo fillable character sheet PDF.

Dedicated test users:
  sf-import@example.com / sf-import

Seed-user import tests verify that the ``seed_starfinder_characters`` script
correctly creates Navasi for both ``bilbo@example.com`` and
``admin@example.com``.

Key Starfinder fields tested:
- ``sheet.system.name == "Starfinder"``
- ``sheet.import.source == "pdf"``
- Ability scores (shared schema)
- ``starfinder_stamina`` / ``starfinder_resolve`` (namespaced, no 5e equivalent)
- ``starfinder_kac`` / ``starfinder_eac`` (namespaced)
- ``starfinder_theme`` (namespaced)
- Saving throws as integer totals
- Skills with ranks and totals
- Feats (flat list)
- Class features
- Equipment list
- Bulk encumbrance
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents.system_detect import infer_ttrpg_system
from server.auth import create_access_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client() -> TestClient:
    return TestClient(main.app)


def _ensure_user(email: str, username: str) -> None:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return
    user = db.create_user(
        email=email,
        password="secret",
        username=username,
        profile={"name": username, "email": email},
    )
    db.verify_user(email, user.verification_token)


def _make_widget_pdf(widget_map: dict[str, str]) -> bytes:
    """Build a minimal PDF with interactive widget annotations from *widget_map*."""
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    y = 750.0
    for field_name, value in widget_map.items():
        annot = DictionaryObject()
        annot.update(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/T"): TextStringObject(field_name),
                NameObject("/V"): TextStringObject(value),
                NameObject("/Rect"): ArrayObject(
                    [FloatObject(50.0), FloatObject(y), FloatObject(500.0), FloatObject(y + 18.0)]
                ),
            }
        )
        ref = writer._add_object(annot)  # noqa: SLF001
        annots = page.get("/Annots")
        if annots is None:
            page[NameObject("/Annots")] = ArrayObject([ref])
        else:
            annots.append(ref)
        y -= 20.0
        if y < 20.0:
            y = 750.0

    bio = io.BytesIO()
    writer.write(bio)
    bio.seek(0)
    return bio.read()


def _make_starfinder_pdf(fields: dict[str, str]) -> bytes:
    """Build a synthetic Starfinder character sheet PDF with the given field values.

    Always injects the Starfinder-unique widget keys (Stamina Points, Resolve
    Points, EAC, KAC) as disambiguation signals so the importer detects the
    correct system.
    """
    base: dict[str, str] = {
        # Starfinder system signals for detection
        "SP Max": "",
        "SP Current": "",
        "RP Max": "",
        "RP Current": "",
        "EAC": "",
        "KAC": "",
        "Theme": "",
    }
    base.update(fields)
    return _make_widget_pdf(base)


# ---------------------------------------------------------------------------
# Fixture widget values (Navasi — iconic Envoy)
# ---------------------------------------------------------------------------

SF_EMAIL = "sf-import@example.com"
SF_USERNAME = "sf-import"

SF_WIDGETS: dict[str, str] = {
    # Identity
    "CharacterName": "Navasi",
    "CLASS  LEVEL": "Envoy 5",
    "Race": "Human",
    "Theme": "Spacefarer",
    "Homeworld": "Absalom Station",
    # Ability scores
    "STR": "10",
    "DEX": "16",
    "CON": "12",
    "INT": "14",
    "WIS": "12",
    "CHA": "18",
    # Hit Points (shared schema)
    "HP Max": "38",
    "HP Current": "38",
    # Stamina Points (Starfinder-specific)
    "SP Max": "38",
    "SP Current": "30",
    # Resolve Points (Starfinder-specific)
    "RP Max": "6",
    "RP Current": "4",
    # Armor Class (Starfinder-specific dual AC)
    "EAC": "16",
    "KAC": "17",
    # Saves
    "Fort": "3",
    "Ref": "7",
    "Will": "5",
    # Skills
    "Bluff Ranks": "5",
    "Bluff Total": "11",
    "Computers Ranks": "5",
    "Computers Total": "9",
    "Diplomacy Ranks": "5",
    "Diplomacy Total": "13",
    "Perception Ranks": "5",
    "Perception Total": "8",
    "Stealth Ranks": "2",
    "Stealth Total": "7",
    # Feats
    "Feat 1": "Skill Focus (Diplomacy)",
    "Feat 2": "Improved Initiative",
    # Class features
    "Class Feature 1": "Expertise",
    "Class Feature 2": "Get 'Em",
    # Equipment
    "Weapon 1": "Tactical Pistol",
    "Armor": "Lashunta Ringwear I",
    "Equipment 1": "Personal Comm Unit",
    # Bulk
    "Current Bulk": "4",
    "Bulk Limit": "10",
}


# ---------------------------------------------------------------------------
# System detection tests
# ---------------------------------------------------------------------------


def test_starfinder_system_detection_from_class():
    """Starfinder sheet should be detected from class name alone."""
    result = infer_ttrpg_system({"class_name": "Envoy"})
    assert result["system_name"] == "Starfinder"


def test_starfinder_system_detection_from_all_classes():
    """All Starfinder class names should resolve to Starfinder."""
    sf_classes = [
        "Biohacker", "Envoy", "Evolutionist", "Mechanic", "Mystic",
        "Nanocyte", "Operative", "Precog", "Solarian", "Soldier",
        "Technomancer", "Vanguard", "Witchwarper",
    ]
    for class_name in sf_classes:
        result = infer_ttrpg_system({"class_name": class_name})
        assert result["system_name"] == "Starfinder", (
            f"Class '{class_name}' detected as '{result['system_name']}' instead of 'Starfinder'"
        )


def test_starfinder_system_detection_from_widget_signals():
    """Stamina/Resolve/EAC/KAC widget keys must tip detection to Starfinder."""
    sheet = {
        "class_name": "Soldier",
        "widget_keys": ["SP Max", "SP Current", "RP Max", "RP Current", "EAC", "KAC", "Theme"],
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Starfinder", (
        f"Expected 'Starfinder' but got '{result['system_name']}' "
        f"(evidence: {result['evidence']})"
    )


def test_starfinder_detection_not_confused_with_pathfinder():
    """A sheet with PF2e-exclusive widget keys should NOT detect as Starfinder."""
    sheet = {
        "class_name": "Fighter",
        "widget_keys": ["Ancestry", "Heritage", "Proficiency Rank Athletics", "Focus Points Max"],
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] != "Starfinder"


# ---------------------------------------------------------------------------
# Import endpoint tests — system and metadata
# ---------------------------------------------------------------------------


def test_starfinder_system_detection_after_import():
    """After importing a Starfinder sheet the system name should be 'Starfinder'."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["system"]["name"] == "Starfinder", f"Got system: {sheet.get('system')}"


def test_starfinder_import_metadata():
    """Import metadata should record source=pdf and system=Starfinder."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf_meta.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["import"]["source"] == "pdf"
    assert sheet["system"]["name"] == "Starfinder"


# ---------------------------------------------------------------------------
# Field extraction tests
# ---------------------------------------------------------------------------


def test_starfinder_character_name():
    """Character name should be extracted from the CharacterName widget."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    assert res.json()["character"]["name"] == "Navasi"


def test_starfinder_ability_scores():
    """Ability scores should be stored under sheet['stats'] (shared schema)."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    stats = res.json()["character"]["sheet"]["stats"]
    assert stats["str"] == 10
    assert stats["dex"] == 16
    assert stats["cha"] == 18


def test_starfinder_stamina_points():
    """Stamina points should be stored under sheet['starfinder_stamina'] (namespaced)."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert "starfinder_stamina" in sheet, "starfinder_stamina key missing from sheet"
    stamina = sheet["starfinder_stamina"]
    assert stamina["max"] == 38
    assert stamina["current"] == 30


def test_starfinder_resolve_points():
    """Resolve points should be stored under sheet['starfinder_resolve'] (namespaced)."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert "starfinder_resolve" in sheet, "starfinder_resolve key missing from sheet"
    resolve = sheet["starfinder_resolve"]
    assert resolve["max"] == 6
    assert resolve["current"] == 4


def test_starfinder_kac_and_eac():
    """KAC and EAC should be stored under namespaced sheet keys."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["starfinder_kac"] == 17
    assert sheet["starfinder_eac"] == 16


def test_starfinder_theme():
    """Theme should be stored under sheet['starfinder_theme'] (namespaced)."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    assert res.json()["character"]["sheet"]["starfinder_theme"] == "Spacefarer"


def test_starfinder_saves():
    """Saving throws should be integer totals (no proficiency ranks)."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    saves = res.json()["character"]["sheet"]["saves"]
    assert saves["fort"] == 3
    assert saves["ref"] == 7
    assert saves["will"] == 5


def test_starfinder_skills():
    """Skills should carry explicit integer ranks and totals."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    skills = res.json()["character"]["sheet"]["skills"]
    assert skills["Diplomacy"]["ranks"] == 5
    assert skills["Diplomacy"]["total"] == 13
    assert skills["Perception"]["ranks"] == 5
    assert skills["Bluff"]["total"] == 11


def test_starfinder_feats_flat_list():
    """Feats should be a flat list (Starfinder does not categorise feats like PF2e)."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    feats = res.json()["character"]["sheet"]["feats"]
    assert isinstance(feats, list)
    assert "Improved Initiative" in feats


def test_starfinder_class_features():
    """Class features should be captured as a list."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    features = res.json()["character"]["sheet"]["class_features"]
    assert "Expertise" in features
    assert "Get 'Em" in features


def test_starfinder_equipment():
    """Equipment list should include weapons and gear."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    equipment = res.json()["character"]["sheet"]["equipment"]
    assert "Tactical Pistol" in equipment


def test_starfinder_bulk():
    """Bulk current and limit should be populated."""
    client = _client()
    _ensure_user(SF_EMAIL, SF_USERNAME)
    token = create_access_token(SF_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["bulk"]["current"] == 4
    assert sheet["bulk"]["limit"] == 10


def test_starfinder_preview_endpoint():
    """The preview endpoint should return Starfinder structure without persisting."""
    client = _client()
    preview_email = "sf-import-preview@example.com"
    _ensure_user(preview_email, "sf-import-preview")
    token = create_access_token(preview_email)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_starfinder_pdf(SF_WIDGETS)
    res = client.post(
        "/characters/import/pdf/preview?source=pdf",
        headers=headers,
        files={"file": ("navasi_sf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 200, res.text
    preview = res.json()["preview"]
    assert preview["sheet"]["system"]["name"] == "Starfinder"
    assert preview["sheet"]["import"]["source"] == "pdf"

    # Confirm nothing was persisted for the preview-only user
    list_res = client.get("/characters", headers=headers)
    assert list_res.status_code == 200
    names = [c["name"] for c in list_res.json().get("characters", [])]
    assert "Navasi" not in names


# ---------------------------------------------------------------------------
# Seed-user import tests
# ---------------------------------------------------------------------------


def test_seed_navasi_for_bilbo():
    """seed_starfinder_characters should create a Navasi character for bilbo@example.com."""
    from server.scripts.seed_starfinder_characters import seed_starfinder_characters

    # Run the seeder (idempotent — safe to call multiple times)
    seed_starfinder_characters()

    bilbo_email = "bilbo@example.com"
    user = db.get_user_by_identifier(bilbo_email)
    assert user is not None, "bilbo@example.com seed user not found"

    chars = db.list_characters_for_user(user.id)
    navasi_chars = [c for c in chars if c.name == "Navasi"]
    assert len(navasi_chars) >= 1, f"No Navasi character found for {bilbo_email}"

    sheet = navasi_chars[0].sheet or {}
    assert (sheet.get("system") or {}).get("name") == "Starfinder"
    assert "starfinder_stamina" in sheet
    assert "starfinder_resolve" in sheet


def test_seed_navasi_for_admin():
    """seed_starfinder_characters should create a Navasi character for admin@example.com."""
    from server.scripts.seed_starfinder_characters import seed_starfinder_characters

    seed_starfinder_characters()

    admin_email = "admin@example.com"
    user = db.get_user_by_identifier(admin_email)
    assert user is not None, "admin@example.com seed user not found"

    chars = db.list_characters_for_user(user.id)
    navasi_chars = [c for c in chars if c.name == "Navasi"]
    assert len(navasi_chars) >= 1, f"No Navasi character found for {admin_email}"

    sheet = navasi_chars[0].sheet or {}
    assert (sheet.get("system") or {}).get("name") == "Starfinder"


def test_seed_is_idempotent():
    """Running seed_starfinder_characters twice should not create duplicate characters."""
    from server.scripts.seed_starfinder_characters import seed_starfinder_characters

    seed_starfinder_characters()
    seed_starfinder_characters()

    bilbo_email = "bilbo@example.com"
    user = db.get_user_by_identifier(bilbo_email)
    assert user is not None

    chars = db.list_characters_for_user(user.id)
    navasi_count = sum(1 for c in chars if c.name == "Navasi")
    assert navasi_count == 1, f"Expected exactly 1 Navasi character but found {navasi_count}"
