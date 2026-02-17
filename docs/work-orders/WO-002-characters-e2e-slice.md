# WO-002 — Characters: Gameplay Create + Session Select (E2E Slice)

## Goal
Enable a player to create a character during gameplay and immediately assign it to the active session member.

This is a small vertical slice of WP#3 (Characters) that improves the campaign → session → play loop.

## Scope
### In
- Frontend: From the Gameplay view, provide a “New Character” action.
- Frontend: Create character via `POST /characters`.
- Frontend: Refresh character list and set the created character as the active session character via `POST /sessions/{sessionId}/character`.
- Frontend: Return user to Gameplay after success (when a session is active).
- Backend: Ensure `/characters` endpoints work with auth and owner scoping.
- Tests: Add backend coverage for `/characters` create/list/delete and ownership isolation.

### Out (future)
- Import flows (Beyond20 / D&D Beyond / PDF).
- Detailed character sheet editing.
- Character-driven roll modifiers in UI.

## Acceptance Criteria
- In Gameplay view, clicking “New Character” opens creation UI.
- Creating a character while a session is active:
  - results in HTTP 201 from `/characters`.
  - the character appears in the character dropdown.
  - the character is automatically selected for the active session.
  - the UI returns to Gameplay.
- Creating a character with no active session still works and lands in the character list.
- Backend tests prove:
  - created characters are visible to the owner.
  - characters from other users do not appear in the owner’s list.
  - delete returns 404 for non-owned characters (or they remain unaffected).

## Test Plan
- `pytest server/tests/test_characters_api.py -q`
- `pytest server/tests/test_session_character.py -q`

## Notes
- Keep changes PR-sized and avoid refactors.
- Prefer existing dashboard views/UI patterns over new component scaffolding.
