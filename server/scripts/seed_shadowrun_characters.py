"""Seed Shadowrun 6e test characters for the canonical dev/test accounts.

Imports a pre-defined Street Samurai (Chrome Razor) on behalf of both
``bilbo@example.com`` (BilboBaggins) and ``admin@example.com`` so that:

- The Admin Panel shows Shadowrun characters for both users after startup.
- Automated tests can validate field fidelity without uploading a real PDF.

Usage — called automatically by ``server/main.py`` when
``TAVERNTAILS_SEED_SHADOWRUN=1`` is set (defaults to ``0`` so CI stays clean):

    TAVERNTAILS_SEED_SHADOWRUN=1 uvicorn server.main:app

Or run stand-alone (creates / migrates the DB as needed):

    python -m server.scripts.seed_shadowrun_characters

Environment variables (all optional — fall back to ``ensure_seed_users`` defaults):
    TAVERNTAILS_ADMIN_EMAIL    (default: admin@example.com)
    TAVERNTAILS_TEST_EMAIL     (default: bilbo@example.com)
"""

from __future__ import annotations

import io
import os
from typing import Any

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

from server import db
from server.agents.characters import _build_character_import_sheet_from_pdf  # noqa: PLC2701


# ---------------------------------------------------------------------------
# Character sheet data — matches the fixture used by test_shadowrun_import.py
# ---------------------------------------------------------------------------
_RAZOR_FIELDS: dict[str, str] = {
    "CharacterName": "Chrome Razor",
    "Metatype": "Human",
    "Archetype": "Street Samurai",
    "BOD": "5",
    "AGI": "6",
    "REA": "4",
    "STR": "4",
    "WIL": "3",
    "LOG": "3",
    "INT": "3",
    "CHA": "2",
    "EDG": "4",
    "ESS": "2.8",
    "PhysMonMax": "11",
    "StunMonMax": "10",
    "PhysDmg": "0",
    "StunDmg": "0",
    "Skill1Name": "Automatics",
    "Skill1Rating": "6",
    "Skill1Spec": "Assault Rifles",
    "Skill2Name": "Pistols",
    "Skill2Rating": "5",
    "Skill3Name": "Blades",
    "Skill3Rating": "5",
    "Skill3Spec": "Katana",
    "Skill4Name": "Unarmed Combat",
    "Skill4Rating": "4",
    "Skill5Name": "Stealth",
    "Skill5Rating": "5",
    "Skill5Spec": "Urban",
    "Skill6Name": "Perception",
    "Skill6Rating": "4",
    "PosQuality1": "Ambidextrous",
    "PosQuality2": "Combat Sense",
    "NegQuality1": "SINner (National)",
    "NegQuality2": "Addiction (Mild, Alcohol)",
    "Cyberware1": "Wired Reflexes 1 (Used)",
    "Cyberware2": "Cybereyes Rating 2",
    "Cyberware3": "Cyberarm (Enhanced Agility)",
    "Contact1Name": "Fixer",
    "Contact1Loyalty": "4",
    "Contact1Connection": "5",
    "Contact2Name": "Street Doc",
    "Contact2Loyalty": "3",
    "Contact2Connection": "3",
    "Nuyen": "2500",
    "Lifestyle": "Low",
}


def _build_fixture_pdf(fields: dict[str, str]) -> bytes:
    """Build a minimal PDF with AcroForm widget annotations from *fields*."""
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


def _import_for_user(user: db.User, pdf_bytes: bytes) -> None:
    """Import a Chrome Razor character for *user* (idempotent — skips if already present)."""
    with db.Session(db.engine) as session:
        from sqlmodel import select

        existing = session.exec(
            select(db.Character).where(
                db.Character.owner_id == user.id,
                db.Character.name == "Chrome Razor",
            )
        ).first()
        if existing:
            return

    final_name, safe_level, final_class_name, sheet = _build_character_import_sheet_from_pdf(
        content=pdf_bytes,
        filename="razor_sr6e.pdf",
        name_override=None,
        level_override=None,
        class_name_override=None,
        ddb_url=None,
        source="pdf",
    )

    db.create_character(
        owner_id=user.id,
        name=final_name,
        level=safe_level,
        class_name=final_class_name,
        sheet=sheet,
    )


def seed_shadowrun_characters() -> None:
    """Import Chrome Razor for both the admin and the bilbo test accounts."""
    db.create_db_and_tables()
    db.ensure_seed_users()

    admin_email = os.environ.get("TAVERNTAILS_ADMIN_EMAIL", "admin@example.com")
    test_email = os.environ.get("TAVERNTAILS_TEST_EMAIL", "bilbo@example.com")

    pdf_bytes = _build_fixture_pdf(_RAZOR_FIELDS)

    for email in (admin_email, test_email):
        user = db.get_user_by_identifier(email)
        if user is None:
            print(f"[seed_shadowrun] User {email!r} not found — skipping")
            continue
        try:
            _import_for_user(user, pdf_bytes)
            print(f"[seed_shadowrun] Chrome Razor imported for {email}")
        except (ValueError, OSError, RuntimeError) as exc:  # pragma: no cover
            print(f"[seed_shadowrun] Failed to import for {email}: {exc}")


if __name__ == "__main__":
    seed_shadowrun_characters()
