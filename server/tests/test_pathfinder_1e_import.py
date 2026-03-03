"""Pathfinder 1e character sheet import tests.

Covers:
  1. Field extraction from a PF1e synthetic PDF (BAB, CMB, CMD, skills,
     feats, special abilities, spells per day, equipment, saving throws).
  2. Schema mapping — verifying that PF1e fields land on the correct
     internal keys and that system metadata is set correctly.
  3. Seed-user imports — confirming that the fixture character can be
     imported for both bilbo@example.com and admin@example.com, and that
     the Admin Panel endpoint can see both imported characters.

The test PDF is the committed fixture at::

    server/tests/fixtures/pathfinder_1e/character.pdf

All tests use the FastAPI TestClient so no running server is required.
"""

from __future__ import annotations

import io
import os

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents.characters import _build_character_import_sheet_from_pdf
from server.agents.system_detect import infer_ttrpg_system
from server.auth import create_access_token

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_FIXTURE_PDF = os.path.join(
    os.path.dirname(__file__),
    "fixtures",
    "pathfinder_1e",
    "character.pdf",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client() -> TestClient:
    return TestClient(main.app)


def _ensure_user(email: str, username: str) -> db.User:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return existing
    user = db.create_user(
        email=email,
        password="secret",
        username=username,
        profile={"name": username, "email": email},
    )
    db.verify_user(email, user.verification_token)
    return db.get_user_by_identifier(email)


def _ensure_admin_user(email: str, username: str) -> db.User:
    _ensure_user(email, username)
    # Grant admin role so the Admin Panel endpoints are accessible
    db.update_profile(email, {"admin": True})
    return db.get_user_by_identifier(email)


def _load_fixture_pdf() -> bytes:
    with open(_FIXTURE_PDF, "rb") as fh:
        return fh.read()


def _import_for_user(client: TestClient, email: str, pdf_bytes: bytes, filename: str = "character.pdf") -> dict:
    """POST to /characters/import/pdf and return the response JSON."""
    token = create_access_token(email)
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": (filename, io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, f"Import failed for {email}: {res.text}"
    return res.json()


# ---------------------------------------------------------------------------
# Fixture PDF presence guard
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    not os.path.isfile(_FIXTURE_PDF),
    reason="Fixture PDF not found — run server/tests/fixtures/pathfinder_1e/generate_valeros.py",
)

# ---------------------------------------------------------------------------
# 1. Field-extraction tests (direct function call, no HTTP)
# ---------------------------------------------------------------------------


def test_field_extraction_system_detection():
    """Extracted sheet must be detected as Pathfinder 1e."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    assert sheet["system"]["name"] == "Pathfinder 1e"
    assert sheet["system"]["publisher"] == "Paizo"


def test_field_extraction_import_source():
    """sheet.import.source must be 'pdf'."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    assert sheet["import"]["source"] == "pdf"


def test_field_extraction_character_name():
    """Character name 'Valeros' must be extracted from the CharacterName widget."""
    content = _load_fixture_pdf()
    name, _, _, _ = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    assert name == "Valeros"


def test_field_extraction_class_and_level():
    """Class name 'Fighter' and level 5 must be extracted."""
    content = _load_fixture_pdf()
    _, level, class_name, _ = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    assert level == 5
    assert class_name == "Fighter"


def test_field_extraction_ability_scores():
    """Ability scores must be stored under sheet['stats'] with correct values."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    stats = sheet["stats"]
    assert stats["str"] == 18
    assert stats["dex"] == 14
    assert stats["con"] == 14
    assert stats["int"] == 10
    assert stats["wis"] == 10
    assert stats["cha"] == 10


def test_field_extraction_pf1e_combat_stats():
    """BAB, CMB, and CMD must be stored under top-level sheet keys."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    assert sheet["bab"] == 5
    assert sheet["cmb"] == 9
    assert sheet["cmd"] == 21


