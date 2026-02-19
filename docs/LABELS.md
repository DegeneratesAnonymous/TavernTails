# Label Reference

This document describes all GitHub labels used in TavernTails, how they are applied, and how they map to [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) work packages.

## Type Labels

| Label | Color | When to use |
|-------|-------|-------------|
| `bug` | 🔴 red | Something isn't working as expected |
| `feature` | 🟢 green | New feature or enhancement |
| `documentation` | 🔵 blue | Documentation improvements |
| `maintenance` | 🟡 yellow | Code cleanup, refactoring, dependency updates |
| `testing` | 🟣 purple | Test coverage improvements, test infrastructure |
| `security` | 🔴 dark red | Security vulnerabilities or hardening |

## Priority Labels

| Label | Color | When to use |
|-------|-------|-------------|
| `priority: critical` | 🔴 dark red | Blocks MVP or production; fix immediately |
| `priority: high` | 🟠 orange | Important for the next release |
| `priority: medium` | 🟡 yellow | Should be done within the current sprint |
| `priority: low` | 🟢 light green | Nice to have; defer if needed |

## Component Labels

These map to specific areas of the codebase.

| Label | Area |
|-------|------|
| `component: backend` | Python/FastAPI (`server/`) |
| `component: frontend` | React/TypeScript (`client/`) |
| `component: agents` | AI agent system (`server/agents/`) |
| `component: database` | SQLModel models, Alembic migrations |
| `component: ci/cd` | GitHub Actions, build scripts |
| `component: docs` | Documentation only |

## Work Package Labels

These align with `PROJECT_PLAN.md §12` work packages.

| Label | Description |
|-------|-------------|
| `WP#1: auth` | Auth & Friends – JWT, email verification, player model |
| `WP#2: campaigns` | Campaigns & Sessions – campaign CRUD, session management |
| `WP#3: characters` | Character Service & Imports – character CRUD, D&D Beyond import |
| `WP#4: dice` | Dice Engine + Beyond20 – roll logging, Beyond20 ingest |
| `WP#5: orchestration` | Agent Orchestration – narrative, scene, NPC agents, WebSocket contracts |
| `WP#6: documents` | Session Documents – upload, list, read, delete (local + S3) |
| `WP#7: chat` | Chat & Turn Queue – session chat, turn management |
| `WP#8: images` | Image Agent – AI image generation, provider adapters |
| `WP#9: testing` | Testing & CI – coverage, CI quality gates, smoke tests |

## Status Labels

| Label | When to use |
|-------|-------------|
| `status: blocked` | Cannot proceed; waiting on a dependency or decision |
| `status: in-progress` | Actively being worked on |
| `status: needs-review` | PR or design is ready for review |
| `status: needs-info` | Needs clarification before work can continue |

## Special Labels

| Label | When to use |
|-------|-------------|
| `dev-agent-task` | Task assigned to a development agent (see `docs/DEV_AGENTS.md`) |
| `player-led-mode` | Related to player-led or AI-optional sessions |
| `ai-optional` | Feature that supports AI-optional gameplay |
| `needs-triage` | Newly opened; needs initial assessment and label assignment |
| `good first issue` | Well-scoped, low-risk – suitable for new contributors |

## Syncing Labels

Labels are defined in [`.github/labels.yml`](../.github/labels.yml) and synced automatically via the [label-sync workflow](../.github/workflows/label-sync.yml) when that file changes on `main`.

To sync manually, trigger the `Sync Labels` workflow from the Actions tab.

## Labeling Existing Issues

The following issues should be labeled according to their content:

| Issue | Labels |
|-------|--------|
| #17 – D&D Beyond Importing | `bug`, `WP#3: characters`, `component: backend`, `priority: high` |
| #26 – Define Campaign Variables | `feature`, `WP#5: orchestration`, `component: agents`, `priority: medium` |
| #30 – Player Led Campaign | `feature`, `player-led-mode`, `WP#2: campaigns`, `WP#5: orchestration`, `component: backend`, `component: frontend`, `priority: high` |
