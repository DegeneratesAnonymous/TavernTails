# Local Development Guide

This guide will help you set up and run TavernTAIls locally for development. Follow these steps to get started quickly!

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Environment Setup](#environment-setup)
- [Running the Application](#running-the-application)
- [Development Scripts](#development-scripts)
- [Common Issues](#common-issues)
- [Development Workflow](#development-workflow)

## Prerequisites

Before you begin, ensure you have the following installed:

### Required Software

1. **Python 3.11 or higher**
   - Download from [python.org](https://www.python.org/downloads/)
   - Verify installation: `python --version` or `python3 --version`

2. **Node.js 20 or higher**
   - Download from [nodejs.org](https://nodejs.org/)
   - Verify installation: `node --version`
   - npm should be installed automatically with Node.js: `npm --version`

3. **Git**
   - Download from [git-scm.com](https://git-scm.com/)
   - Verify installation: `git --version`

### Optional but Recommended

- **VS Code** with Python and React extensions
- **PowerShell 7+** (Windows users) or **Bash** (macOS/Linux users)

## Quick Start

The fastest way to get started is using our one-command startup scripts:

### Windows (PowerShell)

```powershell
# Clone the repository
git clone https://github.com/DegeneratesAnonymous/TavernTails.git
cd TavernTails

# Set up backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r server\requirements.txt

# Set up frontend
cd client
npm install
cd ..

# Copy environment files
copy server\.env.example server\.env
copy client\.env.example client\.env

# Start both services with one command!
.\start-app.ps1
```

### macOS/Linux (Bash)

```bash
# Clone the repository
git clone https://github.com/DegeneratesAnonymous/TavernTails.git
cd TavernTails

# Set up backend
python3 -m venv venv
source venv/bin/activate
pip install -r server/requirements.txt

# Set up frontend
cd client
npm install
cd ..

# Copy environment files
cp server/.env.example server/.env
cp client/.env.example client/.env

# Start both services with one command!
./start-app.sh
```

That's it! The application should now be running:
- **Frontend**: http://localhost:3000
- **Backend API**: http://127.0.0.1:8000
- **API Documentation**: http://127.0.0.1:8000/docs

## Environment Setup

### Backend Environment (.env)

The backend requires a `.env` file in the `server/` directory. Copy the example file and customize as needed:

```bash
# Windows
copy server\.env.example server\.env

# macOS/Linux
cp server/.env.example server/.env
```

**Key settings for local development:**

```env
# Database - SQLite is used by default (no setup required!)
DATABASE_URL=sqlite:///./taverntails.db

# Security - Generate a secure secret key for production
SECRET_KEY=your-secret-key-here-change-in-production

# CORS - Allow local frontend
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# LLM Configuration (Optional for basic testing)
# Get API keys from https://platform.openai.com/api-keys
OPENAI_API_KEY=your-openai-api-key-here
OPENAI_MODEL=gpt-4o-mini

# Session Storage - Local filesystem (default)
SESSIONS_STORAGE_TYPE=local
SESSIONS_BASE_PATH=./server/sessions

# Environment
ENVIRONMENT=development
DEBUG=true
```

**Note:** For basic testing and UI development, you don't need API keys. The app will work without them, but AI features won't function.

### Frontend Environment (.env)

The frontend also needs a `.env` file in the `client/` directory:

```bash
# Windows
copy client\.env.example client\.env

# macOS/Linux
cp client/.env.example client/.env
```

The frontend automatically detects `localhost` and connects to the backend on port 8000, so you typically don't need to change anything.

### Database Initialization

The database will be automatically created and initialized when you first start the backend. By default:
- **SQLite** database is used (no external database required!)
- Database file is created at `server/taverntails.db`
- A development user is automatically created:
  - Email: `test@example.com`
  - Password: `secret`

To run database migrations manually:

```bash
# From the repository root
alembic upgrade head
```

## Running the Application

### One-Command Startup (Recommended)

Use the startup scripts to run both services together:

#### Windows (PowerShell)

```powershell
# Start both backend and frontend
.\start-app.ps1

# Start only backend
.\start-app.ps1 -BackendOnly

# Start only frontend
.\start-app.ps1 -FrontendOnly

# Start with custom backend port
.\start-app.ps1 -BackendPort 8080
```

Press **Enter** to stop all services.

#### macOS/Linux (Bash)

```bash
# Start both backend and frontend
./start-app.sh

# Start only backend
./start-app.sh --backend-only

# Start only frontend
./start-app.sh --frontend-only

# Start with custom backend port
./start-app.sh --port 8080

# Show help
./start-app.sh --help
```

Press **Ctrl+C** to stop all services.

### Manual Startup

If you prefer to run services separately in different terminals:

#### Backend

```bash
# Activate virtual environment
# Windows:
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate

# Start the server
cd server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Or from repository root:
uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend

```bash
cd client
npm start
```

## Development Scripts

### Backend Scripts

```bash
# Install dependencies
pip install -r server/requirements.txt

# Run tests
pytest server/tests

# Run linter
ruff check server/

# Run type checker
mypy server/

# Run database migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "Description"
```

### Frontend Scripts

```bash
cd client

# Install dependencies
npm install

# Start development server
npm start

# Run tests
npm test

# Build for production
npm run build

# Check if port 3000 is available
npm run check-port
```

## Common Issues

### Port Already in Use

**Problem:** Port 3000 (frontend) or 8000 (backend) is already in use.

**Solution:**

1. **Find and kill the process:**

   ```bash
   # Windows (PowerShell)
   Get-Process -Name node | Stop-Process -Force
   Get-Process -Name uvicorn | Stop-Process -Force
   
   # macOS/Linux
   pkill -f "react-scripts start"
   pkill -f "uvicorn server.main:app"
   ```

2. **Or use a different port:**

   ```bash
   # Backend on different port
   ./start-app.sh --port 8080
   
   # Frontend: Set PORT environment variable
   PORT=3001 npm start
   ```

### Python Virtual Environment Not Found

**Problem:** Script can't find `venv/Scripts/python.exe` or `venv/bin/python`

**Solution:**

1. Create the virtual environment:
   ```bash
   # Windows
   python -m venv venv
   
   # macOS/Linux
   python3 -m venv venv
   ```

2. Activate and install dependencies:
   ```bash
   # Windows
   .\venv\Scripts\Activate.ps1
   pip install -r server\requirements.txt
   
   # macOS/Linux
   source venv/bin/activate
   pip install -r server/requirements.txt
   ```

### npm Dependencies Not Installed

**Problem:** Frontend fails to start with module not found errors.

**Solution:**

```bash
cd client
npm install
```

### Database Errors

**Problem:** Backend fails to start with database errors.

**Solution:**

1. Delete the existing database:
   ```bash
   rm server/taverntails.db  # macOS/Linux
   del server\taverntails.db  # Windows
   ```

2. Run migrations:
   ```bash
   alembic upgrade head
   ```

3. Restart the backend - it will recreate the database automatically.

### CORS Errors

**Problem:** Frontend can't connect to backend due to CORS errors.

**Solution:**

1. Check that `CORS_ORIGINS` in `server/.env` includes your frontend URL:
   ```env
   CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
   ```

2. Restart the backend after changing `.env` files.

### Permission Denied on Bash Script

**Problem:** `./start-app.sh` gives "permission denied" error.

**Solution:**

```bash
chmod +x start-app.sh
```

## Development Workflow

### Making Changes

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes** to the code

3. **Test your changes:**
   ```bash
   # Backend tests
   pytest server/tests
   
   # Frontend tests
   cd client && npm test
   ```

4. **Run linters:**
   ```bash
   # Backend
   ruff check server/
   mypy server/
   
   # Frontend linting is automatic with CRA
   ```

5. **Commit and push:**
   ```bash
   git add .
   git commit -m "Description of changes"
   git push origin feature/my-feature
   ```

### Hot Reload

Both backend and frontend support hot reload:

- **Backend:** Changes to Python files automatically reload the server (via `--reload` flag)
- **Frontend:** Changes to React components automatically refresh the browser

### Accessing Logs

Logs are stored in the following locations:

- **Backend logs:** `logs/backend-out.log` and `logs/backend-err.log`
- **Frontend logs:** `client/npm-out.log` and `client/npm-err.log`

You can tail logs in real-time:

```bash
# Windows (PowerShell)
Get-Content logs\backend-out.log -Wait

# macOS/Linux
tail -f logs/backend-out.log
```

### API Documentation

The backend provides interactive API documentation at:

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc

Use these to test API endpoints without writing frontend code.

## Next Steps

- Review the [Project Plan](../PROJECT_PLAN.md) to understand the architecture
- Check [AGENTS_SETUP.md](AGENTS_SETUP.md) for agent-specific development guides
- Read [SECRET_MANAGEMENT.md](SECRET_MANAGEMENT.md) for handling API keys and secrets
- Join our development community and ask questions!

## Need Help?

- **Check existing issues:** Search GitHub issues for similar problems
- **Create a new issue:** If you find a bug or have a question
- **Review documentation:** Check README.md and other docs/ files

Happy coding! 🎲✨
