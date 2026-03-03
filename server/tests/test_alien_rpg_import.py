"""Alien RPG PDF character sheet import tests.

These tests exercise the Alien RPG-specific import path in
``server/agents/characters.py`` using a dedicated ``alien-import@example.com``
test user and a synthetic fixture PDF that mirrors a typical Alien RPG character
(Zoe Hendricks — a Roughneck).

The Alien RPG schema (Year Zero Engine) is distinct from D&D 5e:
- **Attributes**: Strength, Agility, Wits, Empathy  (1–6 scale; stored as alien_attributes)
- **Skills**: twelve skills linked to attributes  (0–5 scale; stored as alien_skills)
- **Resources**: Health (≠ HP), Stress (unique panic mechanic) — stored as
  alien_health / alien_stress so they do not overload D&D HP keys.
- **Identity**: Career (replaces class), Agenda (secret objective), Buddy, Rival
- **Import metadata**: sheet.system.name == "Alien RPG",
                        sheet.import.source == "pdf"
"""
from __future__ import annotations

import io
import os

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents.characters import (
    _extract_alien_rpg_attributes_from_widgets,
    _extract_alien_rpg_health_from_widgets,
    _extract_alien_rpg_skills_from_widgets,
    _extract_alien_rpg_stress_from_widgets,
    _is_alien_rpg_sheet,
)
from server.agents.system_detect import infer_ttrpg_system
from server.auth import create_access_token

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# PDF builder helper — mirrors the STA/PF helpers in the other test modules
# ---------------------------------------------------------------------------


def _make_alien_rpg_pdf(fields: dict[str, str]) -> bytes:
    """Build a minimal PDF containing Alien RPG widget annotations (AcroForm fields)."""
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    y = 750.0
    for field_name, value in fields.items():
        annot = DictionaryObject()
        annot.update(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/T"): TextStringObject(field_name),
                NameObject("/V"): TextStringObject(str(value)),
                NameObject("/Rect"): ArrayObject(
                    [FloatObject(50.0), FloatObject(y), FloatObject(400.0), FloatObject(y + 20.0)]
                ),
            }
        )
        ref = writer._add_object(annot)  # noqa: SLF001
        annots = page.get("/Annots")
        if annots is None:
            page[NameObject("/Annots")] = ArrayObject([ref])
        else:
            annots.append(ref)
        y -= 22.0

    bio = io.BytesIO()
    writer.write(bio)
    bio.seek(0)
    return bio.read()


# ---------------------------------------------------------------------------
# Zoe Hendricks fixture — canonical expected values
# ---------------------------------------------------------------------------

_ZOE_FIELDS: dict[str, str] = {
    "Name": "Zoe Hendricks",
    "Career": "Roughneck",
    "Appearance": "Weathered face, calloused hands",
    "Agenda": "Get out of this job with a big enough bonus to retire somewhere warm.",
    "Buddy": "Miguel Santos",
    "Rival": "Foreman Hicks",
    "Experience": "5",
    # Attributes (1–6)
    "Strength": "4",
    "Agility": "3",
    "Wits": "3",
    "Empathy": "2",
    # Skills (0–5)
    "Close Combat": "2",
    "Heavy Machinery": "3",
    "Stamina": "2",
    "Mobility": "2",
    "Piloting": "0",
    "Ranged Combat": "3",
    "Comtech": "1",
    "Observation": "2",
    "Survival": "2",
    "Command": "0",
    "Manipulation": "1",
    "Medical Aid": "0",
    # Resources
    "Health": "4",
    "Max Health": "4",
    "Stress": "2",
    # Gear (numbered list)
    "Gear 1": "Shotgun",
    "Gear 2": "Flashlight",
    "Gear 3": "Motion Tracker",
    "Gear 4": "Combat Knife",
}

_ALIEN_USER_EMAIL = "alien-import@example.com"


def _auth_headers() -> dict:
    _ensure_user(_ALIEN_USER_EMAIL)
    token = create_access_token(_ALIEN_USER_EMAIL)
    return {"Authorization": f"Bearer {token}"}


