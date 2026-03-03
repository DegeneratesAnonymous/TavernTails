"""Shadow of the Demon Lord (SotDL) PDF character sheet import tests.

These tests exercise the SotDL-specific import path in ``server/agents/characters.py``
using a dedicated ``sotdl-import@example.com`` test user and a synthetic fixture PDF
that mirrors Mira Ashveil (a Human Rogue/Thief).

The SotDL schema is distinct from D&D 5e:
- **Attributes**: Strength, Agility, Intellect, Will (4 stats, not 6)
- **Resources**: Health (replaces HP), Corruption (unique), Insanity (unique)
- **Combat**: Defense (replaces AC), Perception (derived stat, not a skill)
- **Paths**: Novice / Expert / Master path progression (replaces class/level)
- **No skills list**: SotDL uses Boons/Banes rather than skill bonuses

Acceptance criteria covered:
1. System detection returns "Shadow of the Demon Lord"
2. Character name is extracted correctly
3. All four core attributes are stored under sheet['stats']
4. Health maps to sheet['hp']
5. Defense maps to sheet['ac']
6. SotDL-unique fields use the ``sotdl_`` namespace
7. Corruption is stored as ``sotdl_corruption``
8. Paths (novice/expert/master) are stored under ``sotdl_paths``
9. Talents are captured under sheet['talents']
10. Import metadata: source=pdf and system.name="Shadow of the Demon Lord"
11. Preview endpoint returns structure without persisting
12. Seed script imports Mira Ashveil for both bilbo@example.com and admin@example.com
"""
from __future__ import annotations

import io
import os

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.auth import create_access_token

# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_sta_import.py conventions)
# ---------------------------------------------------------------------------


def _client() -> TestClient:
    return TestClient(main.app)


def _ensure_user(email: str, username: str | None = None) -> None:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return
    _uname = username or email.split("@")[0]
    user = db.create_user(
        email=email,
        password="secret",
        username=_uname,
        profile={"name": _uname, "email": email},
    )
    db.verify_user(email, user.verification_token)


# ---------------------------------------------------------------------------
# PDF builder helper
# ---------------------------------------------------------------------------


def _make_sotdl_pdf(fields: dict) -> bytes:
    """Build a minimal PDF containing SotDL widget annotations.

    Each key becomes the widget's /T (field name) and each value becomes its
    /V (field value).  Mirrors the approach used in test_sta_import.py and
    test_pf_import.py.
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
        if y < 20.0:
            y = 750.0

    bio = io.BytesIO()
    writer.write(bio)
    bio.seek(0)
    return bio.read()


# ---------------------------------------------------------------------------
# Mira Ashveil fixture — canonical expected values
# ---------------------------------------------------------------------------

_MIRA_FIELDS: dict[str, str] = {
    # Identity
    "Character Name": "Mira Ashveil",
    "Ancestry": "Human",
    "Novice Path": "Thief",
    "Expert Path": "",
    "Master Path": "",
    # Core attributes (4 stats, not 6)
    "Strength": "10",
    "Agility": "14",
    "Intellect": "11",
    "Will": "10",
    # Combat / survival derived stats
    "Perception": "12",
    "Defense": "14",
    "Health": "13",
    "Healing Rate": "3",
    "Speed": "12",
    # SotDL-unique resources
    "Corruption": "0",
    "Insanity": "0",
    # Talents
    "Talent 1": "Nimble",
    "Talent 2": "Sneaky",
    # Equipment
    "Weapon 1": "Dagger",
    "Weapon 2": "Short Sword",
    # Languages / professions
    "Languages": "Common",
    "Professions": "Criminal, Scout",
}

_SOTDL_USER_EMAIL = "sotdl-import@example.com"


def _auth_headers() -> dict:
    _ensure_user(_SOTDL_USER_EMAIL)
    token = create_access_token(_SOTDL_USER_EMAIL)
    return {"Authorization": f"Bearer {token}"}


def _import_mira(client: TestClient) -> dict:
    """POST the Mira Ashveil PDF and return the full response JSON."""
    pdf_bytes = _make_sotdl_pdf(_MIRA_FIELDS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=_auth_headers(),
        files={"file": ("mira.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
# 1. System detection
# ---------------------------------------------------------------------------


def test_sotdl_pdf_import_detects_shadow_of_the_demon_lord_system():
    """System detection identifies the sheet as Shadow of the Demon Lord."""
    client = _client()
    data = _import_mira(client)
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "Shadow of the Demon Lord"


# ---------------------------------------------------------------------------
# 2. Character name
# ---------------------------------------------------------------------------


def test_sotdl_pdf_import_extracts_character_name():
    """Mira Ashveil's name is extracted correctly."""
    client = _client()
    data = _import_mira(client)
    assert data["character"]["name"] == "Mira Ashveil"


