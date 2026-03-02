"""Tests for Pathfinder 1e and Pathfinder 2e PDF character sheet import.

Covers both editions using synthetic PDFs built with pypdf widget annotations
so the test suite can run in CI without the real Paizo character sheet PDFs.

Dedicated test users:
  pf2-import@example.com / pf2-import
  pf1-import@example.com / pf1-import

Real fixture PDFs (when available) live at:
  server/tests/fixtures/pf2e/character.pdf
  server/tests/fixtures/pf1e/character.pdf
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
    """Build a minimal PDF with interactive widget annotations from *widget_map*.

    Each key becomes the widget's /T (field name) and each value becomes its
    /V (field value).  Mirrors the approach used in test_character_import.py.
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
                NameObject("/V"): TextStringObject(value),
                NameObject("/Rect"): ArrayObject(
                    [FloatObject(50.0), FloatObject(y), FloatObject(500.0), FloatObject(y + 18.0)]
                ),
            }
        )
        ref = writer._add_object(annot)  # noqa: SLF001  # pypdf has no public API for this low-level step
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
    """Build a synthetic PF2e character sheet PDF with the given field values.

    Always injects the PF2e-unique widget keys (Ancestry, Proficiency Rank)
    as disambiguation signals so the importer detects the correct edition.
    """
    base = {
        # PF2e system signals used for edition disambiguation
        "Ancestry": "",
        "Heritage": "",
        "Proficiency Rank Athletics": "",
        "Focus Points Max": "",
        "Class DC": "",
        "Current Bulk": "",
    }
    base.update(fields)
    return _make_widget_pdf(base)


def _make_pf1e_pdf(fields: dict[str, str]) -> bytes:
    """Build a synthetic PF1e character sheet PDF with the given field values.

    Always injects the PF1e-unique widget keys (Base Attack Bonus, CMB, CMD)
    as disambiguation signals so the importer detects the correct edition.
    """
    base = {
        # PF1e system signals used for edition disambiguation
        "Base Attack Bonus": "",
        "CMB": "",
        "CMD": "",
        "Spells Per Day L1": "",
    }
    base.update(fields)
    return _make_widget_pdf(base)


# ---------------------------------------------------------------------------
# PF2e tests
# ---------------------------------------------------------------------------

PF2E_EMAIL = "pf2-import@example.com"
PF2E_USERNAME = "pf2-import"

PF2E_WIDGETS: dict[str, str] = {
    # Character identity
    "CharacterName": "Seoni",
    "CLASS  LEVEL": "Sorcerer 5",
    "Ancestry": "Human",
    "Heritage": "Versatile Human",
    "Background": "Farmhand",
    # Ability scores
    "STR": "10",
    "DEX": "14",
    "CON": "12",
    "INT": "12",
    "WIS": "10",
    "CHA": "18",
    # Ability score modifiers
    "STR Mod": "0",
    "DEX Mod": "2",
    "CON Mod": "1",
    "INT Mod": "1",
    "WIS Mod": "0",
    "CHA Mod": "4",
    # Hit points
    "Hit Point Maximum": "55",
    # Combat stats
    "Armor Class": "16",
    "Class DC": "19",
    "Spell DC": "21",
    # Focus points
    "Focus Points Max": "3",
    "Focus Points Current": "2",
    # Saves with proficiency ranks
    "Fortitude Total": "7",
    "Fortitude Rank": "trained",
    "Reflex Total": "9",
    "Reflex Rank": "expert",
    "Will Total": "8",
    "Will Rank": "trained",
    # Skills with ranks
    "Acrobatics Rank": "untrained",
    "Athletics Rank": "trained",
    "Deception Rank": "expert",
    "Intimidation Rank": "trained",
    "Performance Rank": "legendary",
    # Spell slots by level
    "Spell Slots L1 Max": "4",
    "Spell Slots L2 Max": "4",
    "Spell Slots L3 Max": "3",
    # Feats by category
    "Ancestry Feat 1": "Natural Ambition",
    "Ancestry Feat 2": "General Training",
    "Class Feat 1": "Dangerous Sorcery",
    "Class Feat 2": "Spell Penetration",
    "Skill Feat 1": "Intimidating Prowess",
    "General Feat 1": "Toughness",
    # Bulk
    "Current Bulk": "3",
    "Bulk Limit": "6",
    # Equipment
    "Equipment 1": "Dagger",
    "Equipment 2": "Leather Armor",
    "Equipment 3": "Spell Components Pouch",
    # Traits / tags
    "Character Traits": "Human, Humanoid",
    # Spell known
    "spellName0": "Fireball",
}


