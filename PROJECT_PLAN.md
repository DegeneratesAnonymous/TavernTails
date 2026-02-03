# TavernTAIls – Enhanced Technical and Product Plan

**CANONICAL PLAN (Single Source of Truth).**
This is the authoritative roadmap + architecture doc. Long-form references
(`TavernTAIls_Enhanced_Project_Plan.md`, `PROJECT_PLAN_BREAKDOWN.md`) may lag and
should not be used to make scope decisions.

_Last updated: 2026-02-03 – Maintainers: TavernTAIls Core Team_

Supersedes `PROJECT_PLAN.md` (v2025-11-30) and `PROJECT_PLAN_BREAKDOWN.md` (v2025-11-25).

## Document Map
- **Sections 1–8**: Product vision, personas, UX flows, and system architecture.
- **Sections 9–12**: Security, operations, and quality strategy.
- **Sections 13–17**: Delivery plan, risks, KPIs, and next steps.
- **Companion Checklist**: `MVP_DELIVERY_CHECKLIST.md` mirrors §13 acceptance gates with repo-level tasks/status.

---

## 1. Executive Summary
TavernTAIls is an AI-assisted solo/co-op tabletop RPG companion that assembles a “Session AI” of cooperating agents (Narrative, Scene, NPC, Notes, Storyboard, Image) to run persistent campaigns. The MVP targets deterministic multiplayer-friendly tooling: authenticated players spin up campaigns, curate session documents, invite friends, and rely on lightweight agent stubs while infrastructure, observability, and documentation keep the project contributor-friendly. The product also supports a **player‑run hub mode** where AI is optional: groups can run sessions themselves while TavernTAIls provides automated organization (notes, NPC index, documents, rolls, chat). This plan defines the scope, architecture, delivery phases, and acceptance criteria for the next 3–4 months.

## 2. Product Vision and Pillars
1. **Agent‑Optional Gameplay** – AI agents are additive, not required; sessions can be run by players with AI disabled.
2. **Session‑Centric UX** – Campaigns retain characters, documents, chat, rolls, and images so any device can resume play.
3. **Automated Organization** – Notes, NPC index, session logs, and content tagging reduce DM overhead and improve continuity.
4. **Player Identity & Characters** – Accounts, invites, friend graph, and character import/sync from PDFs or DnD Beyond.
5. **Reliability & Automation** – Scriptable dev setup, CI, telemetry, and playthrough validation keep the project contributor-friendly.

### Target Personas
- **Solo Adventurer** – Single player who wants guided journaling + AI narration.
- **Async Party** – 2–4 friends playing across time zones who need reliable persistence.
- **GM-Builder** – Hosts customizing prompts, documents, and NPCs who need robust control surfaces.
- **Group DM** – A player‑run table that wants automated notes/NPC tracking without AI narration.

## 3. Experience Map
| Flow | Description | Agent Touchpoints | Acceptance Signal |
| --- | --- | --- | --- |
| Onboarding | Signup → email verify → login | Player Agent, Auth | JWT issued, `/player/me` returns profile |
| Campaign Setup | Create campaign, upload documents, seed NPCs | Narrative, Storyboard, Notes | Campaign dashboard lists artifacts |
| Invite & Join | Host invites friend (min level) → player selects character | Player Agent, Scene Agent | Invite status transitions Pending → Accepted |
| Session Play | Chat, narration stream, dice rolls, NPC management | Narrative, Scene, NPC, PencilPusher | WebSocket updates render within 200 ms |
| Player‑Run Session | Players run the session with AI disabled; notes/NPCs auto‑organized | Notes, NPC | Session notes + NPC index updated after play |
| Session Archive | Notes recap, hidden docs updated, session snapshot stored | Notes, Storyboard | Session timeline shows recap + attachments |

