# Shadow of the Demon Lord — Character Sheet Fixtures

## Overview

This directory holds test fixtures for the Shadow of the Demon Lord (SotDL)
character sheet importer.

**Test character:** Mira Ashveil — a Human Rogue (novice path: Thief)

## Field Schema

The official Schwalb Entertainment SotDL character sheet uses the following
PDF AcroForm field names (mapped to TavernTAIls internal keys):

| PDF Widget Key      | TavernTAIls Key             | Notes                                  |
|---------------------|-----------------------------|----------------------------------------|
| Character Name      | `name`                      | Top-level character name               |
| Ancestry            | `sheet.race`                | Closest shared-schema analogue         |
| Novice Path         | `sheet.sotdl_paths.novice`  | SotDL-specific                         |
| Expert Path         | `sheet.sotdl_paths.expert`  | SotDL-specific                         |
| Master Path         | `sheet.sotdl_paths.master`  | SotDL-specific                         |
| Strength            | `sheet.stats.strength`      | Core attribute                         |
| Agility             | `sheet.stats.agility`       | Core attribute                         |
| Intellect           | `sheet.stats.intellect`     | Core attribute                         |
| Will                | `sheet.stats.will`          | Core attribute                         |
| Perception          | `sheet.sotdl_perception`    | Derived stat; **no 5e equivalent**     |
| Defense             | `sheet.ac`                  | Closest shared-schema analogue         |
| Health              | `sheet.hp.max`              | Closest shared-schema analogue         |
| Healing Rate        | `sheet.sotdl_healing_rate`  | **No 5e equivalent**                   |
| Corruption          | `sheet.sotdl_corruption`    | **No 5e equivalent** — unique resource |
| Insanity            | `sheet.sotdl_insanity`      | **No 5e equivalent**                   |
| Speed               | `sheet.sotdl_speed`         | SotDL uses flat speed (not ft.)        |
| Talent 1…N          | `sheet.talents`             | List of talent names                   |
| Spell 1…N           | `sheet.spells`              | List of spell names                    |
| Languages           | `sheet.languages`           | Comma-separated list                   |
| Professions         | `sheet.sotdl_professions`   | **No 5e equivalent**                   |

### System Metadata

```json
{
  "system": {"name": "Shadow of the Demon Lord", "publisher": "Schwalb Entertainment"},
  "import": {"source": "pdf"}
}
```

## Licensing

The *Shadow of the Demon Lord* system is published by Schwalb Entertainment.
No copyrighted character sheet PDFs are committed here.  The synthetic test
PDF (`character.pdf`, when present) is generated entirely from widget
annotations by `generate_mira.py` and contains no content from the published
rulebook.

## Generating the Fixture PDF

```bash
cd server/tests/fixtures/shadow_of_the_demon_lord
python generate_mira.py
```

This writes `character.pdf` which the smoke test
`test_sotdl_real_fixture_pdf_smoke` will pick up automatically.

## Community References

- Official SotDL Character Sheet: https://schwalbentertainment.com (requires purchase)
- Open Game Content / community tools: minimal — field mappings are hand-crafted
  from publicly available rulebook previews and community wikis.
- No open-source PDF parser specifically targeting SotDL was found at the time
  of implementation.  The widget-key names in this fixture match the naming
  conventions used by the official fillable PDF (snake_case with spaces,
  Title Case labels).
