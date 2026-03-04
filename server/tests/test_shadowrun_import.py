"""Shadowrun 6e (SR6e) PDF character sheet import tests.

These tests exercise the Shadowrun-specific import path in
``server/agents/characters.py`` using a synthetic fixture PDF that mirrors the
Chrome Razor character (a Human Street Samurai).

The Shadowrun schema is distinct from D&D 5e:
- **Attributes**: BOD, AGI, REA, STR, WIL, LOG, INT, CHA, EDG (+ MAG/RES + ESS)
- **Resources**: Physical/Stun Condition Monitors (replaces HP), Essence, Nuyen
- **Identity**: Metatype (not race/species), Archetype (not class)
- **Skills**: named skill list with ratings and optional specializations
- **Qualities**: positive/negative Qualities (not feats/traits)
- **Cyberware/Bioware**: implants that reduce Essence
- **Matrix**: optional Attack/Sleaze/DataProcessing/Firewall (Decker/TM only)

All Shadowrun-specific fields are stored under ``shadowrun_*`` namespaced keys
(e.g. ``shadowrun_attributes``, ``shadowrun_condition_monitor``) to avoid
overloading shared keys like ``hp``.
"""
from __future__ import annotations

import io
import os

from fastapi.testclient import TestClient

import server.main as main
from server import db
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


def _auth_headers(email: str = "sr-import@example.com") -> dict[str, str]:
    _ensure_user(email, email.split("@")[0])
    token = create_access_token(email)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------


def _make_sr_pdf(fields: dict[str, str]) -> bytes:
    """Build a minimal PDF with AcroForm widget annotations from *fields*.

    Mirrors the same approach used in test_sta_import.py and test_pf_import.py.
    """
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
# Chrome Razor fixture — canonical expected values
# ---------------------------------------------------------------------------

_RAZOR_FIELDS: dict[str, str] = {
    "CharacterName": "Chrome Razor",
    "Metatype": "Human",
    "Archetype": "Street Samurai",
    # Core attributes
    "BOD": "5",
    "AGI": "6",
    "REA": "4",
    "STR": "4",
    "WIL": "3",
    "LOG": "3",
    "INT": "3",
    "CHA": "2",
    "EDG": "4",
    # Essence (float; reduced by cyberware)
    "ESS": "2.8",
    # Condition monitors
    "PhysMonMax": "11",
    "StunMonMax": "10",
    "PhysDmg": "0",
    "StunDmg": "0",
    # Skills
    "Skill1Name": "Automatics",
    "Skill1Rating": "6",
    "Skill1Spec": "Assault Rifles",
    "Skill2Name": "Pistols",
    "Skill2Rating": "5",
    "Skill3Name": "Blades",
    "Skill3Rating": "5",
    "Skill3Spec": "Katana",
    "Skill4Name": "Unarmed Combat",
    "Skill4Rating": "4",
    "Skill5Name": "Stealth",
    "Skill5Rating": "5",
    "Skill5Spec": "Urban",
    "Skill6Name": "Perception",
    "Skill6Rating": "4",
    # Qualities
    "PosQuality1": "Ambidextrous",
    "PosQuality2": "Combat Sense",
    "NegQuality1": "SINner (National)",
    "NegQuality2": "Addiction (Mild, Alcohol)",
    # Cyberware
    "Cyberware1": "Wired Reflexes 1 (Used)",
    "Cyberware2": "Cybereyes Rating 2",
    "Cyberware3": "Cyberarm (Enhanced Agility)",
    # Contacts
    "Contact1Name": "Fixer",
    "Contact1Loyalty": "4",
    "Contact1Connection": "5",
    "Contact2Name": "Street Doc",
    "Contact2Loyalty": "3",
    "Contact2Connection": "3",
    # Resources
    "Nuyen": "2500",
    "Lifestyle": "Low",
}


