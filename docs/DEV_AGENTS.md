# Development Agents (Workflow)

TavernTAIls already has *gameplay* agents (Narrative/Scene/NPC/etc). This document sets up **development agents**: role-focused prompts and a lightweight workflow so you can delegate planning, implementation, QA, and review to specialized “agents” (usually by pasting the role prompt into Copilot Chat or your preferred LLM).

These dev agents are **process helpers**. They should not change product scope without you explicitly approving it.

## Option A — Orchestrator Workflow (default)

The recommended approach is **Option A**: a single Orchestrator prompt that internally executes every role in order and emits one structured, multi-section response.

### How it works

1. An issue or PR is opened (or assigned to `copilot`, or the `qa-failed` label is applied).
2. The **Agent Workflow** (`.github/workflows/agent-workflow.yml`) automatically posts a checklist comment with a link to the Orchestrator prompt and a Required Inputs checklist.
3. You fill in the Required Inputs (goal, scope, acceptance criteria, constraints, links — plus QA findings on a restart) and run the Orchestrator prompt in a single Copilot/LLM invocation.
4. The Orchestrator produces one structured output with sections for Research, Tech Lead Plan, Backend, Frontend, DevOps, Security, QA, and Documentation.
5. Paste the full output as a comment on the issue/PR and work through the resulting plan.

**Orchestrator prompt:** `docs/dev-agents/ORCHESTRATOR.md`

### QA failure / restart

If QA finds blocking defects:
1. Document findings in an issue/PR comment.
2. Apply the `qa-failed` label.
3. The workflow will post a restart comment prompting you to re-run the Orchestrator with QA findings included as Required Input §6.

### Quick Start
1. Open [`docs/dev-agents/ORCHESTRATOR.md`](dev-agents/ORCHESTRATOR.md).
2. Fill in all Required Inputs from the issue/PR.
3. Run the prompt once; paste the full structured output as a comment.

## Canonical Docs to Reference
- Planning & architecture (canonical): `PROJECT_PLAN.md`
- Long-form reference / brain-dump: `TavernTAIls_Enhanced_Project_Plan.md`
- Execution log: `PROGRESS.md`
- MVP acceptance: `MVP_DELIVERY_CHECKLIST.md`
- CI quality gates: `docs/CI_CHECKLIST.md`
- Gameplay agent map: `AGENTS.md`

## Plan-Aligned Workstreams (PROJECT_PLAN.md §12)
Use this mapping to keep Work Orders small but coherent. Each package should have a clear **lead dev agent**, explicit artifacts (files/endpoints/events), and a test plan.

| Plan Package | Lead Dev Agent | Supporting Dev Agents | Primary Artifacts (examples) | “Done” Signal |
| --- | --- | --- | --- | --- |
| **#1 Core Platform (Auth/Friends)** | Backend | Frontend, QA, Reviewer | `server/agents/player.py`, `server/auth.py`, login/signup UI | `/player/*` flows tested; JWT + verify works |
| **#2 Campaigns & Sessions** | Tech Lead | Backend, Frontend, QA | `server/agents/campaigns.py`, `server/agents/sessions.py`, `client/src/components/CampaignsMenu.tsx` | Campaign→session→play path is unambiguous |
| **#3 Character Service & Imports** | Tech Lead | Backend, Frontend, QA | `server/agents/characters.py`, `client/src/components/CharacterPanel.tsx` | Character CRUD + “active character” selection works |
| **#4 Dice Engine + Beyond20** | Backend | Frontend, QA | `server/agents/rolls.py`, `/integrations/beyond20/roll`, chat roll rendering | Deterministic roll logging + ingest tested |
| **#5 Agent Orchestration** | Tech Lead | Backend, QA | `server/agents/narrative.py`, `server/agents/scene.py`, WS event contracts | Stable event contracts + contract tests |
| **#6 Session Documents** | Backend | Frontend, QA | `server/agents/documents.py`, `server/storage/documents.py`, `DocumentsPanel.tsx` | Upload/list/read/delete works in local + S3 mode |
| **#7 Chat & Turn Queue** | Frontend | Backend, QA | `server/agents/chat.py`, `server/agents/turns.py`, `client/src/components/Chat.tsx` | Session chat + turns feel reliable/live |
| **#8 Image Agent (Phase 2)** | Tech Lead | Backend, Frontend, QA | `server/agents/image.py`, image UI surfaces | Provider adapter + caching contract |
| **#9 Testing & CI** | QA | Backend, Frontend, Reviewer | `.github/workflows/ci.yml`, `server/tests/*`, `client/src/*.test.tsx` | CI gates match docs + are reproducible locally |