## 4. System Architecture Overview
```
[React SPA] --API/WS--> [FastAPI gateway]
				|--> [Agent routers (narrative/scene/npc/...)]
				|--> [Service layer: campaigns, characters, invites]
				|--> [Persistence: SQLModel(DB), sessions/FS, object store]
				'--> [Task queue / worker (future LLM + image jobs)]
```
- **Frontend**: CRA + TypeScript, centralized `apiFetch`, agent-centric components, responsive CSS, WebSocket client.
- **Backend**: FastAPI + SQLModel, modular routers per agent/service, JWT auth, Alembic migrations, uvicorn.
- **Persistence**: SQLite (dev) → PostgreSQL (prod); session docs stored in filesystem for MVP with upgrade path to S3-compatible stores.
- **Realtime**: WebSockets per campaign/session, Redis pub/sub planned for horizontal scale; fall back to SSE/polling.
- **Background Work**: Dedicated queue for long-running LLM/image operations; results posted via agent events table.

## 5. Agent Responsibility Matrix
| Agent | Purpose | Key Inputs | Outputs | Frontend Surface |
| --- | --- | --- | --- | --- |
| GM Orchestrator | Validate and publish agent outputs | Narrative drafts, scene deltas | Player-facing narration/events | Session viewport |
| Narrative | Scene descriptions, dialogue | Storyboard beats, player actions | Narration JSON | Narrative stream panel |
| Scene Analysis | Detect rolls/rules triggers | Current scene snapshot, character stats | Roll requests, rule reminders | Dice prompt + alerts |
| NPC/Enemy Manager | Track stat blocks, initiative | Campaign NPC DB, encounters | NPC actions/state changes | NPC drawer + combat tracker |
| Storyboard | Graph of quests, unresolved hooks | Campaign history, Notes embeddings | Next-beat recommendations | GM helper timeline |
| Notes (Scribe) | Session summaries, loot, XP | Chat log, roll outcomes | Markdown recap, !notes command | Notes pane |
| Image | Prompt-to-image generation | Scene description, style preset | Image URL + metadata | Gallery + inline cards |
| Player Agent | Accounts, characters, invites | Auth payloads, PDF imports | JWTs, character manifests | Auth screens + character list |

Agents communicate via REST endpoints today; future iterations add async job dispatch plus WebSocket push notifications.

## 6. Domain Models and Storage
| Entity | Storage | Notes |
| --- | --- | --- |
| User, Friend, SessionMembership | SQLModel tables (`users`, `friends`, `memberships`) | Handles auth, invites, and host roles |
| Campaign, Session | SQLModel + Alembic | Sessions reference campaign, track state payload + folder path |
| Documents (Core/Flavor/Hidden) | Metadata in DB, files in `server/sessions/{campaign}` | Hidden docs only visible to hosts via RBAC |
| Characters | SQLModel with JSON attributes | Imports from manual form, PDF parser, or DnD Beyond token |
| Rolls & Events | `rolls`, `agent_events` tables | Powers audit trail + websocket replay |
| Images | Metadata table + object store path | Cache by campaign + style |

Document Taxonomy:
- **Core** – Canonical assets (character sheets, world map) with version history.
- **Flavor** – Optional references (random tables, mood boards) re-usable across campaigns.
- **Hidden** – Host-only prep (story beats, NPC secrets) accessible via DM Helper with audit logs.

## 7. Feature Capability Matrix
| Capability | MVP Scope | Phase 1 Enhancements | Dependencies |
| --- | --- | --- | --- |
| Auth & Accounts | Signup/login, email verify, JWT sessions | Refresh tokens, SSO | Email provider, DB |
| Campaigns & Sessions | CRUD, session folder creation, membership | Archive, branching story graph | Auth, Documents |
| Invites & Friends | Friend list, invite by email/user, min level | Presence indicators, notifications | Auth, Characters |
| Characters | Manual create/import, attach to invites | PDF parser, Beyond20/DnD Beyond sync | Storage, Parser tools |
| Dice & Rolls | Local roller, log, Beyond20 ingest endpoint | Rule automation, effect templates | Characters, Scene agent |
| Chat & Turn Queue | Text chat, !notes, manual turn tracking | Mentions, notifications, automated queue | WebSockets, Notifications |
| Automated Organization | Session notes, NPC index, document tagging, recap timeline | Cross‑session search, merge/resolve notes | Chat, Documents, NPC |
| Documents | Upload + tagging, hidden view, version metadata | S3 switch, collaborative editing | Storage adapter |
| Images | Provider abstraction, cached gallery | Style marketplace, per-character portraits | GPU/LLM budget |

