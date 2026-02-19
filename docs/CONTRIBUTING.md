# Contributing to TavernTails

Thank you for contributing! Please read this guide before opening issues or pull requests.

## Workflow

1. **Check the Projects board** – pick up an unassigned issue from the _Backlog_ or _To Do_ column.
2. **Assign the issue to yourself** and move it to _In Progress_.
3. **Create a branch** (see naming conventions below).
4. **Follow the dev-agent workflow** – see [`docs/DEV_AGENTS.md`](DEV_AGENTS.md) for role-based guidelines.
5. **Run CI checks locally** before pushing (see [Running Tests Locally](#running-tests-locally)).
6. **Open a PR** using the PR template. Fill in all sections.
7. **Address review feedback** and keep the branch up to date with `main`.

## Branch Naming

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feature/<issue-number>-short-description` | `feature/42-dice-rolling` |
| Bug fix | `fix/<issue-number>-short-description` | `fix/17-beyond20-import` |
| Documentation | `docs/<description>` | `docs/contributing-guide` |
| Chore/refactor | `chore/<description>` | `chore/cleanup-imports` |

## Running Tests Locally

### Backend
```bash
cd /path/to/TavernTails
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt

# Lint
ruff check server/

# Type check (non-blocking, informational)
mypy server --ignore-missing-imports --check-untyped-defs

# Tests
pytest server/tests -q
```

### Frontend
```bash
cd client
npm ci
npm run lint --if-present
npx tsc --noEmit
npm test -- --watchAll=false
npm run build
```

## Architecture Reference

- **Canonical architecture & roadmap:** [`PROJECT_PLAN.md`](../PROJECT_PLAN.md)
- **MVP acceptance criteria:** [`MVP_DELIVERY_CHECKLIST.md`](../MVP_DELIVERY_CHECKLIST.md)
- **Dev-agent roles & workflow:** [`docs/DEV_AGENTS.md`](DEV_AGENTS.md)
- **Work order template:** [`docs/WORK_ORDER_TEMPLATE.md`](WORK_ORDER_TEMPLATE.md)
- **Quality gates:** [`docs/CI_CHECKLIST.md`](CI_CHECKLIST.md)
- **Gameplay agent map:** [`AGENTS.md`](../AGENTS.md)

## Label Usage Guide

See [`docs/LABELS.md`](LABELS.md) for the full label reference.

**Quick guide:**
- Add a **type label** (`bug`, `feature`, etc.) to every issue.
- Add a **priority label** to communicate urgency.
- Add **component label(s)** to indicate affected areas.
- Add a **work package label** (`WP#1: auth`, etc.) when the issue maps to `PROJECT_PLAN.md §12`.
- `needs-triage` is added automatically by issue templates; remove it once the issue is triaged.

## Definition of Done

A PR is ready to merge when:
- [ ] Acceptance criteria from the linked issue are met
- [ ] Tests added/updated where appropriate
- [ ] All CI checks pass (see [`docs/CI_CHECKLIST.md`](CI_CHECKLIST.md))
- [ ] Documentation updated when behavior or contracts change
- [ ] At least one approving review received
