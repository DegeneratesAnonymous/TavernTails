"""Seed D&D 5e characters for the two standard seed users.

Run from the repository root::

    python -m server.scripts.seed_dandd_5e_characters

Or import and call ``seed_dnd5e_characters()`` from the lifespan handler if
automatic seeding on startup is desired.

The script imports a filled-out D&D 5e character (Thorin Ironfist, a Mountain
Dwarf Fighter 5) for both ``bilbo@example.com`` (BilboBaggins) and
``admin@example.com`` (Admin) so that both accounts have a D&D 5e character
visible in the UI and Admin Panel immediately after first boot.

The seeded sheet includes all fields required by the acceptance criteria:
STR/DEX/CON/INT/WIS/CHA, HP, AC, proficiency bonus, spell slots, skills,
saving throws, hit dice, inspiration, death saves, and features.
"""

from __future__ import annotations

import io
import logging
import os
import sys

# Ensure the repo root is on the path so this script can be run directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thorin Ironfist — canonical D&D 5e seed character
# ---------------------------------------------------------------------------

_THORIN_SHEET: dict = {
    "system": {
        "name": "D&D 5e",
        "publisher": "Wizards of the Coast",
    },
    "import": {
        "source": "seed",
        "imported_at": None,  # filled at runtime
        "filename": "seed_dandd_5e_characters.py",
        "warnings": [],
    },
    "stats": {"str": 18, "dex": 12, "con": 16, "int": 10, "wis": 12, "cha": 8},
    "hp": {"max": 52, "current": 52, "temp": 0},
    "ac": 18,
    "initiative": 1,
    "proficiency_bonus": 3,
    "hit_dice": "5d10",
    "inspiration": False,
    "death_saves": {"successes": 0, "failures": 0},
    "race": "Mountain Dwarf",
    "background": "Soldier",
    "saves": {
        "str": {"total": 7, "proficient": True},
        "dex": {"total": 1, "proficient": False},
        "con": {"total": 6, "proficient": True},
        "int": {"total": 0, "proficient": False},
        "wis": {"total": 1, "proficient": False},
        "cha": {"total": -1, "proficient": False},
    },
    "skills": {
        "Athletics": {"modifier": 7, "proficient": True},
        "Perception": {"modifier": 4, "proficient": True},
        "Intimidation": {"modifier": 2, "proficient": True},
        "Animal Handling": {"modifier": 4, "proficient": True},
        "Sleight of Hand": {"modifier": 1, "proficient": False},
        "Survival": {"modifier": 4, "proficient": True},
    },
    # Fighter 5 with no spellcasting
    "spell_slots": {},
    "features": [
        "Action Surge",
        "Second Wind",
        "Extra Attack",
        "Martial Archetype: Champion",
        "Improved Critical",
    ],
    "equipment": [
        "Longsword",
        "Chain Mail",
        "Shield",
        "Handaxe x2",
        "Explorer's Pack",
    ],
    "languages": ["Common", "Dwarvish"],
    "carry": {
        "weight_current": 85,
        "weight_capacity": 270,
        "use_encumbrance": True,
    },
}


def _build_seed_sheet() -> dict:
    """Return a fresh copy of the seed sheet with the current timestamp."""
    from datetime import datetime, timezone

    sheet = dict(_THORIN_SHEET)
    imp = dict(sheet["import"])
    imp["imported_at"] = datetime.now(timezone.utc).isoformat()
    sheet["import"] = imp
    return sheet


