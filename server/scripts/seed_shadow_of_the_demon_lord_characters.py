"""Seed Shadow of the Demon Lord characters for both BilboBaggins and Admin accounts.

Run this script once on app startup (or manually) to pre-populate the two
canonical seed users with a Shadow of the Demon Lord test character so the
Admin Panel can verify field fidelity from both a user and admin perspective.

Usage::

    python -m server.scripts.seed_shadow_of_the_demon_lord_characters

The script is idempotent: it skips creation if a character named
``"Mira Ashveil"`` already exists for the target user.
"""

from __future__ import annotations

import os
import sys

# Ensure the repo root is on the path when running as a script.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server import db  # noqa: E402  (import after path fixup)

# ---------------------------------------------------------------------------
# Mira Ashveil — canonical SotDL test character
# ---------------------------------------------------------------------------

_CHARACTER_NAME = "Mira Ashveil"

# Pre-built sheet dict mirrors what the PDF importer produces for a SotDL sheet.
# Fields with no D&D 5e equivalent are namespaced with "sotdl_" to avoid
# overloading shared keys (see server/tests/fixtures/shadow_of_the_demon_lord/README.md).
_MIRA_SHEET: dict = {
    # ---- Shared-schema fields ----
    "stats": {
        "strength": 10,
        "agility": 14,
        "intellect": 11,
        "will": 10,
    },
    "ac": 14,  # Defense in SotDL terminology
    "hp": {"max": 13, "current": 13},
    "race": "Human",
    "languages": ["Common"],
    "talents": [
        "Nimble",
        "Sneaky",
    ],
    "spells": [],
    "equipment": [
        "Dagger",
        "Short Sword",
        "Leather Armor",
        "Thieves' Tools",
    ],
    # ---- SotDL-specific fields (namespaced) ----
    "sotdl_healing_rate": 3,      # No D&D 5e equivalent
    "sotdl_perception": 12,       # Derived stat — not a skill list entry
    "sotdl_corruption": 0,        # Unique resource; tracks moral decay
    "sotdl_insanity": 0,          # Unique resource; tracks mental stability
    "sotdl_speed": 12,            # SotDL uses an abstract speed (yards)
    "sotdl_paths": {
        "novice": "Thief",        # Novice path unlocks at character creation
        "expert": "",             # Expert path unlocked at level 3
        "master": "",             # Master path unlocked at level 7
    },
    "sotdl_professions": ["Criminal", "Scout"],
    # ---- Import / system metadata ----
    "system": {
        "name": "Shadow of the Demon Lord",
        "publisher": "Schwalb Entertainment",
    },
    "import": {
        "source": "seed",
        "filename": "seed_shadow_of_the_demon_lord_characters.py",
        "warnings": [],
    },
}


def _seed_for_user(email: str) -> None:
    """Create Mira Ashveil for *email* if she does not already exist."""
    user = db.get_user_by_identifier(email)
    if user is None:
        print(f"[SotDL seed] User {email!r} not found — skipping.")
        return

    existing = db.list_characters_for_user(user.id)
    if any(c.name == _CHARACTER_NAME for c in existing):
        print(f"[SotDL seed] {_CHARACTER_NAME!r} already exists for {email!r} — skipping.")
        return

    char = db.create_character(
        owner_id=user.id,
        name=_CHARACTER_NAME,
        level=1,
        class_name="Rogue",
        sheet=dict(_MIRA_SHEET),
    )
    print(f"[SotDL seed] Created {_CHARACTER_NAME!r} (id={char.id}) for {email!r}.")


def seed_sotdl_characters() -> None:
    """Seed Mira Ashveil for the two canonical development users."""
    db.ensure_seed_users()
    _seed_for_user("bilbo@example.com")
    _seed_for_user("admin@example.com")


if __name__ == "__main__":
    seed_sotdl_characters()
