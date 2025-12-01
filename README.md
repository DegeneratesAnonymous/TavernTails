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
 	- `TAVERNTAILS_SEED_DEV_USER=0` to disable seeding.
 	- `TAVERNTAILS_DEV_EMAIL`, `TAVERNTAILS_DEV_PASSWORD`, `TAVERNTAILS_DEV_USERNAME` to customize the seeded account.
- When running the React dev server it may pick an alternate port (e.g. 3001/3002). The frontend detects `localhost` and maps requests to the backend on port `8000` by default so you shouldn't need to set `REACT_APP_API_URL`. To explicitly configure the API, set `REACT_APP_API_URL` to your backend URL before starting the frontend.

**Quick start (Windows PowerShell)**
```powershell
cd server
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
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

## Next Steps
- Implement agent modules for each feature
- Connect frontend and backend
- Add authentication and session management
- Enhance UI/UX for immersive play

---
For more details, see `.github/copilot-instructions.md`.
