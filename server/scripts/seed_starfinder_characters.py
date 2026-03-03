"""Seed Starfinder characters for the two canonical dev accounts.

Imports a synthetic Navasi (Starfinder Envoy) character sheet on behalf of
``bilbo@example.com`` (BilboBaggins) and ``admin@example.com`` (Admin) so that
both users have a Starfinder character available from the first app startup.

The characters are only created if they do not already exist (idempotent).

Usage (standalone)::

    python -m server.scripts.seed_starfinder_characters

Called automatically by ``server/main.py`` on startup when
``TAVERNTAILS_SEED_STARFINDER=1`` (default).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("taverntails.seed")

# Path to the committed fixture PDF
_FIXTURE_PDF = Path(__file__).parent.parent / "tests" / "fixtures" / "starfinder" / "navasi_starfinder.pdf"

# Character name used for de-duplication checks
_CHAR_NAME = "Navasi"

# Seed account emails (mirror db.ensure_seed_users defaults)
_ADMIN_EMAIL = os.environ.get("TAVERNTAILS_ADMIN_EMAIL", "admin@example.com")
_TEST_EMAIL = os.environ.get("TAVERNTAILS_TEST_EMAIL", "bilbo@example.com")


def _build_pdf_bytes() -> bytes:
    """Return the fixture PDF bytes, building them in-memory if the file is absent."""
    if _FIXTURE_PDF.exists():
        return _FIXTURE_PDF.read_bytes()

    # Fallback: build the PDF in-memory (avoids breaking startup if the fixture
    # was accidentally removed; the fixture should normally be committed).
    logger.warning("Starfinder fixture PDF not found at %s — building in memory", _FIXTURE_PDF)
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tests.fixtures.starfinder.generate_navasi import NAVASI_FIELDS, build_pdf  # type: ignore[import]
    return build_pdf(NAVASI_FIELDS)


def _already_has_navasi(owner_id: int) -> bool:
    from server import db
    chars = db.list_characters_for_user(owner_id)
    return any(c.name == _CHAR_NAME for c in chars)


def _import_for_user(email: str) -> None:
    """Import a Navasi character for *email* if one does not already exist."""
    from server import db
    from server.agents.characters import _build_character_import_sheet_from_pdf  # type: ignore[attr-defined]

    user = db.get_user_by_identifier(email)
    if user is None:
        logger.warning("Seed user %s not found; skipping Starfinder import", email)
        return

    if _already_has_navasi(user.id):
        logger.debug("User %s already has a Navasi character; skipping", email)
        return

    try:
        pdf_bytes = _build_pdf_bytes()
        final_name, safe_level, final_class_name, sheet = _build_character_import_sheet_from_pdf(
            content=pdf_bytes,
            filename="navasi_starfinder.pdf",
            name_override=None,
            level_override=None,
            class_name_override=None,
            ddb_url=None,
            source="pdf",
            system_override=None,
        )
        db.create_character(
            owner_id=user.id,
            name=final_name,
            level=safe_level,
            class_name=final_class_name,
            sheet=sheet,
        )
        logger.info("Seeded Starfinder character '%s' (level %s) for %s", final_name, safe_level, email)
    except Exception:
        logger.exception("Failed to seed Starfinder character for %s", email)


def seed_starfinder_characters() -> None:
    """Idempotent: ensure Navasi exists for both canonical seed accounts."""
    _import_for_user(_ADMIN_EMAIL)
    _import_for_user(_TEST_EMAIL)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_starfinder_characters()
