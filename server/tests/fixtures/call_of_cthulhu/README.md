# Call of Cthulhu Test Fixtures

This directory contains test fixtures for the Call of Cthulhu (CoC 7e) character sheet
import pipeline in TavernTAIls.

## Files

| File | Description |
|------|-------------|
| `generate_investigator.py` | Generates `investigator.pdf` — a synthetic CoC 7e character sheet for *Roland Carmichael* |
| `investigator.pdf` | Pre-generated fixture PDF used by `test_call_of_cthulhu_import.py` smoke test |

## Regenerating the Fixture

```bash
python server/tests/fixtures/call_of_cthulhu/generate_investigator.py
```

## Character: Roland Carmichael

A 1920s private investigator from Boston.  Synthetic fixture character with values chosen
to exercise all CoC-specific import paths.

### Characteristics (CoC 7e, percentile)

| Stat | Value | Notes |
|------|-------|-------|
| STR  | 60    | 3d6×5 |
| CON  | 65    | 3d6×5 |
| SIZ  | 65    | (2d6+6)×5 |
| DEX  | 55    | 3d6×5 |
| APP  | 50    | 3d6×5 |
| INT  | 80    | (2d6+6)×5 |
| POW  | 65    | 3d6×5 |
| EDU  | 75    | (2d6+6)×5 |

### Derived Stats

| Stat | Value | Formula |
|------|-------|---------|
| HP current | 13 | (CON+SIZ)/10 = 13 |
| HP max | 13 | |
| Magic Points current | 13 | POW/5 = 13 |
| Magic Points max | 13 | |
| Sanity current | 65 | POW×5 = 65 |
| Sanity max | 65 | |
| Luck | 55 | 3d6×5 |

### Skills (percentile)

| Skill | % |
|-------|---|
| Spot Hidden | 65 |
| Library Use | 70 |
| Psychology | 55 |
| Fast Talk | 45 |
| Firearms | 45 |
| Cthulhu Mythos | 5 |

### Identity

- Occupation: Private Investigator
- Background: A seasoned investigator from Boston, Roland has seen too much to sleep soundly.

## Schema Notes

CoC-specific fields are stored under **system-namespaced keys** so they cannot
overload D&D-derived fields on the shared Character model:

| CoC concept | Schema key | Why not `hp`, `class`, etc. |
|-------------|-----------|------------------------------|
| Characteristics | `sheet.characteristics` | 8 stats vs 6 in D&D; distinct names |
| Magic Points | `sheet.magic_points` | Not present in D&D; distinct from spell slots |
| Sanity | `sheet.sanity` | CoC-unique resource |
| Luck | `sheet.luck` | CoC-unique resource |
| Skills (%) | `sheet.skills` | Percentile not proficiency bonus |
| Occupation | `sheet.occupation` + top-level `class_name` | No class/level in CoC |

`sheet.system.name` is always set to `"Call of Cthulhu"` and
`sheet.import.source` is set to `"pdf"` for PDF imports.

## Licensing Notes

The fixture PDF is **synthetically generated** by `generate_investigator.py`
using only invented field names and values — it does not reproduce any content
from the Chaosium official character sheet PDF.  Field names used follow community
convention (see <https://cthulhuwiki.chaosium.com/>) but are not copied from any
copyrighted work.  The Chaosium official fillable PDF is NOT distributed in this
repository.