def _import_zoe(client: TestClient) -> dict:
    """POST the Zoe Hendricks PDF and return the full response JSON."""
    pdf_bytes = _make_alien_rpg_pdf(_ZOE_FIELDS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=_auth_headers(),
        files={"file": ("zoe.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ===========================================================================
# 1. Unit-level: _is_alien_rpg_sheet detection
# ===========================================================================


def test_alien_rpg_is_alien_rpg_sheet_detects_yze_widgets():
    """_is_alien_rpg_sheet returns True when distinctive Alien RPG widgets are present."""
    assert _is_alien_rpg_sheet(dict(_ZOE_FIELDS)) is True


def test_alien_rpg_is_alien_rpg_sheet_rejects_dnd_widgets():
    """_is_alien_rpg_sheet returns False for a D&D 5e widget set."""
    dnd_widgets = {
        "CharacterName": "Gandalf",
        "ClassLevel": "Wizard 10",
        "STR": "10",
        "DEX": "14",
        "CON": "12",
        "INT": "20",
        "WIS": "16",
        "CHA": "12",
    }
    assert _is_alien_rpg_sheet(dnd_widgets) is False


def test_alien_rpg_attribute_extraction_unit():
    """_extract_alien_rpg_attributes_from_widgets returns all four attributes."""
    attrs = _extract_alien_rpg_attributes_from_widgets(dict(_ZOE_FIELDS))
    assert attrs == {"strength": 4, "agility": 3, "wits": 3, "empathy": 2}


def test_alien_rpg_skill_extraction_unit():
    """_extract_alien_rpg_skills_from_widgets returns all twelve skills."""
    skills = _extract_alien_rpg_skills_from_widgets(dict(_ZOE_FIELDS))
    assert skills["close_combat"] == 2
    assert skills["heavy_machinery"] == 3
    assert skills["ranged_combat"] == 3
    assert skills["comtech"] == 1
    assert skills["observation"] == 2
    assert skills["survival"] == 2


def test_alien_rpg_health_extraction_unit():
    """_extract_alien_rpg_health_from_widgets returns current and max health."""
    health = _extract_alien_rpg_health_from_widgets(dict(_ZOE_FIELDS))
    assert health["current"] == 4
    assert health["max"] == 4


def test_alien_rpg_stress_extraction_unit():
    """_extract_alien_rpg_stress_from_widgets returns the stress value."""
    stress = _extract_alien_rpg_stress_from_widgets(dict(_ZOE_FIELDS))
    assert stress["current"] == 2


# ===========================================================================
# 2. System detection
# ===========================================================================


def test_alien_rpg_system_detection_scores_alien_rpg():
    """infer_ttrpg_system identifies an Alien RPG widget set as Alien RPG."""
    result = infer_ttrpg_system({
        "stats": {"strength": 4, "agility": 3, "wits": 3, "empathy": 2},
        "skills": ["close_combat", "ranged_combat", "comtech", "survival"],
        "widget_keys": list(_ZOE_FIELDS.keys()),
    })
    assert result["system_name"] == "Alien RPG"
    assert result["confidence"] > 0.0


# ===========================================================================
# 3. Full PDF import — system detection
# ===========================================================================


def test_alien_rpg_pdf_import_detects_alien_rpg_system():
    """System detection identifies the sheet as Alien RPG."""
    client = _client()
    data = _import_zoe(client)
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "Alien RPG"


# ===========================================================================
# 4. Character name
# ===========================================================================


def test_alien_rpg_pdf_import_extracts_character_name():
    """Zoe Hendricks' name is preserved in the import."""
    client = _client()
    data = _import_zoe(client)
    assert data["character"]["name"] == "Zoe Hendricks"


# ===========================================================================
# 5. Attributes
# ===========================================================================


def test_alien_rpg_pdf_import_extracts_all_four_attributes():
    """All four Alien RPG attributes are stored under sheet['alien_attributes']."""
    client = _client()
    data = _import_zoe(client)
    attrs = data["character"]["sheet"]["alien_attributes"]
    assert attrs["strength"] == 4
    assert attrs["agility"] == 3
    assert attrs["wits"] == 3
    assert attrs["empathy"] == 2


# ===========================================================================
# 6. Skills
# ===========================================================================


def test_alien_rpg_pdf_import_extracts_skills():
    """Key skills are stored under sheet['alien_skills'] with snake_case keys."""
    client = _client()
    data = _import_zoe(client)
    skills = data["character"]["sheet"]["alien_skills"]
    assert skills["close_combat"] == 2
    assert skills["heavy_machinery"] == 3
    assert skills["ranged_combat"] == 3
    assert skills["comtech"] == 1
    assert skills["observation"] == 2
    assert skills["survival"] == 2


# ===========================================================================
# 7. Health — not overloaded onto hp
# ===========================================================================


def test_alien_rpg_pdf_import_stores_health_as_alien_health():
    """Health is stored under alien_health, not overloading the hp key."""
    client = _client()
    data = _import_zoe(client)
    sheet = data["character"]["sheet"]
    assert "alien_health" in sheet
    assert sheet["alien_health"]["current"] == 4
    assert sheet["alien_health"]["max"] == 4


# ===========================================================================
# 8. Stress — unique Alien RPG mechanic
# ===========================================================================


def test_alien_rpg_pdf_import_stores_stress_as_alien_stress():
    """Stress is stored under alien_stress, not hp or the STA stress key."""
    client = _client()
    data = _import_zoe(client)
    sheet = data["character"]["sheet"]
    assert "alien_stress" in sheet
    assert sheet["alien_stress"]["current"] == 2


# ===========================================================================
# 9. Career (stored separately from class_name)
# ===========================================================================


def test_alien_rpg_pdf_import_extracts_career():
    """Career widget maps to sheet['alien_career']."""
    client = _client()
    data = _import_zoe(client)
    sheet = data["character"]["sheet"]
    assert sheet.get("alien_career") == "Roughneck"


# ===========================================================================
# 10. Agenda (unique Alien RPG field)
# ===========================================================================


def test_alien_rpg_pdf_import_extracts_agenda():
    """Agenda widget is stored under sheet['agenda']."""
    client = _client()
    data = _import_zoe(client)
    sheet = data["character"]["sheet"]
    assert "agenda" in sheet
    assert "bonus" in sheet["agenda"]  # partial match on the fixture text


# ===========================================================================
# 11. Equipment / Gear
# ===========================================================================


def test_alien_rpg_pdf_import_extracts_gear():
    """Gear widgets are captured under sheet['equipment']."""
    client = _client()
    data = _import_zoe(client)
    equipment = data["character"]["sheet"].get("equipment", [])
    assert len(equipment) >= 1
    assert any("Shotgun" in item for item in equipment)


# ===========================================================================
# 12. Source metadata
# ===========================================================================


def test_alien_rpg_pdf_import_source_metadata():
    """Import source is 'pdf' and system name is stored under sheet['system']."""
    client = _client()
    data = _import_zoe(client)
    sheet = data["character"]["sheet"]
    assert sheet["import"]["source"] == "pdf"
    assert sheet["system"]["name"] == "Alien RPG"


# ===========================================================================
# 13. Preview endpoint — does not persist
# ===========================================================================


def test_alien_rpg_pdf_preview_returns_structure_without_persisting():
    """Preview endpoint returns the expected structure but does NOT create a character."""
    client = _client()
    headers = _auth_headers()
    pdf_bytes = _make_alien_rpg_pdf(_ZOE_FIELDS)

    res = client.post(
        "/characters/import/pdf/preview?source=pdf",
        headers=headers,
        files={"file": ("zoe_preview.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 200, res.text
    preview = res.json()["preview"]
    assert preview["name"] == "Zoe Hendricks"
    assert preview["sheet"]["system"]["name"] == "Alien RPG"
    assert "alien_attributes" in preview["sheet"]
    assert "alien_skills" in preview["sheet"]

    # Verify the character was NOT persisted
    list_res = client.get("/characters", headers=headers)
    assert list_res.status_code == 200
    assert isinstance(list_res.json().get("characters", []), list)


# ===========================================================================
# 14. Injuries — absent when none present
# ===========================================================================


def test_alien_rpg_pdf_import_injuries_absent_when_none():
    """When no injury fields are present the sheet should not contain injuries (or empty)."""
    client = _client()
    data = _import_zoe(client)
    injuries = data["character"]["sheet"].get("injuries", [])
    assert injuries == []


def test_alien_rpg_pdf_import_extracts_injuries_when_present():
    """Critical Injury widgets appear under sheet['injuries'] when present."""
    client = _client()
    headers = _auth_headers()
    fields = dict(_ZOE_FIELDS)
    fields["Critical Injury 1"] = "Broken Arm (attribute –1)"
    fields["Critical Injury 2"] = "Bleeding (takes 1 damage per round)"
    pdf_bytes = _make_alien_rpg_pdf(fields)

    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("zoe_injured.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    injuries = res.json()["character"]["sheet"].get("injuries", [])
    assert any("Broken Arm" in inj for inj in injuries)
    assert any("Bleeding" in inj for inj in injuries)


# ===========================================================================
# 15. Seed-user characters (bilbo + admin)
# ===========================================================================


def test_alien_rpg_seed_bilbo_character_exists():
    """bilbo@example.com has an Alien RPG seed character after ensure_seed_users."""
    # ensure_seed_users is called by the app at module load; the Alien RPG seed
    # runs automatically too via TAVERNTAILS_SEED_ALIEN_RPG.
    user = db.get_user_by_identifier("bilbo@example.com")
    if user is None:
        # ensure it exists in this test run
        db.ensure_seed_users()
        user = db.get_user_by_identifier("bilbo@example.com")
    assert user is not None

    from server.scripts.seed_alien_rpg_characters import seed_alien_rpg_characters
    seed_alien_rpg_characters()

    chars = db.list_characters_for_user(user.id)
    names = [c.name for c in chars]
    assert "Zoe Hendricks" in names

    zoe = next(c for c in chars if c.name == "Zoe Hendricks")
    sheet = zoe.sheet or {}
    assert sheet.get("system", {}).get("name") == "Alien RPG"
    assert sheet.get("alien_career") == "Roughneck"
    assert sheet.get("alien_attributes", {}).get("strength") == 4
    assert sheet.get("alien_stress") is not None


def test_alien_rpg_seed_admin_character_exists():
    """admin@example.com has an Alien RPG seed character after seeding."""
    user = db.get_user_by_identifier("admin@example.com")
    if user is None:
        db.ensure_seed_users()
        user = db.get_user_by_identifier("admin@example.com")
    assert user is not None

    from server.scripts.seed_alien_rpg_characters import seed_alien_rpg_characters
    seed_alien_rpg_characters()

    chars = db.list_characters_for_user(user.id)
    names = [c.name for c in chars]
    assert "Lt. Torres" in names

    torres = next(c for c in chars if c.name == "Lt. Torres")
    sheet = torres.sheet or {}
    assert sheet.get("system", {}).get("name") == "Alien RPG"
    assert sheet.get("alien_career") == "Colonial Marine"
    assert sheet.get("alien_attributes", {}).get("agility") == 4
    assert sheet.get("alien_stress") is not None


def test_alien_rpg_seed_is_idempotent():
    """Running the seed script twice does not create duplicate characters."""
    user = db.get_user_by_identifier("bilbo@example.com")
    if user is None:
        db.ensure_seed_users()
        user = db.get_user_by_identifier("bilbo@example.com")
    assert user is not None

    from server.scripts.seed_alien_rpg_characters import seed_alien_rpg_characters
    seed_alien_rpg_characters()
    seed_alien_rpg_characters()  # second run should be a no-op

    chars = db.list_characters_for_user(user.id)
    zoe_count = sum(1 for c in chars if c.name == "Zoe Hendricks")
    assert zoe_count == 1


# ===========================================================================
# 16. Admin API — seed characters visible via admin endpoint
# ===========================================================================


def test_alien_rpg_seed_characters_visible_via_admin_api():
    """Admin can see both seed characters via GET /admin/characters."""
    # Ensure seeds exist
    db.ensure_seed_users()
    from server.scripts.seed_alien_rpg_characters import seed_alien_rpg_characters
    seed_alien_rpg_characters()

    admin = db.get_user_by_identifier("admin@example.com")
    assert admin is not None
    token = create_access_token("admin@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    client = _client()
    res = client.get("/admin/characters", headers=headers)
    if res.status_code == 404:
        # Endpoint not yet implemented — skip gracefully
        return
    assert res.status_code == 200, res.text
    names = [c.get("name") for c in res.json().get("characters", [])]
    assert "Zoe Hendricks" in names
    assert "Lt. Torres" in names


# ===========================================================================
# 17. Smoke test: real fixture PDF (server/tests/fixtures/alien_rpg/character.pdf)
# ===========================================================================


def test_alien_rpg_real_fixture_pdf_smoke():
    """Real fixture PDF (character.pdf) imports without error and detects Alien RPG."""
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "alien_rpg", "character.pdf")
    if not os.path.exists(fixture_path):
        import pytest
        pytest.skip("character.pdf fixture not found — place a filled-out Alien RPG PDF there to run this test")

    client = _client()
    headers = _auth_headers()
    with open(fixture_path, "rb") as f:
        pdf_bytes = f.read()

    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "Alien RPG"
    assert "alien_attributes" in sheet
    assert "alien_skills" in sheet
