"""D&D 5e PDF character sheet import tests.

These tests exercise the D&D 5e-specific import path in ``server/agents/characters.py``
using a dedicated ``dnd5e-import@example.com`` test user and a synthetic fixture PDF
that mirrors Thorin Ironfist (a Mountain Dwarf Fighter).

The D&D 5e schema differs from other supported systems in several ways:
- **Ability Scores**: STR/DEX/CON/INT/WIS/CHA (same labels as PF1e/PF2e but no
  proficiency ranks — only a flat Proficiency Bonus applied to saves/skills)
- **Saving Throws**: six ability-score saves, each with a proficiency checkbox
- **Skills**: 18 skills with optional proficiency/expertise flags
- **Resources**: HP (max/current/temp), Hit Dice (type × level), Spell Slots per level
- **Inspiration**: boolean flag unique to D&D 5e
- **Death Saves**: successes/failures counters unique to D&D 5e
- **Proficiency Bonus**: flat bonus applied to saves/skills (replaces PF ranks/BAB)

Tests also verify the two-user seed scenario (bilbo@example.com and admin@example.com)
required by the feature acceptance criteria.
"""
from __future__ import annotations

import io
import os

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents.system_detect import infer_ttrpg_system
from server.auth import create_access_token

# ---------------------------------------------------------------------------
# Helpers — mirrors conventions from test_pf_import.py and test_sta_import.py
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
    """Build a minimal PDF with interactive widget annotations.

    Each key becomes the widget's /T (field name) and each value its /V
    (field value).  Mirrors the approach used in test_pf_import.py.
    """
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
                NameObject("/V"): TextStringObject(str(value)),
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


def _make_dnd5e_pdf(fields: dict[str, str]) -> bytes:
    """Build a synthetic D&D 5e character sheet PDF with the given field values.

    Always injects D&D 5e-unique disambiguation signals (Proficiency Bonus,
    Death Saves, Hit Dice) so the system detector reliably identifies the sheet.
    """
    base: dict[str, str] = {
        # D&D 5e system signals — not found on PF1e/PF2e/STA sheets
        "ProfBonus": "3",
        "Death Save Successes": "0",
        "Death Save Failures": "0",
        "HD Total": "5d10",
        "Inspiration": "0",
        # 5e skill with no PF2e equivalent
        "Animal Handling": "2",
        "Sleight of Hand": "1",
    }
    base.update(fields)
    return _make_widget_pdf(base)


# ---------------------------------------------------------------------------
# Thorin Ironfist — canonical test character
# ---------------------------------------------------------------------------

DND5E_EMAIL = "dnd5e-import@example.com"
DND5E_USERNAME = "dnd5e-import"

THORIN_WIDGETS: dict[str, str] = {
    # Identity
    "CharacterName": "Thorin Ironfist",
    "CLASS  LEVEL": "Fighter 5",
    "Race": "Mountain Dwarf",
    "Background": "Soldier",
    # Ability scores
    "STR": "18",
    "DEX": "12",
    "CON": "16",
    "INT": "10",
    "WIS": "12",
    "CHA": "8",
    # Hit points
    "Hit Point Maximum": "52",
    "Current Hit Points": "52",
    "Temporary Hit Points": "0",
    # Combat
    "Armor Class": "18",
    "Initiative": "1",
    # D&D 5e-specific resources
    "ProfBonus": "3",
    "HD Total": "5d10",
    "Inspiration": "0",
    "Death Save Successes": "0",
    "Death Save Failures": "0",
    # Saving throws (D&D 5e ability-score saves with integer totals)
    "ST Strength": "7",
    "ST Dexterity": "1",
    "ST Constitution": "6",
    "ST Intelligence": "0",
    "ST Wisdom": "1",
    "ST Charisma": "-1",
    # Skills (subset — modifier values)
    "Athletics": "7",
    "Perception": "4",
    "Intimidation": "2",
    "Animal Handling": "4",
    "Sleight of Hand": "1",
    # Spell slots (Fighter has no slots at level 5 unless EK)
    "SlotsTotal1": "0",
    # Features & Traits
    "Features and Traits": "Action Surge\nSecond Wind\nExtra Attack",
    # Equipment
    "Equipment 1": "Longsword",
    "Equipment 2": "Chain Mail",
    "Equipment 3": "Shield",
}


def _auth_headers(email: str = DND5E_EMAIL, username: str = DND5E_USERNAME) -> dict:
    _ensure_user(email, username)
    token = create_access_token(email)
    return {"Authorization": f"Bearer {token}"}


