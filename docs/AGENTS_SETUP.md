# Agent Ownership and Quick-Start Guide

This document outlines the agent-based architecture for TavernTAIls, lists all agents with ownership assignments, and provides quick-start steps for contributors.

## Agent Ownership Matrix

| Agent | Responsibility | Owner | Status |
|-------|---------------|-------|--------|
| **Backend/API** | FastAPI services, database models, auth, session management | _[Owner TBD]_ | Active |
| **Frontend/Web** | React UI, components, routing, state management | _[Owner TBD]_ | Active |
| **Agent Orchestration/LLM** | GM Orchestrator, Narrative, Scene Analysis agents, LLM integration | _[Owner TBD]_ | Planned |
| **Data/Integrations** | Beyond20, DnD Beyond, PDF parsing, external APIs | _[Owner TBD]_ | Planned |
| **Infra/DevOps** | CI/CD, deployments, monitoring, environments | _[Owner TBD]_ | Active |
| **QA/Automation** | Testing strategy, E2E tests, smoke tests, test infrastructure | _[Owner TBD]_ | Active |
| **Docs/PM** | Documentation, planning, backlog hygiene, release coordination | _[Owner TBD]_ | Active |

## Agent Roles Details

### 1. Backend/API Agent
**Scope**: Server-side FastAPI application, database models, authentication, API endpoints

**Quick-Start Steps**:
1. Install Python 3.11+ and create virtual environment: `python -m venv venv`
2. Activate environment: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Linux/Mac)
3. Install dependencies: `pip install -r server/requirements.txt`
4. Copy `server/.env.example` to `server/.env` and configure local settings
5. Run migrations: `alembic upgrade head`
6. Start server: `uvicorn server.main:app --reload`
7. Run tests: `pytest server/tests`

**Key Technologies**: FastAPI, SQLModel, Alembic, JWT, pytest

### 2. Frontend/Web Agent
**Scope**: React SPA, UI components, client-side routing, WebSocket integration

**Quick-Start Steps**:
1. Install Node.js 20+
2. Navigate to client directory: `cd client`
3. Install dependencies: `npm install`
4. Copy `client/.env.example` to `client/.env` and configure API URLs
5. Start dev server: `npm start`
6. Run tests: `npm test`
7. Build production: `npm run build`

**Key Technologies**: React 19, TypeScript, Create React App, WebSockets

### 3. Agent Orchestration/LLM Agent
**Scope**: AI agent coordination, LLM integration, prompt engineering, agent contracts

**Quick-Start Steps**:
1. Follow Backend/API setup steps
2. Review agent architecture in `server/agents/` directory
3. Configure LLM API keys in `.env` (see `docs/LLM_IMAGE_CONFIG.md`)
4. Review agent contracts in `AGENTS.md`
5. Test agent endpoints via `/docs` (Swagger UI)
6. Add contract tests in `server/tests/`

**Key Technologies**: OpenAI API, FastAPI, async Python, WebSockets

### 4. Data/Integrations Agent
**Scope**: External API integrations, data parsing, import/export functionality

**Quick-Start Steps**:
1. Follow Backend/API setup steps
2. Review integration endpoints in `server/agents/` (Beyond20, document imports)
3. Configure API credentials in `.env`
4. Test parsers with sample data
5. Add integration tests for new parsers

**Key Technologies**: PyMuPDF, requests, pydantic, async I/O

### 5. Infra/DevOps Agent
**Scope**: CI/CD pipelines, deployment automation, infrastructure as code

**Quick-Start Steps**:
1. Review `.github/workflows/ci.yml` for CI pipeline
2. Review `docs/CI_CHECKLIST.md` for CI gates
3. Test locally with `start-app.ps1` (Windows) or manual start commands
4. Monitor GitHub Actions for build status
5. Review deployment strategy in `PROJECT_PLAN.md` §10

**Key Technologies**: GitHub Actions, Docker (planned), uvicorn, npm

### 6. QA/Automation Agent
**Scope**: Test strategy, automated testing, quality gates, test infrastructure

**Quick-Start Steps**:
1. Review existing tests in `server/tests/` and `client/src/`
2. Run backend tests: `pytest server/tests`
3. Run frontend tests: `cd client && npm test`
4. Review test coverage reports
5. Add new tests following existing patterns
6. Review Playwright setup (planned) for E2E tests

**Key Technologies**: pytest, React Testing Library, Playwright (planned)

### 7. Docs/PM Agent
**Scope**: Documentation maintenance, project planning, backlog grooming, release coordination

**Responsibilities**:
- **Plan Currency**: Keep `PROJECT_PLAN.md`, `MVP_DELIVERY_CHECKLIST.md`, and this document up-to-date
- **Backlog Hygiene**: Groom issues, maintain priority, ensure clear acceptance criteria
- **Release Readiness**: Track MVP/Phase gates, coordinate release preparation
- **Communication**: Update stakeholders on progress, blockers, and decisions
- **Onboarding**: Maintain contributor docs, quick-start guides, architecture diagrams

**Quick-Start Steps**:
1. Review `PROJECT_PLAN.md` for product vision and architecture
2. Review `MVP_DELIVERY_CHECKLIST.md` for current status
3. Update documentation when features are added or changed
4. Keep agent ownership matrix current (this file)
5. Coordinate with other agents on cross-cutting concerns
6. Document decisions and communicate to team

**Key Deliverables**: 
- Accurate planning documents
- Clear onboarding materials
- Release notes and changelog
- Architecture documentation
- Contributor guidelines

## Getting Started as a New Contributor

1. **Choose Your Area**: Select an agent role that matches your skills and interests
2. **Review Documentation**: Read `README.md`, `PROJECT_PLAN.md`, and this document
3. **Set Up Environment**: Follow quick-start steps for your chosen agent(s)
4. **Run the App**: Use `start-app.ps1` to start both backend and frontend
5. **Find a Task**: Check issues labeled with your agent area or ask the PM
6. **Make Changes**: Follow the development workflow and CI requirements
7. **Submit PR**: Ensure tests pass and documentation is updated

## Development Workflow

1. Create a feature branch from `main`
2. Make minimal, focused changes
3. Add/update tests for your changes
4. Update documentation if needed
5. Ensure CI checks pass (linting, tests, build)
6. Submit PR with clear description
7. Address review feedback

## Questions or Issues?

- **Technical Questions**: Check `README.md` or ask in your agent area
- **Planning Questions**: Contact the Docs/PM agent owner
- **Bugs**: Create an issue with steps to reproduce
- **Feature Requests**: Discuss with PM before implementing

---

_Last Updated: 2026-01-09 | Maintainer: TavernTAIls Core Team_
