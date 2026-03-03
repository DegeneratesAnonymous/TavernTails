"""Pathfinder 2e character import tests — acceptance criteria coverage.

Tests the three pillars required by the feature acceptance criteria:
  1. **Field extraction** — PDF widget values map correctly to schema keys.
  2. **Schema mapping** — PF2e-specific fields are stored under system-namespaced
     keys (not overloading D&D 5e equivalents).
  3. **Seed-user imports** — Both ``bilbo@example.com`` and ``admin@example.com``
     have a PF2e character after startup seeding.

The synthetic PDF fixture approach (using pypdf widget annotations) mirrors the
technique used in ``test_pf_import.py`` so CI can run without real Paizo PDFs.

See ``server/tests/fixtures/pf2e/README.md`` for notes on real sheet PDFs.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.auth import create_access_token
from server.scripts.seed_pathfinder_2e_characters import (
    _SEED_CHARACTER_CLASS,
    _SEED_CHARACTER_LEVEL,
    _SEED_CHARACTER_NAME,
    seed_pf2e_characters,
)

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


def _make_pf2e_pdf(fields: dict[str, str]) -> bytes:
    """Build a synthetic PF2e PDF pre-loaded with edition disambiguation signals."""
    base: dict[str, str] = {
        "Ancestry": "",
        "Heritage": "",
        "Proficiency Rank Athletics": "",
        "Focus Points Max": "",
        "Class DC": "",
        "Current Bulk": "",
    }
    base.update(fields)
    return _make_widget_pdf(base)


# ---------------------------------------------------------------------------
# Standard PF2e widget values (Seoni, Human Sorcerer 5)
# Mirrors PF2E_WIDGETS in test_pf_import.py for consistency.
# ---------------------------------------------------------------------------

_PF2E_WIDGETS: dict[str, str] = {
    "CharacterName": "Seoni",
    "CLASS  LEVEL": "Sorcerer 5",
    "Ancestry": "Human",
    "Heritage": "Versatile Human",
    "Background": "Farmhand",
    "STR": "10",
    "DEX": "14",
    "CON": "12",
    "INT": "12",
    "WIS": "10",
    "CHA": "18",
    "Hit Point Maximum": "55",
    "Armor Class": "16",
    "Class DC": "19",
    "Spell DC": "21",
    "Focus Points Max": "3",
    "Focus Points Current": "2",
    "Fortitude Total": "7",
    "Fortitude Rank": "trained",
    "Reflex Total": "9",
    "Reflex Rank": "expert",
    "Will Total": "8",
    "Will Rank": "trained",
    "Athletics Rank": "trained",
    "Deception Rank": "expert",
    "Performance Rank": "legendary",
    "Spell Slots L1 Max": "4",
    "Spell Slots L2 Max": "4",
    "Spell Slots L3 Max": "3",
    "Ancestry Feat 1": "Natural Ambition",
    "Class Feat 1": "Dangerous Sorcery",
    "Skill Feat 1": "Intimidating Prowess",
    "General Feat 1": "Toughness",
    "Current Bulk": "3",
    "Bulk Limit": "6",
    "Equipment 1": "Dagger",
    "Character Traits": "Human, Humanoid",
    "spellName0": "Fireball",
}

_TEST_EMAIL = "pf2e-acceptance@example.com"
_TEST_USERNAME = "pf2e-acceptance"


# ===========================================================================
# 1. Field extraction tests
# ===========================================================================


def test_field_extraction_system_name():
    """Importer must set sheet.system.name = 'Pathfinder 2e'."""
    client = _client()
    _ensure_user(_TEST_EMAIL, _TEST_USERNAME)
    token = create_access_token(_TEST_EMAIL)

    pdf_bytes = _make_pf2e_pdf(_PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("seoni.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["system"]["name"] == "Pathfinder 2e"


def test_field_extraction_import_source():
    """Importer must set sheet.import.source = 'pdf'."""
    client = _client()
    _ensure_user(_TEST_EMAIL, _TEST_USERNAME)
    token = create_access_token(_TEST_EMAIL)

    pdf_bytes = _make_pf2e_pdf(_PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("seoni.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    assert res.json()["character"]["sheet"]["import"]["source"] == "pdf"


def test_field_extraction_ability_scores():
    """All six ability scores must be extracted and stored under sheet.stats."""
    client = _client()
    _ensure_user(_TEST_EMAIL, _TEST_USERNAME)
    token = create_access_token(_TEST_EMAIL)

    pdf_bytes = _make_pf2e_pdf(_PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("seoni.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    stats = res.json()["character"]["sheet"]["stats"]
    assert stats["str"] == 10
    assert stats["dex"] == 14
    assert stats["con"] == 12
    assert stats["cha"] == 18


def test_field_extraction_ancestry_heritage_background():
    """Ancestry, heritage, and background should be extracted as top-level sheet keys."""
    client = _client()
    _ensure_user(_TEST_EMAIL, _TEST_USERNAME)
    token = create_access_token(_TEST_EMAIL)

    pdf_bytes = _make_pf2e_pdf(_PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("seoni.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["ancestry"] == "Human"
    assert sheet["heritage"] == "Versatile Human"
    assert sheet["background"] == "Farmhand"


# ===========================================================================
# 2. Schema mapping tests — PF2e-specific keys must not overload 5e equivalents
# ===========================================================================


def test_schema_proficiency_ranks_are_named_strings():
    """Proficiency ranks must be named strings ('untrained'/'trained'/…), not integers.

    This verifies that PF2e proficiency ranks are NOT stored as integer bonuses
    (the D&D 5e convention) but as the Pathfinder-native rank labels.
    """
    client = _client()
    _ensure_user(_TEST_EMAIL, _TEST_USERNAME)
    token = create_access_token(_TEST_EMAIL)

    pdf_bytes = _make_pf2e_pdf(_PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("seoni.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    skills = res.json()["character"]["sheet"]["skills"]
    assert isinstance(skills, dict), "PF2e skills must be a dict keyed by skill name"
    for name, entry in skills.items():
        if "rank" in entry:
            assert isinstance(entry["rank"], str), f"Rank for {name} must be a string"
            assert entry["rank"] in {"untrained", "trained", "expert", "master", "legendary"}


def test_schema_focus_points_stored_under_focus_key():
    """Focus points must be stored under sheet['focus'], not sheet['spell_slots'] or HP."""
    client = _client()
    _ensure_user(_TEST_EMAIL, _TEST_USERNAME)
    token = create_access_token(_TEST_EMAIL)

    pdf_bytes = _make_pf2e_pdf(_PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("seoni.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    # Must be under sheet["focus"], not clobbering spell_slots or hp
    assert "focus" in sheet, "sheet must have a 'focus' key for PF2e focus points"
    assert sheet["focus"]["max"] == 3
    # HP must not be conflated with focus points
    assert sheet["hp"]["max"] == 55


def test_schema_class_dc_stored_separately():
    """Class DC must be stored under sheet['class_dc'], not sheet['ac'] or sheet['hp']."""
    client = _client()
    _ensure_user(_TEST_EMAIL, _TEST_USERNAME)
    token = create_access_token(_TEST_EMAIL)

    pdf_bytes = _make_pf2e_pdf(_PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("seoni.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["class_dc"] == 19
    # AC must remain unaffected by class_dc
    assert sheet["ac"] == 16


def test_schema_bulk_not_stored_as_weight():
    """PF2e Bulk must be stored under sheet['bulk'], not sheet['carry']['weight_current']."""
    client = _client()
    _ensure_user(_TEST_EMAIL, _TEST_USERNAME)
    token = create_access_token(_TEST_EMAIL)

    pdf_bytes = _make_pf2e_pdf(_PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("seoni.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert "bulk" in sheet, "PF2e sheet must have a 'bulk' key"
    assert sheet["bulk"]["current"] == 3
    assert sheet["bulk"]["limit"] == 6


def test_schema_feats_grouped_by_category():
    """PF2e feats must be grouped by ancestry/class/skill/general, not a flat list."""
    client = _client()
    _ensure_user(_TEST_EMAIL, _TEST_USERNAME)
    token = create_access_token(_TEST_EMAIL)

    pdf_bytes = _make_pf2e_pdf(_PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("seoni.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    feats = res.json()["character"]["sheet"]["feats"]
    # Feats must be a dict with category keys, not a bare list
    assert isinstance(feats, dict), "PF2e feats must be a dict keyed by category"
    assert "Natural Ambition" in feats.get("ancestry", [])
    assert "Dangerous Sorcery" in feats.get("class", [])
    assert "Intimidating Prowess" in feats.get("skill", [])
    assert "Toughness" in feats.get("general", [])


# ===========================================================================
# 3. Seed-user import tests
# ===========================================================================


def _get_pf2e_characters_for_user(email: str) -> list[dict]:
    """Return all PF2e characters owned by *email*."""
    user = db.get_user_by_identifier(email)
    assert user is not None, f"Seed user {email} not found"
    characters = db.list_characters_for_user(user.id)
    return [
        c
        for c in characters
        if (c.sheet or {}).get("system", {}).get("name") == "Pathfinder 2e"
    ]


def test_seed_bilbo_has_pf2e_character():
    """bilbo@example.com must have at least one PF2e character after startup seeding."""
    seed_pf2e_characters()  # idempotent — safe to call again
    chars = _get_pf2e_characters_for_user("bilbo@example.com")
    assert len(chars) >= 1, "bilbo@example.com should have at least one PF2e character"
    char = chars[0]
    assert char.name == _SEED_CHARACTER_NAME
    assert char.level == _SEED_CHARACTER_LEVEL
    assert char.class_name == _SEED_CHARACTER_CLASS


def test_seed_admin_has_pf2e_character():
    """admin@example.com must have at least one PF2e character after startup seeding."""
    seed_pf2e_characters()  # idempotent — safe to call again
    chars = _get_pf2e_characters_for_user("admin@example.com")
    assert len(chars) >= 1, "admin@example.com should have at least one PF2e character"
    char = chars[0]
    assert char.name == _SEED_CHARACTER_NAME
    assert char.level == _SEED_CHARACTER_LEVEL
    assert char.class_name == _SEED_CHARACTER_CLASS


def test_seed_pf2e_sheet_fields():
    """The seeded PF2e character sheet must contain all required fields."""
    seed_pf2e_characters()
    chars = _get_pf2e_characters_for_user("bilbo@example.com")
    assert chars, "bilbo must have a PF2e character"
    sheet = chars[0].sheet or {}

    # System identification
    assert sheet["system"]["name"] == "Pathfinder 2e"
    assert sheet["import"]["source"] == "pdf"

    # Ability scores
    assert sheet["stats"]["str"] == 10
    assert sheet["stats"]["cha"] == 18

    # PF2e-specific fields (not D&D 5e equivalents)
    assert sheet["ancestry"] == "Human"
    assert sheet["heritage"] == "Versatile Human"
    assert isinstance(sheet["focus"], dict)
    assert sheet["focus"]["max"] == 3
    assert sheet["class_dc"] == 19
    assert isinstance(sheet["bulk"], dict)
    assert sheet["bulk"]["current"] == 3

    # Saves must carry rank labels
    saves = sheet["saves"]
    assert saves["fort"]["rank"] == "trained"
    assert saves["ref"]["rank"] == "expert"

    # Feats grouped by category
    feats = sheet["feats"]
    assert isinstance(feats, dict)
    assert "Natural Ambition" in feats.get("ancestry", [])


def test_seed_is_idempotent():
    """Calling seed_pf2e_characters() twice must not create duplicate characters."""
    seed_pf2e_characters()
    seed_pf2e_characters()

    bilbo_chars = _get_pf2e_characters_for_user("bilbo@example.com")
    admin_chars = _get_pf2e_characters_for_user("admin@example.com")

    assert len(bilbo_chars) == 1, f"bilbo should have exactly 1 PF2e character, got {len(bilbo_chars)}"
    assert len(admin_chars) == 1, f"admin should have exactly 1 PF2e character, got {len(admin_chars)}"
