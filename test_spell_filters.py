"""Test spell extraction with the problematic Shillelagh data."""
import sys
import os
import re
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))

# Simulated spell data in vertical format (how it appears in the PDF)
test_text = """
=== CANTRIPS ===
Shillelagh
Druid
1BA
Touch
PHB 275
D: 1m
V/S/M
Shape Water
Druid
1A
30 ft.
PHB 275
Instantaneous
V/S
Light
Cleric
1A
Touch/20 ft. Sphere
PHB 255
D: 1h
V/M
Frostbite
Druid
1A
60 ft.
EE 164
Instantaneous
V/S
Druid / Cleric
WIS / WIS
CON 14
DEX 14
5 ft. Cube
30 ft./5 ft. Cube
"""

def _is_noise_spell_line(text: str) -> bool:
    t = (text or '').strip()
    if not t:
        return True
    if len(t) < 3:
        return True
    # Skip empty or dash-only lines
    if re.match(r"^[—\-\s]+$", t):
        return True
    # Skip class names
    if re.match(r"^(druid|cleric|wizard|sorcerer|bard|warlock|paladin|ranger|artificer|fighter|monk|rogue|barbarian|acolyte|monk)$", t, re.I):
        return True
    # Skip lines containing "/" or "," (components, ranges, multi-values)
    if "/" in t or "," in t:
        return True
    # Skip distances/ranges (including variations like "30 ft./5 ft. Cube")
    if re.search(r"\d+\s*ft\.?|feet|mile", t, re.I):
        return True
    # Skip metadata patterns
    if re.match(r"^(\d+\s*[ABR]A?|[1-9]\s*BA|[1-9]\s*A|[1-9]\s*R|action|bonus\s*action|reaction|touch|self|sight|phb|ee|xgte|tcoe|scag|v|s|m|v/s|s/m|v/m|v/s/m|instantaneous|concentration|wis|int|cha|dex|str|con)$", t, re.I):
        return True
    # Skip lines with colon prefix
    if re.match(r"^[A-Z]:\s*", t):
        return True
    # Skip parenthetical notes
    if re.match(r"^\(", t):
        return True
    # Skip pure numbers, codes, durations
    if re.match(r"^(\d+|[A-Z]{1,3}|\d+m|\d+h|\d+\s*min|\d+\s*hr)$", t):
        return True
    # Skip page references
    if re.search(r"\b(PHB|EE|XGTE|TCOE|SCAG)\s*\d+", t, re.I):
        return True
    # Skip common spell attributes
    if re.match(r"^(prepared|ritual|—|at\s*will|===.*===)$", t, re.I):
        return True
    # Skip stat patterns
    if re.match(r"^[A-Z]{3}\s*\d+$", t) or re.match(r"^[A-Z]{3}\s*/\s*[A-Z]{3}$", t):
        return True
    # headers / separators
    if re.search(r"\b(cantrips?|spellcasting|spells?\s*known)\b", t, re.I):
        return True
    # drop obvious numeric-only or symbol-only
    if re.match(r"^[\W_0-9]+$", t):
        return True
    return False

print("Testing spell extraction filters:")
print("="*60)

for line in test_text.strip().split("\n"):
    line = line.strip()
    if not line:
        continue
    is_noise = _is_noise_spell_line(line)
    status = "FILTERED" if is_noise else "KEPT"
    print(f"{status:10} | {line}")

print("\n" + "="*60)
print("Expected: Only 'Shillelagh', 'Shape Water', 'Light', and 'Frostbite' should be KEPT")
print("All metadata lines should be FILTERED")

# Count results
kept = []
filtered = []
for line in test_text.strip().split("\n"):
    line = line.strip()
    if not line:
        continue
    if _is_noise_spell_line(line):
        filtered.append(line)
    else:
        kept.append(line)

print(f"\nSummary: {len(kept)} spells KEPT, {len(filtered)} metadata lines FILTERED")
print(f"Kept spells: {kept}")
print(f"\nTest {'PASSED' if set(kept) == {'Shillelagh', 'Shape Water', 'Light', 'Frostbite'} else 'FAILED'}!")
