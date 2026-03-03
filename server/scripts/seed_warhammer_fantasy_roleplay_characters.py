"""Seed WFRP 4e test characters for bilbo@example.com and admin@example.com.

This script imports the Heinrich Kessler synthetic fixture character on behalf of
both seed users.  It is idempotent: if a character named "Heinrich Kessler" already
exists for a user it is skipped to avoid duplicates.

Usage::

    python -m server.scripts.seed_warhammer_fantasy_roleplay_characters

Can also be called from application startup by importing and calling ``seed()``.
"""

from __future__ import annotations

import datetime
import os


def _build_kessler_sheet() -> dict:
    """Return a pre-built Heinrich Kessler WFRP character sheet dict.

    This is the canonical fixture character.  Field values mirror those in
    ``server/tests/fixtures/warhammer_fantasy_roleplay/generate_kessler.py``.
    All WFRP-specific fields are namespaced under ``warhammer_*`` keys so they
    do not overload D&D 5e schema fields (e.g. ``warhammer_wounds`` replaces ``hp``).
    """
    return {
        # ---- System identification ----------------------------------------
        "system": {
            "name": "Warhammer Fantasy Roleplay",
            "publisher": "Cubicle 7",
        },
        "import": {
            "source": "seed",
            "imported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "filename": "kessler_wfrp.pdf",
            "warnings": [],
        },
        # ---- Shared schema fields ----------------------------------------
        # species is stored in the shared key; race also available via career context.
        "species": "Human",
        # stats is intentionally empty for WFRP — characteristics live in warhammer_characteristics.
        # Storing a stub here keeps the schema valid without overloading D&D keys.
        "stats": {},
        "hp": {},   # wounds go into warhammer_wounds, not hp
        "ac": None,
        # ---- WFRP characteristics (percentile range 01-100+) -------------
        "warhammer_characteristics": {
            "weapon_skill": {"initial": 35, "advances": 10, "total": 45},
            "ballistic_skill": {"initial": 30, "advances": 5, "total": 35},
            "strength": {"initial": 33, "advances": 5, "total": 38},
            "toughness": {"initial": 30, "advances": 5, "total": 35},
            "initiative": {"initial": 28, "advances": 0, "total": 28},
            "agility": {"initial": 32, "advances": 5, "total": 37},
            "dexterity": {"initial": 27, "advances": 0, "total": 27},
            "intelligence": {"initial": 29, "advances": 0, "total": 29},
            "willpower": {"initial": 31, "advances": 5, "total": 36},
            "fellowship": {"initial": 25, "advances": 0, "total": 25},
        },
        # ---- Wounds (replaces HP in WFRP) --------------------------------
        "warhammer_wounds": {"current": 13, "max": 13},
        # ---- Fate & Fortune ---------------------------------------------
        "warhammer_fate": {"fate": 2, "fortune": 2},
        # ---- Resilience & Resolve ---------------------------------------
        "warhammer_resilience": {"resilience": 1, "resolve": 1},
        # ---- Corruption -------------------------------------------------
        "warhammer_corruption": 0,
        # ---- Experience -------------------------------------------------
        "warhammer_experience": {"total": 1750, "spent": 1500},
        # ---- Career -----------------------------------------------------
        "warhammer_career": {
            "name": "Mercenary",
            "level": "Soldier",
            "status": "Silver 3",
        },
        # ---- Skills (as advances) ---------------------------------------
        "warhammer_skills": [
            {"name": "Melee (Basic)", "characteristic": "WS", "advances": 15},
            {"name": "Dodge", "characteristic": "Agi", "advances": 10},
            {"name": "Endurance", "characteristic": "T", "advances": 5},
            {"name": "Intimidate", "characteristic": "S", "advances": 5},
            {"name": "Perception", "characteristic": "I", "advances": 5},
        ],
        # ---- Talents ----------------------------------------------------
        "warhammer_talents": ["Sturdy", "Resolute", "Strike Mighty Blow"],
        # ---- Trappings / equipment --------------------------------------
        "warhammer_trappings": [
            "Hand Weapon (Sword)",
            "Shield",
            "Leather Armour",
            "Backpack",
        ],
        # ---- Ambitions --------------------------------------------------
        "warhammer_ambitions": {
            "short_term": "Survive the next contract",
            "long_term": "Retire with enough gold to buy a farm",
        },
        # ---- Misc -------------------------------------------------------
        "sheet_type": "character",
    }


def seed() -> None:
    """Import Heinrich Kessler for bilbo@example.com and admin@example.com.

    Idempotent: skips users who already have a character with this name.
    """
    from server import db

    db.create_db_and_tables()
    db.ensure_seed_users()

    admin_email = (
        os.environ.get("TAVERNTAILS_ADMIN_EMAIL", "admin@example.com") or "admin@example.com"
    ).strip().lower()
    bilbo_email = (
        os.environ.get("TAVERNTAILS_TEST_EMAIL", "bilbo@example.com") or "bilbo@example.com"
    ).strip().lower()

    char_name = "Heinrich Kessler"
    char_level = 3  # approximate: career level Soldier ≈ level 3 for UI display
    char_career = "Mercenary"

    for email in (admin_email, bilbo_email):
        user = db.get_user_by_identifier(email)
        if not user:
            print(f"[seed_wfrp] User {email!r} not found — skipping")
            continue

        existing = db.list_characters_for_user(user.id)
        if any(c.name == char_name for c in existing):
            print(f"[seed_wfrp] {email!r} already has '{char_name}' — skipping")
            continue

        db.create_character(
            owner_id=user.id,
            name=char_name,
            level=char_level,
            class_name=char_career,
            sheet=_build_kessler_sheet(),
        )
        print(f"[seed_wfrp] Created '{char_name}' for {email!r}")


if __name__ == "__main__":
    seed()
