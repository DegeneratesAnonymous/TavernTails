# TavernTAIls — AI GM Web App

![CI](https://github.com/DegeneratesAnonymous/TavernTails/actions/workflows/ci.yml/badge.svg)
![Staging](https://github.com/DegeneratesAnonymous/TavernTails/actions/workflows/deploy-staging.yml/badge.svg)

## What is TavernTAIls?

**TavernTAIls** is a web-based AI Game Master companion for tabletop RPGs. It is designed for solo players, small async groups, and GM-builders who want a persistent, organized play environment — with or without AI narration.

When you open TavernTAIls you get a full campaign hub: create characters, spin up campaigns, upload session documents, invite friends, and then actually play — all from your browser. During a session the app keeps a live chat log, handles inline dice rolls (type `1d20+3` right in the chat), displays an AI-generated scene image, and surfaces your character sheet and journal without switching tabs.

**AI is additive, not required.** A group can run their own session while TavernTAIls automatically organizes notes, tracks NPCs, and logs every roll. When AI is enabled a suite of cooperating agents handles narration, scene analysis, NPC profiles, storyboard continuity, session recaps, and scene imagery.

### Who is it for?

| Persona | How they use TavernTAIls |
|---|---|
| **Solo Adventurer** | Guided journaling + AI narration for one player |
| **Async Party** | 2–4 friends across time zones; persistent chat & session logs keep everyone in sync |
| **GM-Builder** | Hosts who customize prompts, upload documents, and manage NPCs without running everything manually |
| **Group DM** | A player-run table that wants automated notes and NPC tracking without AI narration |

### The AI agents (background)

Behind the scenes, six AI agents collaborate to run a session:

| Agent | What it does |
|---|---|
| **Narrative** | Drives gameplay, generates scene narration, manages turn order |
| **Scene Analysis** | Detects when dice rolls are needed, enforces rules, prompts for player actions |
| **NPC / Enemy Manager** | Profiles NPCs and enemies, tracks stats, motivations, and initiative |
| **Storyboard** | Tracks campaign progress, scene branching paths, and unresolved threads |
| **Notes** | Logs session notes and recaps; responds to `!notes` in chat |
| **Image Generation** | Creates AI-generated scene images for immersion |

---

## How It Works — User Flow

Here is the typical journey from first visit to active play:

1. **Landing page** → Read what the app does; click **Sign In** or **Create Account**.
2. **Sign up / Login** → Create a free account with email and password, or use the dev shortcut locally.
3. **Dashboard** → Your home base after login. Pick an action: start a new game, load a saved campaign, manage characters, configure campaigns, explore world lore, or read guides.
4. **Characters** → Create your character from scratch or import one from a JSON export / D&D Beyond link. Characters travel with you across campaigns.
5. **Campaigns** → Create and manage campaigns. Each campaign stores its own players, uploaded documents, NPC index, and session history.
6. **Campaign Settings** → As a host, configure who can join, attach reference documents, and set AI options.
7. **Gameplay / Session View** → The main play screen. The left panel shows the current scene image and scene title. The right panel gives you **Chat** (messages + dice rolls), **Character** (your sheet), and **Journal** (session notes). Type a message or roll dice inline, then press Send.

---

## App Pages

Full per-page documentation — including an auto-updated screenshot for every screen — lives in the **[project wiki](https://github.com/DegeneratesAnonymous/TavernTails/wiki)**:

| Page | Wiki link |
|---|---|
| Landing | [Page-Landing](https://github.com/DegeneratesAnonymous/TavernTails/wiki/Page-Landing) |
| Login | [Page-Login](https://github.com/DegeneratesAnonymous/TavernTails/wiki/Page-Login) |
| Sign Up | [Page-Sign-Up](https://github.com/DegeneratesAnonymous/TavernTails/wiki/Page-Sign-Up) |
| Dashboard | [Page-Dashboard](https://github.com/DegeneratesAnonymous/TavernTails/wiki/Page-Dashboard) |
| Characters | [Page-Characters](https://github.com/DegeneratesAnonymous/TavernTails/wiki/Page-Characters) |
| Import Character | [Page-Import-Character](https://github.com/DegeneratesAnonymous/TavernTails/wiki/Page-Import-Character) |
| Manage Campaigns | [Page-Manage-Campaigns](https://github.com/DegeneratesAnonymous/TavernTails/wiki/Page-Manage-Campaigns) |
| New Campaign | [Page-New-Campaign](https://github.com/DegeneratesAnonymous/TavernTails/wiki/Page-New-Campaign) |
| Campaign Settings | [Page-Campaign-Settings](https://github.com/DegeneratesAnonymous/TavernTails/wiki/Page-Campaign-Settings) |
| Gameplay / Session View | [Page-Gameplay](https://github.com/DegeneratesAnonymous/TavernTails/wiki/Page-Gameplay) |

> Screenshots are auto-updated on every merge to `main` by the
> [screenshot-update](.github/workflows/screenshot-update.yml) workflow, which
> also regenerates the wiki pages.

---

## Getting Started

### Live staging / preview (Docker)

Every merge to `main` or `develop` automatically builds a Docker image and
pushes it to GitHub Container Registry. You can pull and run it anywhere:

```bash
# Run the latest main-branch build
docker run -d \
  --name taverntails-staging \
  -p 8000:8000 \
  -v taverntails_data:/app/data \
  -e TAVERNTAILS_SECRET="change-me" \
  ghcr.io/degeneratesanonymous/taverntails:latest
# → open http://localhost:8000  (login: test@example.com / secret)
```

Or use Docker Compose (builds from source):

```bash
export TAVERNTAILS_SECRET="change-me"
docker compose up --build
```

For full instructions — including how to enable automatic SSH re-deploys to a
staging server — see **[docs/STAGING.md](docs/STAGING.md)**.

### Quick Start (Recommended)

**One command to start both backend and frontend:**

```bash
# Windows (PowerShell)
.\start-app.ps1

# macOS/Linux (Bash)
./start-app.sh
```

This will start both the backend API server and the frontend development server. Press Enter (Windows) or Ctrl+C (macOS/Linux) to stop both services.

**First time setup:**
```bash
# Set up backend
python -m venv venv
# Windows:
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate
pip install -r server/requirements.txt

# Set up frontend
cd client
npm install
cd ..

# Copy environment files
# Windows:
copy server\.env.example server\.env
# macOS/Linux:
cp server/.env.example server/.env
```

**📚 For detailed setup instructions, troubleshooting, and development workflows, see [docs/LOCAL_DEV.md](docs/LOCAL_DEV.md)**

### Alternative: Manual Start

#### Frontend
```sh
cd client
npm start
```

The start script now runs a lightweight port guard to prevent hangs when another process already occupies port `3000`. If the guard reports the port is busy:

1. Stop any existing React dev server (look for `node.exe`/`node` processes or use `taskkill /F /IM node.exe`).
2. Run `npm run check-port` to confirm the port is free before retrying `npm start`.
3. You can temporarily override the guard via `set SKIP_PORT_GUARD=1` (cmd) or `$env:SKIP_PORT_GUARD='1'` (PowerShell), but freeing the port is preferred.

#### Backend
```sh
cd server
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

**Notes for local development**
- The backend will automatically create a verified development user by default on startup: `test@example.com` / `secret`. You can override these with environment variables:
 	- `TAVERNTAILS_SEED_DEV_USER=0` to disable seeding.
 	- `TAVERNTAILS_DEV_EMAIL`, `TAVERNTAILS_DEV_PASSWORD`, `TAVERNTAILS_DEV_USERNAME` to customize the seeded account.
- When running the React dev server it may pick an alternate port (e.g. 3001/3002). The frontend detects `localhost` and maps requests to the backend on port `8000` by default so you shouldn't need to set `REACT_APP_API_URL`. To explicitly configure the API, set `REACT_APP_API_URL` to your backend URL before starting the frontend.

### Document Storage Modes (Local vs S3)
- **Local (default):** `TAVERNTAILS_STORAGE_MODE` omitted or set to `local`. Files land under `server/sessions/<sessionId>/docs/` and are returned by `/documents/{session}/{doc}/raw`.
- **S3-backed uploads:**
	1. Create or reuse an S3 bucket and give your AWS credentials `s3:PutObject`, `s3:GetObject`, and `s3:DeleteObject` on the bucket/prefix.
	2. Set the following environment variables before launching uvicorn:
		 - `TAVERNTAILS_STORAGE_MODE=s3`
		 - `TAVERNTAILS_S3_BUCKET=<your-bucket-name>`
		 - (Optional) `TAVERNTAILS_S3_PREFIX=env/dev` to namespace keys.
	3. Export AWS credentials in the usual way (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optionally `AWS_REGION`). Temporary creds or profiles via `aws configure` also work.
	4. Restart the backend so `server.storage.documents.get_document_store()` rebuilds with the S3 client.

When the API reports S3 mode, the React `DocumentsPanel` automatically requests a presigned POST via `/documents/{sessionId}/presign` and uploads directly to S3 before calling `/documents/{sessionId}/register`. If presign fails or the store is local, the panel falls back to streaming the file through `/documents/{sessionId}/upload`.

**Validation:**
```powershell
cd server
..
venv\Scripts\python.exe -m pytest server/tests/test_uploads.py server/tests/test_presign_register.py -q
```
The first test covers local `/upload`, and the second uses Moto to exercise the presign/register flow without hitting AWS.

**Quick start (Windows PowerShell)**
```powershell
cd server
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..
alembic upgrade head
cd server
python -m uvicorn server.main:app --reload

cd ..\client
npm start
```

If you encounter "Port 3000 in use" errors during the quick start, run:

```powershell
cd client
npm run check-port
```

The command prints the port status so you can free it before starting the dev server again.

## Tech Stack (for contributors)

| Layer | Technology |
|---|---|
| **Frontend** | React 18 + TypeScript (Create React App), CSS modules |
| **Backend** | Python 3.11 + FastAPI + SQLModel (SQLAlchemy) |
| **Database** | SQLite in development → PostgreSQL in production |
| **Migrations** | Alembic |
| **Auth** | JWT tokens |
| **Real-time** | WebSockets (FastAPI) |
| **Storage** | Local filesystem (default) or S3-compatible object store |
| **Testing** | Jest + React Testing Library (frontend); pytest + TestClient (backend) |
| **Linting** | ESLint (frontend); Ruff + mypy (backend) |

The `client/` directory is the React SPA and `server/` is the FastAPI application. See `PROJECT_PLAN.md` for the full architecture reference.

## Dev Automation & Tasks
- Run `start-app.ps1` from the repo root (or the **Start Dev Stack** VS Code task) to kill stray processes, boot uvicorn on port 8000, and start the CRA dev server with logs under `logs/` and `client/`.
- Individual VS Code tasks exist for "Start Backend (uvicorn dev)" and "Start Frontend (npm start)" if you prefer separate terminals; see `.vscode/tasks.json`.
- Logs land in `logs/backend-*.log` for the API and `client/npm-*.log` for the React dev server so you can tail failures quickly.

## Security & Secret Management
- All sensitive environment variables (JWT secret, DB URLs, AWS credentials, AI provider tokens, etc.) follow the rotation playbooks documented in `docs/SECRET_MANAGEMENT.md`.
- Never commit `.env` files or plaintext secrets. Use your password manager or the deployment platform’s secret store when sharing credentials.
- GitHub Actions secrets must be set via the repository settings UI; workflows should only reference secret names.

## MVP Tracking
- The current MVP acceptance criteria (Project Plan §13) are broken down in `MVP_DELIVERY_CHECKLIST.md`; each row links requirements to concrete code/artifacts.
- Update both the Project Plan and the checklist whenever scope shifts so contributors can align on what "MVP complete" means before Phase 1 work begins.
- Chat + Dice loop: `/chat` endpoints persist session messages, and the React chat panel now scopes to the active session, supports `!notes` stub responses, and offloads inline `1d20+3` style rolls to `/rolls` for deterministic logging.

## Next Steps
- Polish documents UI (upload retries/cancel, clearer failure messaging)
- Extend character lifecycle (import polish, edit/merge, session assignment UX)
- Harden agent stubs with contract tests + event persistence
- Expand CI with lint/typecheck + minimal E2E smoke

---

**New here?** The best places to continue reading are:
- `PROJECT_PLAN.md` — full architecture, roadmap, and product vision
- `AGENTS.md` — how the six AI agents are designed to cooperate during a session
- `docs/LOCAL_DEV.md` — detailed local development setup and troubleshooting
- `docs/CONTRIBUTING.md` — how to contribute to the project
