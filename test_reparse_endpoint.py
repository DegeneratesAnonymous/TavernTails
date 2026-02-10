"""Test the actual reparse endpoint with a real character."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))

from server.db import get_character_by_id
import requests

# Assuming character ID 506 (Launk)
CHARACTER_ID = 506

# First, get current spell count
char = get_character_by_id(CHARACTER_ID)
if not char:
    print(f"Character {CHARACTER_ID} not found")
    sys.exit(1)

print(f"Character: {char.name}")
sheet = char.sheet or {}
current_spells = sheet.get("spells", [])
current_spellbook = sheet.get("spellbook", [])

print(f"\nBEFORE REPARSE:")
print(f"  Spells: {len(current_spells)}")
print(f"  Spellbook: {len(current_spellbook)}")
if current_spells:
    print(f"  First 20 spells: {current_spells[:20]}")

# Now call the reparse endpoint
print(f"\n{'='*60}")
print("Calling reparse endpoint...")
print(f"{'='*60}\n")

# Need to authenticate - use admin user
response = requests.post(
    f"http://localhost:8000/api/characters/{CHARACTER_ID}/reparse-spells",
    auth=("admin@example.com", "secret")  # Admin credentials
)

if response.status_code == 200:
    print("✓ Reparse successful!")
    
    # Get updated character
    char = get_character_by_id(CHARACTER_ID)
    sheet = char.sheet or {}
    new_spells = sheet.get("spells", [])
    new_spellbook = sheet.get("spellbook", [])
    
    print(f"\nAFTER REPARSE:")
    print(f"  Spells: {len(new_spells)}")
    print(f"  Spellbook: {len(new_spellbook)}")
    if new_spells:
        print(f"  All spells: {new_spells}")
    
    # Check if metadata was filtered out
    metadata_patterns = [
        'Druid', 'Cleric', '1BA', '1A', 'Touch', 'PHB', 'D:', 'V/S/M', 'V/S',
        'Instantaneous', 'ft.', 'WIS', 'CON', 'DEX'
    ]
    
    metadata_found = []
    for spell in new_spells:
        for pattern in metadata_patterns:
            if pattern.lower() in spell.lower():
                metadata_found.append(spell)
                break
    
    if metadata_found:
        print(f"\n❌ FAILURE: Found {len(metadata_found)} metadata entries:")
        for m in metadata_found[:10]:
            print(f"  - {m}")
    else:
        print(f"\n✓ SUCCESS: No metadata found in spell list!")
        print(f"✓ All {len(new_spells)} entries appear to be valid spell names")
else:
    print(f"❌ Reparse failed: {response.status_code}")
    print(f"   Response: {response.text}")
