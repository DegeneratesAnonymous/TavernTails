# Alien RPG Character Sheet Fixtures

This directory holds test fixtures for the Alien RPG character sheet importer.

## System Overview

**Alien RPG** is published by **Free League Publishing** and uses the **Year Zero Engine
(YZE)** — a dice-pool system where players roll a number of d6s equal to an attribute +
skill rating and count faces (6s) as successes.

The character sheet has two official variants:
- **Colonial Marines** — military personnel with careers such as Colonial Marine, Medic, Pilot.
- **Civilians** — non-military roles such as Roughneck, Scientist, Company Agent, Kid.

## PDF Field Schema (AcroForm)

The Free League fillable PDF uses AcroForm widget annotations.  The canonical field
names used by TavernTAIls' importer are documented below.

### Identity fields

| Widget key     | Maps to                 | Notes                                  |
|----------------|-------------------------|----------------------------------------|
| `Name`         | `character.name`        | Character's full name                  |
| `Career`       | `sheet.alien_career`    | Career/job (replaces D&D class)        |
| `Age`          | `sheet.alien_appearance`| Often stored with appearance info      |
| `Appearance`   | `sheet.alien_appearance`| Physical description                   |
| `Agenda`       | `sheet.agenda`          | Secret personal objective (unique YZE) |
| `Buddy`        | `sheet.alien_buddy`     | Name of the character's trusted ally   |
| `Rival`        | `sheet.alien_rival`     | Name of the character's rival          |
| `Experience`   | `sheet.alien_experience`| Experience points (integer)            |

### Attributes (1–6 scale)

Alien RPG has four core attributes — all stored under `sheet["alien_attributes"]` to
avoid overloading D&D 5e's six-attribute keys.

| Widget key  | `alien_attributes` key |
|-------------|------------------------|
| `Strength`  | `strength`             |
| `Agility`   | `agility`              |
| `Wits`      | `wits`                 |
| `Empathy`   | `empathy`              |

### Skills (0–5 scale)

Stored under `sheet["alien_skills"]` with snake_case keys.

| Widget key         | `alien_skills` key   | Linked attribute |
|--------------------|----------------------|------------------|
| `Close Combat`     | `close_combat`       | Strength         |
| `Heavy Machinery`  | `heavy_machinery`    | Strength         |
| `Stamina`          | `stamina`            | Strength         |
| `Mobility`         | `mobility`           | Agility          |
| `Piloting`         | `piloting`           | Agility          |
| `Ranged Combat`    | `ranged_combat`      | Agility          |
| `Comtech`          | `comtech`            | Wits             |
| `Observation`      | `observation`        | Wits             |
| `Survival`         | `survival`           | Wits             |
| `Command`          | `command`            | Empathy          |
| `Manipulation`     | `manipulation`       | Empathy          |
| `Medical Aid`      | `medical_aid`        | Empathy          |

### Resources

| Widget key     | Sheet key             | Notes                                              |
|----------------|-----------------------|----------------------------------------------------|
| `Health`       | `sheet.alien_health.current` | Current HP; max = Strength score          |
| `Max Health`   | `sheet.alien_health.max`     | Maximum HP                                |
| `Stress`       | `sheet.alien_stress.current` | Current stress level                      |
| `Max Stress`   | `sheet.alien_stress.max`     | Maximum stress (not usually on sheet)     |

> **Why `alien_stress` and not `hp`?**
> Stress is a core Alien RPG mechanic that has no D&D equivalent.  Each stress die
> that comes up a face (panic symbol) triggers a Panic Roll, which can cascade into
> increasingly severe outcomes.  Overloading the `hp` key would destroy this semantic.

### Equipment / Injuries

| Widget pattern         | Sheet key         |
|------------------------|-------------------|
| `Gear N` / `Item N`    | `sheet.equipment` |
| `Critical Injury N`    | `sheet.injuries`  |

## Test Fixture PDFs

> **Note:** The official Free League fillable PDFs are **not** committed to this
> repository.  Real PDFs are protected by copyright and cannot be redistributed.
> The test suite (`server/tests/test_alien_rpg_import.py`) generates synthetic PDFs
> programmatically using **pypdf** so that CI can run without the real sheets.

If you have a legitimately obtained copy of the Free League Alien RPG fillable PDF
you can place it here and the smoke test at the bottom of `test_alien_rpg_import.py`
will pick it up automatically:

```
server/tests/fixtures/alien_rpg/character.pdf
```

## Community Resources & Licensing Notes

- **YZE SRD:** Free League has published the Year Zero Engine SRD under a Creative
  Commons Attribution 4.0 International licence.  The SRD covers the core dice
  mechanic, attribute/skill names, and stress/panic rules at an abstract level.
- **Alien RPG character sheet:** The fillable PDF is copyrighted by Free League
  Publishing and **must not** be committed to this repository.
- **Community tools:** Several community tools exist (e.g. Foundry VTT module, Roll20
  character sheet) that share similar field names, giving us confidence the field
  naming conventions used here are representative.

## Seed Characters

The seed script (`server/scripts/seed_alien_rpg_characters.py`) creates one character
for each of the two development seed accounts:

| Account                | Character name       | Career            |
|------------------------|----------------------|-------------------|
| `bilbo@example.com`    | Zoe Hendricks        | Roughneck         |
| `admin@example.com`    | Lt. Torres           | Colonial Marine   |
