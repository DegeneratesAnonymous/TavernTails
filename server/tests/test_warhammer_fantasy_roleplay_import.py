"""Warhammer Fantasy Roleplay (WFRP 4e) character sheet import tests.

These tests exercise the WFRP-specific import path in ``server/agents/characters.py``
using a dedicated ``wfrp-import@example.com`` test user and a synthetic fixture PDF
that mirrors the Heinrich Kessler character (a Human Mercenary Soldier from the Empire).

The WFRP 4e schema is distinct from D&D 5e:
- **Characteristics**: WS/BS/S/T/I/Agi/Dex/Int/WP/Fel (percentile range 01-100+)
- **Resources**: Wounds (replaces HP), Fate/Fortune, Resilience/Resolve, Corruption
- **Skills**: stored as advances against a characteristic (not a proficiency bonus)
- **Talents**: free-form talent list
- **Career**: replaces class — tracked as name + career level + status
- No spell slots, no saving throw proficiency, no hit dice
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
# Shared helpers (mirrors test_sta_import.py conventions)
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


# ---------------------------------------------------------------------------
# PDF builder helper
# ---------------------------------------------------------------------------


def _make_wfrp_pdf(fields: dict) -> bytes:
    """Build a minimal PDF containing WFRP 4e widget annotations (interactive form fields).

    Each key becomes the widget's /T (field name) and each value becomes its /V (value).
    Always injects the WFRP-unique characteristic abbreviation keys (WS, BS, etc.) as
    disambiguation signals so the importer detects the correct system.
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
                    [FloatObject(50.0), FloatObject(y), FloatObject(450.0), FloatObject(y + 20.0)]
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
            page = writer.add_blank_page(width=612, height=792)
            y = 750.0

    bio = io.BytesIO()
    writer.write(bio)
    bio.seek(0)
    return bio.read()


# ---------------------------------------------------------------------------
# Heinrich Kessler fixture — canonical expected values
# ---------------------------------------------------------------------------

_KESSLER_FIELDS: dict[str, str] = {
    # Identity
    "Character Name": "Heinrich Kessler",
    "Race": "Human",
    "Career": "Mercenary",
    "Career Level": "Soldier",
    "Status": "Silver 3",
    # Characteristics — initial values
    "WS": "35",
    "BS": "30",
    "S": "33",
    "T": "30",
    "I": "28",
    "Agi": "32",
    "Dex": "27",
    "Int": "29",
    "WP": "31",
    "Fel": "25",
    # Advances
    "WS Advances": "10",
    "BS Advances": "5",
    "S Advances": "5",
    "T Advances": "5",
    "I Advances": "0",
    "Agi Advances": "5",
    "Dex Advances": "0",
    "Int Advances": "0",
    "WP Advances": "5",
    "Fel Advances": "0",
    # Wounds (replaces HP in WFRP)
    "Wounds": "13",
    "Current Wounds": "13",
    # Fate & Fortune
    "Fate": "2",
    "Fortune": "2",
    # Resilience & Resolve
    "Resilience": "1",
    "Resolve": "1",
    # Corruption
    "Corruption": "0",
    # Experience
    "Experience": "1750",
    "Experience Spent": "1500",
    # Skills
    "Skill Name 1": "Melee (Basic)",
    "Skill Advances 1": "15",
    "Skill Char 1": "WS",
    "Skill Name 2": "Dodge",
    "Skill Advances 2": "10",
    "Skill Char 2": "Agi",
    "Skill Name 3": "Endurance",
    "Skill Advances 3": "5",
    "Skill Char 3": "T",
    # Talents
    "Talent 1": "Sturdy",
    "Talent 2": "Resolute",
    "Talent 3": "Strike Mighty Blow",
    # Trappings
    "Weapon 1": "Hand Weapon (Sword)",
    "Weapon 2": "Shield",
    "Trapping 1": "Leather Armour",
    # Ambitions
    "Short Term Ambition": "Survive the next contract",
    "Long Term Ambition": "Retire with enough gold to buy a farm",
}

# ---------------------------------------------------------------------------
# Shared fixture PDF bytes (computed once per module load)
# ---------------------------------------------------------------------------

_WFRP_USER_EMAIL = "wfrp-import@example.com"
_WFRP_USERNAME = "wfrp-import"


def _auth_headers() -> dict:
    _ensure_user(_WFRP_USER_EMAIL, _WFRP_USERNAME)
    token = create_access_token(_WFRP_USER_EMAIL)
    return {"Authorization": f"Bearer {token}"}


