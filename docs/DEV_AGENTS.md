# Development Agents (Workflow)

TavernTAIls already has *gameplay* agents (Narrative/Scene/NPC/etc). This document sets up **development agents**: role-focused prompts and a lightweight workflow so you can delegate planning, implementation, QA, and review to specialized “agents” (usually by pasting the role prompt into Copilot Chat or your preferred LLM).

These dev agents are **process helpers**. They should not change product scope without you explicitly approving it.

## Quick Start
1. Pick a role below.
2. Copy the role prompt into a new Copilot Chat.
3. Give the agent a Work Order (see template) and a constraint like “small PR, tests required”.

Recommended cadence:
- PM Agent creates/updates 1–3 Work Orders.
- Backend/Frontend Agent executes a Work Order.
- QA Agent runs/extends tests.
- Reviewer Agent does a final pass and creates a concise merge checklist.

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

### Docs/PM Agent
**Does**: maintains MVP scope decisions, keeps trackers current, creates small Work Orders with acceptance criteria.

**Prompt**: see `docs/dev-agents/PM.md`.

### Tech Lead Agent
**Does**: API/UI architecture decisions within agreed scope; keeps contracts stable.

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
**Does**: final review for scope, security basics, API contract stability, and “definition of done”.

**Prompt**: see `docs/dev-agents/REVIEWER.md`.

## Operating Rules (Important)
- **No scope changes** without explicit approval.
- Each Work Order must include: touched areas, acceptance criteria, test command(s), and rollback note.
- Prefer small PRs.
- Keep planning-doc drift under control by updating the canonical docs after changes land.
 - **Chat is the decision surface**: scope, priorities, and stylistic choices must be confirmed in chat before implementation.
 - **Follow the dev-agent cycle**: PM → Backend/Frontend → QA → Reviewer for any non-trivial change.
