**TavernTAIls — Project Plan**

**Purpose**: Provide a living technical and product plan for TavernTAIls: an AI-assisted solo or co-op tabletop RPG platform where a team of specialized agents (the "Session AI") composes, runs, and manages persistent campaigns.

**Contents**
- **Vision & Scope**: High-level goals and MVP boundaries.
- **Glossary / Lingo**: Definitions for Session AI, Story, Quest, Campaign, Session Documents.
- **Session Documents**: Core / Flavor / Hidden document taxonomy and handling.
- **Architecture**: System components, data flow, storage, realtime, and agent orchestration.
- **Agents**: Roles, responsibilities, I/O contracts, and UX ties.
- **Features & UX**: Campaigns, friends, invites, character creation/import, dice engine, chat, notifications.
- **Integrations**: Beyond20, DnD Beyond sync, PDF parsing, image generation.
- **Data Model & APIs**: Entities and example endpoints.
- **Security & Deployment**: Auth, roles, secrets, hosting recommendations.
- **Developer DX**: `start-app.ps1`, dev environment, recommended commands.
- **Roadmap & Milestones**: MVP → expansion phases, CI/testing.

**Vision & Scope**
- **Product**: A lightweight, extensible web app where players run campaigns backed by modular AI agents. The app supports persistent world state, player-managed documents, and both asynchronous and live play.
- **MVP Focus**: Accounts, campaigns, session documents (Core/Flavor/Hidden), character model, invite + membership flow, basic agent stubs (Narrative, Scene, NPC, Notes), dice engine, chat, and a developer-friendly start script. Integrations and advanced agent logic are Phase 2.

**Glossary / Lingo**
- **Session AI**: Collective name for backend agents that generate session content (Narrator, Writer, Scene, etc.).
- **Campaign / Story / Quest**: Campaign = container for many sessions and quests. Story = the overarching narrative tying quests. Quest = self-contained multi-session adventure.
- **Session Documents**: Files and structured documents used by Session AI. Categorized into Core, Flavor, and Hidden documents (see below).

**Session Documents**
- **Core Documents**: Required persistent assets stored per campaign. Examples: Character Sheets (canonical), Player Notes, World Map, canonical Locations, Party Roster. These are read/write by players with versioning and audit logs.
- **Flavor Documents**: Uploadable, optional artifacts that influence tone and content. Examples: random tables, inspiration PDFs, homebrew subclasses, adventure hooks. Players should be able to upload and reuse across campaigns.
- **Hidden Documents**: DM-only or host-only documents used to run the campaign but hidden from players during normal play. Examples: story beats, NPC secrets, encounter plans, treasure caches, and prewritten quests. Access via elevated UI (DM Helper) and protected by permissions/audit trails.
- **Storage & Access**: Documents live in a campaign-scoped object store (filesystem for MVP, S3-compatible for hosted). Each document has metadata: uploader, visibility, tags, checksum, and optional prompt-derived embedding for semantic search.

**Architecture (High-Level)**
- **Backend**: FastAPI (existing) with a modular router per agent and service. DB: SQLite for local/dev, PostgreSQL for production. ORM: SQLModel/SQLAlchemy.
- **Frontend**: React + TypeScript (CRA), componentized agents UI, progressive/responsive CSS and mobile-first layouts.
- **Realtime**: WebSocket endpoints for live sessions (chat, stream narration, event broadcast). Fallback via polling/SSE for asynchronous play.
- **Agent Orchestration**: Agents run as internal services (functions or submodules). For heavy LLM/image work, use queued workers (Celery/RQ) or external microservices to avoid blocking requests.
- **File Storage**: Campaign-scoped directory tree in server `sessions/` (current approach) with optional move to cloud object store.
- **Search & Embeddings**: Optional vector DB like Redis/pgvector for semantic lookup of session documents and notes.

**Agents — Roles & Responsibilities**
Design principle: each agent is a thin, specialized service with a clear I/O contract and testable behavior. A *GM Agent* composes and validates outputs.

