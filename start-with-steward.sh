#!/usr/bin/env bash
# start-with-steward.sh
# Launch TavernTAIls backend on port 8002, powered by Steward's local Ollama node.
#
# Usage:
#   ./start-with-steward.sh            # backend only (serves built React from FastAPI)
#   ./start-with-steward.sh --dev-ui   # also start React dev server on port 3001
#
# The Steward dashboard embeds TavernTAIls via iframe at http://localhost:8002
# Open the Games tab in Steward to play.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

PORT=8002
DEV_UI=false

for arg in "$@"; do
  case $arg in
    --dev-ui) DEV_UI=true ;;
    --port=*) PORT="${arg#*=}" ;;
  esac
done

# ── Steward Ollama configuration ──────────────────────────────
# Routes TavernTAIls AI agents through the local Ollama node.
# Change OLLAMA_HOST to a Tailscale IP to use a remote cluster node.
export OLLAMA_HOST="http://localhost:11434"
export OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:4b}"

# Keep OPENAI_API_KEY unset (or set to "ollama") — steward_llm.py prefers OLLAMA_HOST.
export OPENAI_API_KEY="ollama"

# ── Database ──────────────────────────────────────────────────
export TAVERNTAILS_DATABASE_URL="${TAVERNTAILS_DATABASE_URL:-sqlite:////${SCRIPT_DIR}/data/taverntails.db}"
export TAVERNTAILS_SECRET="${TAVERNTAILS_SECRET:-dev-secret-change-me}"

mkdir -p "${SCRIPT_DIR}/data"

# Keep acceptance-test campaigns out of the user-facing campaign list.
python3 -m server.scripts.purge_qa_campaigns --commit --quiet || true

# Build React frontend if build/ is missing or src/ is newer than index.html
CLIENT_DIR="$SCRIPT_DIR/client"
BUILD_DIR="$CLIENT_DIR/build"
if [ ! -f "$BUILD_DIR/index.html" ] || [ "$CLIENT_DIR/src" -nt "$BUILD_DIR/index.html" ]; then
  echo "Building TavernTAIls frontend (this takes ~1 min on first run)..."
  (cd "$CLIENT_DIR" && npm install --silent && npm run build)
  echo "Frontend build complete."
fi

VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
  echo "No venv found — using system Python3 (pip --user packages)"
  VENV_PYTHON="$(which python3)"
fi

echo "Starting TavernTAIls on port $PORT (Ollama: $OLLAMA_HOST, model: $OLLAMA_MODEL)"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  [ -n "$BACKEND_PID" ]  && kill "$BACKEND_PID"  2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  echo "Stopped."
  exit 0
}
trap cleanup EXIT INT TERM

"$VENV_PYTHON" -m uvicorn server.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --reload &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID  →  http://localhost:$PORT"

if [ "$DEV_UI" = true ]; then
  CLIENT_DIR="$SCRIPT_DIR/client"
  if [ -d "$CLIENT_DIR" ]; then
    export PORT=3001  # React dev server on 3001 so it doesn't clash with Flowise
    cd "$CLIENT_DIR"
    npm start &
    FRONTEND_PID=$!
    cd "$SCRIPT_DIR"
    echo "  Frontend PID: $FRONTEND_PID  →  http://localhost:3001"
  fi
fi

echo ""
echo "Open the Games tab in Steward to play, or go to http://localhost:$PORT directly."
echo "Press Ctrl+C to stop."

wait $BACKEND_PID
