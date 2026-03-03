# Warhammer Fantasy Roleplay 4e Test Fixtures

## Overview

This directory contains fixture files for testing the Warhammer Fantasy Roleplay (WFRP 4e)
character sheet importer in TavernTAIls.

## Fixture Character: Heinrich Kessler

**Heinrich Kessler** is a synthetic test character — a Human Soldier (Mercenary career) from
the Empire.  He is used by `test_warhammer_fantasy_roleplay_import.py` to validate field
extraction, schema mapping, and the two seed-user imports.

Heinrich is **not** based on any copyrighted Cubicle 7 or Games Workshop published character.
The field values are invented for testing purposes only.

### Key Stats

| Characteristic | Initial | Advances | Total |
|---|---|---|---|
| WS (Weapon Skill) | 35 | 10 | 45 |
| BS (Ballistic Skill) | 30 | 5 | 35 |
| S (Strength) | 33 | 5 | 38 |
| T (Toughness) | 30 | 5 | 35 |
| I (Initiative) | 28 | 0 | 28 |
| Agi (Agility) | 32 | 5 | 37 |
| Dex (Dexterity) | 27 | 0 | 27 |
| Int (Intelligence) | 29 | 0 | 29 |
| WP (Willpower) | 31 | 5 | 36 |
| Fel (Fellowship) | 25 | 0 | 25 |

### Resources

- **Wounds**: Max 13, Current 13
- **Fate**: 2 / **Fortune**: 2
- **Resilience**: 1 / **Resolve**: 1
- **Corruption**: 0
- **Experience**: Total 1750 / Spent 1500

### Career

- Career: Mercenary
- Career Level: Soldier
- Status: Silver 3

## Generating the Fixture PDF

Run the generator script from the repo root:

```bash
python server/tests/fixtures/warhammer_fantasy_roleplay/generate_kessler.py
```

This creates `kessler_wfrp.pdf` in this directory.  The file is committed and used by the
smoke test `test_wfrp_real_fixture_pdf_smoke` in `test_warhammer_fantasy_roleplay_import.py`.

## Licensing Notes

- The Warhammer Fantasy Roleplay game system is published by **Cubicle 7 Entertainment**
  under licence from **Games Workshop**.
- TavernTAIls does **not** distribute any official WFRP character sheet PDFs or extract any
  rules text from Cubicle 7/Games Workshop publications.
- The synthetic fixture PDF is generated programmatically and contains only field names and
  invented values created for testing purposes.  No copyrighted rules content is reproduced.
- The WFRP characteristic abbreviations (WS, BS, S, T, I, Agi, Dex, Int, WP, Fel) are
  industry-standard community abbreviations and their use in field mappings is purely
  referential (like a file-format selector).

## Field Name Conventions

The importer follows these community-standard field name conventions based on the
Cubicle 7 WFRP 4e fillable PDF AcroForm field list:

| Widget Key | Maps To | Notes |
|---|---|---|
| `Name` / `Character Name` | `character.name` | |
| `Race` | `sheet.species` | Also stored as `sheet.warhammer_characteristics` context |
| `Career` | `character.class_name` | |
| `WS` | `sheet.warhammer_characteristics.weapon_skill.initial` | |
| `WS Advances` | `sheet.warhammer_characteristics.weapon_skill.advances` | |
| `Wounds` | `sheet.warhammer_wounds.max` | Replaces HP; not stored in `sheet.hp` |
| `Current Wounds` | `sheet.warhammer_wounds.current` | |
| `Fate` | `sheet.warhammer_fate.fate` | |
| `Fortune` | `sheet.warhammer_fate.fortune` | |
| `Resilience` | `sheet.warhammer_resilience.resilience` | |
| `Resolve` | `sheet.warhammer_resilience.resolve` | |
| `Corruption` | `sheet.warhammer_corruption` | |
| `Skill Name N` | `sheet.warhammer_skills[N].name` | |
| `Skill Advances N` | `sheet.warhammer_skills[N].advances` | |
| `Talent N` | `sheet.warhammer_talents[N]` | |
| `Trapping N` / `Weapon N` | `sheet.warhammer_trappings` | |