- **GM Agent (Orchestrator / Quality Gate)**: Receives outputs from other agents, validates coherency, enforces global constraints (tone, rules), and publishes the final narration to players. Responsible for player-facing presentation.
- **Writer Agent**: Generates long-form story, quests, quest hooks, and evolving plot. Input: campaign state, story beats, player actions; Output: story fragments, quest outlines, beats.
- **Narrator Agent**: Converts Writer outputs and live player actions into scene descriptions, NPC dialogue, and turn prompts. Works with GM for presentation.
- **Scene Agent**: Parses current scene, detects triggers for dice rolls, encounter progression, and required actor actions. Emits roll requests to PencilPusher.
- **PencilPusher Agent (Game Mechanic Engine)**: Runs dice rolls, applies character modifiers (from Character Sheets), resolves damage/HP/conditions, and returns structured outcomes. Integrate with Beyond20 and local dice UI.
- **Scribe Agent (Notes)**: Records session notes, recaps, and extracts notable items (loot, XP, status). Periodically scans character sheets for changes (new spells, level-ups) and feeds Writer Agent.
- **NPC/Enemy Manager**: Stores NPC statblocks, behaviors, initiative management; interfaces with Scene and PencilPusher.
- **Storyboard Agent**: Tracks campaign and quest progress, unresolved threads, and stores story graph for longer-term memory.
- **Image Agent**: Generates scene/character illustrations; abstracts external image APIs; caches generated images; allows style selection.
- **Player Agent**: Handles player-specific tasks: character CRUD, imports, friend/campaign invites, and account sync services.

Agent I/O contract (example):
- Input: JSON containing `campaign_id`, `session_id`, `state_snapshot`, `player_action[]`, `document_refs[]`.
- Output: JSON with `type` (narration/roll_request/scene_update), `payload`, `metadata` (confidence / provenance), and optional `attachments` (image refs).

**Features & UX**
- **Campaigns Menu**: Lists campaigns with **Campaign name**, **player count**, **age**, and quick actions (open, edit, invite, archive). Replaces current load session flow.
- **Friend System**: Add / accept friends, friend-based invites, friend presence indicators. DB table `friends` with mutual links.
- **Invites & Membership**: Invite flows allow senders to require a minimum character level. Invite acceptance requires character selection or creation.
- **Character System**: Full character CRUD, import from PDF (OCR + heuristic parser) and DnD Beyond (API or scraping + user token). Sync strategies discussed below.
- **Dice Engine**: Roll UI, log, and integration with Beyond20 to ingest external roll events. PencilPusher applies modifiers.
- **Chat & Turn Queue**: Persistent chat with a Player Menu to the right for quick access to character shortcuts (Spells, Items, Skills, Actions, Journal). Chat supports asynchronous play and notifications.
- **DM Helper**: Elevated UI to view Hidden Documents and admin controls (teleport player, reveal notes, fudge rolls, fast-forward beats).

**Integrations**
- **Beyond20**: Two-way integration plan:
  - Ingest: Beyond20 can post roll events to localhost via its request to a configured endpoint (or user browser-to-backend forwarding). Implement an endpoint `/integrations/beyond20/roll` that accepts roll payloads and maps to session/player.
  - Outbound: Provide a browser extension bridge page that can forward roll requests or use browser local webhook patterns.
- **DnD Beyond**:
  - Short-term: Allow user-provided export (copy-paste or file) and a parser in `server/agents/player.py` to create Character records.
  - Long-term: Use DnD Beyond OAuth token (if user permits) to poll character changes every X minutes or subscribe to webhooks if available. Aim for near-real-time sync (1–5 minute window) using incremental polling and ETags.
- **PDF parsing**: Use `pdfminer.six` / `PyMuPDF` to extract text; apply heuristics and a mapping layer to transform to structured Character data. Optional ML-based classifier for robust extraction.
- **Image generation**: Abstract provider layer with adapters (Stable Diffusion, DALL·E, local inference). Images cached per `campaign_id` + style.