## 8. Integration Strategy
- **Beyond20**: `/integrations/beyond20/roll` accepts payloads; optional local bridge for browser events.
- **DnD Beyond**: Phase 1 manual export parser; Phase 2 OAuth token polling with etag caching.
- **PDF Import**: `PyMuPDF`/`pdfminer.six` to extract structured JSON with heuristics + ML fallback.
- **External Storage**: Abstraction layer for S3-compatible backends; environment toggle for dev FS vs prod bucket.

## 9. Security, Privacy, and Compliance
- JWT access tokens; refresh tokens optional but recommended before multi-device release.
- RBAC roles: `player`, `host`, `admin`. Hidden docs, campaign settings, and agent overrides require host role.
- PII: email + optional OAuth tokens stored encrypted at rest. Secrets managed via `.env` + secret manager in prod.
- Rate limiting + abuse controls on agent endpoints; guardrails on LLM prompts to avoid policy violations.
- Audit trails: `agent_events`, `document_access` tables log sensitive reads/writes.

## 10. Operational Playbook
- **Dev Environment**: `start-app.ps1` spins backend + frontend, kills stray processes, streams logs to `logs/`.
- **Environments**: `local` (SQLite + filesystem), `staging` (Postgres + S3 mock + feature flags), `prod` (managed Postgres + S3 + CDN).
- **Observability**: Structured logging (JSON), request IDs, tracing hooks ready for OpenTelemetry, metrics via Prometheus-compatible endpoints.
- **Deployments**: GitHub Actions → Docker images (backend) + static build (frontend). Blue/green or rolling deploy once k8s/compose ready.

## 11. Quality Strategy
- **Unit Tests**: Backend pytest for routers/services; frontend Vitest/Jest for hooks + components.
- **Integration Tests**: FastAPI `TestClient` playthrough covering signup → verify → login → create campaign → invite.
- **E2E**: Playwright smoke (desktop + mobile viewport) for login + campaign creation + chat message.
- **Static Analysis**: mypy (backend), ESLint + TypeScript strict mode (frontend), Ruff/Black optional.
- **CI Pipeline**: Lint → unit tests → integration tests → frontend build → artifact upload. Blocking on `main`.

## 12. Delivery Work Packages & Roadmap
| # | Package | Scope Snapshot | Est. | Status |
| --- | --- | --- | --- | --- |
| 1 | Core Platform (Auth/Friends) | JWT auth, email verify, friend graph, `/player/*` endpoints | 3–5 days | MVP ✅ (refresh tokens pending) |
| 2 | Campaigns & Sessions | Campaign CRUD, membership, hidden docs, invites, WS skeleton | 1–2 weeks | In progress |
| 3 | Character Service & Imports | CRUD, Beyond20 ingest, PDF parser scaffolding | 1–3 weeks | Next |
| 4 | Dice Engine + Beyond20 | Deterministic roller, ingestion endpoint, UI log | 3–5 days | Planned |
| 5 | Agent Orchestration | Narrative/Scene/NPC/Notes/Image stubs + GM orchestrator | 2–4 weeks | Planned |
| 6 | Session Documents | Uploads, tagging, permissions, versioning | 1–2 weeks | Planned |
| 7 | Chat & Turn Queue | Persistent chat, mentions, notifications | 1–2 weeks | Planned |
| 8 | Image Agent | Adapter + caching + UI | 1–2 weeks | Phase 2 |
| 9 | Testing & CI | Lint/test/build pipeline, smoke E2E | 1–2 weeks | Started (pytest ✅) |

## 13. Release Phasing & Acceptance
- **MVP Gate**: Auth + campaign CRUD + session documents + chat + dice stub + **Hidden docs RBAC + audited document access** + `start-app.ps1` working on Windows + doc updates. Acceptance: run scripted playthrough without manual DB edits and verify non-host users cannot read `visibility=hidden` documents.
- **Phase 1 Gate**: Invites with character assignment, Beyond20 ingest, responsive session UI, PDF import prototype, background worker for LLMs, and **Player‑Run Session mode** (AI optional; notes/NPC tracking still available).
- **Phase 2 Gate**: DnD Beyond token sync, semantic search, DM Helper enhancements, production-grade image agent.

