# Work Order

## Title
WO-014: Phase 1 Contract Tests Expansion

## Goal
Expand the contract test suite from the WO-007 baseline of 6 tests to cover all agent endpoints including the new generate and campaign-invite endpoints, reaching ≥90% endpoint contract coverage.

## Research Briefing
_See: Tech Lead Assessment 2026-03-06 — contract coverage gaps identified as a CI quality risk._

## Context
- WO-007 established `server/tests/contracts/test_contracts_baseline.py` with 6 tests covering Narrative, Scene, Rolls, NPC, Suggestions, and Turns.
- Several endpoints added since WO-007 are not covered by contract tests: `/generate/*`, `/campaigns/{id}/invites`, `/documents/*`, `/characters/*` import flows, and the new campaign-member endpoints (WO-010).
- Contract tests prevent schema breakage that silently breaks the frontend without backend test failures.

## Scope / Non-Goals
- **In scope:**
  - Add contract tests for: `/generate/npc`, `/generate/location`, `/generate/loot`
  - Add contract tests for: `/documents/{session}` list, upload, delete
  - Add contract tests for: `/characters` list, create, PDF import response shape
  - Add contract tests for: `/campaigns/{id}/invites` (when WO-010 is merged — add placeholder/skip for now)
  - Ensure all contracts assert required fields and types (not just status code)
  - Contract tests should be fast (mock LLM calls; no real OpenAI calls)
- **Out of scope:**
  - End-to-end / Playwright tests (separate WO)
  - Frontend contract tests

## Acceptance Criteria
- [ ] ≥15 total contract tests (up from 6)
- [ ] Generate endpoint contracts: NPC, location, loot response shapes validated
- [ ] Documents endpoint contracts: list response shape, upload response, delete response
- [ ] Characters endpoint contracts: list shape, create shape, import response shape
- [ ] All new tests pass in CI (`.github/workflows/contract-tests.yml`)
- [ ] No real LLM calls in contract tests (mock `openai.ChatCompletion.create`)
- [ ] `server/tests/contracts/README.md` updated with new coverage map

## Implementation Notes
- **Files to modify/create:**
  - `server/tests/contracts/test_contracts_baseline.py` — extend with new tests
  - `server/tests/contracts/test_contracts_generate.py` — new file for generate contracts
  - `server/tests/contracts/test_contracts_documents.py` — new file for document contracts
  - `server/tests/contracts/test_contracts_characters.py` — new file for character contracts
- **Pattern:** Follow `test_contracts_baseline.py` style — `TestClient`, assert status code + required response fields
- **LLM mocking:** `unittest.mock.patch('server.agents.generate.openai')` or patch at the function level
- **Fixtures:** Reuse `auth_headers`, `campaign_id`, `session_id` fixtures from existing test utils

## Test Plan
- `python -m pytest server/tests/contracts/ -q`
- CI: existing `contract-tests.yml` already targets `server/tests/contracts/`

## Rollback
- Remove new contract test files; existing 6 baseline tests unaffected
