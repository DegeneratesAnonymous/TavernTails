# Work Order

## Title
WO-005: Best Practices Retro Audit (Backend/Frontend/Dev UX)

## Goal
Establish and apply a small set of best practices to prevent regressions (e.g., blank refresh, wrong backend instance, 405s on uploads) and make failures debuggable.

## Context
We’ve added features quickly (PDF import, instructional flows, layout polish). Some runtime issues appeared:
- Refresh/white-screen symptoms (often silent crashes or server mismatch).
- PDF upload returning 405 Method Not Allowed (backend instance missing the route).

## Scope / Non-Goals
- In scope:
  - Document best practices and add guardrails that prevent common dev/runtime failure modes.
  - Ensure upload flows have correct headers and actionable error messages.
  - Add a minimal runtime “capability check” pattern for endpoints that are optional/new.
- Out of scope:
  - Large routing refactors (e.g., introducing react-router everywhere).
  - Re-architecting auth/storage.

## Acceptance Criteria
- [ ] A best-practices document exists and is referenced from contributor docs.
- [ ] Frontend upload flows do not set multipart `Content-Type` manually.
- [ ] On a 405/404 during PDF import, the UI provides actionable guidance including the detected API base.
- [ ] Dev startup reliably runs the intended backend+frontend pairing (no stale backend surprise).
- [ ] `./ci.ps1` passes.

## Implementation Notes
- Suggested files:
  - `docs/BEST_PRACTICES.md`
  - `start-app.ps1`
  - `client/src/api.ts`
  - `client/src/components/dashboard/ImportCharacterView.tsx`
- Consider adding a small helper that checks `/openapi.json` for required paths.

## Test Plan
- Backend: `venv\Scripts\python.exe -m pytest server/tests -q`
- Frontend: `cd client; npm test -- --watchAll=false`
- Full: `./ci.ps1`

## Rollback
Revert the guardrail commits (docs and UX messaging are low-risk). For startup script changes, fall back to manual `uvicorn` and `npm start` instructions in README.