**Data Model & Example API Surface**
- **Core Entities**: `User`, `Friend`, `Campaign`, `Character`, `Session`, `Document`, `Invite`, `Message`, `AgentEvent`.
- **Selected endpoints (examples)**:
  - `POST /player/signup`, `POST /player/login`, `GET /player/me`
  - `POST /campaigns` (create), `GET /campaigns` (list), `GET /campaigns/{id}`
  - `POST /campaigns/{id}/invite` (invite email/user, min_level)
  - `POST /campaigns/{id}/documents` (upload, tag, visibility)
  - `GET /campaigns/{id}/documents` (filter by visibility)
  - `POST /campaigns/{id}/characters` (import/create), `GET /characters` (user-scoped)
  - `POST /integrations/beyond20/roll` (ingest external roll event)
  - `WS /campaigns/{id}/ws` (realtime channel for chat/agent updates)

**Persistence & Storage Details**
- **Database**: Start with SQLite + SQLModel for dev. Migrate to PostgreSQL in production with Alembic migration scripts.
- **Documents & Media**: Local filesystem for MVP (`/data/campaigns/{id}/documents/`), with metadata in DB. Support switch to S3-compatible store via configuration.
- **Embeddings/Memory**: Optional vector store (pgvector/Redis) for semantic search across session documents. Store per-campaign index for privacy.

**Realtime & Scaling**
- **WebSockets**: Primary tool for live sessions. Implement channel auth and permissions. Use a pub/sub backend (Redis) for multi-process scaling.
- **Workers**: Delegate long-running LLM calls and image generation to background workers with a job queue and retry logic. Store results and emit events on completion.

**Sync Strategy for DnD Beyond**
- **Option A: User-provided Token (Preferred)**: User supplies an access token; server polls DnD Beyond endpoints for character lists and updates. Poll frequency configurable; update last-modified/etag stored to minimize traffic.
- **Option B: Local Bridge**: Small browser-side helper that forwards events from DnD Beyond (via user browser) to the server. Simpler but less robust.

**Security & Auth**
- **Auth**: JWT access tokens issued on login, optional refresh tokens. Role-based access control: `player`, `host`, `admin`.
- **Documents**: Enforce visibility rules at API / storage level. Hidden docs accessible only to hosts with audited access logs.
- **Rate limits / Abuse**: Per-IP and per-account rate limits for agent endpoints; throttling for LLM calls.

**Developer Experience & `start-app.ps1`**
- **Goal**: One command to stop leftover dev processes and start backend + frontend with logs.
- **Script**: `start-app.ps1` (included at repo root) kills `uvicorn` and `node` processes, starts the backend (`venv\Scripts\python.exe -m uvicorn server.main:app`) and the frontend (`npm start` in `client/`) with logs redirected to `logs/`.
- **Usage**:
```powershell
# from repo root (Windows PowerShell)
.\start-app.ps1
```

**Testing & CI**
- **Unit tests**: backend (pytest), frontend (jest) for components and agents.
- **Integration tests**: use TestClient and Playwright/Cypress for end-to-end flows (signup→verify→login→create campaign→invite→join).
- **CI**: GitHub Actions with matrix for Python versions and Node; run lints, unit tests, build, and e2e stage on PR.

**Roadmap & Milestones**
- **MVP (1–3 weeks dev)**:
  - Auth + DB setup, campaign CRUD, documents (Core/Flavor/Hidden), character CRUD, basic agent stubs (Narrative/Scene/PencilPusher/Scribe), chat, and `start-app.ps1`.
  - Acceptance: sign up, create campaign, upload document, create character, invite friend, basic narrated scene and roll via built-in dice UI.
- **Phase 1 (4–8 weeks)**:
  - Beyond20 ingestion endpoint, improved agent orchestration, background worker queue, WebSocket scaling with Redis, simple PDF import, friend system, and campaign menu UX.
- **Phase 2 (8–16 weeks)**:
  - DnD Beyond sync (token-based), image generation, semantic search, DM Helper advanced features, extended agent instruction sets, and richer editor for Hidden docs.

**Implementation tasks & priorities (short list)**
- Immediate:
  - Finish backend character endpoints and session membership (done partly).
  - Implement `start-app.ps1` (added).
  - Add basic Campaigns UI and Friend table.
- Next:
  - Add WebSocket channel and PencilPusher dice engine endpoint.
  - Integrate Beyond20 ingest endpoint and local roll UI.
  - Add PDF import pipeline and initial parsers.

