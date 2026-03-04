"""Script to (re)generate the Chrome Razor Shadowrun SR6e fixture PDF.

Run from the repo root::

    python server/tests/fixtures/shadowrun/generate_razor.py

The resulting ``razor_sr6e.pdf`` is used by the smoke test in
``test_shadowrun_import.py``.  Re-run whenever the expected field values change.

The widget field names follow the Catalyst Game Labs SR6e fillable PDF
conventions (see README.md for the full field-name mapping table).
"""

import io
import os

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

# Chrome Razor — Human Street Samurai (synthetic fixture character).
# All values are fictional and created solely for import-testing purposes.
RAZOR_FIELDS: dict[str, str] = {
    # Identity
    "CharacterName": "Chrome Razor",
    "Metatype": "Human",
    "Archetype": "Street Samurai",
    # Core attributes (SR6e 1–12 scale)
    "BOD": "5",
    "AGI": "6",
    "REA": "4",
    "STR": "4",
    "WIL": "3",
    "LOG": "3",
    "INT": "3",
    "CHA": "2",
    "EDG": "4",
    # Essence (float; cyberware reduces from 6.0)
    "ESS": "2.8",
    # Condition monitors
    "PhysMonMax": "11",
    "StunMonMax": "10",
    "PhysDmg": "0",
    "StunDmg": "0",
    # Skills
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
    # Qualities
    "PosQuality1": "Ambidextrous",
    "PosQuality2": "Combat Sense",
    "NegQuality1": "SINner (National)",
    "NegQuality2": "Addiction (Mild, Alcohol)",
    # Cyberware
    "Cyberware1": "Wired Reflexes 1 (Used)",
    "Cyberware2": "Cybereyes Rating 2",
    "Cyberware3": "Cyberarm (Enhanced Agility)",
    # Contacts
    "Contact1Name": "Fixer",
    "Contact1Loyalty": "4",
    "Contact1Connection": "5",
    "Contact2Name": "Street Doc",
    "Contact2Loyalty": "3",
    "Contact2Connection": "3",
    # Resources
    "Nuyen": "2500",
    "Lifestyle": "Low",
}


def build_pdf(fields: dict[str, str]) -> bytes:
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
    out_path = os.path.join(os.path.dirname(__file__), "razor_sr6e.pdf")
    pdf_bytes = build_pdf(RAZOR_FIELDS)
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"Written {len(pdf_bytes)} bytes to {out_path}")
