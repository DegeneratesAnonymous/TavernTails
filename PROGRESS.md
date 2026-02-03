# TavernTAIls Progress Tracker
_Last updated: 2026-02-03 by GitHub Copilot_

## Where Things Stand
- **Sprint Focus:** Finish Sprint 1 deliverables (chat upgrades, turn queue, agent stubs, documentation).
- **Runtime:** `start-app.ps1` launches uvicorn (127.0.0.1:8000) + CRA dev server (localhost:3000).
- **Realtime:** `/ws/sessions/{sessionId}?token=<JWT>` now streams suggestions, turn updates, chat messages, and roll results.
- **UI State:** `GameplayLayout` renders drawer/banner/suggestions/player status + new turn tracker; `Chat` has invite/export/tools plus live feed + notes recap command.

## 2026-01 Status Note
- Planning docs drifted a bit: `MVP_DELIVERY_CHECKLIST.md` has been updated to reflect the current codebase; treat `PROJECT_PLAN.md` as canonical and keep this file as the implementation log.
- The biggest remaining “make it real” items are character CRUD/imports and a clearer campaign→session→play flow (hidden-doc RBAC + access auditing is implemented).

## Completed Recently
0. **Player‑Run Mode Toggle (Feb 3)**
   - Added a campaign settings toggle and skipped AI bootstrap when enabled.
0. **Player‑Run Mode Backend Guard (Feb 3)**
   - Added server-side guard to skip AI bootstrap and scene analysis when player-run mode is enabled; covered by new bootstrap test.
0. **Player‑Run Content Advance (Feb 3)**
   - Content advance now skips AI narration/suggestions when player-run mode is enabled; test added.
0. **Player‑Run Banner (Feb 3)**
   - Added a gameplay banner indicating player-run mode when enabled.
0. **Checklist Update: Player‑Run Session Mode (Feb 3)**
   - Added tracking row in MVP_DELIVERY_CHECKLIST.md for the new mode.
0. **Plan Update: Player‑Run Hub Positioning (Feb 3)**
   - Updated PROJECT_PLAN.md to position AI as optional and emphasize automated organization.
0. **Associated NPCs in Manage Characters (Feb 3)**
   - Added an Associated NPCs modal with campaign selection and player-facing NPC details.
0. **Character Update Ownership Test (Feb 3)**
   - Added pytest coverage to ensure non-owners cannot update characters.
0. **Character Update API Coverage (Feb 3)**
   - Added pytest coverage for PUT /characters/{id} owner updates.
0. **Character Delete Cleanup (Feb 3)**
   - Clearing the active session character when the selected character is deleted.
0. **Session Selection UX (Feb 3)**
   - Disabled the select button when a character is already assigned to the active session.
0. **Import Character Navigation (Feb 3)**
   - Added a Back to Play action when importing with an active session.
0. **Manage Characters Session Label (Feb 3)**
   - Displayed the active session name in the character management header when available.
0. **Session Character Clear Action (Feb 3)**
   - Added a quick action in Manage Characters to clear the active session character.
0. **Character Sheet Quick Edit (Feb 3)**
   - Enabled editing name/level/class and parsed fields directly from the character sheet modal.
0. **Gameplay Character Selector (Feb 3)**
   - Added a simple selector in the Character tab to switch active characters during play.
0. **Gameplay Character Empty-State Actions (Feb 3)**
   - Added direct actions to Manage/Import Characters when the player sheet has no roster yet.
0. **Character Import Polish + PDF Summaries (Feb 1)**
   - Added PDF extraction summaries to import review and character sheet views.
   - Improved import review flow (preview, conflict handling, and post-import navigation).
   - Backend PDF parsing now surfaces widget-derived stats/HP/AC/features for UI use.
0. **Best Practices Guardrails + Retro Audit Seed (Jan 30)**
   - Added `docs/BEST_PRACTICES.md` and work order `docs/work-orders/WO-005-best-practices-retro-audit.md`.
   - Hardened PDF upload error messaging to detect a missing backend endpoint (405) and give actionable guidance.
0. **WP#3 Characters E2E Slice + Local CI Runner (Jan 11)**
   - Gameplay toolbar now supports creating a character and auto-assigning it to the active session member.
   - Added `./ci.ps1` Windows-safe runner to execute backend + frontend CI-equivalent checks reliably in paths containing `&`.
   - Added `/characters` API ownership/isolation coverage in `server/tests/test_characters_api.py`.
