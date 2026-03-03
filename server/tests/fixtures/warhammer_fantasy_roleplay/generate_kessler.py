"""Script to (re)generate the Heinrich Kessler WFRP 4e fixture PDF.

Run from the repo root::

    python server/tests/fixtures/warhammer_fantasy_roleplay/generate_kessler.py

The resulting ``kessler_wfrp.pdf`` is committed and used by the smoke test in
``test_warhammer_fantasy_roleplay_import.py``.  Re-run whenever the expected field values change.

Heinrich Kessler is a synthetic test character (Human Soldier/Mercenary) created for
testing purposes only.  No copyrighted Cubicle 7 / Games Workshop rules content is reproduced.
"""

import io
import os

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject

# Heinrich Kessler — Human Soldier (Mercenary career) from the Empire.
# Synthetic fixture character; field values are invented for testing purposes only.
KESSLER_FIELDS: dict[str, str] = {
    # Identity
    "Character Name": "Heinrich Kessler",
    "Race": "Human",
    "Career": "Mercenary",
    "Career Level": "Soldier",
    "Status": "Silver 3",
    # Characteristics — initial (base) values
    "WS": "35",
    "BS": "30",
    "S": "33",
    "T": "30",
    "I": "28",
    "Agi": "32",
    "Dex": "27",
    "Int": "29",
    "WP": "31",
    "Fel": "25",
    # Characteristic advances (from career/XP)
    "WS Advances": "10",
    "BS Advances": "5",
    "S Advances": "5",
    "T Advances": "5",
    "I Advances": "0",
    "Agi Advances": "5",
    "Dex Advances": "0",
    "Int Advances": "0",
    "WP Advances": "5",
    "Fel Advances": "0",
    # Wounds (replaces HP in WFRP)
    "Wounds": "13",
    "Current Wounds": "13",
    # Fate & Fortune
    "Fate": "2",
    "Fortune": "2",
    # Resilience & Resolve
    "Resilience": "1",
    "Resolve": "1",
    # Corruption
    "Corruption": "0",
    # Experience
    "Experience": "1750",
    "Experience Spent": "1500",
    # Skills (name + advances pairs)
    "Skill Name 1": "Melee (Basic)",
    "Skill Advances 1": "15",
    "Skill Char 1": "WS",
    "Skill Name 2": "Dodge",
    "Skill Advances 2": "10",
    "Skill Char 2": "Agi",
    "Skill Name 3": "Endurance",
    "Skill Advances 3": "5",
    "Skill Char 3": "T",
    "Skill Name 4": "Intimidate",
    "Skill Advances 4": "5",
    "Skill Char 4": "S",
    "Skill Name 5": "Perception",
    "Skill Advances 5": "5",
    "Skill Char 5": "I",
    # Talents
    "Talent 1": "Sturdy",
    "Talent 2": "Resolute",
    "Talent 3": "Strike Mighty Blow",
    # Trappings / equipment
    "Weapon 1": "Hand Weapon (Sword)",
    "Weapon 2": "Shield",
    "Trapping 1": "Leather Armour",
    "Trapping 2": "Backpack",
    # Ambitions
    "Short Term Ambition": "Survive the next contract",
    "Long Term Ambition": "Retire with enough gold to buy a farm",
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
                    [FloatObject(50.0), FloatObject(y), FloatObject(450.0), FloatObject(y + 20.0)]
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
        if y < 20.0:
            page = writer.add_blank_page(width=612, height=792)
            y = 750.0

    bio = io.BytesIO()
    writer.write(bio)
    bio.seek(0)
    return bio.read()


if __name__ == "__main__":
    out_path = os.path.join(os.path.dirname(__file__), "kessler_wfrp.pdf")
    pdf_bytes = build_pdf(KESSLER_FIELDS)
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"Written {len(pdf_bytes)} bytes to {out_path}")