def test_field_extraction_saving_throws():
    """PF1e saving throws must be integer totals (no proficiency ranks)."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    saves = sheet["saves"]
    assert saves["fort"] == 6
    assert saves["ref"] == 3
    assert saves["will"] == 2


def test_field_extraction_skills_with_ranks():
    """PF1e skills must carry integer ranks and a computed total."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    skills = sheet["skills"]
    assert skills["Perception"]["ranks"] == 3
    assert skills["Perception"]["total"] == 6
    assert skills["Intimidate"]["ranks"] == 5
    assert skills["Intimidate"]["total"] == 9


def test_field_extraction_feats_flat_list():
    """PF1e feats must be a flat list (no category subdivisions like PF2e)."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    feats = sheet["feats"]
    assert isinstance(feats, list), "PF1e feats must be a flat list, not a dict"
    assert "Power Attack" in feats
    assert "Cleave" in feats
    assert "Weapon Focus" in feats


def test_field_extraction_special_abilities():
    """Class features must be stored under sheet['special_abilities']."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    special = sheet["special_abilities"]
    assert "Bravery" in special
    assert "Weapon Training" in special
    assert "Armor Training" in special


def test_field_extraction_equipment():
    """Equipment items must appear in sheet['equipment']."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    equipment = sheet["equipment"]
    assert "Longsword" in equipment
    assert "Full Plate" in equipment


def test_field_extraction_hit_points():
    """HP max and current must be extracted into sheet['hp']."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    hp = sheet["hp"]
    assert hp["max"] == 47
    assert hp["current"] == 47


def test_field_extraction_spells_per_day():
    """Spells per day must be stored keyed by spell-level string."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    spells_per_day = sheet["spells_per_day"]
    assert "1" in spells_per_day


def test_field_extraction_weight_carried():
    """Encumbrance / carry weight must be in sheet['carry']['weight_current']."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    assert sheet["carry"]["weight_current"] == 110


# ---------------------------------------------------------------------------
# 2. Schema-mapping tests (verify internal key conventions)
# ---------------------------------------------------------------------------


def test_schema_background_is_none():
    """Background must be explicitly None — it is not a PF1e concept."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    assert sheet.get("background") is None


def test_schema_race_field():
    """Race must be stored under sheet['race'] (not sheet['ancestry'])."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    assert sheet["race"] == "Human"
    assert "ancestry" not in sheet


