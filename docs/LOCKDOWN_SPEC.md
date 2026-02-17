# Campaign + Character Lockdown Spec

Purpose: Lock down campaign settings, character fields, and import contracts before we finalize the Home flow. This doc defines required fields, defaults, and data capture goals so UI and API stay aligned.

## 1) Campaign Settings (Authoritative Fields)
Required:
- `name` (string, 1–80)
- `description` (string, 0–240)

Settings block (`campaign.metadata_json.settings`):
- `world_name` (string, 0–80)
- `setting_summary` (string, 0–500)
- `tone` (enum: heroic | grim | dark-fantasy | comedy | horror | "")
- `ruleset` (enum: 5e | custom)
- `starting_level` (int: 1–20)
- `house_rules` (string, 0–500)
- `player_run_mode` (bool)
- `setting_documents` (array of document IDs + metadata)

Notes:
- Host-only fields: all settings above.
- Player-visible fields: `name`, `description`, `world_name`, `tone`, `starting_level`.
- Validation should occur server-side and mirrored client-side.
- Setting documents: user-uploaded files (PDF, TXT, DOCX) that provide campaign context or AI guidance.

## 2) Character Core Model (Authoritative Fields)
Required:
- `name` (string, 1–80)
- `level` (int, 1–20)

Optional (top-level):
- `class_name` (string)
- `campaign_id` (string | null)

Sheet payload (`character.sheet`):
- `stats`: { str, dex, con, int, wis, cha } (int)
- `hp`: { current, max, temp? } (int)
- `ac` (int)
- `speed`: { walk? } (int)
- `passives`: { perception, insight, investigation } (int)
- `skills`: { name, mod }[]
- `inventory`: string[]
- `features`: string[]
- `spells`: string[]
- `spellbook`: structured entries
- `species` (string)
- `background` (string)
- `multiclass`: { class_name, level }[]
- `carry`: { weight_current?, weight_capacity?, encumbered_at?, heavily_encumbered_at?, use_encumbrance } (numbers + bool)
- `portrait_url` (string)
- `story`: { backstory?, personality_traits?, ideals?, bonds?, flaws?, allies? } (string)
- `associations`: { campaign_id? }
- `import`: metadata block

Import metadata (`sheet.import`):
- `source` (enum: manual | pdf | ddb-link | json)
- `source_label` (string, e.g., filename or URL)
- `imported_at` (ISO string)
- `fields_extracted` (string[])
- `warnings` (string[])

## 3) PDF Import Contract (Required Extraction)
Must capture:
- Character name, class, level
- Stats: STR/DEX/CON/INT/WIS/CHA
- HP current/max/temp
- AC, initiative, speed (walk)
- Passives: perception/insight/investigation
- Species, background
- Multiclass breakdown if present
- Carry weight + encumbrance thresholds (when available)
- Skills list (if present)
- Features (class/racial/other)
- Spells (list + structured spellbook when available)

Nice-to-have:
- Equipment/inventory
- Proficiencies/senses
- Spell save DC, attack bonus
- Portrait
- Backstory + personality (ideals/bonds/flaws/allies)

Failure handling:
- Missing fields should be defaulted and surfaced in `import.warnings`.
- Keep all raw extraction notes for debugging (not exposed in UI by default).

## 4) D&D Beyond Link Import (Public Link)
Expected:
- Accept a public share URL (no scraping beyond user-provided link).
- Extract the same required fields as PDF.
- Capture `source_label` as URL + timestamp.

Notes:
- If extraction fails, return a partial character with warnings and ask user to upload PDF.

## 5) Learning Data (Session AI Inputs)
Goal: capture a consistent, minimal dataset for agents without PII leakage.

### 5.1 Canonical Event Types
- `chat.message`
- `roll.result`
- `npc.state` (creates/updates)
- `scene.summary`
- `note.entry`
- `document.tag`
- `character.update`

### 5.2 Required Event Fields
- `session_id`
- `campaign_id`
- `timestamp` (ISO)
- `source` (user|system|agent|integration)
- `payload` (type-specific)

### 5.3 Agent Inputs (Minimum)
- Scene snapshot (active character summaries, active campaign settings)
- Recent 50–200 events
- Current notes index (titles + IDs)
- Current NPC roster (names + IDs)

### 5.4 Storage & Privacy
- Do not store full raw PDFs.
- Redact email/identifiers from AI payloads.
- Keep audit log for agent inputs/outputs.

## 6) UI Flow Checkpoints
- Character list shows import source + warning badge if incomplete.
- Import flow ends with a “Review & Confirm” step.
- Campaign settings show required/optional fields distinctly.

---
If approved, convert sections 1–4 into API validation + UI forms, and section 5 into an `agent_events` schema update.
