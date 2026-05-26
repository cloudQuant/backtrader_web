"""
System status and health check endpoints.

Provides observability for cache, database, and application state.
"""

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.cache import get_cache
from app.db.database import async_session_maker

router = APIRouter()

# Track application start time for uptime calculation
_app_start_time: float = time.monotonic()

APP_VERSION = "2.0.0"
DB_HEALTH_CHECK_TIMEOUT = 5.0  # seconds


async def _db_ping() -> None:
    """Execute a simple database query."""
    async with async_session_maker() as session:
        await session.execute(text("SELECT 1"))


async def _check_database_health() -> str:
    """Check database connectivity with a timeout.

    Returns:
        "healthy" if database responds within timeout, "unhealthy" otherwise.
    """
    try:
        await asyncio.wait_for(_db_ping(), timeout=DB_HEALTH_CHECK_TIMEOUT)
        return "healthy"
    except (asyncio.TimeoutError, Exception):
        return "unhealthy"


@router.get("/health", summary="Health check")
async def health_check(request: Request) -> Any:
    """Standardized health check endpoint.

    Returns:
        200 with status "healthy" when all systems are operational.
        503 with status "shutting_down" when the application is shutting down.
        503 with status "unhealthy" when database connection fails.
    """
    uptime = round(time.monotonic() - _app_start_time, 1)

    # Return 503 during graceful shutdown so load balancers remove this node
    if getattr(request.app.state, "shutting_down", False):
        return JSONResponse(
            content={
                "status": "shutting_down",
                "version": APP_VERSION,
                "database": "unknown",
                "uptime": uptime,
            },
            status_code=503,
        )

    db_status = await _check_database_health()

    status = "healthy" if db_status == "healthy" else "unhealthy"
    response_body = {
        "status": status,
        "version": APP_VERSION,
        "database": db_status,
        "uptime": uptime,
    }

    if status == "unhealthy":
        return JSONResponse(content=response_body, status_code=503)

    return response_body


@router.get("/status/cache", summary="Cache statistics")
async def get_cache_status() -> dict[str, Any]:
    """Get cache statistics for observability.

    Returns:
        Cache hit/miss counts, hit rate, and capacity metrics.
    """
    cache = get_cache()
    if hasattr(cache, "get_stats"):
        stats = await cache.get_stats()
        return {"cache": stats}
    return {"cache": {"type": "unknown", "stats_unavailable": True}}


@router.get("/status/routers", summary="Optional router status")
async def get_router_status() -> dict[str, Any]:
    """Get status of optional routers.

    Returns:
        Dictionary of optional router availability status.
    """
    from app.api.router import optional_router_status

    return {"optional_routers": optional_router_status}