1. **Suggestion + Turn Queue Stream (Dec 3-4)**
   - Added `server/realtime.py` broadcaster, `/suggestions` endpoint, `/turns` API, websocket router, and React polling/WS consumers.
2. **Chat Live Feed & Notes (Dec 4)**
   - `/chat` POST now broadcasts; `/rolls` emits events when `session_id` is present.
   - `Chat.tsx` listens on the session socket, dedupes entries, requests turn-based notes via `/notes/log`, and includes roll/system messages.
3. **Sprint-1 UI Items**
   - Command drawer, rotating banner, suggestion rail, player capsule, and turn tracker all implemented per Plan §18.
4. **Session Documents + DB Guard (Dec 4)**
   - Introduced `server/agents/documents.py` with list/create/delete endpoints backed by the new `DocumentStore` abstraction plus coverage in `server/tests/test_documents.py`.
   - Hardened `server/main.py` startup so DB seeding occurs even when tests swap the SQLModel engine, ensuring dev-logins succeed consistently.
5. **Beyond20 Socket Flow (Dec 4)**
   - Normalized `/integrations/beyond20/roll` payloads so remote totals + dice are preserved, persisted, and broadcast as `rolls.result` + `beyond20.roll` websocket events; covered by `server/tests/test_rolls.py`.
   - `GameplayLayout` now surfaces a transient Beyond20 pill + waiting indicator, while `Chat` labels websocket rolls with mentions and dispatches waiting hints.
6. **Mention-driven Waiting Indicator (Dec 4)**
   - `Chat.tsx` forwards mention metadata from websocket payloads and emits `session:waiting` events; `GameplayLayout` applies timed overrides so mention pings don’t clobber the turn tracker.
7. **Session Docs UI (Dec 4)**
   - Added `/documents/{session}/{doc}` detail endpoint plus storage read helpers; frontend sidebar now includes a `DocumentsPanel` for listing, previewing, creating, and deleting shared notes.
8. **Scene & NPC Agent Streams (Dec 4)**
   - `/scene/analyze` and `/npc/manage` accept `session_id` and broadcast `scene.cues` / `npc.profile` Ws events; `Chat` tools now capture context and prompt for NPC data, while `CharacterPanel` surfaces live cues.
9. **S3-backed Document Uploads (Dec 5)**
   - `TAVERNTAILS_STORAGE_MODE=s3` now swaps in `S3DocumentStore`, `/documents/{session}/presign` + `/register` enable direct browser uploads, and `/documents/{session}/upload` remains available for local/dev mode.
   - Moto-based regression coverage in `server/tests/test_presign_register.py` keeps CI green without hitting AWS while `server/tests/test_uploads.py` continues to exercise the filesystem path.
10. **Adventure Loader Guard + Upload Smoke Test (Dec 5)**
   - Hardened `client/src/components/NarrativeView.tsx` so `choices` defaults to an empty array, preventing `Cannot read properties of undefined (reading 'map')` when campaign files omit options.
   - Added `server/tools/smoke_upload.py` to automate session creation + `/documents/{session}/upload` verification against a running dev stack; handy for quick health checks during handoffs.
11. **Scene Cue Roll Triggers (Dec 6)**
   - `GameplayLayout` now stores structured `SceneCue` objects with dice recommendations from `/scene/analyze` broadcasts and passes them into `CharacterPanel`.
   - Each cue renders a contextual “Roll” button that calls `/rolls` with session context, closes the loop between scene analysis hints and logged dice results.
12. **NPC Persistence (Dec 6)**
   - `server/agents/npc.py` now persists NPC profiles into the session folder (`sessions/<session_id>/npcs.json`) when `/npc/manage` is called with a `session_id`. The endpoint still broadcasts a `npc.profile` event.
13. **Secret Management SOP (Dec 8)**
   - Added `docs/SECRET_MANAGEMENT.md` detailing secret inventory, rotation cadence, and runbooks for JWT, AWS, DB, and provider tokens.
   - README now links to the SOP so new contributors know how to handle `.env` files, GitHub secrets, and calendar reminders.

