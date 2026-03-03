"""Seed script: create sample Alien RPG characters for bilbo@example.com and admin@example.com.

Called automatically on app startup when ``TAVERNTAILS_SEED_ALIEN_RPG=1``
(the default in development mode).  Safe to run multiple times — existing
characters are left unchanged.

Characters created:
  - bilbo@example.com  → "Zoe Hendricks" (Roughneck)
  - admin@example.com  → "Lt. Torres" (Colonial Marine)

Both characters have all Alien RPG-specific fields populated so that the
Admin Panel can verify field fidelity from both a player and admin
perspective.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger("taverntails.seed_alien_rpg")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_alien_rpg_sheet(
    *,
    career: str,
    attributes: Dict[str, int],
    skills: Dict[str, int],
    health_current: int,
    health_max: int,
    stress_current: int,
    agenda: str,
    buddy: str,
    rival: str,
    appearance: str,
    equipment: list[str],
    injuries: list[str],
    experience: int = 0,
) -> Dict[str, Any]:
    """Return a character sheet dict in the canonical Alien RPG import shape."""
    return {
        # System identification — matches the keys set by the PDF importer.
        "system": {
            "name": "Alien RPG",
            "publisher": "Free League Publishing",
        },
        "import": {
            "source": "seed",
            "imported_at": _now_iso(),
            "ddb_url": None,
            "filename": None,
            "warnings": [],
            "overrides": {"name": None, "level": None, "class_name": None},
            "extracted": {"name": None, "level": None, "class_name": None},
            "raw_text_len": 0,
            "pdf_widgets": {"count": 0, "valued_sample": {}, "values": {}},
        },
        "sheet_type": "character",
        # Alien RPG-specific fields (namespaced to avoid D&D 5e collisions).
        "alien_career": career,
        "alien_attributes": attributes,
        "alien_skills": skills,
        "alien_health": {"current": health_current, "max": health_max},
        # Stress is a unique Year Zero Engine mechanic — not HP.
        "alien_stress": {"current": stress_current},
        "agenda": agenda,
        "alien_buddy": buddy,
        "alien_rival": rival,
        "alien_appearance": appearance,
        "alien_experience": experience,
        "equipment": equipment,
        "injuries": injuries,
        # Stub D&D-style fields that the UI may reference (kept empty for non-5e sheets).
        "hp": None,
        "ac": None,
        "stats": {},
        "skills": [],
        "features": [],
        "spells": [],
        "spellbook": [],
        "inventory": [],
        "languages": [],
        "armor_proficiencies": [],
        "weapon_proficiencies": [],
        "tool_proficiencies": [],
        "other_proficiencies": [],
        "passives": {},
        "speed": None,
        "species": None,
        "background": None,
        "story": None,
        "carry": {},
        "raw_text": "",
    }


# ---------------------------------------------------------------------------
# Canonical seed characters
# ---------------------------------------------------------------------------

_ZOE_HENDRICKS: Dict[str, Any] = {
    "name": "Zoe Hendricks",
    "level": 1,
    "class_name": "Roughneck",
    "sheet": _build_alien_rpg_sheet(
        career="Roughneck",
        attributes={"strength": 4, "agility": 3, "wits": 3, "empathy": 2},
        skills={
            "close_combat": 2,
            "heavy_machinery": 3,
            "stamina": 2,
            "mobility": 2,
            "piloting": 0,
            "ranged_combat": 3,
            "comtech": 1,
            "observation": 2,
            "survival": 2,
            "command": 0,
            "manipulation": 1,
            "medical_aid": 0,
        },
        health_current=4,
        health_max=4,
        stress_current=2,
        agenda="Get out of this job with a big enough bonus to retire somewhere warm.",
        buddy="Miguel Santos",
        rival="Foreman Hicks",
        appearance="Weathered face, calloused hands, always smells faintly of hydraulic fluid.",
        equipment=["Shotgun", "Flashlight", "Motion Tracker", "Combat Knife", "Ration Pack (x3)"],
        injuries=[],
        experience=5,
    ),
}

_LT_TORRES: Dict[str, Any] = {
    "name": "Lt. Torres",
    "level": 1,
    "class_name": "Colonial Marine",
    "sheet": _build_alien_rpg_sheet(
        career="Colonial Marine",
        attributes={"strength": 4, "agility": 4, "wits": 3, "empathy": 3},
        skills={
            "close_combat": 3,
            "heavy_machinery": 1,
            "stamina": 3,
            "mobility": 3,
            "piloting": 1,
            "ranged_combat": 4,
            "comtech": 2,
            "observation": 2,
            "survival": 2,
            "command": 2,
            "manipulation": 1,
            "medical_aid": 1,
        },
        health_current=4,
        health_max=4,
        stress_current=0,
        agenda="Follow orders and bring every Marine back alive.",
        buddy="Corporal Webb",
        rival="Captain Steele",
        appearance="Regulation haircut, squared jaw, M41A pulse rifle never more than arm's reach away.",
        equipment=[
            "M41A Pulse Rifle",
            "M3 Personnel Armor",
            "Motion Tracker",
            "Medkit",
            "Frag Grenade (x2)",
            "Service Pistol",
        ],
        injuries=[],
        experience=8,
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def seed_alien_rpg_characters() -> None:
    """Create Alien RPG seed characters for the two development accounts.

    Idempotent: a character is only created when the account has **no** existing
    character whose name matches the seed record.  This prevents duplicate
    characters on repeated restarts while still allowing manual deletion + reseed.
    """
    try:
        from server import db
    except ImportError:
        logger.warning("server.db not available — skipping Alien RPG character seed")
        return

    _SEEDS = [
        ("bilbo@example.com", _ZOE_HENDRICKS),
        ("admin@example.com", _LT_TORRES),
    ]

    for email, seed in _SEEDS:
        try:
            user = db.get_user_by_identifier(email)
            if user is None:
                logger.warning("Seed user %s not found — skipping Alien RPG character seed", email)
                continue

            existing = db.list_characters_for_user(user.id)
            names = [c.name for c in existing]
            if seed["name"] in names:
                logger.debug("Alien RPG seed character %r already exists for %s", seed["name"], email)
                continue

            db.create_character(
                owner_id=user.id,
                name=seed["name"],
                level=seed["level"],
                class_name=seed["class_name"],
                sheet=seed["sheet"],
            )
            logger.info("Created Alien RPG seed character %r for %s", seed["name"], email)
        except Exception:
            logger.exception("Failed to seed Alien RPG character for %s", email)