def _import_kessler(client: TestClient) -> dict:
    """POST the Kessler PDF and return the full response JSON."""
    pdf_bytes = _make_wfrp_pdf(_KESSLER_FIELDS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=_auth_headers(),
        files={"file": ("kessler.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
# 1. System detection
# ---------------------------------------------------------------------------


def test_wfrp_pdf_import_detects_warhammer_system():
    """System detection identifies the sheet as Warhammer Fantasy Roleplay."""
    client = _client()
    data = _import_kessler(client)
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "Warhammer Fantasy Roleplay", (
        f"Got system: {sheet.get('system')}"
    )


# ---------------------------------------------------------------------------
# 2. Character name
# ---------------------------------------------------------------------------


def test_wfrp_pdf_import_extracts_character_name():
    """Character name is extracted from the 'Character Name' widget."""
    client = _client()
    data = _import_kessler(client)
    assert data["character"]["name"] == "Heinrich Kessler"


# ---------------------------------------------------------------------------
# 3. Career maps to class_name
# ---------------------------------------------------------------------------


def test_wfrp_pdf_import_career_maps_to_class_name():
    """Career field maps to the top-level class_name field."""
    client = _client()
    data = _import_kessler(client)
    assert data["character"]["class_name"] == "Mercenary"


# ---------------------------------------------------------------------------
# 4. Characteristics extraction
# ---------------------------------------------------------------------------


def test_wfrp_pdf_import_extracts_characteristics_initial():
    """Characteristic initial values are stored under sheet['warhammer_characteristics']."""
    client = _client()
    data = _import_kessler(client)
    chars = data["character"]["sheet"]["warhammer_characteristics"]
    assert chars["weapon_skill"]["initial"] == 35
    assert chars["ballistic_skill"]["initial"] == 30
    assert chars["strength"]["initial"] == 33
    assert chars["toughness"]["initial"] == 30
    assert chars["initiative"]["initial"] == 28
    assert chars["agility"]["initial"] == 32
    assert chars["dexterity"]["initial"] == 27
    assert chars["intelligence"]["initial"] == 29
    assert chars["willpower"]["initial"] == 31
    assert chars["fellowship"]["initial"] == 25


def test_wfrp_pdf_import_extracts_characteristic_advances():
    """Characteristic advances are stored alongside initial values."""
    client = _client()
    data = _import_kessler(client)
    chars = data["character"]["sheet"]["warhammer_characteristics"]
    assert chars["weapon_skill"]["advances"] == 10
    assert chars["ballistic_skill"]["advances"] == 5
    assert chars["agility"]["advances"] == 5


def test_wfrp_pdf_import_computes_characteristic_totals():
    """Characteristic totals (initial + advances) are pre-computed."""
    client = _client()
    data = _import_kessler(client)
    chars = data["character"]["sheet"]["warhammer_characteristics"]
    assert chars["weapon_skill"]["total"] == 45   # 35 + 10
    assert chars["toughness"]["total"] == 35      # 30 + 5
    assert chars["fellowship"]["total"] == 25     # 25 + 0


# ---------------------------------------------------------------------------
# 5. Wounds track (replaces HP)
# ---------------------------------------------------------------------------


def test_wfrp_pdf_import_extracts_wounds_not_hp():
    """Wounds are stored under warhammer_wounds, not in the shared hp field."""
    client = _client()
    data = _import_kessler(client)
    sheet = data["character"]["sheet"]
    wounds = sheet["warhammer_wounds"]
    assert wounds["max"] == 13
    assert wounds["current"] == 13
    # The shared hp key must NOT be populated with wounds data
    hp = sheet.get("hp") or {}
    assert hp.get("max") != 13 or hp == {}, (
        "WFRP wounds must not be stored in the shared 'hp' key — use 'warhammer_wounds' instead"
    )


# ---------------------------------------------------------------------------
# 6. Fate / Fortune
# ---------------------------------------------------------------------------


def test_wfrp_pdf_import_extracts_fate_and_fortune():
    """Fate total and Fortune points are stored under sheet['warhammer_fate']."""
    client = _client()
    data = _import_kessler(client)
    fate = data["character"]["sheet"]["warhammer_fate"]
    assert fate["fate"] == 2
    assert fate["fortune"] == 2


# ---------------------------------------------------------------------------
# 7. Resilience / Resolve
# ---------------------------------------------------------------------------


def test_wfrp_pdf_import_extracts_resilience_and_resolve():
    """Resilience and Resolve are stored under sheet['warhammer_resilience']."""
    client = _client()
    data = _import_kessler(client)
    resil = data["character"]["sheet"]["warhammer_resilience"]
    assert resil["resilience"] == 1
    assert resil["resolve"] == 1


# ---------------------------------------------------------------------------
# 8. Skills as advances
# ---------------------------------------------------------------------------


def test_wfrp_pdf_import_extracts_skills_as_advances():
    """Skills are stored as advance-value dicts under sheet['warhammer_skills']."""
    client = _client()
    data = _import_kessler(client)
    skills = data["character"]["sheet"]["warhammer_skills"]
    assert len(skills) >= 1
    names = [s["name"] for s in skills]
    assert "Melee (Basic)" in names
    assert "Dodge" in names
    # Advances value present for Melee (Basic)
    melee = next(s for s in skills if s["name"] == "Melee (Basic)")
    assert melee["advances"] == 15


# ---------------------------------------------------------------------------
# 9. Talents
# ---------------------------------------------------------------------------


def test_wfrp_pdf_import_extracts_talents():
    """Talents are captured under sheet['warhammer_talents']."""
    client = _client()
    data = _import_kessler(client)
    talents = data["character"]["sheet"]["warhammer_talents"]
    assert "Sturdy" in talents
    assert "Resolute" in talents
    assert "Strike Mighty Blow" in talents


# ---------------------------------------------------------------------------
# 10. Career
# ---------------------------------------------------------------------------


def test_wfrp_pdf_import_extracts_career():
    """Career name, level, and status are stored under sheet['warhammer_career']."""
    client = _client()
    data = _import_kessler(client)
    career = data["character"]["sheet"]["warhammer_career"]
    assert career["name"] == "Mercenary"
    assert career["level"] == "Soldier"
    assert career["status"] == "Silver 3"


# ---------------------------------------------------------------------------
# 11. Trappings / equipment
# ---------------------------------------------------------------------------


def test_wfrp_pdf_import_extracts_trappings():
    """Trappings / equipment are captured under sheet['warhammer_trappings']."""
    client = _client()
    data = _import_kessler(client)
    trappings = data["character"]["sheet"]["warhammer_trappings"]
    assert len(trappings) >= 1
    assert any("Sword" in t or "Weapon" in t for t in trappings)


# ---------------------------------------------------------------------------
# 12. Source metadata
# ---------------------------------------------------------------------------


def test_wfrp_pdf_import_source_metadata():
    """Import source is 'pdf' and system name is stored in sheet['system']."""
    client = _client()
    data = _import_kessler(client)
    sheet = data["character"]["sheet"]
    assert sheet["import"]["source"] == "pdf"
    assert sheet["system"]["name"] == "Warhammer Fantasy Roleplay"
    assert sheet["system"]["publisher"] == "Cubicle 7"


# ---------------------------------------------------------------------------
# 13. Preview endpoint — does not persist
# ---------------------------------------------------------------------------


def test_wfrp_pdf_preview_returns_structure_without_persisting():
    """Preview endpoint returns the WFRP structure but does NOT create a character."""
    client = _client()
    preview_email = "wfrp-import-preview@example.com"
    _ensure_user(preview_email, "wfrp-import-preview")
    token = create_access_token(preview_email)
    headers = {"Authorization": f"Bearer {token}"}
    pdf_bytes = _make_wfrp_pdf(_KESSLER_FIELDS)

    res = client.post(
        "/characters/import/pdf/preview?source=pdf",
        headers=headers,
        files={"file": ("kessler_preview.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 200, res.text
    preview = res.json()["preview"]
    assert preview["name"] == "Heinrich Kessler"
    assert preview["sheet"]["system"]["name"] == "Warhammer Fantasy Roleplay"
    assert "warhammer_characteristics" in preview["sheet"]
    assert "warhammer_wounds" in preview["sheet"]

    # Verify the character was NOT persisted
    list_res = client.get("/characters", headers=headers)
    assert list_res.status_code == 200
    names = [c["name"] for c in list_res.json().get("characters", [])]
    assert "Heinrich Kessler" not in names


# ---------------------------------------------------------------------------
# 14. Experience
# ---------------------------------------------------------------------------


def test_wfrp_pdf_import_extracts_experience():
    """Experience total and spent are stored under sheet['warhammer_experience']."""
    client = _client()
    data = _import_kessler(client)
    xp = data["character"]["sheet"]["warhammer_experience"]
    assert xp["total"] == 1750
    assert xp["spent"] == 1500


# ---------------------------------------------------------------------------
# 15. System detection via infer_ttrpg_system (unit test, no HTTP)
# ---------------------------------------------------------------------------


def test_wfrp_system_detect_unit():
    """infer_ttrpg_system identifies a WFRP sheet from characteristic keys + skills."""
    sheet = {
        "class_name": "Mercenary",
        "stats": {"ws": 1, "bs": 1, "t": 1, "wp": 1, "fel": 1},
        "skills": [
            {"name": "Melee"},
            {"name": "Dodge"},
            {"name": "Endurance"},
            {"name": "Cool"},
        ],
        "widget_keys": [
            "Character Name", "Race", "Career", "WS", "BS", "S", "T",
            "WS Advances", "BS Advances", "Wounds", "Fate", "Resilience",
            "Skill Name 1", "Skill Advances 1",
        ],
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Warhammer Fantasy Roleplay", (
        f"Expected 'Warhammer Fantasy Roleplay' but got '{result['system_name']}' "
        f"(evidence: {result['evidence']})"
    )


# ---------------------------------------------------------------------------
# 16. Seed script — imports Kessler for bilbo and admin
# ---------------------------------------------------------------------------


def test_seed_wfrp_characters_creates_kessler_for_both_seed_users():
    """seed() creates Heinrich Kessler for both bilbo@example.com and admin@example.com."""
    from server.scripts.seed_warhammer_fantasy_roleplay_characters import seed

    # Run seed (idempotent)
    seed()

    for email in ("bilbo@example.com", "admin@example.com"):
        user = db.get_user_by_identifier(email)
        assert user is not None, f"Seed user {email!r} not found"
        chars = db.list_characters_for_user(user.id)
        names = [c.name for c in chars]
        assert "Heinrich Kessler" in names, (
            f"'Heinrich Kessler' not found in characters for {email!r}: {names}"
        )


def test_seed_wfrp_characters_sheet_fields():
    """The seeded Kessler character has correct WFRP schema fields."""
    from server.scripts.seed_warhammer_fantasy_roleplay_characters import seed

    seed()

    user = db.get_user_by_identifier("bilbo@example.com")
    assert user is not None
    chars = db.list_characters_for_user(user.id)
    kessler = next((c for c in chars if c.name == "Heinrich Kessler"), None)
    assert kessler is not None

    sheet = kessler.sheet or {}
    assert sheet["system"]["name"] == "Warhammer Fantasy Roleplay"
    assert sheet["import"]["source"] == "seed"
    assert sheet["warhammer_wounds"]["max"] == 13
    assert sheet["warhammer_characteristics"]["weapon_skill"]["total"] == 45
    assert "Sturdy" in sheet["warhammer_talents"]


def test_seed_wfrp_characters_is_idempotent():
    """Running seed() twice does not create duplicate characters."""
    from server.scripts.seed_warhammer_fantasy_roleplay_characters import seed

    seed()
    seed()  # second call must be a no-op

    user = db.get_user_by_identifier("bilbo@example.com")
    assert user is not None
    chars = db.list_characters_for_user(user.id)
    kessler_count = sum(1 for c in chars if c.name == "Heinrich Kessler")
    assert kessler_count == 1, f"Expected 1 Kessler character but found {kessler_count}"


# ---------------------------------------------------------------------------
# 17. Smoke test: real fixture PDF (server/tests/fixtures/warhammer_fantasy_roleplay/kessler_wfrp.pdf)
# ---------------------------------------------------------------------------


def test_wfrp_real_fixture_pdf_smoke():
    """Real fixture PDF (kessler_wfrp.pdf) imports without error and detects WFRP."""
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        "fixtures", "warhammer_fantasy_roleplay", "kessler_wfrp.pdf",
    )
    if not os.path.exists(fixture_path):
        import pytest
        pytest.skip(
            "kessler_wfrp.pdf fixture not found — run generate_kessler.py to create it"
        )

    client = _client()
    headers = _auth_headers()
    with open(fixture_path, "rb") as f:
        pdf_bytes = f.read()

    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("kessler_wfrp.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    sheet = data["character"]["sheet"]
    assert sheet["system"]["name"] == "Warhammer Fantasy Roleplay"
    assert data["character"]["name"] == "Heinrich Kessler"
    assert "warhammer_characteristics" in sheet
    assert "warhammer_wounds" in sheet
    assert "warhammer_talents" in sheet
