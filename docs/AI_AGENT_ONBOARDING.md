# AI Agent Onboarding Guide

This document is the single source of truth for how an AI agent should work in the TavernTails workspace.

## 1) Always start here
Read these in order before making changes:
1. PROJECT_PLAN.md (architecture + goals)
2. MVP_DELIVERY_CHECKLIST.md (acceptance criteria)
3. PROGRESS.md (current state)
4. docs/CI_CHECKLIST.md (quality gates)

If you are unsure where to act next, check docs/DEV_AGENTS.md for the role playbook and docs/work-orders/ for scoped tasks.

## 2) Role-based workflow
We use role-based agents (PM/Backend/Frontend/QA/Reviewer/Tech Lead).
- Playbook: docs/DEV_AGENTS.md
- Work order template: docs/WORK_ORDER_TEMPLATE.md
- Role prompts: docs/dev-agents/*.md

If a work order exists, follow it. If not, propose a small, PR-sized task that aligns with PROJECT_PLAN.md.

## 3) Definition of Done (DoD)
A change is complete only when all are true:
- Acceptance criteria met
- Tests added/updated where appropriate
- CI-equivalent commands run for the touched area(s)
- Documentation updated when behavior/contracts change

## 4) Project map (high level)
- Frontend: client/ (React + TypeScript)
- Backend: server/ (FastAPI + SQLModel)
- Docs: docs/ and root .md files
- Agents: AGENTS.md (roles + locations)

## 5) Development principles
- Make small, reviewable changes.
- Preserve existing style and public APIs unless explicitly requested.
- Prefer canonical docs listed above when making decisions.
- Avoid large refactors unless requested.

## 6) Testing & quality
Before declaring done:
- Run frontend tests when frontend code changes.
- Run backend tests when backend code changes.
- Check relevant lint/type checks if present in CI checklist.

Reference: docs/CI_CHECKLIST.md.

## 7) Operational safety
- Do not delete or overwrite files outside the requested scope.
- Never assume secrets; use docs/SECRET_MANAGEMENT.md.
- If data migrations are required, check server/alembic/ and alembic.ini.

## 8) Where to find agent modules
See AGENTS.md for the gameplay agent architecture and file locations.

## 9) Common commands (informational)
Use the project scripts rather than ad-hoc commands.
- Start app: start-app.ps1
- Python env: .venv\Scripts\Activate.ps1

If a command is needed, check the project docs first.

## 10) Escalation & uncertainty
If requirements are unclear:
- Check PROJECT_PLAN.md and PROGRESS.md
- Look for a relevant work order in docs/work-orders/
- If still unclear, propose a minimal, reversible change and ask for confirmation.

---
Last updated: 2026-02-08
