"""Seed Star Trek Adventures characters for the canonical dev/test accounts.

Imports a synthetic Ja'pel (Vulcan science officer) character sheet into both
the Admin account (admin@example.com) and the BilboBaggins account
(bilbo@example.com) so that both users can explore STA character tracking and
the Admin can verify field fidelity from the Admin Panel.

The import is **idempotent**: if a character named "Ja'pel" already exists for
a user it is skipped rather than duplicated.

Usage::

    python -m server.scripts.seed_star_trek_adventures_characters

Environment variables (same as ``db.ensure_seed_users``):

    TAVERNTAILS_ADMIN_EMAIL   default: admin@example.com
    TAVERNTAILS_TEST_EMAIL    default: bilbo@example.com
"""
from __future__ import annotations

import io
import os
import sys

# ---------------------------------------------------------------------------
# Bootstrap path so the script can be run directly from the repo root.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from server import db  # noqa: E402 — after sys.path fixup
from server.agents.characters import _build_character_import_sheet_from_pdf  # noqa: E402

# ---------------------------------------------------------------------------
# Ja'pel fixture fields — mirrors server/tests/fixtures/sta/generate_japel.py
# Public so tests can import them directly.
# ---------------------------------------------------------------------------
JAPEL_FIELDS: dict[str, str] = {
    "Character Name": "Ja'pel",
    "Species": "Vulcan",
    "Rank": "Lieutenant",
    "Assignment": "USS Enterprise",
    "Department": "Science",
    # Attributes (1–12 scale)
    "Control": "10",
    "Daring": "7",
    "Fitness": "9",
    "Insight": "11",
    "Presence": "8",
    "Reason": "12",
    # Disciplines (0–5 scale)
    "Command": "2",
    "Conn": "2",
    "Engineering": "3",
    "Medicine": "2",
    "Science": "5",
    "Security": "2",
    # Resources
    "Stress": "11",
    "Stress Max": "11",
    "Determination": "1",
    # Values
    "Value 1": "Infinite Diversity in Infinite Combinations",
    "Value 2": "Logic Governs All Things",
    "Value 3": "The Mission Comes First",
    "Value 4": "My People's Burden",
    # Focuses
    "Focus 1": "Astrophysics",
    "Focus 2": "Temporal Mechanics",
    "Focus 3": "Vulcan Meditation",
    # Talents
    "Talent 1": "Kolinahr",
    "Talent 2": "Logical Mind",
    # Traits
    "Trait 1": "Vulcan",
    "Trait 2": "Starfleet Officer",
    # Equipment
    "Weapon 1": "Type-2 Phaser",
    "Weapon 2": "Tricorder",
}


def build_japel_pdf() -> bytes:
    """Build the Ja'pel synthetic PDF in memory.

    Uses pypdf's internal ``_add_object`` helper (same as the fixture generator
    and test_sta_import.py) — the public PdfWriter API does not expose a direct
    method for creating individual form-field annotations; the private helper is
    the established pattern in this codebase.
    """
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    y = 750.0
    for field_name, value in JAPEL_FIELDS.items():
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

    bio = io.BytesIO()
    writer.write(bio)
    bio.seek(0)
    return bio.read()


def _seed_for_user(email: str, dry_run: bool = False) -> None:
    """Seed Ja'pel for a single user account, skipping if already present."""
    user = db.get_user_by_identifier(email)
    if not user:
        print(f"  SKIP  {email} — user not found (run ensure_seed_users first)")
        return

    existing = db.list_characters_for_user(user.id)
    if any(c.name == "Ja'pel" for c in existing):
        print(f"  SKIP  {email} — Ja'pel already exists")
        return

    if dry_run:
        print(f"  DRY   {email} — would import Ja'pel")
        return

    pdf_bytes = build_japel_pdf()
    char_name, safe_level, class_name, sheet = _build_character_import_sheet_from_pdf(
        content=pdf_bytes,
        filename="japelsta.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
        system_override=None,
    )

    character = db.create_character(
        owner_id=user.id,
        name=char_name,
        level=safe_level,
        class_name=class_name,
        sheet=sheet,
    )
    print(f"  OK    {email} — imported Ja'pel (character id={character.id})")


def seed(dry_run: bool = False) -> None:
    """Seed Ja'pel for the Admin and BilboBaggins accounts."""
    db.create_db_and_tables()
    db.ensure_seed_users()

    admin_email = os.environ.get("TAVERNTAILS_ADMIN_EMAIL", "admin@example.com")
    test_email = os.environ.get("TAVERNTAILS_TEST_EMAIL", "bilbo@example.com")

    print("Seeding Star Trek Adventures characters …")
    for email in (admin_email, test_email):
        _seed_for_user(email, dry_run=dry_run)
    print("Done.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    seed(dry_run=dry_run)
