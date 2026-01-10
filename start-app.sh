#!/usr/bin/env bash

# start-app.sh
# Start TavernTAIls development services (backend and/or frontend) for macOS/Linux
#
# Usage:
#   ./start-app.sh                 # Start both backend and frontend
#   ./start-app.sh --backend-only  # Start only backend
#   ./start-app.sh --frontend-only # Start only frontend
#   ./start-app.sh --port 8080     # Start with custom backend port

set -e  # Exit on error

# Default values
BACKEND_PORT=8000
START_BACKEND=true
START_FRONTEND=true

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
NC='\033[0m' # No Color

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --backend-only)
            START_FRONTEND=false
            shift
            ;;
        --frontend-only)
            START_BACKEND=false
            shift
            ;;
        --port)
            BACKEND_PORT="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Start TavernTAIls development services locally"
            echo ""
            echo "Options:"
            echo "  --backend-only   Start only the backend FastAPI server"
            echo "  --frontend-only  Start only the frontend React dev server"
            echo "  --port PORT      Set backend port (default: 8000)"
            echo "  --help, -h       Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                      # Start both services"
            echo "  $0 --backend-only       # Start only backend"
            echo "  $0 --port 8080          # Start with backend on port 8080"
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate options
if [ "$START_BACKEND" = false ] && [ "$START_FRONTEND" = false ]; then
    echo -e "${RED}Error: Cannot use --backend-only and --frontend-only together${NC}"
    exit 1
fi

# Store PIDs for cleanup
BACKEND_PID=""
FRONTEND_PID=""

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping services...${NC}"
    
    if [ -n "$BACKEND_PID" ]; then
        echo "Stopping backend (PID: $BACKEND_PID)..."
        kill $BACKEND_PID 2>/dev/null || true
        wait $BACKEND_PID 2>/dev/null || true
    fi
    
    if [ -n "$FRONTEND_PID" ]; then
        echo "Stopping frontend (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID 2>/dev/null || true
        wait $FRONTEND_PID 2>/dev/null || true
    fi
    
    # Kill any remaining node/uvicorn processes
    pkill -f "uvicorn server.main:app" 2>/dev/null || true
    pkill -f "react-scripts start" 2>/dev/null || true
    
    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
}

# Register cleanup on script exit
trap cleanup EXIT INT TERM

echo -e "${CYAN}=== TavernTAIls Local Development Startup ===${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Clean up any existing processes
echo -e "${GRAY}Cleaning up existing processes...${NC}"
pkill -f "uvicorn server.main:app" 2>/dev/null || true
pkill -f "react-scripts start" 2>/dev/null || true
sleep 0.5

# Ensure logs directory exists
mkdir -p logs

# Start Backend
if [ "$START_BACKEND" = true ]; then
    echo -e "${GREEN}Starting backend (uvicorn) on port $BACKEND_PORT...${NC}"
    
    VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
    
    if [ -f "$VENV_PYTHON" ]; then
        BACKEND_LOG_OUT="$SCRIPT_DIR/logs/backend-out.log"
        BACKEND_LOG_ERR="$SCRIPT_DIR/logs/backend-err.log"
        
        # Start backend in background
        "$VENV_PYTHON" -m uvicorn server.main:app \
            --host 0.0.0.0 \
            --port "$BACKEND_PORT" \
            --reload \
            > "$BACKEND_LOG_OUT" 2> "$BACKEND_LOG_ERR" &
        
        BACKEND_PID=$!
        
        echo -e "  ${GREEN}✓${NC} Backend started (PID: $BACKEND_PID)"
        echo -e "  ${GRAY}→ API: http://127.0.0.1:$BACKEND_PORT${NC}"
        echo -e "  ${GRAY}→ Logs: $BACKEND_LOG_OUT${NC}"
    else
        echo -e "${YELLOW}Warning: Virtualenv python not found at $VENV_PYTHON${NC}"
        echo -e "  ${YELLOW}Please run: python3 -m venv venv && source venv/bin/activate && pip install -r server/requirements.txt${NC}"
    fi
    echo ""
fi

# Start Frontend
if [ "$START_FRONTEND" = true ]; then
    echo -e "${GREEN}Starting frontend (React dev server)...${NC}"
    
    CLIENT_DIR="$SCRIPT_DIR/client"
    
    if [ -d "$CLIENT_DIR" ]; then
        FRONTEND_LOG_OUT="$CLIENT_DIR/npm-out.log"
        FRONTEND_LOG_ERR="$CLIENT_DIR/npm-err.log"
        
        # Start frontend in background
        cd "$CLIENT_DIR"
        npm start > "$FRONTEND_LOG_OUT" 2> "$FRONTEND_LOG_ERR" &
        FRONTEND_PID=$!
        cd "$SCRIPT_DIR"
        
        echo -e "  ${GREEN}✓${NC} Frontend started (PID: $FRONTEND_PID)"
        echo -e "  ${GRAY}→ UI: http://localhost:3000 (will open in browser)${NC}"
        echo -e "  ${GRAY}→ Logs: $FRONTEND_LOG_OUT${NC}"
    else
        echo -e "${YELLOW}Warning: client directory not found at $CLIENT_DIR${NC}"
        echo -e "  ${YELLOW}Please ensure the client directory exists${NC}"
    fi
    echo ""
fi

# Show status
echo -e "${CYAN}=== Services Running ===${NC}"
if [ "$START_BACKEND" = true ]; then
    echo -e "  ${NC}Backend:  http://127.0.0.1:$BACKEND_PORT${NC}"
    echo -e "  ${NC}Docs:     http://127.0.0.1:$BACKEND_PORT/docs${NC}"
fi
if [ "$START_FRONTEND" = true ]; then
    echo -e "  ${NC}Frontend: http://localhost:3000${NC}"
fi
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services...${NC}"

# Wait for processes
if [ -n "$BACKEND_PID" ] && [ -n "$FRONTEND_PID" ]; then
    wait $BACKEND_PID $FRONTEND_PID
elif [ -n "$BACKEND_PID" ]; then
    wait $BACKEND_PID
elif [ -n "$FRONTEND_PID" ]; then
    wait $FRONTEND_PID
fi
