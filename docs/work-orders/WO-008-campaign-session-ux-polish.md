# Work Order

## Title
WO-008: Campaign→Session UX Polish

## Goal
Make the campaign→session→play flow deterministic and remove session scoping ambiguity that leads to UI errors and unexpected bootstrap behavior.

## Context
- Users report edge cases where active session persists across campaigns or bootstrap is non-deterministic.
- `client/src/components/LoggedInDashboard.tsx` and `GameplayHeader` manage active session state; backend has `/sessions/{id}/meta` and `/sessions/{id}/bootstrap`.

## Scope / Non-Goals
- In scope: ensure active session is always scoped to active campaign, add deterministic bootstrap API validation, add integration tests covering campaign switch and session creation.
- Out of scope: UI redesign beyond small state fixes and adding tests.

## Acceptance Criteria
- [ ] When switching campaigns, `activeSession` is cleared or aligned to a session in the selected campaign.
- [ ] Creating a campaign with `create_session=true` returns session meta and sets `activeSession` deterministically.
- [ ] Integration tests cover switching campaigns and bootstrapping sessions.

## Implementation Notes
- Files to inspect/change: `client/src/components/LoggedInDashboard.tsx`, `client/src/components/GameplayHeader.tsx`, backend `server/agents/campaigns.py` and `server/agents/sessions.py`.
- Tests: add `server/tests/test_campaign_session_flow.py` integration tests using `TestClient`.

## Test Plan
- Backend: `venv\Scripts\python.exe -m pytest server/tests/test_campaign_session_flow.py -q`
- Frontend smoke: `npm run build` and manual playtest in dev (or Playwright smoke later).

## Rollback
- Revert changes to session-setting logic and restore previous state management.
