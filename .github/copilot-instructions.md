# TavernTAIls — GitHub Copilot Instructions

This file provides context for GitHub Copilot and AI coding assistants working on TavernTAIls.

> **GitHub Copilot Agent Mode**: Specialized agent-role prompts are in `.github/agents/`. Each `*.agent.md` file activates a specific dev-agent role (PM, Tech Lead, Backend, Frontend, QA, Security, DevOps, Documentation, Research, Reviewer, Integration, Observability, Performance). Load the appropriate file for your task.

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
│   ├── agents/                        # GitHub Copilot Agent mode role configs
│   │   ├── backend.agent.md           # Backend Agent (FastAPI, pytest)
│   │   ├── frontend.agent.md          # Frontend Agent (React, TypeScript)
│   │   ├── TechLead.agent.md          # Tech Lead Agent (planning, contracts)
│   │   ├── Security.agent.md          # Security Agent (RBAC, auth, vulns)
│   │   ├── QA.agent.md                # QA Agent (test plans, coverage)
│   │   ├── DevOPs.agent.md            # DevOps Agent (CI/CD, infra)
│   │   ├── Research.agent.md          # Research Agent (options, recommendations)
│   │   ├── Documentation.agent.md     # Documentation Agent (README, docs/)
│   │   ├── PM.agent.md                # PM Agent (scope, work orders)
│   │   ├── Reviewer.agent.md          # Reviewer Agent (holistic PR review)
│   │   ├── Integration.agent.md       # Integration Agent (WS, E2E flows)
│   │   ├── Observability.agent.md     # Observability Agent (logs, traces)
│   │   └── Performance.agent.md       # Performance Agent (load, hot paths)
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.yml
│   │   ├── feature_request.yml
│   │   ├── dev_agent_task.yml
│   │   └── player_led_mode.yml
│   ├── workflows/
│   │   ├── ci.yml                     # Main CI pipeline (blocking checks)
│   │   ├── auto-fix.yml               # Auto-fix lint issues on PRs
│   │   ├── contract-tests.yml         # API contract validation
│   │   ├── copilot-ci-gate.yml        # Posts CI status to copilot/** PRs
│   │   ├── deploy-staging.yml         # Staging deployment
│   │   ├── dev-agent-task-to-pr.yml   # Auto-creates draft PR from issues
│   │   ├── issue-backfill.yml         # Backfills existing issues to templates
│   │   ├── issue-confirm.yml          # Handles /proceed command on issues
│   │   ├── issue-triage.yml           # Auto-triages new issues
│   │   ├── label-sync.yml             # Syncs labels from labels.yml
│   │   ├── pr-agent-collaboration.yml # Posts agent review request on PRs
│   │   ├── pr-labeler.yml             # Auto-labels PRs by changed files
│   │   ├── screenshot-update.yml      # Updates UI screenshots
│   │   └── validate-issue-pr-format.yml # Validates issue/PR structure
│   ├── CODEOWNERS                     # Code ownership rules
│   ├── SECURITY.md                    # Vulnerability reporting policy
│   ├── copilot-instructions.md        # This file
│   ├── dependabot.yml                 # Automated dependency updates
│   ├── labeler.yml                    # PR labeling rules
│   ├── labels.yml                     # Label definitions
│   └── pull_request_template.md       # PR template
├── client/                        # React frontend
│   ├── public/                    # Static assets
│   ├── src/
│   │   ├── agents/                # Agent-specific React components
│   │   ├── components/            # UI components
│   │   ├── lib/                   # Utilities (apiFetch, etc.)
│   │   └── App.tsx               # Main app component
│   ├── .npmrc                     # npm config (legacy-peer-deps=true)
│   ├── package.json
│   └── tsconfig.json
├── server/                        # FastAPI backend
│   ├── agents/                    # Agent routers (narrative, scene, etc.)
│   ├── storage/                   # Document/session storage
│   ├── tests/                     # pytest test suite
│   │   └── fixtures/              # Test fixture PDFs (gitignored)
│   ├── tools/                     # Dev/CI tools (smoke_upload.py, init_db.py)
│   ├── auth.py                    # JWT authentication
│   ├── db.py                      # Database models
│   ├── main.py                    # FastAPI app + router registration
│   └── requirements.txt
├── alembic/                       # Database migration scripts
├── docs/                          # Documentation
│   ├── CI_CHECKLIST.md           # Quality gates
│   ├── DEV_AGENTS.md             # Development workflow
│   └── dev-agents/               # Copy-paste prompts (human-use; canonical versions in .github/agents/)
├── ruff.toml                      # Python linter config (120-char line length)
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
We use role-based development agents as a workflow model. Each agent has a dedicated prompt in `.github/agents/`:

