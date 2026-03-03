"""Seed Pathfinder 1e characters for the two canonical development accounts.

Imports the Valeros (Human Fighter 5) fixture character on behalf of both:
  * bilbo@example.com  (BilboBaggins — the default test player)
  * admin@example.com  (Admin — the default admin account)

The seed data comes from the committed fixture PDF at::

    server/tests/fixtures/pathfinder_1e/character.pdf

Usage (from repo root)::

    python -m server.scripts.seed_pathfinder_1e_characters

The script is idempotent: if a character named "Valeros" already exists for
the target user it is skipped rather than duplicated.

The fixture PDF is a synthetic sheet built with pypdf widget annotations and
does NOT reproduce any copyrighted Paizo artwork or rules text.
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Bootstrap path so we can import server modules whether run as a script or
# as a module (python -m server.scripts.seed_pathfinder_1e_characters).
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server import db  # noqa: E402  # import after path fix
from server.agents.characters import _build_character_import_sheet_from_pdf  # noqa: E402

# ---------------------------------------------------------------------------
# Path to the committed fixture PDF
# ---------------------------------------------------------------------------
_FIXTURE_PDF = os.path.join(
    os.path.dirname(__file__),
    "..",
    "tests",
    "fixtures",
    "pathfinder_1e",
    "character.pdf",
)


def _seed_for_user(email: str, display_name: str) -> None:
    """Import the Valeros fixture character for *email*, unless one already exists."""
    user = db.get_user_by_identifier(email)
    if not user:
        print(f"  SKIP  {email}: user not found (run db.ensure_seed_users() first)")
        return

    # Skip if Valeros already exists for this user
    existing = db.list_characters_for_user(user.id)
    if any(c.name == "Valeros" for c in existing):
        print(f"  SKIP  {email}: Valeros already imported")
        return

    fixture_path = os.path.abspath(_FIXTURE_PDF)
    if not os.path.isfile(fixture_path):
        print(f"  ERROR {email}: fixture PDF not found at {fixture_path}")
        print("         Run: python server/tests/fixtures/pathfinder_1e/generate_valeros.py")
        return

    with open(fixture_path, "rb") as fh:
        content = fh.read()

    try:
        final_name, safe_level, final_class_name, sheet = _build_character_import_sheet_from_pdf(
            content=content,
            filename="character.pdf",
            name_override=None,
            level_override=None,
            class_name_override=None,
            ddb_url=None,
            source="pdf",
            system_override=None,
        )
    except Exception as exc:  # pragma: no cover
        print(f"  ERROR {email}: import failed — {exc}")
        return

    character = db.create_character(
        owner_id=user.id,
        name=final_name,
        level=safe_level,
        class_name=final_class_name,
        sheet=sheet,
    )
    system_name = (sheet.get("system") or {}).get("name", "Unknown")
    print(f"  OK    {email}: created character #{character.id} '{character.name}' "
          f"(level {character.level}, system={system_name})")


def seed() -> None:
    db.create_db_and_tables()
    db.ensure_seed_users()

    admin_email = (os.environ.get("TAVERNTAILS_ADMIN_EMAIL") or "admin@example.com").strip().lower()
    test_email = (os.environ.get("TAVERNTAILS_TEST_EMAIL") or "bilbo@example.com").strip().lower()

    print("Seeding Pathfinder 1e characters …")
    _seed_for_user(admin_email, "Admin")
    _seed_for_user(test_email, "BilboBaggins")
    print("Done.")


if __name__ == "__main__":
    seed()
