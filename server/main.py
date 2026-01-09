from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .agents.player import router as player_router
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import logging
import os


# Simple request logging to make activity visible in the console
logger = logging.getLogger("taverntails")
logging.basicConfig(level=logging.INFO)

try:
    from . import db as _db
except Exception:
    logger.exception('DB module not available or failed to import')
    _db = None


_db_initialized = False
_db_engine_signature = None


def _init_db_if_needed():
    global _db_initialized, _db_engine_signature
    if _db is None:
        logger.warning('DB module missing; skipping initialization')
        return
    engine_sig = id(_db.engine)
    if _db_engine_signature != engine_sig:
        _db_initialized = False
        _db_engine_signature = engine_sig
    if _db_initialized:
        return
    try:
        logger.info('Initializing database...')
        _db.create_db_and_tables()
        if os.environ.get('TAVERNTAILS_SEED_DEV_USER', '1') == '1':
            _db.ensure_dev_user()
            logger.info('Dev user ensured (test@example.com / secret)')
        logger.info('Database ready')
        _db_initialized = True
    except Exception:
        logger.exception('Database initialization failed')


# Ensure the database is ready for modules/tests that instantiate the app without running lifespan.
_init_db_if_needed()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Application startup: pid=%s ts=%s", os.getpid(), datetime.now(timezone.utc).isoformat())
    _init_db_if_needed()
    try:
        yield
    finally:
        logger.info('Application shutdown complete')


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def log_requests(request, call_next):
    _init_db_if_needed()
    logger.info(f"--> {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"<-- {response.status_code} {request.method} {request.url}")
    return response


# ===================================
# PLACEHOLDER: RATE LIMITING MIDDLEWARE
# ===================================
# TODO: Implement rate limiting middleware when TAVERNTAILS_RATE_LIMIT_ENABLED=true
# This will enforce per-user and per-endpoint request limits to prevent abuse.
#
# Implementation notes:
# 1. Check TAVERNTAILS_RATE_LIMIT_ENABLED environment variable
# 2. Track requests per user (from JWT token) in memory or Redis
# 3. Return 429 Too Many Requests when limits exceeded
# 4. Use sliding window or token bucket algorithm
# 5. Support per-endpoint limits from TAVERNTAILS_RATE_LIMIT_PER_ENDPOINT
#
# Example structure:
# @app.middleware("http")
# async def rate_limit_middleware(request, call_next):
#     if os.getenv("TAVERNTAILS_RATE_LIMIT_ENABLED") != "true":
#         return await call_next(request)
#     
#     user_id = get_user_from_request(request)  # Extract from JWT
#     endpoint = request.url.path
#     
#     if is_rate_limited(user_id, endpoint):
#         return JSONResponse(
#             status_code=429,
#             content={"detail": "Rate limit exceeded. Try again later."}
#         )
#     
#     response = await call_next(request)
#     record_request(user_id, endpoint)
#     return response
#
# See docs/AGENT_GUARDRAILS.md Section 6 for full specification.


# ===================================
# PLACEHOLDER: AUDIT LOGGING MIDDLEWARE
# ===================================
# TODO: Implement audit logging middleware when TAVERNTAILS_ENABLE_AUDIT_LOGGING=true
# This will log all agent actions to the agent_events table for PM review.
#
# Implementation notes:
# 1. Check TAVERNTAILS_ENABLE_AUDIT_LOGGING environment variable
# 2. Log all requests to agent endpoints (/narrative, /image, /chat, etc.)
# 3. Store: timestamp, user_id, agent, action, resource_id, result, details
# 4. Create agent_events table in server/db.py (similar to ChatMessage, Roll tables)
# 5. Log after response to include status code and timing
# 6. Include request/response bodies for sensitive operations (hidden docs, role changes)
#
# Example structure:
# @app.middleware("http")
# async def audit_logging_middleware(request, call_next):
#     if os.getenv("TAVERNTAILS_ENABLE_AUDIT_LOGGING") != "true":
#         return await call_next(request)
#     
#     start_time = datetime.now(timezone.utc)
#     user_id = get_user_from_request(request)  # Extract from JWT or "anonymous"
#     
#     response = await call_next(request)
#     
#     # Log to agent_events table if this is an agent endpoint
#     if should_audit(request.url.path):
#         await log_agent_event(
#             user_id=user_id,
#             agent=extract_agent_name(request.url.path),
#             action=request.method,
#             resource_id=extract_resource_id(request),
#             result="success" if response.status_code < 400 else "failure",
#             duration_ms=(datetime.now(timezone.utc) - start_time).total_seconds() * 1000
#         )
#     
#     return response
#
# See docs/AGENTS_SETUP.md Section 2.4 for weekly audit review process.


from fastapi.responses import JSONResponse
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception(f"Unhandled error during request {request.method} {request.url}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or restrict to ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(player_router)
from .agents.narrative import router as narrative_router
app.include_router(narrative_router)
from .agents.content import router as content_router
app.include_router(content_router)
from .agents.sessions import router as sessions_router
app.include_router(sessions_router)
from .agents.characters import router as characters_router
app.include_router(characters_router)
from .agents.campaigns import router as campaigns_router
app.include_router(campaigns_router)
from .agents.rolls import router as rolls_router
app.include_router(rolls_router)
from .agents.chat import router as chat_router
app.include_router(chat_router)
from .agents.storyboard import router as storyboard_router
app.include_router(storyboard_router)
from .agents.notes import router as notes_router
app.include_router(notes_router)
from .agents.image import router as image_router
app.include_router(image_router)
from .agents.suggestions import router as suggestions_router
app.include_router(suggestions_router)
from .agents import ws as ws_router
app.include_router(ws_router.router)
from .agents.turns import router as turns_router
app.include_router(turns_router)
from .agents.documents import router as documents_router
app.include_router(documents_router)
from .agents.scene import router as scene_router
app.include_router(scene_router)
from .agents.npc import router as npc_router
app.include_router(npc_router)

# Serve static build (if present) so the app is reachable at the backend port.
build_dir = Path(__file__).resolve().parents[1] / 'client' / 'build'
if build_dir.exists():
    app.mount('/', StaticFiles(directory=str(build_dir), html=True), name='static')

@app.get("/")
def read_root():
    return {"message": "TavernTAIls AI GM backend is running."}


# Initialize DB via lifespan (handled above)
