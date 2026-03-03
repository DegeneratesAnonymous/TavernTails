"""Script to (re)generate the Roland Carmichael CoC 7e fixture PDF.

Run from the repo root::

    python server/tests/fixtures/call_of_cthulhu/generate_investigator.py

The resulting ``investigator.pdf`` is committed and used by the smoke test in
``test_call_of_cthulhu_import.py``.  Re-run whenever the expected field values change.

The PDF uses only synthetic widget annotations — it does not reproduce any content
from the Chaosium official character sheet.
"""

import io
import os

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

# Roland Carmichael — 1920s private investigator (synthetic fixture character)
INVESTIGATOR_FIELDS = {
    # Identity
    "Investigator Name": "Roland Carmichael",
    "Occupation": "Private Investigator",
    "Age": "38",
    "Residence": "Boston",
    "Birthplace": "Providence, RI",
    # Characteristics (percentile)
    "STR": "60",
    "CON": "65",
    "SIZ": "65",
    "DEX": "55",
    "APP": "50",
    "INT": "80",
    "POW": "65",
    "EDU": "75",
    # Derived stats
    "Hit Points": "13",
    "Hit Points Max": "13",
    "Magic Points": "13",
    "Magic Points Max": "13",
    "Sanity Points": "65",
    "Sanity Points Max": "65",
    "Luck": "55",
    # Skills (percentile)
    "Spot Hidden": "65",
    "Library Use": "70",
    "Psychology": "55",
    "Fast Talk": "45",
    "Firearms": "45",
    "Cthulhu Mythos": "5",
    # Background
    "Background": "A seasoned investigator from Boston, Roland has seen too much to sleep soundly.",
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
    out_path = os.path.join(os.path.dirname(__file__), "investigator.pdf")
    pdf_bytes = build_pdf(INVESTIGATOR_FIELDS)
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"Written {len(pdf_bytes)} bytes to {out_path}")
