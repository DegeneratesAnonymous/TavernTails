"""Star Trek Adventures (STA) character sheet import tests.

This file is the canonical acceptance test for the STA importer feature.
It covers:

1. Field extraction — all STA-specific fields are parsed from the PDF
2. Schema mapping  — fields land in the correct TavernTAIls schema keys
3. Seed-user imports — Ja'pel is importable on behalf of both
   ``bilbo@example.com`` (BilboBaggins) and ``admin@example.com`` (Admin)

The STA schema is distinct from D&D 5e:
- **Attributes**: Control, Daring, Fitness, Insight, Presence, Reason
- **Disciplines**: Command, Conn, Engineering, Medicine, Science, Security
- **Resources**: Stress (replaces HP), Determination
- **Identity**: Species, Rank, Assignment, Values, Focuses, Talents, Traits
"""
from __future__ import annotations

import io
import os

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.auth import create_access_token
from server.scripts.seed_star_trek_adventures_characters import build_japel_pdf, JAPEL_FIELDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURE_PDF = os.path.join(
    os.path.dirname(__file__), "fixtures", "star_trek_adventures", "japelsta.pdf"
)

_STA_TEST_EMAIL = "sta-seed-test@example.com"


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


def _auth_headers(email: str) -> dict:
    _ensure_user(email)
    token = create_access_token(email)
    return {"Authorization": f"Bearer {token}"}