# ---------------------------------------------------------------------------
# 3. Attribute extraction
# ---------------------------------------------------------------------------


def test_sotdl_pdf_import_extracts_all_four_attributes():
    """All four SotDL core attributes are stored under sheet['stats']."""
    client = _client()
    data = _import_mira(client)
    stats = data["character"]["sheet"]["stats"]
    assert stats["strength"] == 10
    assert stats["agility"] == 14
    assert stats["intellect"] == 11
    assert stats["will"] == 10


# ---------------------------------------------------------------------------
# 4. Health → hp
# ---------------------------------------------------------------------------


def test_sotdl_pdf_import_maps_health_to_hp():
    """Health maps to sheet['hp']['max'] (closest shared-schema analogue)."""
    client = _client()
    data = _import_mira(client)
    hp = data["character"]["sheet"]["hp"]
    assert hp["max"] == 13


# ---------------------------------------------------------------------------
# 5. Defense → ac
# ---------------------------------------------------------------------------


def test_sotdl_pdf_import_maps_defense_to_ac():
    """Defense maps to sheet['ac'] (closest shared-schema analogue)."""
    client = _client()
    data = _import_mira(client)
    assert data["character"]["sheet"]["ac"] == 14


# ---------------------------------------------------------------------------
# 6. SotDL-unique resources are namespaced
# ---------------------------------------------------------------------------


def test_sotdl_pdf_import_stores_healing_rate_in_namespace():
    """Healing Rate is stored as sotdl_healing_rate (no 5e equivalent)."""
    client = _client()
    data = _import_mira(client)
    assert data["character"]["sheet"]["sotdl_healing_rate"] == 3


def test_sotdl_pdf_import_stores_perception_in_namespace():
    """Perception (derived stat) is stored as sotdl_perception."""
    client = _client()
    data = _import_mira(client)
    assert data["character"]["sheet"]["sotdl_perception"] == 12


def test_sotdl_pdf_import_stores_speed_in_namespace():
    """Speed is stored as sotdl_speed."""
    client = _client()
    data = _import_mira(client)
    assert data["character"]["sheet"]["sotdl_speed"] == 12


# ---------------------------------------------------------------------------
# 7. Corruption
# ---------------------------------------------------------------------------


def test_sotdl_pdf_import_stores_corruption_in_namespace():
    """Corruption is stored as sotdl_corruption (unique resource, no 5e equivalent)."""
    client = _client()
    data = _import_mira(client)
    assert data["character"]["sheet"]["sotdl_corruption"] == 0


