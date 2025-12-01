**TavernTAIls — Work Package Breakdown**

Purpose: Break the high-level `PROJECT_PLAN.md` into actionable work packages that can be assigned to individuals or small teams. Each package lists scope, deliverables, API/DB touchpoints, acceptance criteria, rough estimate, dependencies, and risks.

How to use this file:
- Assign owners to packages and move the package to your sprint board.
- Use the acceptance criteria to verify completion.
- Update estimates and dependencies as work progresses.

Work packages
----------------

1) Core Platform — Auth, Users, Friends, and Accounts
- Scope:
  - Implement robust JWT auth, refresh tokens (optional), user profiles, and friend relationships.
  - User settings (email, display name, DnD Beyond token storage opt-in).
- Deliverables:
  - DB: `users`, `friends` tables and migrations.
  - Endpoints: `POST /player/signup`, `POST /player/login`, `GET /player/me`, `POST /player/friends`, `GET /player/friends`.
  - Tests: unit tests for signup/login, integration tests for friend invites/acceptance.
- Acceptance:
  - Sign up, email verification (dev-mode token), login, and friend add/accept flows pass e2e.
  - Proper role checks for host vs player.
- Est: 3–5 days
 - Dependencies: DB migrations, `server/auth.py` updates.
 - Risks: OAuth integration complexity for DnD Beyond.

2) Campaigns & Sessions (Campaign CRUD + membership)
- Scope:
  - Campaign creation, list, update, archive.
  - Session management within a campaign: create session, save/load documents, invite flow with required level, membership enforcement.
- Deliverables:
  - DB: `campaigns`, `sessions`, `invites`, `documents` metadata.
  - Endpoints: `POST /campaigns`, `GET /campaigns`, `POST /campaigns/{id}/invite`, `WS /campaigns/{id}/ws`.
  - UI: Campaigns menu, session creation modal (choose flavor/core/hidden docs), invite UI that allows requiring character level.
- Acceptance:
  - Host creates campaign and session, invites player specifying minimum level, invited player accepts by selecting a character.
  - Membership checks enforce session file access and hidden document visibility.
- Est: 1–2 weeks
 - Dependencies: Core Platform, Character service, Session Documents storage.
 - Risks: Access control bugs exposing hidden docs.

3) Character Service & Import Pipeline
- Scope:
  - Character CRUD for user-scoped characters, import from DnD Beyond (short-term: user-export; long-term: token-based sync), PDF parsing (PyMuPDF + heuristics).
- Deliverables:
  - DB: `characters` table (owner_id, name, level, attributes JSON, skills, spells, items JSON).
  - Endpoints: `POST /characters` (create/import), `GET /characters` (user), `PUT /characters/{id}`.
  - Tools: `server/tools/character_import.py` prototype and unit tests for parsing heuristics.
- Acceptance:
  - User can create character manually and import a sample DnD Beyond export or PDF; data maps to fields and appears in UI.
  - Character changes reflected via API within expected sync window (if DnD Beyond token sync enabled).
- Est: 1–3 weeks (PDF heuristics increase effort)
 - Dependencies: Core Platform (user auth), Campaigns/Invites.
 - Risks: PDF parsing accuracy; legal/ToS concerns around DnD Beyond scraping.

4) Dice Engine (PencilPusher) & Beyond20 Ingest
- Scope:
  - Implement deterministic dice roll engine with modifiers and a roll history.
  - Endpoint for ingestion of Beyond20 roll events: `/integrations/beyond20/roll`.
- Deliverables:
  - Endpoint: `POST /rolls` (local), `POST /integrations/beyond20/roll` (external), `GET /rolls/{session}`.
  - Backend resolver that maps Beyond20 payload to player & session and calls the same resolve path.
  - Frontend roll UI & integration with player menu shortcuts.
- Acceptance:
  - Rolls performed in-app (with modifier application) and Beyond20 POSTs map to the same result pipeline.
  - Roll history flushes to session log and can be replayed.
- Est: 3–5 days
 - Dependencies: Character Service (modifiers), Campaign Sessions, WebSocket updates.
 - Risks: Browser->server forwarding pattern for Beyond20; users must configure bridge; CORS issues.

5) Agents: Narrative, Writer, Narrator, Scene, Scribe, NPC Manager, Storyboard
- Scope:
  - Create modular agent interfaces and minimal implementations (stubs) for each agent to iterate on behavior.
  - Define I/O contracts and example JSON payloads.
- Deliverables:
  - `server/agents/{name}.py` routers for each agent exposing REST hooks.
  - Worker pattern for long-running LLM calls (job queue + results persistence).
  - GM Agent that composes outputs and validates them.
- Acceptance:
  - Agents can be invoked with a state snapshot and return structured output (narration, roll_request, scene_update).
  - GM Agent receives agent outputs, validates and publishes through WebSocket to clients.