def _import_razor(client: TestClient, email: str = "sr-import@example.com") -> dict:
    headers = _auth_headers(email)
    pdf_bytes = _make_sr_pdf(_RAZOR_FIELDS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("razor_sr6e.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ===========================================================================
# 1. System detection
# ===========================================================================


def test_shadowrun_pdf_import_detects_shadowrun_system():
    """Importing a Shadowrun sheet sets sheet['system']['name'] = 'Shadowrun'."""
    client = _client()
    data = _import_razor(client)
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "Shadowrun"


def test_shadowrun_pdf_import_sets_publisher():
    """sheet['system']['publisher'] is set to Catalyst Game Labs."""
    client = _client()
    data = _import_razor(client)
    sheet = data["character"]["sheet"]
    assert "Catalyst" in sheet["system"].get("publisher", "")


# ===========================================================================
# 2. Character name
# ===========================================================================


def test_shadowrun_pdf_import_extracts_character_name():
    """Character name is extracted from the CharacterName widget."""
    client = _client()
    data = _import_razor(client)
    assert data["character"]["name"] == "Chrome Razor"


# ===========================================================================
# 3. Attributes
# ===========================================================================


def test_shadowrun_pdf_import_extracts_all_nine_core_attributes():
    """All nine core SR6e attributes are present under sheet['shadowrun_attributes']."""
    client = _client()
    data = _import_razor(client)
    attrs = data["character"]["sheet"].get("shadowrun_attributes", {})
    for attr_name, expected in [
        ("body", 5),
        ("agility", 6),
        ("reaction", 4),
        ("strength", 4),
        ("willpower", 3),
        ("logic", 3),
        ("intuition", 3),
        ("charisma", 2),
        ("edge", 4),
    ]:
        assert attrs.get(attr_name) == expected, f"{attr_name}: expected {expected}, got {attrs.get(attr_name)}"


def test_shadowrun_pdf_import_extracts_essence():
    """Essence is stored as a float under sheet['shadowrun_essence']."""
    client = _client()
    data = _import_razor(client)
    sheet = data["character"]["sheet"]
    assert sheet.get("shadowrun_essence") == 2.8


# ===========================================================================
# 4. Condition monitors
# ===========================================================================


def test_shadowrun_pdf_import_extracts_condition_monitors():
    """Physical and stun condition monitor max values are populated."""
    client = _client()
    data = _import_razor(client)
    cmon = data["character"]["sheet"].get("shadowrun_condition_monitor", {})
    assert cmon.get("physical", {}).get("max") == 11
    assert cmon.get("stun", {}).get("max") == 10


# ===========================================================================
# 5. Skills
# ===========================================================================


def test_shadowrun_pdf_import_extracts_skills():
    """At least 4 skills are extracted under sheet['shadowrun_skills']."""
    client = _client()
    data = _import_razor(client)
    skills = data["character"]["sheet"].get("shadowrun_skills", [])
    assert len(skills) >= 4
    names = [s["name"] for s in skills]
    assert "Automatics" in names
    assert "Blades" in names


def test_shadowrun_pdf_import_extracts_skill_ratings():
    """Skill ratings are extracted correctly."""
    client = _client()
    data = _import_razor(client)
    skills = data["character"]["sheet"].get("shadowrun_skills", [])
    auto_skill = next((s for s in skills if s["name"] == "Automatics"), None)
    assert auto_skill is not None
    assert auto_skill["rating"] == 6


def test_shadowrun_pdf_import_extracts_skill_specializations():
    """Skill specializations are extracted when present."""
    client = _client()
    data = _import_razor(client)
    skills = data["character"]["sheet"].get("shadowrun_skills", [])
    auto_skill = next((s for s in skills if s["name"] == "Automatics"), None)
    assert auto_skill is not None
    assert auto_skill.get("specialization") == "Assault Rifles"


# ===========================================================================
# 6. Qualities
# ===========================================================================


def test_shadowrun_pdf_import_extracts_positive_qualities():
    """Positive qualities are stored under sheet['shadowrun_qualities']['positive']."""
    client = _client()
    data = _import_razor(client)
    quals = data["character"]["sheet"].get("shadowrun_qualities", {})
    positive = quals.get("positive", [])
    assert "Ambidextrous" in positive
    assert "Combat Sense" in positive


def test_shadowrun_pdf_import_extracts_negative_qualities():
    """Negative qualities are stored under sheet['shadowrun_qualities']['negative']."""
    client = _client()
    data = _import_razor(client)
    quals = data["character"]["sheet"].get("shadowrun_qualities", {})
    negative = quals.get("negative", [])
    assert any("SINner" in q for q in negative)


# ===========================================================================
# 7. Cyberware
# ===========================================================================


def test_shadowrun_pdf_import_extracts_cyberware():
    """Cyberware items are stored under sheet['shadowrun_cyberware']."""
    client = _client()
    data = _import_razor(client)
    cyberware = data["character"]["sheet"].get("shadowrun_cyberware", [])
    assert len(cyberware) >= 2
    assert any("Wired Reflexes" in item for item in cyberware)
    assert any("Cybereyes" in item for item in cyberware)


# ===========================================================================
# 8. Nuyen and Lifestyle
# ===========================================================================


def test_shadowrun_pdf_import_extracts_nuyen():
    """Nuyen balance is stored under sheet['shadowrun_nuyen'] (not gold/gp)."""
    client = _client()
    data = _import_razor(client)
    sheet = data["character"]["sheet"]
    assert sheet.get("shadowrun_nuyen") == 2500
    # Must NOT be stored in the generic currency field used by D&D sheets
    assert sheet.get("gold") is None or sheet.get("gold") == 0


def test_shadowrun_pdf_import_extracts_lifestyle():
    """Lifestyle tier is stored under sheet['shadowrun_lifestyle']."""
    client = _client()
    data = _import_razor(client)
    sheet = data["character"]["sheet"]
    assert sheet.get("shadowrun_lifestyle") == "Low"


# ===========================================================================
# 9. Contacts
# ===========================================================================


def test_shadowrun_pdf_import_extracts_contacts():
    """Contacts are stored under sheet['shadowrun_contacts']."""
    client = _client()
    data = _import_razor(client)
    contacts = data["character"]["sheet"].get("shadowrun_contacts", [])
    assert len(contacts) >= 2
    fixer = next((c for c in contacts if c["name"] == "Fixer"), None)
    assert fixer is not None
    assert fixer.get("loyalty") == 4
    assert fixer.get("connection") == 5


# ===========================================================================
# 10. Import metadata
# ===========================================================================


def test_shadowrun_pdf_import_source_metadata():
    """Import source is 'pdf' and sheet.system.name is 'Shadowrun'."""
    client = _client()
    data = _import_razor(client)
    sheet = data["character"]["sheet"]
    assert sheet["import"]["source"] == "pdf"
    assert sheet["system"]["name"] == "Shadowrun"


# ===========================================================================
# 11. Matrix stats (Decker / Technomancer)
# ===========================================================================


def test_shadowrun_pdf_import_extracts_matrix_stats_when_present():
    """Matrix persona stats (Attack/Sleaze/DP/FW) are extracted when present."""
    client = _client()
    headers = _auth_headers()
    fields = dict(_RAZOR_FIELDS)
    fields["Attack"] = "5"
    fields["Sleaze"] = "6"
    fields["DataProcessing"] = "7"
    fields["Firewall"] = "4"
    pdf_bytes = _make_sr_pdf(fields)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("decker.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    matrix = res.json()["character"]["sheet"].get("shadowrun_matrix", {})
    assert matrix.get("attack") == 5
    assert matrix.get("sleaze") == 6
    assert matrix.get("data_processing") == 7
    assert matrix.get("firewall") == 4


def test_shadowrun_pdf_import_no_matrix_stats_when_absent():
    """Matrix stats key is absent (or empty) when not present in the PDF."""
    client = _client()
    data = _import_razor(client)
    sheet = data["character"]["sheet"]
    # Chrome Razor is not a Decker — matrix key should be absent
    assert "shadowrun_matrix" not in sheet or sheet["shadowrun_matrix"] == {}


# ===========================================================================
# 12. Preview endpoint
# ===========================================================================


def test_shadowrun_pdf_preview_returns_structure_without_persisting():
    """Preview endpoint returns Shadowrun structure but does NOT persist a character."""
    client = _client()
    headers = _auth_headers()
    pdf_bytes = _make_sr_pdf(_RAZOR_FIELDS)

    res = client.post(
        "/characters/import/pdf/preview?source=pdf",
        headers=headers,
        files={"file": ("razor_sr6e.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 200, res.text
    preview = res.json()["preview"]
    assert preview["name"] == "Chrome Razor"
    assert preview["sheet"]["system"]["name"] == "Shadowrun"
    assert "shadowrun_attributes" in preview["sheet"]


# ===========================================================================
# 13. Seed-user imports (bilbo + admin)
# ===========================================================================


def test_shadowrun_seed_import_for_bilbo():
    """Chrome Razor can be imported programmatically for the bilbo seed user."""
    bilbo_email = os.environ.get("TAVERNTAILS_TEST_EMAIL", "bilbo@example.com")
    _ensure_user(bilbo_email, "BilboBaggins")
    user = db.get_user_by_identifier(bilbo_email)
    assert user is not None

    # Build and import
    pdf_bytes = _make_sr_pdf(_RAZOR_FIELDS)
    headers = _auth_headers(bilbo_email)
    client = _client()
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("razor_sr6e.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["character"]["name"] == "Chrome Razor"
    assert data["character"]["sheet"]["system"]["name"] == "Shadowrun"


def test_shadowrun_seed_import_for_admin():
    """Chrome Razor can be imported programmatically for the admin seed user."""
    admin_email = os.environ.get("TAVERNTAILS_ADMIN_EMAIL", "admin@example.com")
    _ensure_user(admin_email, "Admin")
    user = db.get_user_by_identifier(admin_email)
    assert user is not None

    pdf_bytes = _make_sr_pdf(_RAZOR_FIELDS)
    headers = _auth_headers(admin_email)
    client = _client()
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("razor_sr6e.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["character"]["name"] == "Chrome Razor"
    assert data["character"]["sheet"]["system"]["name"] == "Shadowrun"


# ===========================================================================
# 14. schema mapping sanity — Shadowrun fields NOT overloading D&D keys
# ===========================================================================


def test_shadowrun_pdf_condition_monitor_not_stored_as_hp():
    """Condition monitor values are NOT stored in the shared 'hp' key."""
    client = _client()
    data = _import_razor(client)
    sheet = data["character"]["sheet"]
    # Physical condition monitor is 11 for Chrome Razor — verify it lives
    # under the namespaced key, not in the generic D&D hp field.
    assert sheet["shadowrun_condition_monitor"]["physical"]["max"] == 11
    # The generic hp key (if present) must not have been populated from SR
    # condition monitor values.  It is either absent or holds a value that
    # was NOT derived from the SR sheet (0 / None / absent all acceptable).
    hp = sheet.get("hp")
    if isinstance(hp, dict):
        assert hp.get("max") != 11, "SR condition monitor (11) must not overwrite shared hp.max"
    elif isinstance(hp, int):
        assert hp != 11, "SR condition monitor (11) must not overwrite shared hp integer"


# ===========================================================================
# 15. Smoke test: real fixture PDF (server/tests/fixtures/shadowrun/razor_sr6e.pdf)
# ===========================================================================


def test_shadowrun_real_fixture_pdf_smoke():
    """Real fixture PDF (razor_sr6e.pdf) imports without error and detects Shadowrun."""
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "shadowrun", "razor_sr6e.pdf")
    if not os.path.exists(fixture_path):
        import pytest

        pytest.skip("razor_sr6e.pdf fixture not found — run generate_razor.py to create it")

    client = _client()
    headers = _auth_headers()
    with open(fixture_path, "rb") as f:
        pdf_bytes = f.read()

    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("razor_sr6e.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "Shadowrun"
    assert data["character"]["name"] == "Chrome Razor"
    assert "shadowrun_attributes" in sheet
    assert "shadowrun_condition_monitor" in sheet