def test_sotdl_pdf_import_stores_nonzero_corruption():
    """A non-zero Corruption value round-trips correctly."""
    client = _client()
    headers = _auth_headers()
    fields = dict(_MIRA_FIELDS)
    fields["Corruption"] = "3"
    pdf_bytes = _make_sotdl_pdf(fields)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("mira_corrupt.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    assert res.json()["character"]["sheet"]["sotdl_corruption"] == 3


# ---------------------------------------------------------------------------
# 8. Paths (novice / expert / master)
# ---------------------------------------------------------------------------


def test_sotdl_pdf_import_extracts_novice_path():
    """Novice path is stored under sheet['sotdl_paths']['novice']."""
    client = _client()
    data = _import_mira(client)
    paths = data["character"]["sheet"]["sotdl_paths"]
    assert paths["novice"] == "Thief"


def test_sotdl_pdf_import_extracts_multiple_paths():
    """Expert and Master paths are captured when present."""
    client = _client()
    headers = _auth_headers()
    fields = dict(_MIRA_FIELDS)
    fields["Expert Path"] = "Assassin"
    fields["Master Path"] = "Shadowblade"
    pdf_bytes = _make_sotdl_pdf(fields)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("mira_expert.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    paths = res.json()["character"]["sheet"]["sotdl_paths"]
    assert paths["expert"] == "Assassin"
    assert paths["master"] == "Shadowblade"


# ---------------------------------------------------------------------------
# 9. Talents
# ---------------------------------------------------------------------------


def test_sotdl_pdf_import_extracts_talents():
    """Talent widgets are captured under sheet['talents']."""
    client = _client()
    data = _import_mira(client)
    talents = data["character"]["sheet"].get("talents", [])
    assert len(talents) >= 1
    assert "Nimble" in talents
    assert "Sneaky" in talents


# ---------------------------------------------------------------------------
# 10. Source metadata
# ---------------------------------------------------------------------------


def test_sotdl_pdf_import_source_metadata():
    """Import source is 'pdf' and system name is stored in sheet['system']."""
    client = _client()
    data = _import_mira(client)
    sheet = data["character"]["sheet"]
    assert sheet["import"]["source"] == "pdf"
    assert sheet["system"]["name"] == "Shadow of the Demon Lord"


# ---------------------------------------------------------------------------
# 11. Preview endpoint — does not persist
# ---------------------------------------------------------------------------


def test_sotdl_pdf_preview_returns_structure_without_persisting():
    """Preview endpoint returns the same structure but does NOT create a character."""
    client = _client()
    preview_email = "sotdl-preview@example.com"
    _ensure_user(preview_email, "sotdl-preview")
    token = create_access_token(preview_email)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_sotdl_pdf(_MIRA_FIELDS)
    res = client.post(
        "/characters/import/pdf/preview?source=pdf",
        headers=headers,
        files={"file": ("mira_preview.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 200, res.text
    preview = res.json()["preview"]
    assert preview["name"] == "Mira Ashveil"
    assert preview["sheet"]["system"]["name"] == "Shadow of the Demon Lord"
    assert "stats" in preview["sheet"]
    assert "sotdl_corruption" in preview["sheet"]

    # Verify the character was NOT persisted for the preview-only user
    list_res = client.get("/characters", headers=headers)
    assert list_res.status_code == 200
    names = [c["name"] for c in list_res.json().get("characters", [])]
    assert "Mira Ashveil" not in names


# ---------------------------------------------------------------------------
# 12. Seed script — imports Mira for bilbo + admin
# ---------------------------------------------------------------------------


def test_seed_sotdl_characters_creates_mira_for_bilbo_and_admin():
    """Seed script creates Mira Ashveil for bilbo@example.com and admin@example.com."""
    from server.scripts.seed_shadow_of_the_demon_lord_characters import seed_sotdl_characters

    # Ensure seed users exist before seeding characters
    db.ensure_seed_users()
    seed_sotdl_characters()

    for email in ("bilbo@example.com", "admin@example.com"):
        user = db.get_user_by_identifier(email)
        assert user is not None, f"Seed user {email!r} not found"
        chars = db.list_characters_for_user(user.id)
        names = [c.name for c in chars]
        assert "Mira Ashveil" in names, f"Mira Ashveil not seeded for {email!r}; got {names}"
        # Verify key sheet fields
        mira = next(c for c in chars if c.name == "Mira Ashveil")
        sheet = mira.sheet or {}
        assert sheet.get("system", {}).get("name") == "Shadow of the Demon Lord"
        assert "sotdl_corruption" in sheet
        assert sheet.get("sotdl_corruption") == 0
        assert "sotdl_healing_rate" in sheet


# ---------------------------------------------------------------------------
# 13. Ancestry extraction
# ---------------------------------------------------------------------------


def test_sotdl_pdf_import_extracts_ancestry():
    """Ancestry is stored as sheet['race'] (closest shared-schema analogue)."""
    client = _client()
    data = _import_mira(client)
    assert data["character"]["sheet"]["race"] == "Human"


# ---------------------------------------------------------------------------
# 14. Smoke test: real fixture PDF (if present)
# ---------------------------------------------------------------------------


def test_sotdl_real_fixture_pdf_smoke():
    """Real fixture PDF (character.pdf) imports without error and detects SotDL."""
    fixture_path = os.path.join(
        os.path.dirname(__file__), "fixtures", "shadow_of_the_demon_lord", "character.pdf"
    )
    if not os.path.exists(fixture_path):
        import pytest

        pytest.skip(
            "character.pdf fixture not found -- run generate_mira.py to create it"
        )

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
    assert sheet["system"]["name"] == "Shadow of the Demon Lord"
    assert "stats" in sheet