- Est: 2–4 weeks for solid MVP stubs and orchestration
 - Dependencies: Worker queue, LLM keys, persistence.
 - Risks: Cost of LLM calls; unpredictability in outputs requiring safety/validation.

6) Session Documents (Core / Flavor / Hidden)
- Scope:
  - Document upload/download UI, tagging (core/flavor/hidden), permissions enforcement, versioning for Core docs.
- Deliverables:
  - Storage layout: `/data/campaigns/{id}/documents/` with metadata in DB.
  - Endpoints: `POST /campaigns/{id}/documents`, `GET /campaigns/{id}/documents`, `GET /documents/{id}`.
  - DM Helper UI to view hidden docs and perform admin actions.
- Acceptance:
  - Uploads stored and retrievable; hidden docs are not visible to non-hosts via API or UI.
  - Document version and uploader metadata are present and retrievable.
- Est: 1–2 weeks
 - Dependencies: Campaigns & Sessions, Auth
 - Risks: Large file storage, migrations to S3 later.

7) Chat, Turn Queue & Notifications
- Scope:
  - Persistent chat per session with message history, player menu, and optional email/push notifications.
  - Implement asynchronous play features: turn queue, notifications (email/poke), mention/poke.
- Deliverables:
  - DB: `messages` table, `notifications` queue table.
  - Endpoints: `POST /campaigns/{id}/messages`, `GET /campaigns/{id}/messages`, WebSocket channel.
  - Notification worker to send emails or store push notifications.
- Acceptance:
  - Chat persists, shows order, and sends a notification when a player is pinged.
  - Turn queue indicates whose turn it is and allows passing.
- Est: 1–2 weeks
 - Dependencies: WebSocket infra, email provider or local SMTP dev config.
 - Risks: Spam/abuse; need rate-limiting.

8) Image Agent & Illustration Styles
- Scope:
  - Image generation adapter layer with style presets (8-bit, cartoon, pencil, classic). Provide safe defaults and caching.
- Deliverables:
  - Adapter pattern with `ImageProvider` interface, local caching, style presets endpoint `POST /images/generate`.
  - UI to request images and attach to session documents.
- Acceptance:
  - Player can request an image with a style and receive an image URL after generation.
  - Generation events are queued and non-blocking to the main request thread.
- Est: 1–2 weeks for adapter + queue; extra time for provider tuning.
 - Dependencies: LLM or image provider keys, worker queue.
 - Risks: Costs and content policy safety.

9) PDF Import & Character Parsing (prototype)
- Scope:
  - Extract text via `PyMuPDF` or `pdfminer.six` and map fields into `characters` schema using heuristics.
- Deliverables:
  - `server/tools/pdf_import.py` with tests and sample PDFs.
  - UI flow for uploading a PDF and mapping parsed fields.
- Acceptance:
  - Example PDFs map correctly to name, level, ability scores, and simple equipment lists.
- Est: 1–3 weeks (depends on PDF variety)
 - Dependencies: Character service, storage
 - Risks: Poor accuracy; may require ML-based extraction later.

10) Testing, CI, and E2E
- Scope:
  - Unit tests, integration tests, and E2E tests with Playwright/Cypress. GitHub Actions pipeline to run tests and build.
- Deliverables:
  - Test coverage for backend routers and critical frontend flows.
  - GitHub Actions workflows to run tests on PRs and deploy preview builds.
- Acceptance:
  - CI runs on PRs and fails on regressions; smoke E2E exists for signup→login→create campaign→invite.
- Est: 1–2 weeks to establish baseline pipeline
 - Dependencies: Test fixtures, seeded DB, dev infra for Playwright.
 - Risks: E2E flakiness; maintain tests as product evolves.

Appendix: Example API & DB mappings (short)
- DB tables (minimum): `users`, `friends`, `campaigns`, `sessions`, `documents`, `characters`, `messages`, `invites`, `rolls`, `agent_events`.
- Example endpoints (grouped):
  - Auth: `POST /player/signup`, `POST /player/login`, `GET /player/me`
  - Campaigns: `POST /campaigns`, `GET /campaigns`, `POST /campaigns/{id}/invite`
  - Characters: `POST /characters`, `GET /characters`, `PUT /characters/{id}`
  - Rolls: `POST /rolls`, `POST /integrations/beyond20/roll`
  - Documents: `POST /campaigns/{id}/documents`, `GET /campaigns/{id}/documents`

Owner assignment template
- For each package, set:
  - Owner: (name)
  - Sprint target: (dates)
  - Acceptance criteria: (copy from package)
  - Blockers: (list)

Next steps
- Review packages and assign owners/estimates.
- Create GitHub issues per package with the acceptance text copied into the issue body.
- Begin work on `Core Platform` and `Campaigns & Sessions` in the next sprint.

---
This document is actionable and intended to be used alongside `PROJECT_PLAN.md`. Update as work is subdivided further.
