"""Direct test of reparse logic without HTTP."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))

from server import db
from server.agents.characters import _extract_spellbook_from_text
import re
from typing import Any, Dict

# Get character 506
character = db.get_character_by_id(506)
if not character:
    print("Character not found")
    sys.exit(1)

print(f"Character: {character.name}")
sheet = character.sheet or {}

# Get raw text
raw_text = sheet.get("raw_text") or ""

# Get widget values
import_meta = sheet.get("import", {}) if isinstance(sheet.get("import"), dict) else {}
pdf_widgets = import_meta.get("pdf_widgets", {}) if isinstance(import_meta.get("pdf_widgets"), dict) else {}
widget_values = pdf_widgets.get("values", {}) if isinstance(pdf_widgets.get("values"), dict) else {}

print(f"\n===  CURRENT STATE ===")
current_spells = sheet.get("spells", [])
current_spellbook = sheet.get("spellbook", [])
print(f"Spells: {len(current_spells)}")
print(f"Spellbook: {len(current_spellbook)}")
if current_spells:
    print(f"First 20: {current_spells[:20]}")

# Simulate reparse logic
print(f"\n=== SIMULATING REPARSE ===")
spell_entries = _extract_spellbook_from_text(raw_text)
print(f"Extracted {len(spell_entries)} spell entries from text")

spells = []
if spell_entries:
    spells = [e.get("name") for e in spell_entries if isinstance(e.get("name"), str)]
else:
    # Widget fallback
    for k, v in widget_values.items():
        if not v:
            continue
        if re.search(r"spell(source|time|range|comp|duration|page|save|hit|prepared|header|slot|level|class|school|ritual|material|attack|dc)", k, re.I):
            continue
        if re.search(r"spell|cantrip", k, re.I):
            if isinstance(v, str) and ("\n" in v or "," in v):
                parts = re.split(r"\r?\n|,", v)
                for p in parts:
                    s = p.strip()
                    if s:
                        spells.append(s)
            else:
                spells.append(str(v).strip())

print(f"Initial spell list: {len(spells)} items")

# Apply aggressive filtering (same as in reparse endpoint)
def _is_noise(s2):
    if not s2 or len(s2) < 3:
        return True
    if re.match(r"^[—\-\s]+$", s2):
        return True
    if re.match(r"^(druid|cleric|wizard|sorcerer|bard|warlock|paladin|ranger|artificer|fighter|monk|rogue|barbarian|acolyte)$", s2, re.I):
        return True
    if "/" in s2 or "," in s2:
        return True
    if re.search(r"\d+\s*ft\.?|feet|mile", s2, re.I):
        return True
    if re.match(r"^(\d+\s*[ABR]A?|[1-9]\s*BA|[1-9]\s*A|[1-9]\s*R|action|bonus\s*action|reaction|touch|self|sight|phb|ee|xgte|tcoe|scag|v|s|m|v/s|s/m|v/m|v/s/m|instantaneous|concentration|wis|int|cha|dex|str|con)$", s2, re.I):
        return True
    if re.match(r"^[A-Z]:\s*", s2):
        return True
    if re.match(r"^\(", s2):
        return True
    if re.match(r"^(\d+|[A-Z]{1,3}|\d+m|\d+h|\d+\s*min|\d+\s*hr)$", s2):
        return True
    if re.search(r"\b(PHB|EE|XGTE|TCOE|SCAG)\s*\d+", s2, re.I):
        return True
    if re.match(r"^(prepared|ritual|—|at\s*will|===.*===)$", s2, re.I):
        return True
    if re.match(r"^[A-Z]{3}\s*\d+$", s2) or re.match(r"^[A-Z]{3}\s*/\s*[A-Z]{3}$", s2):
        return True
    return False

cleaned = []
seen = set()
for s in spells:
    s2 = (s or "").strip()
    if _is_noise(s2):
        continue
    key = s2.lower()
    if key in seen:
        continue
    seen.add(key)
    cleaned.append(s2)

print(f"\n=== AFTER FILTERING ===")
print(f"Cleaned spells: {len(cleaned)}")
print(f"All cleaned spells: {cleaned}")

# Check for metadata
metadata_found = []
metadata_patterns = ['Druid', 'Cleric', '1BA', '1A', 'Touch', 'PHB', 'D:', 'V/S', 'ft.', 'WIS', 'CON']
for spell in cleaned:
    for pattern in metadata_patterns:
        if pattern.lower() in spell.lower():
            metadata_found.append((spell, pattern))
            break

if metadata_found:
    print(f"\n❌ FAILURE: Found {len(metadata_found)} metadata entries:")
    for spell, pattern in metadata_found[:10]:
        print(f"  - '{spell}' (matched '{pattern}')")
else:
    print(f"\n✓ SUCCESS: No metadata found!")
    print(f"✓ All {len(cleaned)} entries are valid spell names")