| Agent | File | Responsibility |
|---|---|---|
| **PM** | `PM.agent.md` | Scope, work orders, priorities |
| **Research** | `Research.agent.md` | Options analysis, recommendations |
| **Tech Lead** | `TechLead.agent.md` | Architecture, contracts, task breakdown |
| **Backend** | `backend.agent.md` | FastAPI, DB, auth, pytest |
| **Frontend** | `frontend.agent.md` | React, TypeScript, Jest/RTL |
| **QA** | `QA.agent.md` | Test plans, coverage, acceptance criteria |
| **Security** | `Security.agent.md` | Auth/RBAC, input validation, CVEs |
| **DevOps** | `DevOPs.agent.md` | CI/CD, infra, dependency management |
| **Documentation** | `Documentation.agent.md` | README, docs/, inline comments |
| **Reviewer** | `Reviewer.agent.md` | Holistic PR review, sign-off |
| **Integration** | `Integration.agent.md` | WebSocket/E2E smoke flows |
| **Observability** | `Observability.agent.md` | Logging, traces, CI artifacts |
| **Performance** | `Performance.agent.md` | Load testing, hot-path profiling |

**Workflow cadence:** PM → Research → Tech Lead → Backend/Frontend/Security/DevOps (parallel) → QA → Reviewer → Documentation

- **Playbook:** `docs/DEV_AGENTS.md`
- **Work orders:** `docs/WORK_ORDER_TEMPLATE.md`
- **Agent mode configs:** `.github/agents/*.agent.md` (load in GitHub Copilot Agent mode)
- **Copy-paste prompts for humans:** `docs/dev-agents/` (legacy; `.github/agents/` is canonical)

### Automated GitHub Workflow

New issues trigger an automated pipeline:

1. **Issue filed** → `issue-triage.yml` labels + scaffolds the body, posts instructions
2. **Author comments `/proceed`** → `issue-confirm.yml` applies `dev-agent-task` label
3. **`dev-agent-task` label added** → `dev-agent-task-to-pr.yml` creates a draft branch + PR
4. **PR opened/edited** → `pr-agent-collaboration.yml` posts an agent collaboration comment
5. **PR pushed (copilot/** branch)** → `copilot-ci-gate.yml` posts CI pass/fail status to the PR
6. **PR merged to `main`** → staging deploy (if configured)

### Definition of Done
- ✅ Acceptance criteria met
- ✅ Tests added/updated where appropriate
- ✅ CI-equivalent commands pass for touched areas
- ✅ Documentation updated when behavior/contracts change

## Code Style & Conventions

### Backend (Python)
- **Line length:** 120 characters (configured in `ruff.toml` at repo root)
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
- **Migrations:** Use Alembic (`alembic/` + `alembic.ini`). Always autogenerate revisions, never hand-edit migration files.

### Frontend (TypeScript/React)
- **Linter:** ESLint with react-app config (`npm run lint`)
- **Type checking:** TypeScript strict mode (`tsc --noEmit`)
- **Component style:** Functional components with hooks
- **Props:** Define explicit TypeScript interfaces
- **State:** Prefer local state; use Context for shared global state
- **API calls:** Use `apiFetch` from `lib/` (handles auth, errors)
- **File naming:** PascalCase for components (e.g., `CharacterPanel.tsx`)
- **Dependency install:** `client/.npmrc` sets `legacy-peer-deps=true` (required for react-scripts@5 + TypeScript 5). Always use `npm ci` in CI and `npm install` locally.

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
  - Fixture PDFs are gitignored (`*.pdf`); tests generate them programmatically via `pypdf`
  - Smoke tests use `pytest.skip` when real fixture PDFs are absent

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
- **Triggers:** Push to `main`, `develop`, `copilot/**`; PRs to `main` or `develop`
- **Jobs:** Backend (lint/test on Python 3.11 + 3.12), Frontend (lint/typecheck/test/build on Node 18 + 20), Smoke, E2E
- **Blocking checks:** `backend` job (Python 3.11 tests) + `frontend` job (both Node versions) via `all-checks-passed`
- **Non-blocking:** mypy, smoke upload, Playwright E2E (all `continue-on-error: true`)
- **Auto-fix:** `auto-fix.yml` runs ruff + ESLint auto-fix and commits back to the PR branch
- **Local equivalent:** `./ci.ps1` (Windows-safe runner)

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
- **Agent Mode Files:** `.github/agents/` (GitHub Copilot Agent mode role configs)
- **Security Policy:** `.github/SECURITY.md` (vulnerability reporting)

## Contact & Support

For questions about architecture or scope decisions, consult `PROJECT_PLAN.md` or create a GitHub issue. For immediate help, check existing documentation in `docs/` or recent PRs for similar work.
