# Work Order: WO-001 — Mypy Baseline Triage

## Owner
- PM Agent: `docs/dev-agents/PM.md`
- Tech Lead Agent: `docs/dev-agents/TECH_LEAD.md`
- Backend Agent: `docs/dev-agents/BACKEND.md`
- QA Agent: `docs/dev-agents/QA.md`
- Reviewer Agent: `docs/dev-agents/REVIEWER.md`

## Context
We want a healthier, more actionable mypy signal for the backend. Per [docs/CI_CHECKLIST.md](../CI_CHECKLIST.md), mypy is currently non-blocking, but we still want to reduce noise and prevent obvious typing regressions.

Current command:
- `mypy server/ --ignore-missing-imports --check-untyped-defs`

Current state (as of 2026-01-11):
- mypy runs but reports many errors across core modules (DB/auth) and non-runtime areas (tools/scripts/alembic/tests).

## Goals
1. Make mypy output actionable (prioritize runtime paths).
2. Reduce error count incrementally with PR-sized changes.
3. Avoid large refactors; prefer narrow type narrowing, casts, and small annotations.

## Non-Goals
- Full strict typing of the entire codebase.
- Large ORM/query refactors inside `server/db.py`.

## Acceptance Criteria
- A documented triage of mypy errors grouped by area.
- First slice lands:
  - `server/auth.py` mypy errors resolved with safe typing.
  - Any quick, obviously-correct fixes applied in small modules (e.g. a few Optional narrows).
- Mypy error count reduced measurably (target: -10+ errors) without changing runtime behavior.

## Plan (Slices)
### Slice A (Low-risk typing hygiene)
- Fix `server/auth.py` typing (JWT payload dict types, identifier cast).
- Fix a couple obvious Optional narrows in leaf agents where safe.

### Slice B (Noise reduction)
- Decide whether to exclude `server/alembic/`, `server/scripts/`, `server/tools/`, and tests from mypy for now (or mark as `ignore_errors`).

### Slice C (DB typing)
- Triage `server/db.py` errors into:
  - Optional-narrowing fixes
  - SQLModel typing limitations (may require `Any`/casts)
  - Real bugs (if any)

## Verification
- Run `mypy server/ --ignore-missing-imports --check-untyped-defs` and record new error count.
- Run backend tests: `pytest server/tests`.

## Notes
This work order is intentionally incremental: we improve signal first, then iterate.
