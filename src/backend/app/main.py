"""
FastAPI application entrypoint.

Includes API routing, logging, rate limiting, security headers, and WebSocket
streaming for backtest progress updates.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.router import api_router, optional_router_status
from app.config import get_settings
from app.db.database import ensure_database_ready
from app.main_routes import register_runtime_routes
from app.middleware.exception_handling import register_exception_handlers
from app.middleware.logging import (
    AuditLoggingMiddleware,
    LoggingMiddleware,
    PerformanceLoggingMiddleware,
)
from app.middleware.rate_limit_headers import RateLimitHeadersMiddleware
from app.middleware.security_headers import add_security_headers
from app.rate_limit import limiter
from app.shutdown import GracefulShutdownManager
from app.startup import run_shutdown, run_startup
from app.telemetry import setup_telemetry
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
    app.state.startup_logger = logger
    app.state.ensure_database_ready = ensure_database_ready
    await run_startup(app, settings)
    logger.info("Application ready - accepting requests")
    yield
    logger.info("Shutting down Backtrader Web API...")

    shutdown_mgr = GracefulShutdownManager()
    await shutdown_mgr.initiate(app)
    await run_shutdown(app, settings)

    try:
        from app.services.quote_service import get_quote_service

        get_quote_service().shutdown()
    except Exception:
        pass


app = FastAPI(
    title="Backtrader Web API",
    description=APP_DESCRIPTION,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.state.limiter = limiter

# OpenTelemetry instrumentation (opt-in via OTEL_ENABLED=true)
setup_telemetry(app)
register_exception_handlers(app)
add_security_headers(app)
app.add_middleware(RateLimitHeadersMiddleware)
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

_route_handlers = register_runtime_routes(app, settings, logger, optional_router_status)
globals().update(_route_handlers)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
