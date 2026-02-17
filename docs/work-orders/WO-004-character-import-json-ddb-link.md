# WO-004: Character Import (JSON + DDB Link)

## Goal
Add a first-pass character import flow that lets players bring a character into TavernTails without manual re-entry.

This slice focuses on **ToS-safe** mechanisms:
- Paste JSON export
- Upload JSON export file
- Store an optional D&D Beyond character URL (no scraping)

## Scope
### Backend
- Add endpoints:
  - `POST /characters/import` (paste JSON)
  - `POST /characters/import/file` (upload JSON)
- Store the full import in `Character.sheet` under:
  - `sheet.import.{source, imported_at, ddb_url}`
  - `sheet.raw` (verbatim object)
- Best-effort extraction for top-level character fields:
  - `name`, `level`, `class_name`

### Frontend
- Add a new dashboard view: **Import Character**
- Supports:
  - JSON textarea paste
  - `.json` file upload
  - optional DDB URL input
- On success:
  - refresh roster
  - if a session is active, auto-assign imported character to the active session and return to Gameplay

### Tests
- Add pytest coverage for both import endpoints.

## Acceptance Criteria
- User can import a character via pasted JSON and via uploaded JSON.
- Imported character appears under “View Characters”.
- If an active session exists, imported character can be selected/auto-assigned.
- `./ci.ps1` passes.

## Out of Scope (Future)
- Parsing specific vendor formats into canonical stats/skills/spells
- Full Beyond20-to-TavernTails roll relay
- DDB API integration or scraping
- Updating existing characters via import merge