## Immediate Next Steps (suggested order)
1. **Player‑Run Mode switch** – add a campaign/session flag to disable AI outputs while keeping notes/NPC tracking active.
2. **Documents UI polish** – add upload retries/cancel flows, inline thumbnail previews, and clearer failure messaging for presigned uploads.
3. **Scene/NPC automation follow‑through** – connect cues to real dice triggers + NPC tracking data persisted per session.
4. **CI coverage expansion** – extend GitHub Actions to lint/type-check the React app and pin/test boto3+moto compatibility for presign coverage.
5. **LLM Agent Hardening** – capture structured prompts/results in storage ahead of multiplayer testing.

## S3 & Direct Upload Configuration
1. **Prereqs:** Keep `boto3`/`moto` from `server/requirements.txt` installed and provision an S3 bucket with `Put/Get/Delete` rights.
2. **Env vars:**
   - `TAVERNTAILS_STORAGE_MODE=s3`
   - `TAVERNTAILS_S3_BUCKET=<bucket>`
   - Optional `TAVERNTAILS_S3_PREFIX=env/dev` for namespacing.
3. **AWS credentials:** Export `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optionally `AWS_REGION`, or use a configured profile.
4. **Server restart:** Bounce uvicorn so `server.storage.documents.get_document_store()` rebuilds and log output confirms S3 mode.
5. **Frontend flow:** `DocumentsPanel` first calls `/documents/{session}/presign`; on success it posts directly to S3 then hits `/register`. Failures or local mode fall back to `/documents/{session}/upload`.
6. **Smoke tests:** `venv\Scripts\python.exe -m pytest server/tests/test_uploads.py server/tests/test_presign_register.py -q` covers both storage paths without touching AWS.

## Validation Log
| Date (UTC) | Command |
| --- | --- |
| 2025-12-04 | `$env:PYTHONDONTWRITEBYTECODE=1; venv\Scripts\python.exe -m pytest server/tests/test_chat.py server/tests/test_agents.py server/tests/test_turns.py -q` |
| 2025-12-04 | `$env:PYTHONDONTWRITEBYTECODE=1; venv\Scripts\python.exe -m pytest server/tests/test_chat.py -q` (spot-check) |
| 2025-12-04 | `npm run build` (client) |
| 2025-12-04 | `$env:PYTHONDONTWRITEBYTECODE=1; venv\Scripts\python.exe -m pytest server/tests` |
| 2025-12-04 | `$env:PYTHONDONTWRITEBYTECODE=1; venv\Scripts\python.exe -m pytest server/tests` (post Beyond20 & mentions) |
| 2025-12-04 | `$env:PYTHONDONTWRITEBYTECODE=1; venv\Scripts\python.exe -m pytest server/tests` (docs UI + scene/NPC streams) |
| 2025-12-04 | `npm run build` (client) |
| 2025-12-05 | `venv\Scripts\python.exe -m pytest server/tests -q` |
| 2025-12-05 | `npm run build` (client) |
| 2025-12-05 | `$env:PYTHONPATH='C:\\Users\\colem\\OneDrive\\solottrpg'; venv\Scripts\python.exe server/tools/smoke_upload.py` |
| 2025-12-06 | `npm run build` (client) |
| 2026-02-01 | `venv\Scripts\python.exe -m pytest server/tests -q` |
| 2026-02-03 | `python -m pytest server/tests/test_campaign_settings.py -q` |
| 2026-02-03 | `python -m pytest server/tests/test_characters_api.py -q` |
| 2026-02-03 | `python -m pytest server/tests/test_session_bootstrap.py -q` |
| 2026-02-03 | `python -m pytest server/tests/test_session_bootstrap.py -q` (player-run content advance) |
| 2026-02-03 | `npm_config_script_shell=/bin/bash npm test -- --watchAll=false` (client) |

## How To Resume
1. **Activate env:** `& .\venv\Scripts\Activate.ps1` at repo root.
2. **Start stack:** `./start-app.ps1` (writes logs to `logs/` & `client/npm-*.log`).
3. **Connect client:** Visit `http://localhost:3000`, log in with `test@example.com / secret` (dev user ensured at startup).
4. **Join session:** Create or open a session, then connect UI panels:
   - Suggestions refresh automatically (and via websocket).
   - Turn tracker updates through `/turns` endpoints or future UI controls.
   - Chat reflects invites, notes recap (`!notes`), dice rolls, and websocket-fed updates.
5. **Pick up next Sprint task:** Start with the “Immediate Next Steps” list above.
6. **Run tests:** From repo root run `venv\Scripts\python.exe -m pytest server/tests` (PowerShell inherits the venv path), especially if `pytest` isn’t on PATH.
