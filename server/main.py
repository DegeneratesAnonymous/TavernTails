import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .agents import references as references_router
from .agents import srd as srd_router
from .agents import ws as ws_router
from .agents.admin import router as admin_router
from .agents.campaigns import router as campaigns_router
from .agents.characters import router as characters_router
from .agents.chat import router as chat_router
from .agents.content import router as content_router
from .agents.documents import router as documents_router
from .agents.generate import router as generate_router
from .agents.image import router as image_router
from .agents.messages import router as messages_router
from .agents.moderation import router as moderation_router
from .agents.narrative import router as narrative_router
from .agents.notes import router as notes_router
from .agents.npc import router as npc_router
from .agents.player import router as player_router
from .agents.rolls import router as rolls_router
from .agents.scene import router as scene_router
from .agents.sessions import router as sessions_router
from .agents.storyboard import router as storyboard_router
from .agents.suggestions import router as suggestions_router
from .agents.support import router as support_router
from .agents.turns import router as turns_router
from .agents.users import router as users_router

# Simple request logging to make activity visible in the console
logger = logging.getLogger("taverntails")
logging.basicConfig(level=logging.INFO)

_db: Any
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
        if os.environ.get('TAVERNTAILS_SEED_DEV_USER', '0') == '1':
            _db.ensure_dev_user()
            logger.info('Dev user ensured (test@example.com / secret) — set TAVERNTAILS_SEED_DEV_USER=0 in production')
        if os.environ.get('TAVERNTAILS_SEED_USERS', '1') == '1':
            _db.ensure_seed_users()
            logger.info('Seed users ensured (admin + bilbo)')
        if os.environ.get('TAVERNTAILS_SEED_ALIEN_RPG', '1') == '1':
            try:
                from .scripts.seed_alien_rpg_characters import seed_alien_rpg_characters
                seed_alien_rpg_characters()
                logger.info('Alien RPG seed characters ensured (bilbo + admin)')
            except Exception:
                logger.exception('Alien RPG character seed failed (non-fatal)')
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


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception(f"Unhandled error during request {request.method} {request.url}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    # NOTE: When allow_credentials=True, browsers reject allow_origins=['*'].
    # This API uses bearer tokens (Authorization header) rather than cookies,
    # so we keep credentialed CORS disabled to allow simple local/dev setups
    # and cross-origin userscripts (e.g., dndbeyond.com -> localhost).
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(player_router)
app.include_router(admin_router)
app.include_router(users_router)
app.include_router(support_router)
app.include_router(moderation_router)
app.include_router(messages_router)
app.include_router(narrative_router)
app.include_router(content_router)
app.include_router(sessions_router)
app.include_router(characters_router)
app.include_router(campaigns_router)
app.include_router(generate_router)
app.include_router(rolls_router)
app.include_router(chat_router)
app.include_router(storyboard_router)
app.include_router(notes_router)
app.include_router(image_router)
app.include_router(suggestions_router)
app.include_router(ws_router.router)
app.include_router(turns_router)
app.include_router(documents_router)
app.include_router(scene_router)
app.include_router(npc_router)
app.include_router(references_router.router)
app.include_router(srd_router.router)

# Serve static build (if present) so the app is reachable at the backend port.
build_dir = Path(__file__).resolve().parents[1] / 'client' / 'build'
if build_dir.exists():
    app.mount('/', StaticFiles(directory=str(build_dir), html=True), name='static')

@app.get("/")
def read_root():
    return {"message": "TavernTAIls AI GM backend is running."}


# Initialize DB via lifespan (handled above)