**Open questions / decisions**
- Do we want first-class versioning for Core Documents? (Recommended yes — simple version + snapshots.)
- Vector DB: defer to Phase 2 unless semantic search is required immediately.
- Hosting: prefer Docker Compose for local dev and Kubernetes for scale; start with simple Docker/Procfile for easy deploy.

**Appendix: Where to start now (developer instructions)**
- Run dev backend (venv must be active) and frontend dev server via `.\start-app.ps1`.
- Run tests: `python -m pytest server/tests -q`.
- Build frontend for prod: `cd client; $env:REACT_APP_API_URL='http://localhost:8000'; npm run build`.

---
Documentation maintained in this file is a living document — update as architecture and requirements evolve.
# TavernTAIls AI GM – Living Plan

_Last updated: 2025-11-30_

## 1. Product Vision
Create a solo-friendly tabletop RPG companion that acts as an AI Game Master, orchestrating narrative beats, scene mechanics, NPCs, and visual aids so a single player (or small asynchronous group) can enjoy deep campaign experiences from any device.

## 2. Core Pillars
1. **Agent-Oriented Gameplay** – Dedicated backend/front-end agents for Narrative, Scene Analysis, NPC/Enemy, Storyboard, Notes, and Image generation (see `AGENTS.md`) that collaborate via REST APIs.
2. **Session-Centric UX** – Sessions bundle story progress, settings, invites, and shared state so multiple devices (desktop/mobile) can resume seamlessly.
3. **Player Identity & Characters** – Authenticated users manage characters, accept invites, and join sessions at GM-defined levels.
4. **Reliability & Automation** – Deterministic local dev experience, automated playthrough tests, and future CI/E2E coverage.

## 3. Architecture Snapshot
- **Frontend (client/)** – React + TypeScript (CRA). Centralized API helper (`src/api.ts`). Key screens: Login/Signup, Logged-In Dashboard, Gameplay Layout, Session settings. Responsive design in progress.
- **Backend (server/)** – FastAPI + SQLModel/SQLite. Routers under `server/agents/` for player, sessions, content, etc. JWT auth via `server/auth.py`. Filesystem-backed session storage (`server/sessions/`).
- **Tooling** – `server/tools/playthrough.py` automates signup→verify→login→session→invite; `npm run check-port` guards CRA dev server port usage.

## 4. Completed Milestones
| Area | Highlights |
| --- | --- |
| Auth & Dev Ergonomics | DB-backed signup/login with JWT, auto-seeded dev user (`test@example.com/secret`), login input normalization, `/player/me` refresh. |
| Frontend Infrastructure | Central API resolver, token persistence, login/signup UX, protective port guard, CRA build passing. |
| Stability Tooling | Automated backend playthrough, basic docs (`README.md`, `AGENTS.md`). |

## 5. Active Initiatives
1. **Session UI Polish & Responsiveness** – Modernize layout, mobile breakpoints, and session controls.
2. **Invite Workflow Enhancements** – End-to-end UX for sending/accepting invites, surfacing membership state.
3. **Character Creation & Selection** – Players create/manage characters, choose one when accepting invites; hosts set desired level.

## 6. Near-Term Roadmap
| Priority | Description | Owner | Status |
| --- | --- | --- | --- |
| Responsive session UI | Refactor layout, add CSS breakpoints, ensure touch-friendly controls | Frontend | Planned |
| Character service | DB models + endpoints for characters (create/list/update) tied to users | Backend | Planned |
| Invite flow w/ character assignment | Extend `/sessions/*` endpoints + UI to capture character + level | Full-stack | Planned |
| E2E automation | Playwright smoke test for login→session→invite | Infra | Planned |

## 7. Technical Decisions & Notes
- **State Storage** – Sessions currently file-based; will migrate to DB when collaboration features mature.
- **Image Agent** – Stubbed; will integrate once core UX solid.
- **Security** – Access tokens only; refresh tokens TBD (see todo list).
- **Documentation** – Update this file whenever scope or milestones change; treat as the source of truth for stakeholders.

## 8. Open Questions
1. Should session assets (notes/story/etc.) move to DB before multi-user editing? (Impacts collaboration.)
2. Preferred AI/image provider and cost constraints?
3. Do we need offline caching for mobile devices?

> Next update checklist: note responsive UI progress, capture character schema decisions, and record test automation status.
