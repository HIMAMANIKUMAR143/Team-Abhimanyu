"""
Application entry point. Run with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Or via Docker Compose (recommended for the whole team, see README.md).

Interactive API docs (auto-generated, useful for frontend team to test
endpoints without writing any UI code first): http://localhost:8000/docs
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine
from app.routers import reports, verification

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Pollution Tracker API",
    description="Municipal pollution reporting workflow: detect -> assign -> verify.",
    version="0.1.0",
)

# CORS: wide open for hackathon development. If you deploy this publicly
# beyond the demo, narrow allow_origins to your actual frontend URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reports.router)
app.include_router(verification.router)


@app.on_event("startup")
def on_startup():
    # Creates tables if they don't exist. Fine for hackathon speed;
    # for anything longer-lived, switch to Alembic migrations (scaffolded
    # in alembic/ but not required to touch this week).
    Base.metadata.create_all(bind=engine)

    if settings.GEMINI_MOCK_MODE:
        logger.warning(
            "=" * 70 + "\n"
            "GEMINI_API_KEY not set — running in MOCK classification mode.\n"
            "The full pipeline works, but classifications are simulated.\n"
            "Get a free key at aistudio.google.com, add it to .env, restart.\n"
            + "=" * 70
        )
    else:
        logger.info("Gemini API key detected — running in REAL classification mode.")


@app.get("/")
def root():
    return {
        "status": "ok",
        "mode": "MOCK" if settings.GEMINI_MOCK_MODE else "LIVE",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
