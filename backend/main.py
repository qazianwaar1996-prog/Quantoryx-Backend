# backend/main.py
"""
Quantoryx — FastAPI Backend Application Entry Point.

This module initializes the FastAPI application, maps CORS policies,
attaches request middleware, binds exception handlers, registers core trading,
authentication, portfolio, and WebSocket routers, and configures documentation.
It runs automatic database initialization and bootstrap checks on startup.
"""

import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Guarantee the root directory is on the python search path.
# This prevents relative import lookup failures when starting the backend service.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import config
from utils.logging_config import get_logger
from backend.api.endpoints import router as core_router
from backend.api.platform_endpoints import router as platform_router
from backend.api.auth_endpoints import router as auth_router
from backend.api.portfolio_endpoints import router as portfolio_router
from backend.api.ws_endpoints import router as ws_router
from backend.api.godlevel_endpoints import router as godlevel_router
from backend.middleware.logging_middleware import QuantoryxLoggingMiddleware

# Initialize centralized logger
logger = get_logger("backend.main")

# =====================================================================
# APPLICATION LIFESPAN (replaces deprecated @app.on_event)
# =====================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles startup and shutdown lifecycle events."""
    # ── STARTUP ──────────────────────────────────────────────────────
    logger.info("Initializing %s API service workspace directories...", config.SYSTEM_NAME)
    try:
        from utils.path_manager import PathManager
        PathManager.initialize_workspace()

        from backend.database.connection import initialize_database
        if not initialize_database():
            logger.critical("Database startup checks failed. System may operate in degraded state.")
        else:
            logger.info("Database startup checks completed successfully.")

        logger.info("%s API service successfully initialized and operational.", config.SYSTEM_NAME)
        logger.info("  - Swagger Documentation: /docs")
        logger.info("  - ReDoc Documentation:   /redoc")
    except Exception as e:
        logger.critical("Initialization failed on startup: %s", str(e), exc_info=True)

    yield  # Application runs here

    # ── SHUTDOWN ─────────────────────────────────────────────────────
    logger.info("Shutting down %s API service. Cleaning runtime connections.", config.SYSTEM_NAME)


# Initialize FastAPI instance with enterprise documentation settings
app = FastAPI(
    lifespan=lifespan,
    title=f"{config.SYSTEM_NAME} Quantitative Trading Research API",
    description=(
        f"Production-ready backend API service for the {config.SYSTEM_NAME} trading engine.\n\n"
        "Provides REST interfaces for market-regime detection, walk-forward validation, "
        "hyper-parameter optimization, cognitive AI strategy selection, paper-trading execution, "
        "and unified dashboard metrics visualization.\n\n"
        "**Phase 3 Database Persistence Active:** SQLite relational database, SQLAlchemy ORM models, "
        "reusable repository pattern, and secure transaction contexts are operational."
    ),
    version=config.VERSION,
    docs_url="/docs",      # Interactive Swagger UI endpoint
    redoc_url="/redoc",    # Interactive ReDoc UI endpoint
    openapi_url="/openapi.json"
)

# =====================================================================
# CORS MIDDLEWARE & SECURITY HEADERS POLICY
# =====================================================================
# ── CORS origin list ─────────────────────────────────────────────────
# Production GitHub Pages origin + local dev origins.
# "*" is included as a temporary testing fallback — remove it once
# you have confirmed end-to-end connectivity with the explicit origins.
ALLOWED_ORIGINS = [
    "https://qazianwaar1996-prog.github.io",
    "https://qazianwaar1996-prog.github.io/Quantoryx-v6",
    "http://localhost:3000",
    "http://localhost:5173",
    "*",   # temporary fallback — remove in strict-security mode
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers_middleware(request: Request, call_next):
    """
    HTTP middleware introducing modern, strict security response headers.
    """
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # FastAPI's Swagger UI is served by the API but loads its bundled assets
    # from jsDelivr. Keep the policy restrictive while allowing only the
    # documented Swagger stylesheet, script, and favicon hosts.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response


# =====================================================================
# CUSTOM LOGGING MIDDLEWARE
# =====================================================================
app.add_middleware(QuantoryxLoggingMiddleware)

# =====================================================================
# GLOBAL EXCEPTION HANDLERS
# =====================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Standardizes unhandled application crashes into structured JSON responses.
    """
    logger.critical(
        "Unhandled exception triggered during request %s %s: %s",
        request.method, request.url.path, str(exc),
        exc_info=True
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred processing your request.",
            "detail": str(exc) if os.environ.get("QUANTORYX_LOG_LEVEL") == "DEBUG" else "Contact system administrator."
        }
    )


@app.exception_handler(ValueError)
async def value_error_exception_handler(request: Request, exc: ValueError):
    """
    Standardizes bad value violations into clean bad-request responses.
    """
    logger.warning(
        "Request bad value exception on %s %s: %s",
        request.method, request.url.path, str(exc)
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "BadRequest",
            "message": "The request parameters are structurally invalid.",
            "detail": str(exc)
        }
    )


# =====================================================================
# ROUTER REGISTRATION
# =====================================================================
# Each router already declares prefix="/api/..." in its own APIRouter()
# definition, so include_router needs no additional prefix here.

# Register identity and authentication routes  →  /api/auth/...
app.include_router(auth_router)

# Register portfolio, watchlist, and settings routes  →  /api/portfolio/...
app.include_router(portfolio_router)

# Register real-time WebSocket routes  →  /api/ws/...
app.include_router(ws_router)

# Register core analysis and simulation routes  →  /api/health, /api/backtest, …
app.include_router(core_router)

# v6.0 platform features: alerts, journal, signals, billing, builder, help  →  /api/alerts, …
app.include_router(platform_router)
# God-Level Platform — all 28 new endpoints
app.include_router(godlevel_router)


# Standard launch trigger for direct script execution
if __name__ == "__main__":
    import uvicorn
    # Railway injects $PORT at runtime; fall back to 8000 for local dev.
    # host MUST be "0.0.0.0" — Railway's ingress layer requires it;
    # binding to 127.0.0.1 makes the container unreachable from outside.
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
