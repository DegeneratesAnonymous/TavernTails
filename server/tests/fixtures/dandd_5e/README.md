# D&D 5e Character Sheet Fixtures

This directory holds fixture files for D&D 5e character sheet import tests.

## Test Character — Thorin Ironfist

**Character:** Thorin Ironfist  
**Class / Level:** Fighter 5  
**Race:** Mountain Dwarf  
**Background:** Soldier

Thorin is used in `server/tests/test_dandd_5e_import.py` as the canonical test
subject for D&D 5e PDF imports.  The PDF is generated synthetically in the test
file using pypdf widget annotations so the suite can run in CI without a
commercially licensed character-sheet PDF.

## PDF Field Schema

The official D&D 5e fillable character sheet (available from Wizards of the
Coast / D&D Beyond) uses the following AcroForm widget key conventions.  The
table below documents the mapping used by TavernTAIls.

| Widget Key (PDF)            | TavernTAIls sheet field          | Notes                          |
|-----------------------------|----------------------------------|--------------------------------|
| `CharacterName`             | `character.name`                 |                                |
| `CLASS  LEVEL`              | `character.class_name` + level   | e.g. "Fighter 5"               |
| `Race`                      | `sheet.race`                     | Also stored as `sheet.species` |
| `Background`                | `sheet.background`               |                                |
| `STR`                       | `sheet.stats.str`                |                                |
| `DEX`                       | `sheet.stats.dex`                |                                |
| `CON`                       | `sheet.stats.con`                |                                |
| `INT`                       | `sheet.stats.int`                |                                |
| `WIS`                       | `sheet.stats.wis`                |                                |
| `CHA`                       | `sheet.stats.cha`                |                                |
| `Hit Point Maximum`         | `sheet.hp.max`                   |                                |
| `Current Hit Points`        | `sheet.hp.current`               |                                |
| `Temporary Hit Points`      | `sheet.hp.temp`                  |                                |
| `Armor Class`               | `sheet.ac`                       |                                |
| `Initiative`                | `sheet.initiative`               |                                |
| `ProfBonus`                 | `sheet.proficiency_bonus`        | D&D 5e-specific                |
| `Inspiration`               | `sheet.inspiration`              | Boolean                        |
| `HD Total`                  | `sheet.hit_dice`                 | e.g. "5d10"                    |
| `Death Save Successes`      | `sheet.death_saves.successes`    | D&D 5e-specific                |
| `Death Save Failures`       | `sheet.death_saves.failures`     | D&D 5e-specific                |
| `ST Strength`               | `sheet.saves.str.total`          |                                |
| `ST Dexterity`              | `sheet.saves.dex.total`          |                                |
| `ST Constitution`           | `sheet.saves.con.total`          |                                |
| `ST Intelligence`           | `sheet.saves.int.total`          |                                |
| `ST Wisdom`                 | `sheet.saves.wis.total`          |                                |
| `ST Charisma`               | `sheet.saves.cha.total`          |                                |
| `Acrobatics`                | `sheet.skills.Acrobatics`        |                                |
| `SlotsTotal1`–`SlotsTotal9` | `sheet.spell_slots.1`–`.9`       | D&D 5e-specific                |
| `Equipment 1`…              | `sheet.equipment`                |                                |
| `Features and Traits`       | `sheet.features`                 |                                |

## Fields Without a D&D 5e Equivalent

The following fields exist in other supported systems but have no D&D 5e
equivalent.  They are **never populated** on a D&D 5e character sheet.

| Other-system field  | System       | Reason not populated in D&D 5e         |
|---------------------|--------------|----------------------------------------|
| Stress              | STA          | D&D 5e uses HP; no stress track exists |
| Ancestry            | Pathfinder 2e| D&D 5e uses Race instead               |
| Focus Points        | Pathfinder 2e| D&D 5e has no focus pool mechanic      |
| Base Attack Bonus   | Pathfinder 1e| D&D 5e uses Proficiency Bonus instead  |
| CMB / CMD           | Pathfinder 1e| D&D 5e has no combat maneuver system   |

## Import Metadata

A correctly imported D&D 5e character sheet will have:

```json
{
  "sheet": {
    "system": {
      "name": "D&D 5e",
      "publisher": "Wizards of the Coast"
    },
    "import": {
      "source": "pdf"
    }
  }
}
```

## Licensing Notes

The official Wizards of the Coast fillable character sheet PDF is available
under the [Fan Content Policy](https://www.wizards.com/en/fan-site-kit) for
**personal / non-commercial use only** and **must not be redistributed**.

Therefore **no WotC-licensed PDF is committed to this repository**.  Tests use
synthetically constructed PDFs (pypdf widget annotations) that contain only
field names and placeholder values — no copyrighted artwork or text.

The community-maintained **Form-Fillable Character Sheet** variants (e.g. those
from the SRD-5.1 community) are similarly not included because their
redistribution rights vary by version.

For real-integration smoke testing, place a filled-out personal-use PDF at
`server/tests/fixtures/dandd_5e/character.pdf` (git-ignored) and run the
optional smoke test via:

```bash
pytest server/tests/test_dandd_5e_import.py -k "smoke"
```
