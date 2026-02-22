# ── Stage 1: Build the React frontend ────────────────────────────────────────
FROM node:20-slim AS frontend-builder
WORKDIR /app/client
COPY client/package*.json ./
RUN npm ci --silent
COPY client/ ./
# REACT_APP_API_URL is empty so the built app talks to its own origin.
RUN npm run build

# ── Stage 2: Python backend + serve the compiled frontend ────────────────────
FROM python:3.11-slim
WORKDIR /app

# Install Python dependencies
COPY server/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY alembic.ini ./
COPY server/ server/

# Copy the compiled frontend so FastAPI can serve it at /
COPY --from=frontend-builder /app/client/build client/build

# Persistent data volume mount-point (SQLite DB lives here)
RUN mkdir -p /app/data

EXPOSE 8000

# DATABASE_URL used by both Alembic and the app
ENV TAVERNTAILS_DATABASE_URL=sqlite:////app/data/taverntails.db

# On start: run any pending DB migrations then launch the API server
CMD ["sh", "-c", "python -m alembic upgrade head && python -m uvicorn server.main:app --host 0.0.0.0 --port 8000"]
