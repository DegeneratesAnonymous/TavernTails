## TavernTAIls Copilot Instructions

### Default workflow
- Prefer **small, PR-sized changes** with tests.
- Use **canonical docs** when making decisions:
	- `PROJECT_PLAN.md` (plan/architecture)
	- `MVP_DELIVERY_CHECKLIST.md` (MVP acceptance)
	- `PROGRESS.md` (execution log)
	- `docs/CI_CHECKLIST.md` (quality gates)

### Development “Agents”
We use role-based development agents (PM/Backend/Frontend/QA/Reviewer) as a workflow.

- Playbook: `docs/DEV_AGENTS.md`
- Work orders: `docs/WORK_ORDER_TEMPLATE.md`
- Role prompts: `docs/dev-agents/*.md`

### Definition of done
- Acceptance criteria met.
- Tests added/updated where appropriate.
- CI-equivalent commands run for the touched area(s).
- Documentation updated when behavior/contracts change.
