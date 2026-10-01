"""
main.py — FastAPI application entry point for Abhedya-Chakra

This is where all routes are registered and the app is configured.

Run with:
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

STATUS: IMPLEMENTED
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db.loader import get_connection  # Initializes DB on startup
from backend.api.routes import accounts, investigate, evidence, reports, ai_narrative, judge

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB connection on startup."""
    logger.info("🚀 Abhedya-Chakra backend starting...")
    conn = get_connection()
    logger.info("✅ DuckDB ready.")
    yield
    logger.info("🔻 Shutting down.")


# ── Application ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Operation Abhedya-Chakra — Freeze-First API",
    description=(
        "Decision-support tool for financial fraud investigation. "
        "Traces victim money through a transaction graph, computes tainted balances, "
        "and recommends which accounts to freeze first to maximize fund preservation. "
        "\n\n"
        "⚠️ PROTOTYPE — Not production-ready. "
        "All outputs require authorized human review. "
        "Currently running on DEVELOPMENT / SYNTHETIC DATA."
    ),
    version="1.0.0-dev",
    lifespan=lifespan,
)

# ── CORS (allow frontend on localhost:3000 during development) ─────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",  # Vite dev server
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ─────────────────────────────────────────────────────────────────────
app.include_router(accounts.router)
app.include_router(investigate.router)
app.include_router(evidence.router)
app.include_router(reports.router)
app.include_router(ai_narrative.router)
app.include_router(judge.router)


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Abhedya-Chakra Freeze-First API",
        "version": "1.0.0-dev",
        "data_label": "DEVELOPMENT / SYNTHETIC DATA",
    }


@app.get("/", tags=["system"])
def root():
    """Root endpoint — redirect hint."""
    return {
        "message": "Operation Abhedya-Chakra API is running.",
        "docs": "/docs",
        "health": "/health",
        "demo": "/api/judge/demo",
        "investigate": "/api/investigate/{account_id}",
    }