def test_schema_system_namespaced_keys():
    """PF1e-only combat fields must not clobber D&D 5e hp key."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    # bab/cmb/cmd are PF1e-only; they must exist as top-level keys
    assert "bab" in sheet
    assert "cmb" in sheet
    assert "cmd" in sheet
    # hp must still follow the shared schema (not overloaded)
    assert isinstance(sheet["hp"], dict)
    assert "max" in sheet["hp"]


def test_schema_feats_not_categorised():
    """PF1e feats list must not contain category keys like 'class' or 'ancestry'."""
    content = _load_fixture_pdf()
    _, _, _, sheet = _build_character_import_sheet_from_pdf(
        content=content,
        filename="character.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )
    feats = sheet["feats"]
    assert isinstance(feats, list)
    # Ensure it's not accidentally a dict with PF2e-style category keys
    assert not isinstance(feats, dict)


# ---------------------------------------------------------------------------
# 3. Seed-user import tests (bilbo + admin via HTTP)
# ---------------------------------------------------------------------------

_BILBO_EMAIL = "bilbo@example.com"
_ADMIN_EMAIL = "admin@example.com"


def test_bilbo_can_import_pf1e_character():
    """bilbo@example.com must be able to import the PF1e fixture character."""
    client = _client()
    _ensure_user(_BILBO_EMAIL, "BilboBaggins")
    pdf_bytes = _load_fixture_pdf()
    data = _import_for_user(client, _BILBO_EMAIL, pdf_bytes, "valeros_bilbo.pdf")
    char = data["character"]
    assert char["name"] == "Valeros"
    assert char["sheet"]["system"]["name"] == "Pathfinder 1e"
    assert char["sheet"]["import"]["source"] == "pdf"


def test_admin_can_import_pf1e_character():
    """admin@example.com must be able to import the PF1e fixture character."""
    client = _client()
    _ensure_admin_user(_ADMIN_EMAIL, "Admin")
    pdf_bytes = _load_fixture_pdf()
    data = _import_for_user(client, _ADMIN_EMAIL, pdf_bytes, "valeros_admin.pdf")
    char = data["character"]
    assert char["name"] == "Valeros"
    assert char["sheet"]["system"]["name"] == "Pathfinder 1e"
    assert char["sheet"]["import"]["source"] == "pdf"


def test_admin_panel_can_see_imported_characters():
    """Admin must be able to see the imported Valeros character via the characters endpoint."""
    client = _client()
    admin = _ensure_admin_user(_ADMIN_EMAIL, "Admin")

    # Ensure Valeros is imported for admin
    pdf_bytes = _load_fixture_pdf()
    token = create_access_token(_ADMIN_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    # Check if Valeros already imported; if not, import it
    list_res = client.get("/characters", headers=headers)
    assert list_res.status_code == 200
    names = [c["name"] for c in list_res.json().get("characters", [])]
    if "Valeros" not in names:
        imp_res = client.post(
            "/characters/import/pdf?source=pdf",
            headers=headers,
            files={"file": ("valeros_admin_panel.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
        assert imp_res.status_code == 201, imp_res.text

    # Verify via the characters list endpoint (what the Admin Panel uses to show user characters)
    list_res2 = client.get("/characters", headers=headers)
    assert list_res2.status_code == 200
    all_chars = list_res2.json().get("characters", [])
    valeros = next((c for c in all_chars if c["name"] == "Valeros"), None)
    assert valeros is not None, f"Expected Valeros in admin characters; got: {[c['name'] for c in all_chars]}"
    # Field fidelity check: system and source must reflect PF1e import
    assert valeros["sheet"]["system"]["name"] == "Pathfinder 1e"
    assert valeros["sheet"]["import"]["source"] == "pdf"
    assert valeros["sheet"]["bab"] == 5
    assert valeros["sheet"]["cmb"] == 9
    assert valeros["sheet"]["cmd"] == 21

    # Verify admin panel user detail endpoint is accessible
    admin_user_res = client.get(f"/admin/users/{admin.id}", headers=headers)
    assert admin_user_res.status_code == 200, admin_user_res.text


def test_bilbo_characters_visible_via_list_endpoint():
    """Characters list endpoint must return Valeros after import for bilbo."""
    client = _client()
    _ensure_user(_BILBO_EMAIL, "BilboBaggins")
    token = create_access_token(_BILBO_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    # Import if not already present
    list_res = client.get("/characters", headers=headers)
    assert list_res.status_code == 200
    names = [c["name"] for c in list_res.json().get("characters", [])]
    if "Valeros" not in names:
        pdf_bytes = _load_fixture_pdf()
        imp_res = client.post(
            "/characters/import/pdf?source=pdf",
            headers=headers,
            files={"file": ("valeros_bilbo_list.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
        assert imp_res.status_code == 201, imp_res.text

    # Verify via list
    list_res2 = client.get("/characters", headers=headers)
    assert list_res2.status_code == 200
    names2 = [c["name"] for c in list_res2.json().get("characters", [])]
    assert "Valeros" in names2


def test_system_detection_with_widget_signals():
    """infer_ttrpg_system must detect PF1e from widget_signals alone."""
    sheet = {
        "widget_keys": ["Base Attack Bonus", "CMB", "CMD", "Spells Per Day L1"],
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Pathfinder 1e"


def test_pf1e_mechanic_profile_keys():
    """PF1e mechanic_profile must include resolution and genre."""
    sheet = {
        "widget_keys": ["Base Attack Bonus", "CMB", "CMD"],
        "class_name": "Fighter",
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Pathfinder 1e"
    profile = result["mechanic_profile"]
    assert profile["resolution"] == "d20-check"
    assert profile["genre"] == "heroic-fantasy"
    assert "base-attack-bonus" in profile.get("key_mechanics", [])
