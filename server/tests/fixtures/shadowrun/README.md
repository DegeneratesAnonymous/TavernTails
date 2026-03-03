# Shadowrun Fixture — Chrome Razor

## Overview

This directory holds the Shadowrun 6th Edition (SR6e) test character fixture
used by `server/tests/test_shadowrun_import.py`.

## Test Character: Chrome Razor

**Chrome Razor** is a synthetic Street Samurai built specifically for import
testing.  No real Catalyst Game Labs PDF is distributed here (see *Licensing*
below).  Instead, `generate_razor.py` produces a minimal PDF containing AcroForm
widget annotations that mirror the field names from the SR6e fillable character
sheet.

### Character Summary

| Field         | Value                    |
|---------------|--------------------------|
| Name          | Chrome Razor             |
| Metatype      | Human                    |
| Archetype     | Street Samurai           |
| BOD / AGI     | 5 / 6                    |
| REA / STR     | 4 / 4                    |
| WIL / LOG     | 3 / 3                    |
| INT / CHA     | 3 / 2                    |
| EDG           | 4                        |
| Essence       | 2.8 (cyberware installed) |
| Nuyen         | 2500                     |
| Lifestyle     | Low                      |

### Skills

| Skill          | Rating | Specialization |
|----------------|--------|----------------|
| Automatics     | 6      | Assault Rifles |
| Pistols        | 5      | —              |
| Blades         | 5      | Katana         |
| Unarmed Combat | 4      | —              |
| Stealth        | 5      | Urban          |
| Perception     | 4      | —              |

### Qualities

- **Positive:** Ambidextrous, Combat Sense
- **Negative:** SINner (National), Addiction (Mild, Alcohol)

### Cyberware / Bioware

- Wired Reflexes 1 (Used)
- Cybereyes Rating 2
- Cyberarm (Enhanced Agility)

### Contacts

| Contact     | Loyalty | Connection |
|-------------|---------|------------|
| Fixer       | 4       | 5          |
| Street Doc  | 3       | 3          |

### Condition Monitors

- Physical: max 11
- Stun: max 10

---

## Generating the Fixture PDF

Run from the repository root:

```bash
python server/tests/fixtures/shadowrun/generate_razor.py
```

This writes `razor_sr6e.pdf` in this directory.  The file is **gitignored**
(all `*.pdf` files under `server/` are excluded) so it must be regenerated
locally for the smoke test.

---

## PDF Widget Key Conventions

The widget field names used here follow the Catalyst Game Labs SR6e fillable
PDF conventions (as documented by the Shadowrun community):

- **Attributes:** `BOD`, `AGI`, `REA`, `STR`, `WIL`, `LOG`, `INT`, `CHA`, `EDG`, `MAG`/`RES`, `ESS`
- **Metatype / Archetype:** `Metatype`, `Archetype`
- **Condition Monitors:** `PhysMonMax`, `StunMonMax`, `PhysDmg`, `StunDmg`
- **Skills:** `Skill1Name` / `Skill1Rating` / `Skill1Spec` (numbered 1–*n*)
- **Qualities:** `PosQuality1` / `NegQuality1` (numbered 1–*n*)
- **Cyberware:** `Cyberware1` (numbered 1–*n*)
- **Contacts:** `Contact1Name` / `Contact1Loyalty` / `Contact1Connection` (numbered 1–*n*)
- **Nuyen / Lifestyle:** `Nuyen`, `Lifestyle`
- **Matrix (Decker/TM):** `Attack`, `Sleaze`, `DataProcessing`, `Firewall`

---

## Internal Schema Mapping

All Shadowrun-specific fields are stored under `shadowrun_*` namespaced keys
in `character.sheet` to avoid overloading shared keys such as `hp`.

| PDF field(s)           | `sheet` key                               | Notes                        |
|------------------------|-------------------------------------------|------------------------------|
| BOD/AGI/REA/…         | `shadowrun_attributes.body` etc.          | integer ratings              |
| ESS / Essence          | `shadowrun_essence`                       | float; reduced by cyberware  |
| PhysMonMax / StunMonMax| `shadowrun_condition_monitor.physical.max`| replaces D&D HP              |
| PhysDmg / StunDmg      | `shadowrun_condition_monitor.*.damage`    | boxes filled                 |
| Skill*Name/Rating/Spec | `shadowrun_skills`                        | list of {name,rating,spec?}  |
| Pos/NegQuality*        | `shadowrun_qualities.positive/negative`   | list of strings              |
| Cyberware*             | `shadowrun_cyberware`                     | list of strings              |
| Nuyen                  | `shadowrun_nuyen`                         | integer                      |
| Lifestyle              | `shadowrun_lifestyle`                     | string                       |
| Contact*Name/Loy/Con   | `shadowrun_contacts`                      | list of {name,loyalty?,conn?}|
| Attack/Sleaze/DP/FW    | `shadowrun_matrix`                        | only set for Decker/TM       |

Fields with no D&D 5e equivalent (**Essence**, **Nuyen**, **Metatype**,
**condition monitors**, **matrix stats**) are never mapped to shared keys.

`sheet.system.name` is set to `"Shadowrun"` and `sheet.import.source` to
`"pdf"` on every import.

---

## Licensing

The **Shadowrun** name and the Catalyst Game Labs character sheet design are
trademarks/copyrights of **Catalyst Game Labs**.  No official PDFs are
distributed in this repository.  The synthetic fixture PDF generated by
`generate_razor.py` contains only field names and test values created for
open-source compatibility testing.