## 14. Risks and Mitigations
| Risk | Impact | Likelihood | Mitigation |
| --- | --- | --- | --- |
| AI cost overruns | Limits frequency of agent calls | Medium | Cache prompts, support local models, add usage quotas |
| Hidden doc leaks | Player trust loss | Medium | Strict RBAC, audited endpoints, automated tests for permissions |
| Parsing accuracy (PDF/DnD Beyond) | Frustrating character imports | High | Provide manual override UI, capture parsing telemetry, iterate heuristics |
| WebSocket scaling | Dropped events for async parties | Medium | Adopt Redis pub/sub, add reconnection/backfill logic |
| Key/secrets hygiene (SSH, API keys) | Security breach | Medium | Enforce `.gitignore`, rotate keys, document secure storage |

## 15. Success Metrics & Telemetry
- **Activation**: % of signups completing first campaign creation within 24h (target 60%).
- **Retention**: Weekly Active Sessions / Weekly Created Sessions ≥ 0.7 once invites ship.
- **Automation**: ≥ 80% of narration events auto-generated by Narrative + GM agents without manual edits.
- **Reliability**: P99 WebSocket round-trip under 400 ms, backend error rate < 1%.
- **Quality**: CI pass rate ≥ 95%, test coverage trending upward (backend ≥ 70%, frontend ≥ 60%).

## 16. Open Questions
1. Timeline for migration from filesystem session docs to managed object store?
2. Preferred AI/image provider and associated budget caps per month?
3. Do we require offline-capable clients (service workers + local caches) for mobile play?
4. What governance is needed for user-generated content (reporting, moderation)?

## 17. Next Actions
1. Generate Alembic migration for campaign/session schema changes (`metadata_json`).
2. Implement CI workflow (Python + Node matrix) and smoke tests.
3. Flesh out agent stubs with contract tests and example payloads.
4. Finalize document storage abstraction and S3 toggle.
5. Schedule key rotations and document secret management SOP.

## 18. Session UI Layout Notes (2025-12-03)
The following high-level UI requirements came from the latest layout discussion. Each item is mapped to the work package where it will be delivered so we avoid jumping ahead of the roadmap.

| Ref | Requirement | Description | Planned Package |
| --- | --- | --- | --- |
| 1 | Primary Scene Canvas | Full-width/height viewport that supports narration text, layered NPC portraits, and inline imagery; becomes the focal area inside `GameplayLayout` and `NarrativeView`. | #5 Agent Orchestration (Narrative UX) + #7 Chat & Turn Queue (UI polish) |
| 2 | Character Icon Strip | Use the new PNG icon set (Abilities/Features/Inventory/etc.) to visualize key stats pulled from the active character sheet. | #3 Character Service & Imports feeding #7 UI |
| 3 | Collapsible Utility Drawer | Consolidate Characters + Create Character into a single `Characters` drawer, merge Load Adventure/Campaign Settings into `Campaigns`, and rename Campaign Settings → Adventure Settings. Drawer collapses to a top-left button. | #2 Campaigns & Sessions (nav) + #7 UI |
| 4 | Rotating Banner | Banner slot that cycles between campaign title and status messages (e.g., "Waiting on <player>"). | #7 Chat & Turn Queue (session HUD) |
| 5 | Suggestion Bar | Surface 2–4 obvious next actions provided by Narrative/Scene agents (“suggestions” actions). | #5 Agent Orchestration |
| 6 | Player Stat Capsule | Compact strip showing player name, AC, current HP, temp HP, death saves, exhaustion, spell save DC. | #3 Character Service & Imports + #7 UI |
| 7 | Chat Pane Enhancements | Persistent chat with friend invites, export log, and power tools (pinning, filters). | #7 Chat & Turn Queue |

Action: include these acceptance notes when grooming Tickets/Epics tied to Packages #2/#3/#5/#7 so the UI implementation aligns with the agreed layout.

---
_This enhanced plan is the single source of truth for TavernTAIls planning, architecture, and delivery tracking. Update the “Last updated” stamp whenever material changes are made._
