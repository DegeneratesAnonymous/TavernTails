# TavernTAIls MVP Delivery Checklist

_Source of truth: `PROJECT_PLAN.md` §13 (MVP Gate) and §12 Work Packages._

This checklist translates the MVP acceptance criteria into concrete implementation tasks tied to the current repo. Update the **Status** column as work completes.

| Capability (Plan Ref) | Acceptance Target | Current Implementation Snapshot | Status | Next Action |
| --- | --- | --- | --- | --- |
| Auth & Email Verify (WP#1) | `/player/signup`, verify token, `/player/login`, `/player/me` with JWT | Backend: `server/agents/player.py` + JWT via `server/auth.py` + dev seed user. Frontend: `client/src/agents/LoginSignupAgent.tsx` persists `access_token`, refreshes `/player/me`, and supports verify/resend token (dev token returned). | ✅ Backend + ✅ Frontend | Consider refresh tokens before multi-device; add basic auth E2E smoke (optional). |
| Campaign CRUD (WP#2) | Create/list/get/update/delete campaigns tied to owner; optionally auto-session per §7 | Backend: `server/agents/campaigns.py` + `campaign.metadata_json` stores session IDs. Frontend: `client/src/components/CampaignsMenu.tsx` lists/creates campaigns and can create sessions via `/campaigns/{id}/create_session`. | ✅ MVP | Decide whether Gameplay uses campaigns-first navigation (recommended) vs sessions-first; tighten acceptance tests accordingly. |
| Session Documents (WP#2/6) | Folder per session at `server/sessions/{id}` storing meta/notes/npcs/pcs/story; API for CRUD; **hidden doc RBAC + audited access (per Plan §13 MVP Gate)** | Backend: `server/agents/sessions.py` (FS session scaffold) + `server/agents/documents.py` (document store abstraction w/ local + S3 presign/register). Frontend: `client/src/components/DocumentsPanel.tsx` (in GameplayLayout drawer). | ✅ MVP | Optional: add a host-only UI for viewing `document_access.jsonl` and/or surface “hidden” category explicitly in the drawer. |
| Dice Stub (WP#4) | Deterministic roller endpoint + Beyond20 ingest + UI log | `/rolls` + `/integrations/beyond20/roll` implemented; chat panel now detects inline `NdM+K` entries, calls `/rolls`, and renders structured summaries. | ✅ MVP scope | Ensure Beyond20 domains UI surfaces roll history in future iterations. |
| Chat Surface (WP#7) | Text chat panel (persisted) with optional `!notes` helper; integrates with backend for MVP | REST router `server/agents/chat.py` + SQLModel table persist session messages; React chat component scopes to the active session, fetches history, posts via `/chat`, adds `!notes` recap (deterministic multi-note summary via `server/agents/notes.py`), and displays inline roll results. | ✅ MVP | Optional: upgrade recap quality (LLM) later; consider adding auth/membership checks to `/notes/log` when ready. |
| Agents Stubs (WP#5) | Narrative/Scene/NPC/Notes/Image endpoints return deterministic scaffolding responses with contract tests | Routers wired in `server/main.py`: `scene`, `npc`, `notes`, `storyboard`, `image`, `suggestions`, plus `/ws/sessions/{session_id}` events. Coverage exists broadly in `server/tests/*` (contract breadth can grow). | ✅ Stubs wired | Add explicit contract tests per agent payload shape + version them (snapshots) so UI doesn’t break on refactors. |
| Player‑Run Session Mode | AI can be disabled; notes/NPC index still available | Plan updated; no UI toggle or backend flag yet. | ⏳ Planned | Add campaign/session mode flag + UI control; ensure notes/NPC capture still runs. |
| start-app.ps1 (Plan §10) | Windows script terminates stray processes, boots backend/frontend, logs to `logs/` | Script present and documented in README; CI includes a Linux smoke that starts uvicorn + runs upload smoke. | ✅ Dev automation | Optional: add a Windows CI job later if desired; keep `start-app.ps1` as local dev convenience. |
| Documentation (Plan §11, §17.5) | README + plan describe setup, secrets, and dev workflow | README covers frontend/backend/dev stack, storage modes, and secret SOP in `docs/SECRET_MANAGEMENT.md`. Multiple plan docs exist (see note below). | ✅ Core docs | Consolidate “single source of truth” planning docs to reduce drift (recommended). |
| CI & Tests (WP#9) | GitHub Actions pipeline running lint/tests/build for backend/frontend | `.github/workflows/ci.yml` runs backend pytest, frontend tests/build, and an API smoke upload step. | ✅ In place | Optional: add lint/typecheck (mypy/ruff/eslint) as separate jobs once configs are finalized.

## Sequence to Complete MVP
1. **Stabilize Data Layer** — ✅ Alembic scaffold + migration `20251201_01` now ensure `campaign.metadata_json` and a `chatmessage` table exist; remaining DB work is wiring invites/friends into tables.
2. **Frontend Auth & Campaigns** — ✅ Login/signup + token persistence + campaigns UI are live.
3. **Session Interaction Loop** — 🔄 Chat + rolls + WS updates are live. Remaining MVP decision: keep `!notes` as stub (OK for MVP) vs upgrade Notes agent to persist/recap from chat log.
4. **Agent Scaffold & Tests** — expand contract tests per agent event (`scene.cues`, `npc.profile`, `suggestions.update`, `turns.update`) so UI changes are safe.
5. **Operational Hardening** — ✅ CI exists; remaining is doc consolidation (reduce plan drift) + scripted playthrough definition.

## Plan Hygiene Note
There are multiple overlapping planning docs in the repo (`PROJECT_PLAN*.md` and `TavernTAIls_Enhanced_Project_Plan.md`). Pick one as the single source of truth and add a short “THIS IS CANONICAL” banner to the others to prevent drift.

_Update this file as tasks progress to keep MVP tracking aligned with `PROJECT_PLAN.md`._
