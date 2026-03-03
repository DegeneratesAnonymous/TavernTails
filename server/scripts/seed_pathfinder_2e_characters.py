"""Seed script: import sample Pathfinder 2e characters for the default seed users.

Runs automatically on app startup when ``TAVERNTAILS_SEED_USERS=1`` (the default).
Importing again is idempotent — the script skips any user who already has a
character whose ``sheet.system.name`` is ``"Pathfinder 2e"``.

Seed users (created by ``db.ensure_seed_users``):
  - ``bilbo@example.com`` / BilboBaggins
  - ``admin@example.com`` / Admin

The character data below mirrors the canonical Seoni (iconic Pathfinder sorcerer)
using field names and values identical to those tested in
``server/tests/test_pf_import.py`` so the seeded records are consistent with
the test fixtures.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("taverntails.seed.pf2e")

# ---------------------------------------------------------------------------
# Canonical PF2e seed character — Seoni, Human Sorcerer 5
# All fields use the system-namespaced keys defined in the acceptance criteria.
# ---------------------------------------------------------------------------

_SEONI_SHEET: dict[str, Any] = {
    # System identification (required by acceptance criteria)
    "system": {
        "name": "Pathfinder 2e",
        "publisher": "Paizo",
    },
    "import": {
        "source": "pdf",
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "filename": "seoni_pf2e_seed.pdf",
        "warnings": [],
    },
    # Ability scores (shared 6-score model)
    "stats": {
        "str": 10,
        "dex": 14,
        "con": 12,
        "int": 12,
        "wis": 10,
        "cha": 18,
    },
    # Armor class
    "ac": 16,
    # Hit points
    "hp": {"max": 55, "current": 55},
    # PF2e identity fields
    "ancestry": "Human",
    "heritage": "Versatile Human",
    "background": "Farmhand",
    # `species` mirrors `ancestry` for UI compatibility — the character list view
    # reads sheet.species as the primary race/species display field.
    "species": "Human",
    # PF2e combat / spellcasting stats (no D&D 5e equivalent — stored under
    # their own keys rather than overloading generic fields)
    "class_dc": 19,
    "spell_dc": 21,
    # Focus points (PF2e resource track; no 5e equivalent)
    "focus": {"max": 3, "current": 2},
    # Saving throws with proficiency ranks
    "saves": {
        "fort": {"total": 7, "rank": "trained"},
        "ref": {"total": 9, "rank": "expert"},
        "will": {"total": 8, "rank": "trained"},
    },
    # Skills keyed by name with proficiency rank
    "skills": {
        "Acrobatics": {"rank": "untrained"},
        "Athletics": {"rank": "trained"},
        "Deception": {"rank": "expert"},
        "Intimidation": {"rank": "trained"},
        "Performance": {"rank": "legendary"},
    },
    # Spell slots by level string
    "spell_slots": {"1": 4, "2": 4, "3": 3},
    # Feats grouped by category (PF2e-specific subdivision)
    "feats": {
        "ancestry": ["Natural Ambition", "General Training"],
        "class": ["Dangerous Sorcery", "Spell Penetration"],
        "skill": ["Intimidating Prowess"],
        "general": ["Toughness"],
    },
    # Bulk (PF2e encumbrance; no direct 5e equivalent)
    "bulk": {"current": 3, "limit": 6},
    # Equipment
    "equipment": ["Dagger", "Leather Armor", "Spell Components Pouch"],
    # Character traits / tags
    "traits": ["Human", "Humanoid"],
    # Known spells
    "spells": ["Fireball"],
    # Sheet type
    "sheet_type": "character",
}

_SEED_CHARACTER_NAME = "Seoni"
_SEED_CHARACTER_LEVEL = 5
_SEED_CHARACTER_CLASS = "Sorcerer"


def _already_seeded(owner_id: int) -> bool:
    """Return True if the user already has a PF2e character (idempotency guard)."""
    from server import db

    characters = db.list_characters_for_user(owner_id)
    for char in characters:
        sheet = char.sheet or {}
        system_name = (sheet.get("system") or {}).get("name", "")
        if system_name == "Pathfinder 2e":
            return True
    return False


def seed_pf2e_characters() -> None:
    """Create the sample PF2e character for each default seed user if absent."""
    from server import db

    targets = [
        ("bilbo@example.com", "BilboBaggins"),
        ("admin@example.com", "Admin"),
    ]

    for email, _username in targets:
        user = db.get_user_by_identifier(email)
        if not user:
            logger.warning("Seed user %s not found; skipping PF2e character seed", email)
            continue

        if _already_seeded(user.id):
            logger.debug("PF2e character already seeded for %s; skipping", email)
            continue

        import copy

        sheet = copy.deepcopy(_SEONI_SHEET)
        # Refresh the import timestamp so each run records the actual import time.
        sheet["import"]["imported_at"] = datetime.now(timezone.utc).isoformat()

        db.create_character(
            owner_id=user.id,
            name=_SEED_CHARACTER_NAME,
            level=_SEED_CHARACTER_LEVEL,
            class_name=_SEED_CHARACTER_CLASS,
            sheet=sheet,
        )
        logger.info("Seeded PF2e character '%s' for %s", _SEED_CHARACTER_NAME, email)