def test_pf2e_system_detection():
    """After importing a PF2e sheet the system name should be 'Pathfinder 2e'."""
    client = _client()
    _ensure_user(PF2E_EMAIL, PF2E_USERNAME)
    token = create_access_token(PF2E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf2e_pdf(PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf2e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["system"]["name"] == "Pathfinder 2e", f"Got system: {sheet.get('system')}"


def test_pf2e_character_name():
    """Character name should be extracted from the CharacterName widget."""
    client = _client()
    _ensure_user(PF2E_EMAIL, PF2E_USERNAME)
    token = create_access_token(PF2E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf2e_pdf(PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf2e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    assert res.json()["character"]["name"] == "Seoni"


def test_pf2e_ability_scores():
    """Ability scores should be stored under sheet['stats']."""
    client = _client()
    _ensure_user(PF2E_EMAIL, PF2E_USERNAME)
    token = create_access_token(PF2E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf2e_pdf(PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf2e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    stats = res.json()["character"]["sheet"]["stats"]
    assert stats["str"] == 10
    assert stats["dex"] == 14
    assert stats["cha"] == 18


def test_pf2e_core_identity_fields():
    """Ancestry, heritage, and background should be extracted."""
    client = _client()
    _ensure_user(PF2E_EMAIL, PF2E_USERNAME)
    token = create_access_token(PF2E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf2e_pdf(PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf2e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    char = res.json()["character"]
    sheet = char["sheet"]
    assert char["class_name"] == "Sorcerer"
    assert sheet["ancestry"] == "Human"
    assert sheet["heritage"] == "Versatile Human"
    assert sheet["background"] == "Farmhand"


def test_pf2e_proficiency_ranks():
    """Skills and saves must carry a rank label instead of a proficiency bonus."""
    client = _client()
    _ensure_user(PF2E_EMAIL, PF2E_USERNAME)
    token = create_access_token(PF2E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf2e_pdf(PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf2e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    skills = sheet["skills"]
    assert skills["Athletics"]["rank"] == "trained"
    assert skills["Deception"]["rank"] == "expert"
    assert skills["Performance"]["rank"] == "legendary"
    saves = sheet["saves"]
    assert saves["fort"]["rank"] == "trained"
    assert saves["ref"]["rank"] == "expert"
    assert saves["will"]["rank"] == "trained"


def test_pf2e_hit_points_and_class_dc():
    """HP max and class DC should be populated separately."""
    client = _client()
    _ensure_user(PF2E_EMAIL, PF2E_USERNAME)
    token = create_access_token(PF2E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf2e_pdf(PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf2e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["hp"]["max"] == 55
    assert sheet["class_dc"] == 19
    assert sheet["spell_dc"] == 21


def test_pf2e_focus_points():
    """Focus point maximum should be stored under sheet['focus']['max']."""
    client = _client()
    _ensure_user(PF2E_EMAIL, PF2E_USERNAME)
    token = create_access_token(PF2E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf2e_pdf(PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf2e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["focus"]["max"] == 3


def test_pf2e_spell_slots():
    """Spell slot maximums should be keyed by level string."""
    client = _client()
    _ensure_user(PF2E_EMAIL, PF2E_USERNAME)
    token = create_access_token(PF2E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf2e_pdf(PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf2e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["spell_slots"]["1"] == 4
    assert sheet["spell_slots"]["2"] == 4
    assert sheet["spell_slots"]["3"] == 3


def test_pf2e_feats_by_category():
    """PF2e feats must be grouped by ancestry / class / skill / general category."""
    client = _client()
    _ensure_user(PF2E_EMAIL, PF2E_USERNAME)
    token = create_access_token(PF2E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf2e_pdf(PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf2e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    feats = res.json()["character"]["sheet"]["feats"]
    assert "Natural Ambition" in feats["ancestry"]
    assert "Dangerous Sorcery" in feats["class"]
    assert "Intimidating Prowess" in feats["skill"]
    assert "Toughness" in feats["general"]


def test_pf2e_bulk_and_equipment():
    """Bulk current/limit and equipment list should be populated."""
    client = _client()
    _ensure_user(PF2E_EMAIL, PF2E_USERNAME)
    token = create_access_token(PF2E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf2e_pdf(PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf2e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["bulk"]["current"] == 3
    assert sheet["bulk"]["limit"] == 6
    assert "Dagger" in sheet["equipment"]


def test_pf2e_traits():
    """Character traits list should be parsed from the Traits widget."""
    client = _client()
    _ensure_user(PF2E_EMAIL, PF2E_USERNAME)
    token = create_access_token(PF2E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf2e_pdf(PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf2e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    traits = res.json()["character"]["sheet"]["traits"]
    assert "Human" in traits
    assert "Humanoid" in traits


def test_pf2e_preview_endpoint():
    """The preview endpoint should return PF2e structure without persisting."""
    client = _client()
    preview_email = "pf2-import-preview@example.com"
    _ensure_user(preview_email, "pf2-import-preview")
    token = create_access_token(preview_email)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf2e_pdf(PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf/preview?source=pdf",
        headers=headers,
        files={"file": ("pf2e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 200, res.text
    preview = res.json()["preview"]
    assert preview["sheet"]["system"]["name"] == "Pathfinder 2e"
    assert preview["sheet"]["import"]["source"] == "pdf"

    # Confirm nothing was persisted for the preview-only user
    list_res = client.get("/characters", headers=headers)
    assert list_res.status_code == 200
    names = [c["name"] for c in list_res.json().get("characters", [])]
    assert "Seoni" not in names


def test_pf2e_import_metadata():
    """Import metadata should record source=pdf and system=Pathfinder 2e."""
    client = _client()
    _ensure_user(PF2E_EMAIL, PF2E_USERNAME)
    token = create_access_token(PF2E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf2e_pdf(PF2E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf2e_seoni_meta.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["import"]["source"] == "pdf"
    assert sheet["system"]["name"] == "Pathfinder 2e"


# ---------------------------------------------------------------------------
# PF1e tests
# ---------------------------------------------------------------------------

PF1E_EMAIL = "pf1-import@example.com"
PF1E_USERNAME = "pf1-import"

PF1E_WIDGETS: dict[str, str] = {
    # Character identity
    "CharacterName": "Valeros",
    "CLASS  LEVEL": "Fighter 5",
    "RACE": "Human",
    # Ability scores
    "STR": "18",
    "DEX": "14",
    "CON": "14",
    "INT": "10",
    "WIS": "10",
    "CHA": "10",
    # Hit points
    "Hit Point Maximum": "47",
    "Current Hit Points": "47",
    # Combat stats unique to PF1e
    "Base Attack Bonus": "5",
    "CMB": "9",
    "CMD": "21",
    # Armor
    "Armor Class": "19",
    # Saving throws (integer totals, no ranks)
    "Fortitude Total": "6",
    "Reflex Total": "3",
    "Will Total": "2",
    # Skills with explicit ranks and totals
    "Stealth Ranks": "1",
    "Stealth Total": "3",
    "Perception Ranks": "3",
    "Perception Total": "6",
    "Intimidate Ranks": "5",
    "Intimidate Total": "9",
    # Spells per day (Fighter has none; use a caster for a real character)
    "Spells Per Day L1": "0",
    # Feats (flat list)
    "Feat 1": "Power Attack",
    "Feat 2": "Cleave",
    "Feat 3": "Weapon Focus",
    # Equipment
    "Equipment 1": "Longsword",
    "Equipment 2": "Heavy Steel Shield",
    "Equipment 3": "Full Plate",
    # Carry / weight
    "Weight Carried": "110",
    # Special abilities / class features
    "Special Ability 1": "Bravery",
    "Special Ability 2": "Weapon Training",
    "Special Ability 3": "Armor Training",
}


def test_pf1e_system_detection():
    """After importing a PF1e sheet the system name should be 'Pathfinder 1e'."""
    client = _client()
    _ensure_user(PF1E_EMAIL, PF1E_USERNAME)
    token = create_access_token(PF1E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf1e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["system"]["name"] == "Pathfinder 1e", f"Got system: {sheet.get('system')}"


def test_pf1e_character_name():
    """Character name should be extracted from the CharacterName widget."""
    client = _client()
    _ensure_user(PF1E_EMAIL, PF1E_USERNAME)
    token = create_access_token(PF1E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf1e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    assert res.json()["character"]["name"] == "Valeros"


def test_pf1e_ability_scores():
    """Ability scores should be stored under sheet['stats'] (shared schema)."""
    client = _client()
    _ensure_user(PF1E_EMAIL, PF1E_USERNAME)
    token = create_access_token(PF1E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf1e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    stats = res.json()["character"]["sheet"]["stats"]
    assert stats["str"] == 18
    assert stats["dex"] == 14


def test_pf1e_core_identity_fields():
    """Race field should be populated; background should be null for PF1e."""
    client = _client()
    _ensure_user(PF1E_EMAIL, PF1E_USERNAME)
    token = create_access_token(PF1E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf1e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    char = res.json()["character"]
    sheet = char["sheet"]
    assert char["class_name"] == "Fighter"
    assert sheet["race"] == "Human"
    assert sheet.get("background") is None


def test_pf1e_combat_stats():
    """BAB, CMB, and CMD should be stored under their own sheet keys."""
    client = _client()
    _ensure_user(PF1E_EMAIL, PF1E_USERNAME)
    token = create_access_token(PF1E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf1e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["bab"] == 5
    assert sheet["cmb"] == 9
    assert sheet["cmd"] == 21


def test_pf1e_saving_throws():
    """PF1e saves should be integer totals (no proficiency rank)."""
    client = _client()
    _ensure_user(PF1E_EMAIL, PF1E_USERNAME)
    token = create_access_token(PF1E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf1e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    saves = res.json()["character"]["sheet"]["saves"]
    assert saves["fort"] == 6
    assert saves["ref"] == 3
    assert saves["will"] == 2


def test_pf1e_skill_ranks():
    """PF1e skills should carry explicit integer ranks and a computed total."""
    client = _client()
    _ensure_user(PF1E_EMAIL, PF1E_USERNAME)
    token = create_access_token(PF1E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf1e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    skills = res.json()["character"]["sheet"]["skills"]
    assert skills["Stealth"]["ranks"] == 1
    assert skills["Stealth"]["total"] == 3
    assert skills["Perception"]["ranks"] == 3


def test_pf1e_hit_points():
    """HP max and current should be extracted."""
    client = _client()
    _ensure_user(PF1E_EMAIL, PF1E_USERNAME)
    token = create_access_token(PF1E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf1e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    hp = res.json()["character"]["sheet"]["hp"]
    assert hp["max"] == 47
    assert hp["current"] == 47


def test_pf1e_spells_per_day():
    """Spells per day should be stored keyed by spell level string."""
    client = _client()
    _ensure_user(PF1E_EMAIL, PF1E_USERNAME)
    token = create_access_token(PF1E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf1e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    spells_per_day = res.json()["character"]["sheet"]["spells_per_day"]
    assert "1" in spells_per_day


def test_pf1e_feats_flat_list():
    """PF1e feats should be a flat list (no category subdivisions)."""
    client = _client()
    _ensure_user(PF1E_EMAIL, PF1E_USERNAME)
    token = create_access_token(PF1E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf1e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    feats = res.json()["character"]["sheet"]["feats"]
    assert isinstance(feats, list)
    assert "Power Attack" in feats
    assert "Cleave" in feats


def test_pf1e_equipment_and_weight():
    """Equipment list and carried weight should be stored."""
    client = _client()
    _ensure_user(PF1E_EMAIL, PF1E_USERNAME)
    token = create_access_token(PF1E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf1e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert "Longsword" in sheet["equipment"]
    assert sheet["carry"]["weight_current"] == 110


def test_pf1e_special_abilities():
    """Special abilities / class features should be captured."""
    client = _client()
    _ensure_user(PF1E_EMAIL, PF1E_USERNAME)
    token = create_access_token(PF1E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf1e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    special = res.json()["character"]["sheet"]["special_abilities"]
    assert "Bravery" in special
    assert "Weapon Training" in special


def test_pf1e_preview_endpoint():
    """The preview endpoint should return PF1e structure without persisting."""
    client = _client()
    preview_email = "pf1-import-preview@example.com"
    _ensure_user(preview_email, "pf1-import-preview")
    token = create_access_token(preview_email)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf/preview?source=pdf",
        headers=headers,
        files={"file": ("pf1e_character.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 200, res.text
    preview = res.json()["preview"]
    assert preview["sheet"]["system"]["name"] == "Pathfinder 1e"
    assert preview["sheet"]["import"]["source"] == "pdf"

    # Confirm nothing was persisted for the preview-only user
    list_res = client.get("/characters", headers=headers)
    assert list_res.status_code == 200
    names = [c["name"] for c in list_res.json().get("characters", [])]
    assert "Valeros" not in names


def test_pf1e_import_metadata():
    """Import metadata should record source=pdf and system=Pathfinder 1e."""
    client = _client()
    _ensure_user(PF1E_EMAIL, PF1E_USERNAME)
    token = create_access_token(PF1E_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = _make_pf1e_pdf(PF1E_WIDGETS)
    res = client.post(
        "/characters/import/pdf?source=pdf",
        headers=headers,
        files={"file": ("pf1e_valeros_meta.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    sheet = res.json()["character"]["sheet"]
    assert sheet["import"]["source"] == "pdf"
    assert sheet["system"]["name"] == "Pathfinder 1e"


# ---------------------------------------------------------------------------
# Edition disambiguation
# ---------------------------------------------------------------------------

def test_pf_edition_disambiguation_prefers_pf2e_over_pf1e_on_proficiency_rank_field():
    """A sheet whose widget keys include PF2e-exclusive fields must detect as PF2e.

    'Ranger' appears in both PF1e and PF2e class lists so class name alone is
    ambiguous.  The widget-key signals (Proficiency Rank, Ancestry, Heritage)
    must tip the score decisively toward PF2e.
    """
    sheet = {
        "class_name": "Ranger",
        "widget_keys": [
            "CharacterName",
            "Ancestry",
            "Heritage",
            "Proficiency Rank Athletics",
            "Proficiency Rank Stealth",
            "Focus Points Max",
            "Class DC",
            "Current Bulk",
        ],
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Pathfinder 2e", (
        f"Expected 'Pathfinder 2e' but got '{result['system_name']}' "
        f"(evidence: {result['evidence']})"
    )


def test_pf_edition_disambiguation_prefers_pf1e_on_bab_cmb_cmd():
    """A sheet whose widget keys include PF1e-exclusive combat fields must detect as PF1e."""
    sheet = {
        "class_name": "Ranger",
        "widget_keys": [
            "CharacterName",
            "Base Attack Bonus",
            "CMB",
            "CMD",
            "Spells Per Day L1",
            "Spells Per Day L2",
        ],
    }
    result = infer_ttrpg_system(sheet)
    assert result["system_name"] == "Pathfinder 1e", (
        f"Expected 'Pathfinder 1e' but got '{result['system_name']}' "
        f"(evidence: {result['evidence']})"
    )
