"""
FastAPI application entrypoint.

Includes API routing, logging, rate limiting, security headers, and WebSocket
streaming for backtest progress updates.
"""

import time as _time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.backtest_enhanced import websocket_endpoint as stream_backtest_progress
from app.api.router import api_router, optional_router_status
from app.config import _DEFAULT_PASSWORDS, _DEFAULT_SECRETS, get_settings
from app.db.database import ensure_database_ready
from app.middleware.exception_handling import register_exception_handlers
from app.middleware.logging import (
    AuditLoggingMiddleware,
    LoggingMiddleware,
    PerformanceLoggingMiddleware,
)
from app.middleware.security_headers import add_security_headers
from app.rate_limit import limiter
from app.utils.logger import setup_logger

settings = get_settings()
logger = setup_logger(__name__)

APP_DESCRIPTION = """
# Backtrader Web API

Backtrader Web provides authenticated REST endpoints and WebSocket streams for
strategy management, backtests, optimization, portfolio workflows, and
monitoring.

## Runtime Notes

- Frontend: Vue 3 + TypeScript
- Backend: FastAPI + SQLAlchemy 2.x
- Database: SQLite / PostgreSQL / MySQL
- Long-running backtests are currently launched by the API process, while task
  status is persisted in the database for later queries.

## API Documentation

- Swagger UI: `/docs`
- ReDoc UI: `/redoc`
- OpenAPI Spec: `/openapi.json`
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting Backtrader Web API...")

    # Database initialization with clear status logging
    if settings.DB_AUTO_CREATE_SCHEMA:
        logger.info("DB_AUTO_CREATE_SCHEMA=true: Creating database tables...")
        await ensure_database_ready()
        logger.info("Database tables created/verified successfully")
    else:
        logger.info("DB_AUTO_CREATE_SCHEMA=false: Verifying database connection...")
        await ensure_database_ready()
        logger.info("Database connection verified (schema auto-creation skipped)")

    # Cache initialization status
    cache_type = "Redis" if settings.REDIS_URL else "Memory"
    logger.info(f"Cache backend: {cache_type}")

    # Security warnings
    if settings.SECRET_KEY in _DEFAULT_SECRETS or settings.JWT_SECRET_KEY in _DEFAULT_SECRETS:
        logger.warning("Using default security key. Set SECRET_KEY / JWT_SECRET_KEY in production.")
    if settings.ADMIN_PASSWORD.lower() in _DEFAULT_PASSWORDS:
        logger.warning("Default admin password detected. Change ADMIN_PASSWORD in production.")

    logger.info("Application ready - accepting requests")
    yield
    logger.info("Shutting down Backtrader Web API...")


app = FastAPI(
    title="Backtrader Web API",
    description=APP_DESCRIPTION,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.state.limiter = limiter

register_exception_handlers(app)
add_security_headers(app)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuditLoggingMiddleware)
app.add_middleware(PerformanceLoggingMiddleware, slow_request_threshold=0.5)

app.include_router(api_router, prefix="/api/v1")


_feature_flags_cache: dict[str, bool] | None = None


def _get_feature_flags() -> dict[str, bool]:
    global _feature_flags_cache
    if _feature_flags_cache is not None:
        return _feature_flags_cache

    route_paths = {route.path for route in app.routes if hasattr(route, "path")}

    def has_prefix(prefix: str) -> bool:
        return any(path.startswith(prefix) for path in route_paths)

    _feature_flags_cache = {
        "sandbox_execution": True,
        "rbac": True,
        "rate_limiting": True,
        "optimization": has_prefix("/api/v1/optimization")
        or has_prefix("/api/v1/backtests/optimization"),
        "report_export": any(
            path.startswith("/api/v1/backtests/") and "/report/" in path for path in route_paths
        ),
        "websocket": "/ws/backtest/{task_id}" in route_paths
        or "/api/v1/backtests/ws/backtest/{task_id}" in route_paths,
        "paper_trading": has_prefix("/api/v1/paper-trading"),
        "live_trading": has_prefix("/api/v1/live-trading"),
        "version_control": has_prefix("/api/v1/strategy-versions"),
        "comparison": has_prefix("/api/v1/comparisons"),
        "realtime_data": has_prefix("/api/v1/realtime"),
        "monitoring": has_prefix("/api/v1/monitoring"),
    }
    return _feature_flags_cache


def _get_root_features() -> list[str]:
    feature_flags = _get_feature_flags()
    features = [
        "Strategy Management",
        "Backtesting Analysis",
        "API Rate Limiting",
        "Secure Sandbox Execution",
    ]

    optional_features = [
        ("optimization", "Parameter Optimization"),
        ("report_export", "Report Export"),
        ("websocket", "WebSocket Real-time Push"),
        ("paper_trading", "Paper Trading"),
        ("live_trading", "Live Trading Integration"),
        ("comparison", "Backtest Result Comparison"),
        ("version_control", "Strategy Version Control"),
        ("realtime_data", "Real-time Market Data"),
        ("monitoring", "Monitoring and Alerts"),
    ]
    for key, label in optional_features:
        if feature_flags.get(key):
            features.append(label)
    return features


def _get_optional_router_status() -> dict[str, dict[str, str | bool | None]]:
    return {
        name: {"available": status["available"], "error": status["error"]}
        for name, status in optional_router_status.items()
    }


@app.get("/", summary="Root route")
async def root():
    """Return service metadata."""
    return {
        "service": "Backtrader Web API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "features": _get_root_features(),
    }


_health_cache: dict | None = None
_health_cache_ts: float = 0
_HEALTH_CACHE_TTL = 10  # seconds


@app.get("/health", summary="Health check")
async def health_check():
    """Return service and database health (cached for 10 seconds)."""
    global _health_cache, _health_cache_ts

    now = _time.monotonic()
    if _health_cache is not None and (now - _health_cache_ts) < _HEALTH_CACHE_TTL:
        return _health_cache

    from sqlalchemy import text

    from app.db.database import async_session_maker

    db_status = "disconnected"
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        logger.exception("Health check database probe failed")

    unavailable_optional_routers = sorted(
        name
        for name, status in _get_optional_router_status().items()
        if not status["available"]
    )

    result = {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": settings.APP_NAME,
        "database": db_status,
        "backtrader": "available",
        "optional_routers": {
            "unavailable_count": len(unavailable_optional_routers),
            "unavailable": unavailable_optional_routers,
        },
        "version": "2.0.0",
    }

    _health_cache = result
    _health_cache_ts = now
    return result


@app.get("/info", summary="System information")
async def system_info():
    """Return high-level runtime information."""
    return {
        "version": "2.0.0",
        "database_type": settings.DATABASE_TYPE,
        "features": _get_feature_flags(),
        "optional_routers": _get_optional_router_status(),
    }


@app.websocket("/ws/backtest/{task_id}")
async def websocket_backtest_progress(websocket: WebSocket, task_id: str):
    """Stream backtest progress updates over WebSocket."""
    await stream_backtest_progress(websocket, task_id)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
