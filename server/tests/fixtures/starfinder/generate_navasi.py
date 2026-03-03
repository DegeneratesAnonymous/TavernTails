"""Script to (re)generate the Navasi Starfinder fixture PDF.

Run from the repo root::

    python server/tests/fixtures/starfinder/generate_navasi.py

The resulting ``navasi_starfinder.pdf`` is committed and used by
``test_starfinder_import.py`` and the seed script.  Re-run whenever the
expected field values change.

Character: Navasi — iconic Starfinder Envoy (synthetic fixture, not from any
official Paizo PDF artwork).
"""

import io
import os

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

# Navasi — iconic Envoy (synthetic fixture character)
NAVASI_FIELDS = {
    # Identity
    "CharacterName": "Navasi",
    "CLASS  LEVEL": "Envoy 5",
    "Race": "Human",
    "Theme": "Spacefarer",
    "Homeworld": "Absalom Station",
    "Alignment": "CN",
    # Ability scores
    "STR": "10",
    "DEX": "16",
    "CON": "12",
    "INT": "14",
    "WIS": "12",
    "CHA": "18",
    # Hit Points
    "HP Max": "38",
    "HP Current": "38",
    # Stamina Points (Starfinder-specific, no D&D 5e equivalent)
    "SP Max": "38",
    "SP Current": "30",
    # Resolve Points (Starfinder-specific, no D&D 5e equivalent)
    "RP Max": "6",
    "RP Current": "4",
    # Armor Class (Starfinder has two AC values, no D&D 5e equivalent)
    "EAC": "16",
    "KAC": "17",
    # Initiative
    "Initiative": "3",
    # Saving throws (integer totals, no proficiency ranks)
    "Fort": "3",
    "Ref": "7",
    "Will": "5",
    # Speed
    "Speed": "30",
    # Skills with ranks and totals
    "Bluff Ranks": "5",
    "Bluff Total": "11",
    "Computers Ranks": "5",
    "Computers Total": "9",
    "Culture Ranks": "5",
    "Culture Total": "9",
    "Diplomacy Ranks": "5",
    "Diplomacy Total": "13",
    "Intimidate Ranks": "3",
    "Intimidate Total": "9",
    "Perception Ranks": "5",
    "Perception Total": "8",
    "Piloting Ranks": "3",
    "Piloting Total": "8",
    "Stealth Ranks": "2",
    "Stealth Total": "7",
    # Feats (flat list — Starfinder does not categorise feats like PF2e)
    "Feat 1": "Skill Focus (Diplomacy)",
    "Feat 2": "Improved Initiative",
    "Feat 3": "Versatile Weapon Proficiency",
    # Class features
    "Class Feature 1": "Expertise",
    "Class Feature 2": "Envoy Improvisations",
    "Class Feature 3": "Get 'Em",
    "Class Feature 4": "Clever Feint",
    # Equipment / weapons
    "Weapon 1": "Tactical Pistol",
    "Weapon 2": "Survival Knife",
    "Armor": "Lashunta Ringwear I",
    "Equipment 1": "Personal Comm Unit",
    "Equipment 2": "Medpatch x3",
    # Bulk
    "Current Bulk": "4",
    "Bulk Limit": "10",
    # Starfinder widget signals for system detection
    "Stamina Points": "",
    "Resolve Points": "",
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
    out_path = os.path.join(os.path.dirname(__file__), "navasi_starfinder.pdf")
    pdf_bytes = build_pdf(NAVASI_FIELDS)
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"Written {len(pdf_bytes)} bytes to {out_path}")