def _import_thorin(client: TestClient, email: str = DND5E_EMAIL) -> dict:
    """POST the Thorin PDF and return the full response JSON."""
    pdf_bytes = _make_dnd5e_pdf(THORIN_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=_auth_headers(email),
        files={"file": ("thorin.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
# 1. System detection
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_detects_dnd_5e_system():
    """System detection identifies the sheet as D&D 5e."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "D&D 5e", f"Got system: {sheet.get('system')}"


# ---------------------------------------------------------------------------
# 2. Character name
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_extracts_character_name():
    """Character name is extracted from the CharacterName widget."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    assert data["character"]["name"] == "Thorin Ironfist"


# ---------------------------------------------------------------------------
# 3. Class name and level
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_extracts_class_and_level():
    """Class name and level are parsed from the CLASS  LEVEL widget."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    char = data["character"]
    assert char["class_name"] == "Fighter"
    assert char["level"] == 5


# ---------------------------------------------------------------------------
# 4. Ability scores
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_extracts_ability_scores():
    """All six ability scores are stored under sheet['stats']."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    stats = data["character"]["sheet"]["stats"]
    assert stats["str"] == 18
    assert stats["dex"] == 12
    assert stats["con"] == 16
    assert stats["int"] == 10
    assert stats["wis"] == 12
    assert stats["cha"] == 8


# ---------------------------------------------------------------------------
# 5. Hit points
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_extracts_hit_points():
    """HP max and current are extracted into sheet['hp']."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    hp = data["character"]["sheet"]["hp"]
    assert hp["max"] == 52
    assert hp["current"] == 52


# ---------------------------------------------------------------------------
# 6. Armour Class
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_extracts_armor_class():
    """Armour Class is extracted into sheet['ac']."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    assert data["character"]["sheet"]["ac"] == 18


# ---------------------------------------------------------------------------
# 7. D&D 5e-specific resources
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_extracts_proficiency_bonus():
    """Proficiency bonus is stored under sheet['proficiency_bonus']."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    assert data["character"]["sheet"]["proficiency_bonus"] == 3


def test_dnd5e_pdf_import_extracts_hit_dice():
    """Hit dice type is stored under sheet['hit_dice']."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    assert data["character"]["sheet"]["hit_dice"] == "5d10"


def test_dnd5e_pdf_import_extracts_death_saves():
    """Death saves successes/failures are stored under sheet['death_saves']."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    death_saves = data["character"]["sheet"]["death_saves"]
    assert "successes" in death_saves
    assert "failures" in death_saves


# ---------------------------------------------------------------------------
# 8. Saving throws
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_extracts_saving_throws():
    """Six ability-score saves are stored under sheet['saves']."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    saves = data["character"]["sheet"]["saves"]
    assert saves["str"]["total"] == 7
    assert saves["dex"]["total"] == 1
    assert saves["con"]["total"] == 6
    assert saves["int"]["total"] == 0
    assert saves["wis"]["total"] == 1
    assert saves["cha"]["total"] == -1


# ---------------------------------------------------------------------------
# 9. Skills
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_extracts_skills():
    """Skill modifiers are stored in sheet['skills'] as a list of {name, modifier, ...} objects."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    skills = data["character"]["sheet"]["skills"]
    # Skills may be stored as a list of objects or a dict; handle both.
    if isinstance(skills, list):
        skills_by_name = {s["name"]: s for s in skills if isinstance(s, dict) and "name" in s}
    else:
        skills_by_name = skills
    assert "Athletics" in skills_by_name
    assert skills_by_name["Athletics"]["modifier"] == 7
    assert "Perception" in skills_by_name
    assert skills_by_name["Perception"]["modifier"] == 4


# ---------------------------------------------------------------------------
# 10. Race / Background
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_extracts_race_and_background():
    """Race and background are extracted into sheet['race'] and sheet['background']."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    sheet = data["character"]["sheet"]
    assert sheet["race"] == "Mountain Dwarf"
    assert sheet["background"] == "Soldier"


# ---------------------------------------------------------------------------
# 11. Import metadata
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_source_metadata():
    """Import source is 'pdf' and system name is stored in both sheet keys."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    sheet = data["character"]["sheet"]
    assert sheet["import"]["source"] == "pdf"
    assert sheet["system"]["name"] == "D&D 5e"
    assert sheet["system"]["publisher"] == "Wizards of the Coast"


# ---------------------------------------------------------------------------
# 12. Preview endpoint — does not persist
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_preview_returns_structure_without_persisting():
    """Preview endpoint returns the same structure but does NOT create a character."""
    client = _client()
    preview_email = "dnd5e-import-preview@example.com"
    _ensure_user(preview_email, "dnd5e-import-preview")
    token = create_access_token(preview_email)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_dnd5e_pdf(THORIN_WIDGETS)
    res = client.post(
        "/characters/import/pdf/preview?source=pdf",
        headers=headers,
        files={"file": ("thorin_preview.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 200, res.text
    preview = res.json()["preview"]
    assert preview["name"] == "Thorin Ironfist"
    assert preview["sheet"]["system"]["name"] == "D&D 5e"
    assert preview["sheet"]["import"]["source"] == "pdf"

    # Verify the character was NOT persisted
    list_res = client.get("/characters", headers=headers)
    assert list_res.status_code == 200
    names = [c["name"] for c in list_res.json().get("characters", [])]
    assert "Thorin Ironfist" not in names


# ---------------------------------------------------------------------------
# 13. Equipment
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_extracts_equipment():
    """Equipment widget values are captured under sheet['equipment']."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    equipment = data["character"]["sheet"].get("equipment", [])
    assert len(equipment) >= 1
    assert any("Longsword" in item for item in equipment)


# ---------------------------------------------------------------------------
# 14. Features & Traits
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_extracts_features():
    """Features & Traits are captured under sheet['features']."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    data = _import_thorin(client)
    features = data["character"]["sheet"].get("features", [])
    assert len(features) >= 1
    assert any("Action Surge" in f or "Second Wind" in f for f in features)


# ---------------------------------------------------------------------------
# 15. System detection — pure unit test (no HTTP round-trip)
# ---------------------------------------------------------------------------


def test_dnd5e_system_detection_unit():
    """infer_ttrpg_system correctly identifies D&D 5e from widget key signals."""
    sheet = {
        "class_name": "Fighter",
        "widget_keys": [
            "CharacterName",
            "ProfBonus",
            "Death Save Successes",
            "Death Save Failures",
            "HD Total",
            "Animal Handling",
            "Sleight of Hand",
            "Inspiration",
            "SlotsTotal1",
        ],
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "D&D 5e", (
        f"Expected 'D&D 5e' but got '{result['system_name']}' "
        f"(evidence: {result['evidence']})"
    )


def test_dnd5e_not_confused_with_pf2e():
    """A sheet with PF2e-exclusive fields must NOT detect as D&D 5e."""
    sheet = {
        "class_name": "Fighter",
        "widget_keys": [
            "CharacterName",
            "Ancestry",
            "Heritage",
            "Proficiency Rank Athletics",
            "Focus Points Max",
            "Class DC",
            "Current Bulk",
        ],
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Pathfinder 2e", (
        f"Expected 'Pathfinder 2e' but got '{result['system_name']}'"
    )


def test_dnd5e_not_confused_with_pf1e():
    """A sheet with PF1e-exclusive fields must NOT detect as D&D 5e."""
    sheet = {
        "class_name": "Fighter",
        "widget_keys": [
            "CharacterName",
            "Base Attack Bonus",
            "CMB",
            "CMD",
            "Spells Per Day L1",
        ],
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Pathfinder 1e", (
        f"Expected 'Pathfinder 1e' but got '{result['system_name']}'"
    )


# ---------------------------------------------------------------------------
# 16. Spell slots
# ---------------------------------------------------------------------------


def test_dnd5e_pdf_import_extracts_spell_slots_when_present():
    """Spell slots keyed by level string are stored under sheet['spell_slots']."""
    client = _client()
    _ensure_user(DND5E_EMAIL, DND5E_USERNAME)
    token = create_access_token(DND5E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    caster_widgets = dict(THORIN_WIDGETS)
    caster_widgets["CLASS  LEVEL"] = "Wizard 5"
    caster_widgets["CharacterName"] = "Gandalf the Grey"
    caster_widgets["SlotsTotal1"] = "4"
    caster_widgets["SlotsTotal2"] = "3"
    caster_widgets["SlotsTotal3"] = "2"
    pdf_bytes = _make_dnd5e_pdf(caster_widgets)

    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("gandalf.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["spell_slots"]["1"] == 4
    assert sheet["spell_slots"]["2"] == 3
    assert sheet["spell_slots"]["3"] == 2


# ---------------------------------------------------------------------------
# 17. Seed-user imports — bilbo@example.com and admin@example.com
#
# These tests validate the acceptance-criteria requirement that both the
# BilboBaggins and Admin seed accounts can import a D&D 5e character.
# They mirror what seed_dandd_5e_characters.py does at startup.
# ---------------------------------------------------------------------------


def test_dnd5e_import_bilbo_seed_user():
    """bilbo@example.com (BilboBaggins) can import a D&D 5e character."""
    client = _client()
    bilbo_email = "bilbo@example.com"
    _ensure_user(bilbo_email, "BilboBaggins")

    data = _import_thorin(client, email=bilbo_email)
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "D&D 5e"
    assert data["character"]["name"] == "Thorin Ironfist"


def test_dnd5e_import_admin_seed_user():
    """admin@example.com (Admin) can import a D&D 5e character."""
    client = _client()
    admin_email = "admin@example.com"
    _ensure_user(admin_email, "Admin")

    data = _import_thorin(client, email=admin_email)
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "D&D 5e"
    assert data["character"]["name"] == "Thorin Ironfist"


# ---------------------------------------------------------------------------
# 18. Smoke test — real fixture PDF (optional, skipped in CI)
# ---------------------------------------------------------------------------


def test_dnd5e_real_fixture_pdf_smoke():
    """Real fixture PDF (character.pdf) imports without error and detects D&D 5e."""
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "dandd_5e", "character.pdf")
    if not os.path.exists(fixture_path):
        import pytest
        pytest.skip("character.pdf fixture not found — add a personal-use D&D 5e PDF to run this test")

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
    sheet = res.json()["character"]["sheet"]
    assert sheet["system"]["name"] == "D&D 5e"
    assert "stats" in sheet
