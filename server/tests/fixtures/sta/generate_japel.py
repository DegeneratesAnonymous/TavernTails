"""Script to (re)generate the Ja'pel STA fixture PDF.

Run from the repo root::

    python server/tests/fixtures/sta/generate_japel.py

The resulting ``japelsta.pdf`` is committed and used by the smoke test in
``test_sta_import.py``.  Re-run whenever the expected field values change.
"""

import io
import os

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

# Ja'pel — Vulcan science officer (synthetic fixture character)
JAPEL_FIELDS = {
    "Character Name": "Ja'pel",
    "Species": "Vulcan",
    "Rank": "Lieutenant",
    "Assignment": "USS Enterprise",
    "Department": "Science",
    # Attributes
    "Control": "10",
    "Daring": "7",
    "Fitness": "9",
    "Insight": "11",
    "Presence": "8",
    "Reason": "12",
    # Disciplines
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
    # Equipment / weapons
    "Weapon 1": "Type-2 Phaser",
    "Weapon 2": "Tricorder",
}


def build_pdf(fields: dict) -> bytes:
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


if __name__ == "__main__":
    out_path = os.path.join(os.path.dirname(__file__), "japelsta.pdf")
    pdf_bytes = build_pdf(JAPEL_FIELDS)
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"Written {len(pdf_bytes)} bytes to {out_path}")
