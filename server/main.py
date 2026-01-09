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