### Cross-Cutting Workstreams (always-on)
- **Security/RBAC** (Lead: Backend; Support: QA, Reviewer)
	- Goal: enforce host/player roles consistently across documents, sessions, and future invites.
	- Must-have tests: deny access for non-host; audit or event log where required.
- **Realtime Contracts** (Lead: Tech Lead; Support: Backend, Frontend, QA)
	- Goal: keep WebSocket payload shapes stable; version if breaking.
	- Must-have tests: contract tests for `scene.cues`, `npc.profile`, `turns.update`, `suggestions.update`, `rolls.result`.

## How to Slice Work Orders (so agents stay efficient)
- Prefer a Work Order that touches **one package** and at most **one UI surface**.
- If a change touches both backend+frontend, write one Work Order but include clear “Backend tasks” and “Frontend tasks” sections.
- For anything that changes payload shapes, require: (1) contract test update, (2) UI update, (3) brief note in `PROGRESS.md`.

## Work Order Template
Use `docs/WORK_ORDER_TEMPLATE.md`.

## Agent Roles

### Research Agent
**Does**: web research, best-practice lookups, spec/API reference gathering. Delivers a Research Briefing to the Tech Lead *before* any implementation planning begins. Does NOT write code or make architecture decisions.

**When to invoke**: at the start of any Work Order that involves a new technology, external format (e.g. PDF parsing, game system schemas), third-party API, or unfamiliar domain.

**Prompt**: see `docs/dev-agents/RESEARCH.md`.

### Docs/PM Agent
**Does**: maintains MVP scope decisions, keeps trackers current, creates small Work Orders with acceptance criteria.

**Prompt**: see `docs/dev-agents/PM.md`.

### Tech Lead Agent
**Does**: API/UI architecture decisions within agreed scope; keeps contracts stable. Consumes Research Briefing from the Research Agent when available.

**Prompt**: see `docs/dev-agents/TECH_LEAD.md`.

### Backend/API Agent
**Does**: implements FastAPI endpoints, DB/storage changes, websocket events, pytest coverage.

**Prompt**: see `docs/dev-agents/BACKEND.md`.

### Frontend/Web Agent
**Does**: implements React UI flows, state handling, API integration, component tests.

**Prompt**: see `docs/dev-agents/FRONTEND.md`.

### QA/Automation Agent
**Does**: test plans, adds/updates tests, tightens CI gates, identifies flakiness.

**Prompt**: see `docs/dev-agents/QA.md`.

### Reviewer Agent
**Does**: final holistic review for scope alignment, API contract stability, code quality, and “definition of done”. Complements (does not replace) the Security Reviewer.

**Prompt**: see `docs/dev-agents/REVIEWER.md`.

### Security Reviewer Agent
**Does**: focused security review — authentication/authorization enforcement, input validation, RBAC boundary testing, secret handling, and data-exposure risks. Distinct from the general Reviewer; this agent specifically checks security implications.

**Prompt**: see `docs/dev-agents/SECURITY.md`.

### DevOps Agent
**Does**: CI/CD pipeline, GitHub Actions workflows, infrastructure configuration, deployment scripts, dependency management, and environment/secret setup.

**Prompt**: see `docs/dev-agents/DEVOPS.md`.

## Operating Rules (Important)
- **No scope changes** without explicit approval.
- Each Work Order must include: touched areas, acceptance criteria, test command(s), and rollback note.
- Prefer small PRs.
- Keep planning-doc drift under control by updating the canonical docs after changes land.
