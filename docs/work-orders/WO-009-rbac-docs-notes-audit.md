# Work Order

## Title
WO-009: RBAC Audit — Documents & Notes

## Goal
Ensure RBAC for document access and notes logging is fully covered by tests and that audit logs are validated for host-only sensitive actions.

## Context
- Hidden documents are logged to `document_access.jsonl`; there are tests for hidden docs but notes endpoints and some edge-cases may lack coverage.

## Scope / Non-Goals
- In scope: add tests for `/documents/{session}` listing, read, create/delete with host/non-host permutations; add tests for `/notes/log` and `/notes/*` where membership matters; validate audit file presence and contents.
- Out of scope: refactor of RBAC model.

## Acceptance Criteria
- [ ] Tests assert non-hosts cannot list/read/create hidden documents.
- [ ] Tests assert audit file has expected entries after attempted/allowed operations.
- [ ] Notes endpoints verify membership and fail with 403 for non-members.

## Implementation Notes
- Files: `server/tests/test_hidden_docs.py` (extend), `server/tests/test_notes_rbac.py` (new).
- Use `sessions_module.create_session_folder` helper and `create_access_token` for test users.

## Test Plan
- Run: `venv\Scripts\python.exe -m pytest server/tests/test_hidden_docs.py server/tests/test_notes_rbac.py -q`

## Rollback
- Revert test additions if they introduce instability; file-based audits remain unchanged.
