"""Script to (re)generate the Valeros PF1e fixture PDF.

Run from the repo root::

    python server/tests/fixtures/pathfinder_1e/generate_valeros.py

The resulting ``character.pdf`` is committed and used by the seed script
``server/scripts/seed_pathfinder_1e_characters.py`` and the test suite in
``server/tests/test_pathfinder_1e_import.py``.  Re-run whenever the expected
field values change.

The PDF is a synthetic fixture built with pypdf widget annotations.  It does
NOT reproduce any copyrighted Paizo artwork or layout — only the character
statistics (name, ability scores, class, and combat values) are included.
"""

import io
import os

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

# Valeros — Pathfinder iconic Human Fighter 5
VALEROS_FIELDS = {
    # Character identity
    "CharacterName": "Valeros",
    "CLASS  LEVEL": "Fighter 5",
    "RACE": "Human",
    "Alignment": "NG",
    "Deity": "Cayden Cailean",
    "Age": "28",
    # Ability scores
    "STR": "18",
    "DEX": "14",
    "CON": "14",
    "INT": "10",
    "WIS": "10",
    "CHA": "10",
    # Ability score modifiers (derived)
    "STR Mod": "4",
    "DEX Mod": "2",
    "CON Mod": "2",
    "INT Mod": "0",
    "WIS Mod": "0",
    "CHA Mod": "0",
    # Hit points
    "Hit Point Maximum": "47",
    "Current Hit Points": "47",
    # Combat stats unique to PF1e
    "Base Attack Bonus": "5",
    "CMB": "9",
    "CMD": "21",
    # Armor Class
    "Armor Class": "19",
    "Touch AC": "12",
    "Flat-Footed AC": "17",
    # Initiative
    "Initiative": "2",
    # Speed
    "Speed": "30",
    # Saving throws (integer totals, no ranks)
    "Fortitude Total": "6",
    "Reflex Total": "3",
    "Will Total": "2",
    # Skills with explicit ranks and totals
    "Stealth Ranks": "1",
    "Stealth Total": "3",
    "Perception Ranks": "3",
    "Perception Total": "6",
    "Intimidate Ranks": "5",
    "Intimidate Total": "9",
    "Climb Ranks": "3",
    "Climb Total": "10",
    "Swim Ranks": "2",
    "Swim Total": "9",
    # Spells per day (Fighter has none at level 5)
    "Spells Per Day L1": "0",
    # Feats (flat list — PF1e has no feat-type subdivisions)
    "Feat 1": "Power Attack",
    "Feat 2": "Cleave",
    "Feat 3": "Weapon Focus",
    "Feat 4": "Dodge",
    "Feat 5": "Improved Initiative",
    # Equipment / gear
    "Equipment 1": "Longsword",
    "Equipment 2": "Heavy Steel Shield",
    "Equipment 3": "Full Plate",
    "Equipment 4": "Dagger",
    # Carry / encumbrance
    "Weight Carried": "110",
    # Special abilities / class features
    "Special Ability 1": "Bravery",
    "Special Ability 2": "Weapon Training",
    "Special Ability 3": "Armor Training",
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
                    [FloatObject(50.0), FloatObject(y), FloatObject(500.0), FloatObject(y + 18.0)]
                ),
            }
        )
        ref = writer._add_object(annot)  # noqa: SLF001
        annots = page.get("/Annots")
        if annots is None:
            page[NameObject("/Annots")] = ArrayObject([ref])
        else:
            annots.append(ref)
        y -= 20.0
        if y < 20.0:
            y = 750.0

    bio = io.BytesIO()
    writer.write(bio)
    bio.seek(0)
    return bio.read()


if __name__ == "__main__":
    out_path = os.path.join(os.path.dirname(__file__), "character.pdf")
    pdf_bytes = build_pdf(VALEROS_FIELDS)
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"Written {len(pdf_bytes)} bytes to {out_path}")
