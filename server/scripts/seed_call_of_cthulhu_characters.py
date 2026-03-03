"""Seed script — import a Call of Cthulhu character for both seed users.

Imports the Roland Carmichael investigator sheet on behalf of:
  - bilbo@example.com  (BilboBaggins)
  - admin@example.com  (Admin)

Usage (from repo root)::

    python server/scripts/seed_call_of_cthulhu_characters.py

Can also be called programmatically::

    from server.scripts.seed_call_of_cthulhu_characters import run
    run()

The script is idempotent: if a character named "Roland Carmichael" already
exists for a user it will not create a duplicate.

No actual PDF file is required — the script builds the fixture bytes in memory
using the same synthetic field data as the test fixtures.
"""
from __future__ import annotations

import io
import os
import sys

# Allow running directly from repo root without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _build_investigator_pdf() -> bytes:
    """Build the Roland Carmichael investigator PDF in memory."""
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

    fields = {
        "Investigator Name": "Roland Carmichael",
        "Occupation": "Private Investigator",
        "Age": "38",
        "Residence": "Boston",
        "Birthplace": "Providence, RI",
        "STR": "60",
        "CON": "65",
        "SIZ": "65",
        "DEX": "55",
        "APP": "50",
        "INT": "80",
        "POW": "65",
        "EDU": "75",
        "Hit Points": "13",
        "Hit Points Max": "13",
        "Magic Points": "13",
        "Magic Points Max": "13",
        "Sanity Points": "65",
        "Sanity Points Max": "65",
        "Luck": "55",
        "Spot Hidden": "65",
        "Library Use": "70",
        "Psychology": "55",
        "Fast Talk": "45",
        "Firearms": "45",
        "Cthulhu Mythos": "5",
        "Background": "A seasoned investigator from Boston, Roland has seen too much to sleep soundly.",
    }

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


def _seed_for_user(email: str) -> None:
    """Import the CoC investigator character for *email* if not already present."""
    from server import db
    from server.agents.characters import _build_character_import_sheet_from_pdf

    user = db.get_user_by_identifier(email)
    if not user:
        print(f"[coc-seed] User {email!r} not found — skipping")
        return

    # Idempotency check: skip if a CoC Roland character already exists for this user
    existing = db.list_characters_for_user(user.id)
    for char in existing:
        if char.name == "Roland Carmichael":
            sheet = char.sheet or {}
            if (sheet.get("system") or {}).get("name") == "Call of Cthulhu":
                print(f"[coc-seed] Roland Carmichael already exists for {email!r} — skipping")
                return

    pdf_bytes = _build_investigator_pdf()
    final_name, safe_level, final_class_name, sheet = _build_character_import_sheet_from_pdf(
        content=pdf_bytes,
        filename="investigator.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
        system_override=None,
    )

    character = db.create_character(
        owner_id=user.id,
        name=final_name,
        level=safe_level,
        class_name=final_class_name,
        sheet=sheet,
    )
    print(f"[coc-seed] Created character {character.name!r} (id={character.id}) for {email!r}")


def run() -> None:
    """Seed CoC characters for all standard seed users."""
    from server import db as _db

    _db.create_db_and_tables()
    _db.ensure_seed_users()

    seed_emails = [
        os.environ.get("TAVERNTAILS_TEST_EMAIL", "bilbo@example.com"),
        os.environ.get("TAVERNTAILS_ADMIN_EMAIL", "admin@example.com"),
    ]
    for email in seed_emails:
        try:
            _seed_for_user(email)
        except Exception as exc:
            print(f"[coc-seed] ERROR seeding {email!r}: {exc}")


if __name__ == "__main__":
    run()
