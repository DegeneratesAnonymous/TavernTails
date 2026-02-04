# Work Order

## Title
WO-007: Contract Tests Baseline

## Goal
Establish a baseline of contract tests for agent REST endpoints and WebSocket events to prevent UI regressions and provide a stable foundation for agent changes.

## Context
- There are multiple agent endpoints and WS event shapes used by the frontend (`scene.cues`, `rolls.result`, `suggestions.update`, `npc.profile`, `turns.update`, `/narrative/generate`, etc.).
- Existing tests exist (unit and some integration) but we want a dedicated `server/tests/contracts/` suite that validates schemas and payload shapes and runs in CI as a blocking job.

## Scope / Non-Goals
- In scope: add `server/tests/contracts/` with contract tests for Narrative, Scene, Rolls, NPC, Suggestions, and Turns; add CI job entry (GH Actions adjustment is separate WO).
- Out of scope: sweeping refactors of existing endpoints or frontend changes.

## Acceptance Criteria
- [ ] Contract tests exist for the listed agent endpoints and WS messages.
- [ ] Tests assert required fields and types (pydantic models / JSON keys) for each contract.
- [ ] Tests run in CI and pass on main (CI job will be added subsequently).
- [ ] README note added: how to run contract tests locally.

## Implementation Notes
- Files to modify/create:
  - `server/tests/contracts/test_contracts_baseline.py`
  - `server/tests/agent_payloads.py` (reuse existing fixtures)
  - Add a short README section under `server/tests/README.md` (optional)
- Endpoints to cover: `/narrative/generate`, `/scene/analyze`, `/rolls`, `/npc/manage`, `/suggestions`, `/turns/{session}`
- WS messages to validate via `TestClient` websocket helper (where practical): `rolls.result`, `scene.cues`, `npc.profile`, `turns.update`, `suggestions.update`

## Test Plan
- Run locally: `venv\Scripts\python.exe -m pytest server/tests/contracts -q`
- CI: add a job `contracts` that runs the same pytest target (separate WO).

## Rollback
- Remove the `server/tests/contracts/` folder and any CI adjustments if needed.