def _make_seed_pdf() -> bytes:
    """Build a minimal synthetic PDF for the seed character.

    Uses pypdf widget annotations so the import pipeline can be exercised
    end-to-end without depending on a real WotC-licensed character sheet PDF.
    """
    try:
        from pypdf import PdfWriter
        from pypdf.generic import (
            ArrayObject,
            DictionaryObject,
            FloatObject,
            NameObject,
            TextStringObject,
        )
    except ImportError:
        logger.warning("pypdf not available — using direct DB creation for seed import")
        return b""

    widgets: dict[str, str] = {
        "CharacterName": "Thorin Ironfist",
        "CLASS  LEVEL": "Fighter 5",
        "Race": "Mountain Dwarf",
        "Background": "Soldier",
        "STR": "18",
        "DEX": "12",
        "CON": "16",
        "INT": "10",
        "WIS": "12",
        "CHA": "8",
        "Hit Point Maximum": "52",
        "Current Hit Points": "52",
        "Temporary Hit Points": "0",
        "Armor Class": "18",
        "Initiative": "1",
        "ProfBonus": "3",
        "HD Total": "5d10",
        "Inspiration": "0",
        "Death Save Successes": "0",
        "Death Save Failures": "0",
        "ST Strength": "7",
        "ST Dexterity": "1",
        "ST Constitution": "6",
        "ST Intelligence": "0",
        "ST Wisdom": "1",
        "ST Charisma": "-1",
        "Athletics": "7",
        "Perception": "4",
        "Intimidation": "2",
        "Animal Handling": "4",
        "Sleight of Hand": "1",
        "SlotsTotal1": "0",
        "Features and Traits": "Action Surge\nSecond Wind\nExtra Attack",
        "Equipment 1": "Longsword",
        "Equipment 2": "Chain Mail",
        "Equipment 3": "Shield",
    }

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    y = 750.0
    for field_name, value in widgets.items():
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


def _ensure_user_exists(email: str, username: str) -> None:
    """Ensure the seed user account exists and is verified."""
    from server import db

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


def _character_already_seeded(owner_id: int) -> bool:
    """Return True if the owner already has a D&D 5e character named Thorin Ironfist."""
    from server import db

    chars = db.list_characters_for_user(owner_id)
    for c in chars:
        sheet = c.sheet or {}
        system_name = (sheet.get("system") or {}).get("name", "")
        if c.name == "Thorin Ironfist" and system_name == "D&D 5e":
            return True
    return False


def _import_via_pdf_pipeline(email: str) -> None:
    """Use the PDF import pipeline (preferred path — exercises the full importer)."""
    from fastapi.testclient import TestClient

    import server.main as _main
    from server.auth import create_access_token

    pdf_bytes = _make_seed_pdf()
    if not pdf_bytes:
        raise RuntimeError("Could not build seed PDF")

    client = TestClient(_main.app)
    token = create_access_token(email)
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post(
        "/characters/import/pdf?source=seed",
        headers=headers,
        files={"file": ("thorin_seed.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    if res.status_code not in (200, 201):
        raise RuntimeError(f"PDF import failed ({res.status_code}): {res.text}")
    logger.info("Seeded D&D 5e character for %s via PDF pipeline", email)


def _import_via_direct_db(email: str) -> None:
    """Fallback: create the character directly in the DB without a PDF round-trip."""
    from server import db

    user = db.get_user_by_identifier(email)
    if not user:
        raise RuntimeError(f"User not found: {email}")
    sheet = _build_seed_sheet()
    db.create_character(
        owner_id=user.id,
        name="Thorin Ironfist",
        level=5,
        class_name="Fighter",
        sheet=sheet,
    )
    logger.info("Seeded D&D 5e character for %s via direct DB creation", email)


def seed_dnd5e_characters() -> None:
    """Import a D&D 5e character for both bilbo@example.com and admin@example.com.

    Safe to call multiple times — skips users who already have Thorin Ironfist
    in their character list.
    """
    from server import db

    seed_accounts = [
        ("bilbo@example.com", "BilboBaggins"),
        ("admin@example.com", "Admin"),
    ]

    for email, username in seed_accounts:
        try:
            _ensure_user_exists(email, username)
            user = db.get_user_by_identifier(email)
            if user is None:
                logger.warning("Could not find user %s after ensure — skipping", email)
                continue
            if _character_already_seeded(user.id):
                logger.info("D&D 5e character already seeded for %s — skipping", email)
                continue
            try:
                _import_via_pdf_pipeline(email)
            except Exception as pdf_exc:
                logger.warning(
                    "PDF import pipeline failed for %s (%s); falling back to direct DB creation",
                    email,
                    pdf_exc,
                )
                _import_via_direct_db(email)
        except Exception:
            logger.exception("Failed to seed D&D 5e character for %s", email)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    seed_dnd5e_characters()
    print("D&D 5e character seeding complete.")
