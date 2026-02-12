# TavernTAIls — GitHub Copilot Instructions

This file provides context for GitHub Copilot and AI coding assistants working on TavernTAIls.

## Project Overview

**TavernTAIls** is an AI-assisted solo/co-op tabletop RPG companion that assembles a "Session AI" of cooperating agents (Narrative, Scene, NPC, Notes, Storyboard, Image) to run persistent campaigns. The application supports both AI-assisted gameplay and player-run sessions where AI is optional but automated organization (notes, NPC tracking, documents) remains available.

**Key Features:**
- Agent-optional gameplay (AI assists but doesn't control)
- Session-centric UX with persistent campaigns, characters, documents, chat, and rolls
- Automated organization with session notes, NPC index, and content tagging
- Player identity with account management, invites, and character import
- Real-time WebSocket updates for multi-player sessions

## Tech Stack

### Frontend
- **Framework:** React 18 with Create React App (CRA)
- **Language:** TypeScript (strict mode)
- **State Management:** React hooks + Context API
- **API Client:** Custom `apiFetch` utility with JWT auth
- **Real-time:** WebSocket client for session updates
- **Styling:** CSS modules, responsive design
- **Build Tool:** react-scripts (webpack under the hood)
- **Testing:** Jest + React Testing Library

### Backend
- **Framework:** FastAPI (Python 3.11+)
- **ORM:** SQLModel (SQLAlchemy core)
- **Database:** SQLite (dev) → PostgreSQL (production)
- **Migrations:** Alembic
- **Auth:** JWT tokens via `server/auth.py`
- **Real-time:** WebSockets with FastAPI
- **Storage:** Local filesystem + S3-compatible object store (abstracted)
- **Testing:** pytest with TestClient
- **Linting:** Ruff (replaces flake8/black)
- **Type Checking:** mypy (gradually typed)

## Architecture

```
[React SPA] --REST/WS--> [FastAPI Gateway]
                          ├── Agent Routers (narrative, scene, npc, etc.)
                          ├── Service Layer (campaigns, characters, invites)
                          ├── Persistence (SQLModel/DB + filesystem sessions)
                          └── Background Workers (future: LLM/image jobs)
```

### Directory Structure

```
TavernTAIls/
├── .github/
│   ├── copilot-instructions.md    # This file
│   └── workflows/ci.yml           # CI/CD pipeline
├── client/                        # React frontend
│   ├── public/                    # Static assets
│   ├── src/
│   │   ├── agents/                # Agent-specific React components
│   │   ├── components/            # UI components
│   │   ├── lib/                   # Utilities (apiFetch, etc.)
│   │   └── App.tsx               # Main app component
│   ├── package.json
│   └── tsconfig.json
├── server/                        # FastAPI backend
│   ├── agents/                    # Agent routers (narrative, scene, etc.)
│   ├── storage/                   # Document/session storage
│   ├── tests/                     # pytest test suite
│   ├── auth.py                    # JWT authentication
│   ├── db.py                      # Database models
│   ├── main.py                    # FastAPI app + router registration
│   └── requirements.txt
├── docs/                          # Documentation
│   ├── CI_CHECKLIST.md           # Quality gates
│   ├── DEV_AGENTS.md             # Development workflow
│   └── dev-agents/               # Role-based agent prompts
├── PROJECT_PLAN.md               # Canonical architecture & roadmap
├── MVP_DELIVERY_CHECKLIST.md     # MVP acceptance tracking
├── PROGRESS.md                   # Execution log
├── AGENTS.md                     # Gameplay agent architecture
├── README.md                     # Setup & getting started
└── alembic.ini                   # Database migration config
```

## Development Workflow

### Default Workflow
- Prefer **small, PR-sized changes** with tests
- Use **canonical docs** when making decisions:
  - `PROJECT_PLAN.md` — Architecture & roadmap (single source of truth)
  - `MVP_DELIVERY_CHECKLIST.md` — MVP acceptance criteria
  - `PROGRESS.md` — Execution log
  - `docs/CI_CHECKLIST.md` — Quality gates

### Development "Agents"
We use role-based development agents (PM/Backend/Frontend/QA/Reviewer) as a workflow model:
- **Playbook:** `docs/DEV_AGENTS.md`
- **Work orders:** `docs/WORK_ORDER_TEMPLATE.md`
- **Role prompts:** `docs/dev-agents/*.md`

### Definition of Done
- ✅ Acceptance criteria met
- ✅ Tests added/updated where appropriate
- ✅ CI-equivalent commands pass for touched areas
- ✅ Documentation updated when behavior/contracts change

## Code Style & Conventions

### Backend (Python)
- **Line length:** 120 characters (configured in `ruff.toml`)
- **Linter:** Ruff (`ruff check server/`)
- **Auto-fix:** `ruff check server/ --fix`
- **Type hints:** Gradually typed; use mypy (`mypy server/ --ignore-missing-imports --check-untyped-defs`)
- **Imports:** Sorted with isort (handled by Ruff)
- **Strings:** Double quotes
- **Naming:** snake_case for functions/variables, PascalCase for classes
- **FastAPI patterns:**
  - Use `Depends()` for dependency injection (e.g., auth, DB sessions)
  - Return Pydantic models or JSONResponse
  - Keep routers in `server/agents/` organized by domain

### Frontend (TypeScript/React)
- **Linter:** ESLint with react-app config (`npm run lint`)
- **Type checking:** TypeScript strict mode (`tsc --noEmit`)
- **Component style:** Functional components with hooks
- **Props:** Define explicit TypeScript interfaces
- **State:** Prefer local state; use Context for shared global state
- **API calls:** Use `apiFetch` from `lib/` (handles auth, errors)
- **File naming:** PascalCase for components (e.g., `CharacterPanel.tsx`)

### Common Patterns

**Backend: Protected Endpoints**
```python
from fastapi import Depends
from server.auth import require_auth, AuthedUser

@router.get("/protected")
async def protected_endpoint(user: AuthedUser = Depends(require_auth)):
    return {"user_id": user.id}
```

**Frontend: API Calls**
```typescript
import { apiFetch } from '../lib/apiFetch';

const data = await apiFetch('/api/endpoint', {
  method: 'POST',
  body: JSON.stringify({ key: 'value' })
});
```

**WebSocket Events**
```python
# Backend: Broadcasting to session
await broadcast_to_session(session_id, {
    "type": "narrative.update",
    "payload": {"text": "..."}
})
```

## Testing Strategy

### Backend Tests
- **Location:** `server/tests/`
- **Run:** `pytest server/tests` or `pytest server/tests -v`
- **Coverage:** `pytest server/tests --cov=server --cov-report=term`
- **Targets:** 70%+ overall, 90%+ for auth/RBAC
- **Patterns:**
  - Use `TestClient` from FastAPI for integration tests
  - Mock external services (LLMs, S3) with pytest fixtures
  - Isolate test state (database fixtures, cleanup)

### Frontend Tests
- **Location:** `client/src/**/*.test.tsx`
- **Run:** `npm test` (watch mode) or `npm test -- --watchAll=false` (CI mode)
- **Coverage:** `npm test -- --coverage`
- **Targets:** 60%+ overall, 80%+ for critical flows (auth, session)
- **Patterns:**
  - Use React Testing Library (`render`, `screen`, `fireEvent`)
  - Mock API calls with Jest mocks
  - Test user interactions, not implementation details

### Smoke Tests
- **Location:** `server/tools/smoke_upload.py`, CI workflow
- **Purpose:** End-to-end validation of critical flows
- **Non-blocking:** Currently informational; will be blocking when stable

## Build & Development Commands

### Backend
```bash
cd server
python -m venv venv
source venv/bin/activate  # or venv/Scripts/Activate.ps1 (PowerShell) or venv\Scripts\activate (cmd)
pip install -r requirements.txt
python -m alembic upgrade head  # Run migrations
python -m uvicorn server.main:app --reload  # Start dev server on :8000
```

**Linting & Testing:**
```bash
ruff check server/              # Lint
ruff check server/ --fix        # Auto-fix
mypy server/ --ignore-missing-imports --check-untyped-defs  # Type check
pytest server/tests -v          # Run tests
```

### Frontend
```bash
cd client
npm install
npm start                       # Start dev server (usually :3000)
```

**Linting & Testing:**
```bash
npm run lint                    # ESLint
npx tsc --noEmit               # TypeScript check
npm test -- --watchAll=false   # Run tests once
npm run build                  # Production build
```

### Full Stack
```powershell
# Windows PowerShell (from repo root)
.\start-app.ps1                 # Terminates stray processes, boots backend+frontend
```

### CI/CD
- **Workflow:** `.github/workflows/ci.yml`
- **Triggers:** Push to `main`, PRs to `main`
- **Jobs:** Backend (lint/test), Frontend (lint/typecheck/test/build), Smoke
- **Blocking checks:** Backend tests, frontend build, linting
- **Local equivalent:** `./ci.ps1` (Windows-safe runner for special paths)

## Security & RBAC

### Authentication
- **Method:** JWT tokens via `server/auth.py`
- **Protected routes:** Use `Depends(require_auth)` for endpoints
- **Roles:** `player` (default), `host` (campaign owner), `admin` (future)
- **Email verification:** Required for signup; dev mode auto-verifies

### Authorization (RBAC)
- **Hidden documents:** Only hosts can read `visibility=hidden` documents
- **Campaign settings:** Only hosts can modify campaign metadata
- **Audit trails:** `agent_events` and `document_access` tables log sensitive operations
- **Security testing:** Always test permission boundaries for new endpoints

### Best Practices
- Never commit secrets (`.env` files, API keys, JWT secrets)
- Rotate credentials regularly (see `docs/SECRET_MANAGEMENT.md`)
- Validate input for file uploads, document paths, user IDs
- Use parameterized queries (SQLModel handles this)
- Rate-limit agent endpoints to prevent abuse

## Common Tasks

### Adding a New Agent Endpoint
1. Create router in `server/agents/your_agent.py`
2. Define Pydantic request/response models
3. Add route with `@router.post("/endpoint")` or similar
4. Register router in `server/main.py` (`app.include_router(...)`)
5. Add tests in `server/tests/test_your_agent.py`
6. Update frontend in `client/src/agents/YourAgent.tsx`
7. Add WebSocket event types if needed
8. Document in `AGENTS.md` if it's a gameplay agent

### Adding a New UI Component
1. Create component in `client/src/components/YourComponent.tsx`
2. Define TypeScript interfaces for props
3. Use `apiFetch` for API calls
4. Add basic tests in `YourComponent.test.tsx`
5. Import and use in parent component/view
6. Update styling as needed (CSS modules or inline)

### Running Database Migrations
```bash
cd /path/to/TavernTAIls
python -m alembic revision --autogenerate -m "Description of change"
python -m alembic upgrade head
```

### Debugging WebSocket Events
- Backend: Check logs for `broadcast_to_session` calls
- Frontend: Use browser DevTools → Network → WS tab
- Test payload shapes with `server/tests/test_ws_*.py`

## Troubleshooting

### Port 3000 Already in Use
```bash
cd client
npm run check-port  # Identify what's using the port
# Then stop the process or use SKIP_PORT_GUARD=1
```

### Backend Won't Start
- Check database migrations: `python -m alembic upgrade head`
- Verify environment variables (see `.env.template`)
- Check logs in `uvicorn.log` or console output

### Tests Failing
- Match CI environment versions (Python 3.11+, Node 18/20)
- Clear caches: `pytest --cache-clear` or `npm test -- --clearCache`
- Check for hardcoded paths or missing fixtures

### CI Failures
- Review `docs/CI_CHECKLIST.md` for specific failure modes
- Reproduce locally with exact CI commands
- Check GitHub Actions logs for detailed error messages

## Important Notes

### What NOT to Change Without Discussion
- Auth flow (JWT, email verification)
- Database schema (requires migration + approval)
- Agent contract shapes (WebSocket events, API responses)
- File structure for `server/agents/` or `client/src/agents/`
- CI blocking checks (without documenting in CI_CHECKLIST.md)

### Prefer Small Changes
- Target 1-3 files per PR when possible
- Keep refactors separate from feature work
- Update tests alongside code changes
- Document breaking changes in PR description

## References

- **Project Plan:** `PROJECT_PLAN.md` (canonical architecture & roadmap)
- **MVP Checklist:** `MVP_DELIVERY_CHECKLIST.md` (acceptance criteria)
- **Agent Architecture:** `AGENTS.md` (gameplay agent responsibilities)
- **Development Model:** `docs/DEV_AGENTS.md` (role-based workflow)
- **CI/CD Guide:** `docs/CI_CHECKLIST.md` (quality gates)
- **Setup Guide:** `README.md` (getting started)

## Contact & Support

For questions about architecture or scope decisions, consult `PROJECT_PLAN.md` or create a GitHub issue. For immediate help, check existing documentation in `docs/` or recent PRs for similar work.
