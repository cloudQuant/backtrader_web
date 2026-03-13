"""
FastAPI application entrypoint.

Includes API routing, logging, rate limiting, security headers, and WebSocket
streaming for backtest progress updates.
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.router import api_router
from app.config import get_settings
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
from app.websocket_manager import manager as ws_manager

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
    await ensure_database_ready()
    logger.info("Database schema and default admin verified")
    if "change-in-production" in settings.SECRET_KEY or (
        "change-in-production" in settings.JWT_SECRET_KEY
    ):
        logger.warning("Using default security key. Set SECRET_KEY / JWT_SECRET_KEY in production.")
    if settings.ADMIN_PASSWORD == "admin123":
        logger.warning("Default admin password is admin123. Change ADMIN_PASSWORD in production.")
    logger.info("Application ready")
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
app.add_middleware(PerformanceLoggingMiddleware, slow_request_threshold=5.0)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", summary="Root route")
async def root():
    """Return service metadata."""
    return {
        "service": "Backtrader Web API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "features": [
            "Strategy Management",
            "Backtesting Analysis",
            "Parameter Optimization",
            "Report Export",
            "WebSocket Real-time Push",
            "Paper Trading",
            "Live Trading Integration",
            "Backtest Result Comparison",
            "Strategy Version Control",
            "Real-time Market Data",
            "Monitoring and Alerts",
            "API Rate Limiting",
            "Secure Sandbox Execution",
        ],
    }


@app.get("/health", summary="Health check")
async def health_check():
    """Return service and database health."""
    from sqlalchemy import text

    from app.db.database import async_session_maker

    db_status = "disconnected"
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        logger.exception("Health check database probe failed")

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": settings.APP_NAME,
        "database": db_status,
        "backtrader": "available",
        "version": "2.0.0",
    }


@app.get("/info", summary="System information")
async def system_info():
    """Return high-level runtime information."""
    return {
        "version": "2.0.0",
        "database_type": settings.DATABASE_TYPE,
        "features": {
            "sandbox_execution": True,
            "rbac": True,
            "rate_limiting": True,
            "optimization": True,
            "report_export": True,
            "websocket": True,
            "paper_trading": True,
            "live_trading": True,
            "version_control": True,
            "comparison": True,
            "realtime_data": True,
            "monitoring": True,
        },
    }


@app.websocket("/ws/backtest/{task_id}")
async def websocket_backtest_progress(websocket: WebSocket, task_id: str):
    """Stream backtest progress updates over WebSocket."""
    client_id = str(uuid.uuid4())[:8]
    await ws_manager.connect(websocket, task_id, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, task_id, client_id)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
