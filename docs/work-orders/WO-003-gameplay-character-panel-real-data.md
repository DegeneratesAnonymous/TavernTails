# WO-003 — Gameplay Character Panel Uses Real Characters

## Goal
Replace the hardcoded demo roster in gameplay with the authenticated user’s real character list, and keep the Character Panel selection in sync with the active session character.

## Context
Today `GameplayLayout` renders the Character Panel and Player Status Bar using a hardcoded `demoRoster`. The dashboard already:
- fetches `/characters`
- tracks an active character
- assigns session character via `POST /sessions/{sessionId}/character`

This WO stitches those together so gameplay reflects actual characters.

## Scope
### In
- Remove `demoRoster` usage from gameplay.
- Pass real roster + selection into `GameplayLayout` from the dashboard.
- Map `/characters` API objects into the UI’s `CharacterSummary` shape with safe defaults.
- Allow selecting a character directly in the Character Panel (calls the existing session assignment endpoint).

### Out
- Full character sheet editing.
- Import flows (Beyond20/DDB/PDF).

## Acceptance Criteria
- Gameplay right-side Character Panel lists real characters.
- Selecting a character in the panel updates the active character selection and posts session assignment.
- Player status bar uses selected character (or reasonable defaults).
- `./ci.ps1` passes.

## Test Plan
- `./ci.ps1`

## Notes
- Keep mapping conservative: if sheet fields aren’t present, default to sensible values (AC 10, HP 10, etc.).