def _post_japel(client: TestClient, email: str, pdf_bytes: bytes | None = None) -> dict:
    if pdf_bytes is None:
        pdf_bytes = build_japel_pdf()
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=_auth_headers(email),
        files={"file": ("japelsta.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
# A. Field extraction
# ---------------------------------------------------------------------------


def test_sta_field_extraction_character_name():
    """Character name with apostrophe is preserved."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    assert data["character"]["name"] == "Ja'pel"


def test_sta_field_extraction_species():
    """Species is stored in sheet['species']."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    assert data["character"]["sheet"]["species"] == "Vulcan"


def test_sta_field_extraction_rank_and_assignment():
    """Rank and Assignment are stored in dedicated sheet keys."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    sheet = data["character"]["sheet"]
    assert sheet["rank"] == "Lieutenant"
    assert sheet["assignment"] == "USS Enterprise"


def test_sta_field_extraction_department_as_class_name():
    """Department widget maps to top-level class_name field."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    assert data["character"]["class_name"] == "Science"


def test_sta_field_extraction_all_six_attributes():
    """All six STA attributes are extracted under sheet['attributes']."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    attrs = data["character"]["sheet"]["attributes"]
    assert attrs["control"] == 10
    assert attrs["daring"] == 7
    assert attrs["fitness"] == 9
    assert attrs["insight"] == 11
    assert attrs["presence"] == 8
    assert attrs["reason"] == 12


def test_sta_field_extraction_all_six_disciplines():
    """All six STA disciplines are extracted under sheet['disciplines']."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    discs = data["character"]["sheet"]["disciplines"]
    assert discs["command"] == 2
    assert discs["conn"] == 2
    assert discs["engineering"] == 3
    assert discs["medicine"] == 2
    assert discs["science"] == 5
    assert discs["security"] == 2


def test_sta_field_extraction_stress():
    """Stress track (max) is extracted — replaces D&D HP."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    stress = data["character"]["sheet"]["stress"]
    assert stress["max"] == 11


def test_sta_field_extraction_values():
    """Character Values (motivations) are extracted as a list."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    values = data["character"]["sheet"]["values"]
    assert isinstance(values, list)
    assert len(values) >= 1
    assert "Infinite Diversity in Infinite Combinations" in values
    assert "Logic Governs All Things" in values


def test_sta_field_extraction_focuses():
    """Focuses (specialist skills) are extracted as a list."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    focuses = data["character"]["sheet"]["focuses"]
    assert isinstance(focuses, list)
    assert "Astrophysics" in focuses
    assert "Temporal Mechanics" in focuses


def test_sta_field_extraction_talents():
    """Talents (special abilities) are extracted as a list."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    talents = data["character"]["sheet"].get("talents", [])
    assert "Kolinahr" in talents
    assert "Logical Mind" in talents


def test_sta_field_extraction_traits():
    """Traits (narrative descriptors) are extracted."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    traits = data["character"]["sheet"].get("traits", [])
    assert "Vulcan" in traits


def test_sta_field_extraction_equipment():
    """Equipment / weapon widgets are extracted under sheet['equipment']."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    equipment = data["character"]["sheet"].get("equipment", [])
    assert len(equipment) >= 1
    assert any("Phaser" in item for item in equipment)


# ---------------------------------------------------------------------------
# B. Schema mapping
# ---------------------------------------------------------------------------


def test_sta_schema_system_name():
    """sheet['system']['name'] is set to 'Star Trek Adventures'."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    assert data["character"]["sheet"]["system"]["name"] == "Star Trek Adventures"


def test_sta_schema_publisher():
    """sheet['system']['publisher'] is set to Modiphius Entertainment."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    assert "Modiphius" in data["character"]["sheet"]["system"]["publisher"]


def test_sta_schema_import_source():
    """sheet['import']['source'] is 'pdf'."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    assert data["character"]["sheet"]["import"]["source"] == "pdf"


def test_sta_schema_stress_not_stored_as_hp():
    """Stress is stored under sheet['stress'], NOT overloading sheet['hp']."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    sheet = data["character"]["sheet"]
    # stress key must exist
    assert "stress" in sheet
    # hp key must NOT be set to the stress value (it may be absent or 0)
    hp = sheet.get("hp")
    if hp is not None:
        assert hp != sheet["stress"]["max"], "Stress must not overload the hp field"


def test_sta_schema_attributes_lowercase_keys():
    """Attribute keys are stored in lowercase (control, daring, etc.)."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    attrs = data["character"]["sheet"]["attributes"]
    for key in ("control", "daring", "fitness", "insight", "presence", "reason"):
        assert key in attrs, f"Missing attribute key: {key}"


def test_sta_schema_disciplines_lowercase_keys():
    """Discipline keys are stored in lowercase."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    discs = data["character"]["sheet"]["disciplines"]
    for key in ("command", "conn", "engineering", "medicine", "science", "security"):
        assert key in discs, f"Missing discipline key: {key}"


def test_sta_schema_no_injuries_when_absent():
    """When no injury fields exist, sheet['injuries'] is absent or empty."""
    data = _post_japel(_client(), _STA_TEST_EMAIL)
    injuries = data["character"]["sheet"].get("injuries", [])
    assert injuries == []


# ---------------------------------------------------------------------------
# C. Seed-user imports (bilbo@example.com and admin@example.com)
# ---------------------------------------------------------------------------


def test_sta_seed_bilbo_can_import_japel():
    """bilbo@example.com can successfully import the Ja'pel STA character."""
    bilbo_email = os.environ.get("TAVERNTAILS_TEST_EMAIL", "bilbo@example.com")
    _ensure_user(bilbo_email)
    data = _post_japel(_client(), bilbo_email)
    char = data["character"]
    assert char["name"] == "Ja'pel"
    assert char["sheet"]["system"]["name"] == "Star Trek Adventures"
    assert char["sheet"]["import"]["source"] == "pdf"


def test_sta_seed_admin_can_import_japel():
    """admin@example.com can successfully import the Ja'pel STA character."""
    admin_email = os.environ.get("TAVERNTAILS_ADMIN_EMAIL", "admin@example.com")
    _ensure_user(admin_email)
    data = _post_japel(_client(), admin_email)
    char = data["character"]
    assert char["name"] == "Ja'pel"
    assert char["sheet"]["system"]["name"] == "Star Trek Adventures"
    assert char["sheet"]["import"]["source"] == "pdf"


def test_sta_seed_admin_character_visible_in_character_list():
    """After import, Admin's Ja'pel appears in their character list."""
    admin_email = os.environ.get("TAVERNTAILS_ADMIN_EMAIL", "admin@example.com")
    _ensure_user(admin_email)
    client = _client()
    # Import
    _post_japel(client, admin_email)
    # List
    headers = _auth_headers(admin_email)
    res = client.get("/characters", headers=headers)
    assert res.status_code == 200, res.text
    names = [c["name"] for c in res.json().get("characters", [])]
    assert "Ja'pel" in names


def test_sta_seed_bilbo_character_visible_in_character_list():
    """After import, Bilbo's Ja'pel appears in their character list."""
    bilbo_email = os.environ.get("TAVERNTAILS_TEST_EMAIL", "bilbo@example.com")
    _ensure_user(bilbo_email)
    client = _client()
    # Import
    _post_japel(client, bilbo_email)
    # List
    headers = _auth_headers(bilbo_email)
    res = client.get("/characters", headers=headers)
    assert res.status_code == 200, res.text
    names = [c["name"] for c in res.json().get("characters", [])]
    assert "Ja'pel" in names


# ---------------------------------------------------------------------------
# D. Committed fixture PDF smoke test
# ---------------------------------------------------------------------------


def test_sta_committed_fixture_pdf_imports_correctly():
    """The committed japelsta.pdf in fixtures/star_trek_adventures/ imports correctly."""
    if not os.path.exists(_FIXTURE_PDF):
        import pytest

        pytest.skip("japelsta.pdf fixture not found — check fixtures/star_trek_adventures/")

    with open(_FIXTURE_PDF, "rb") as f:
        pdf_bytes = f.read()

    data = _post_japel(_client(), _STA_TEST_EMAIL, pdf_bytes=pdf_bytes)
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "Star Trek Adventures"
    assert data["character"]["name"] == "Ja'pel"
    assert "attributes" in sheet
    assert "disciplines" in sheet
