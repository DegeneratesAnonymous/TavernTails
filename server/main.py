

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .agents.player import router as player_router
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import logging
import os
import time


app = FastAPI()

# Simple request logging to make activity visible in the console
logger = logging.getLogger("taverntails")
logging.basicConfig(level=logging.INFO)


@app.middleware("http")
async def log_requests(request, call_next):
    logger.info(f"--> {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"<-- {response.status_code} {request.method} {request.url}")
    return response


@app.on_event("startup")
def on_startup():
    logger.info(f"Application startup: pid={os.getpid()} ts={int(time.time())}")


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

# Serve static build (if present) so the app is reachable at the backend port.
build_dir = Path(__file__).resolve().parents[1] / 'client' / 'build'
if build_dir.exists():
    app.mount('/', StaticFiles(directory=str(build_dir), html=True), name='static')

@app.get("/")
def read_root():
    return {"message": "TavernTAIls AI GM backend is running."}


# Initialize DB (if present)
try:
    from . import db as _db
    @app.on_event('startup')
    def _init_db():
        logger.info('Initializing database...')
        _db.create_db_and_tables()
        if os.environ.get('TAVERNTAILS_SEED_DEV_USER', '1') == '1':
            _db.ensure_dev_user()
            logger.info('Dev user ensured (test@example.com / secret)')
        logger.info('Database ready')
except Exception:
    logger.info('DB module not available or failed to import')
