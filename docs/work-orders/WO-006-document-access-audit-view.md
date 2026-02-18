# Work Order

## Title
WO-006: Document Access Audit Viewer (Backend + Frontend)

## Goal
Expose a host-only audit log for session document access and make it visible in the Documents panel.

## Context
Hidden document access is already audited to a per-session JSONL file. The MVP checklist suggests a host-facing view of the audit log, but the UI lacks any way to inspect it.

## Scope / Non-Goals
- In scope:
  - Backend endpoint to read the audit log for a session (host-only).
  - Frontend UI in DocumentsPanel to fetch and display audit entries when host.
  - Tests for the new endpoint and RBAC.
- Out of scope:
  - Full pagination or export flows.
  - Changing audit record schema or storage format.

## Acceptance Criteria
- [ ] Hosts can request `/documents/{session_id}/audit` and receive a list of audit entries.
- [ ] Non-host session members are denied access (403).
- [ ] Documents panel shows an “Access Log” view for hosts only.
- [ ] Tests pass.

## Implementation Notes
- Suggested files:
  - `server/agents/documents.py`
  - `server/tests/test_hidden_docs.py` (or a new test module)
  - `client/src/components/DocumentsPanel.tsx`
- API endpoints affected:
  - `GET /documents/{session_id}/audit`
- WebSocket events affected: none

## Test Plan
- Backend: `venv\Scripts\python.exe -m pytest server/tests/test_hidden_docs.py -q`
- Frontend: `cd client; npm test -- --watchAll=false` (or skip if no UI tests are added)

## Rollback
Revert the endpoint and UI panel changes; audit logging to JSONL remains untouched.
