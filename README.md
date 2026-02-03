# TavernTAIls — AI GM Web App

This project is a web application for solo tabletop RPG play, featuring an AI Game Master. It uses React (TypeScript) for the frontend and FastAPI (Python) for the backend. The app is designed to support agent-based AI modules for:

- Scene analysis (dice rolls)
- Scene image generation
- Campaign storyboard management
- Narrative generation
- Session note-taking
- NPC/enemy management

## Structure
- `client/` — React frontend
- `server/` — FastAPI backend

## Getting Started

### Frontend
```sh
cd client
npm start
```

The start script now runs a lightweight port guard to prevent hangs when another process already occupies port `3000`. If the guard reports the port is busy:

1. Stop any existing React dev server (look for `node.exe`/`node` processes or use `taskkill /F /IM node.exe`).
2. Run `npm run check-port` to confirm the port is free before retrying `npm start`.
3. You can temporarily override the guard via `set SKIP_PORT_GUARD=1` (cmd) or `$env:SKIP_PORT_GUARD='1'` (PowerShell), but freeing the port is preferred.

### Backend
```sh
cd server
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

**Notes for local development**
- The backend will automatically create a verified development user by default on startup: `test@example.com` / `secret`. You can override these with environment variables:

![CI](https://github.com/DegeneratesAnonymous/TavernTails/actions/workflows/ci.yml/badge.svg)
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
For more details, see `.github/copilot-instructions.md`.
