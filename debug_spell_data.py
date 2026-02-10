"""Debug script to check spell extraction for a specific character."""
import sys
import os

# Add server to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))

from server.db import get_character_by_id
from server.agents.characters import _extract_spellbook_from_text

# Get the character (ID 506 was Launk)
character = get_character_by_id(506)
if not character:
    print("Character not found")
    sys.exit(1)

print(f"Character: {character.name}")
sheet = character.sheet or {}

# Get raw text
raw_text = sheet.get("raw_text") or ""
print(f"\n=== RAW TEXT LENGTH: {len(raw_text)} ===")

# Get widget values
import_meta = sheet.get("import", {}) if isinstance(sheet.get("import"), dict) else {}
pdf_widgets = import_meta.get("pdf_widgets", {}) if isinstance(import_meta.get("pdf_widgets"), dict) else {}
widget_values = pdf_widgets.get("values", {}) if isinstance(pdf_widgets.get("values"), dict) else {}

print(f"\n=== WIDGET KEYS CONTAINING 'spell' ===")
spell_widgets = {k: v for k, v in widget_values.items() if "spell" in k.lower() or "cantrip" in k.lower()}
for k, v in sorted(spell_widgets.items())[:20]:
    v_str = str(v)[:100] if v else "(empty)"
    print(f"{k}: {v_str}")

# Extract spells from text
print(f"\n=== EXTRACTING FROM TEXT ===")
spell_entries = _extract_spellbook_from_text(raw_text, debug=True)
print(f"Found {len(spell_entries)} spell entries from text")
if spell_entries:
    print("\nFirst 10 entries:")
    for entry in spell_entries[:10]:
        print(f"  {entry.get('name')} | header={entry.get('header')} | source={entry.get('source')}")

# Check current spells in sheet
current_spells = sheet.get("spells", [])
current_spellbook = sheet.get("spellbook", [])
print(f"\n=== CURRENT SHEET DATA ===")
print(f"Spells count: {len(current_spells)}")
print(f"Spellbook count: {len(current_spellbook)}")
if current_spells:
    print(f"\nFirst 20 spells:")
    for spell in current_spells[:20]:
        print(f"  - {spell}")

# Look for "Shillelagh" in raw text
print(f"\n=== SEARCHING FOR 'Shillelagh' IN RAW TEXT ===")
lines = raw_text.split("\n")
for i, line in enumerate(lines):
    if "shillelagh" in line.lower():
        print(f"Line {i}: {line[:200]}")
        # Show context
        if i > 0:
            print(f"  BEFORE: {lines[i-1][:100]}")
        if i < len(lines) - 1:
            print(f"  AFTER: {lines[i+1][:100]}")
