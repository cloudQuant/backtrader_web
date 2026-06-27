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

CAPABILITY_DOMAINS: list[dict[str, Any]] = [
    {
        "id": "data",
        "label": "Market Data",
        "capabilities": [
            {"id": "data.market", "api_prefixes": ["/api/v1/data"], "optional": ["data"]},
            {"id": "data.quote", "api_prefixes": ["/api/v1/quote"], "optional": ["quote"]},
            {
                "id": "data.governance",
                "api_prefixes": ["/api/v1/data-governance"],
                "optional": [],
                "requires_admin": True,
            },
            {
                "id": "data.topics",
                "api_prefixes": ["/api/v1/data-topics"],
                "optional": [],
            },
            {"id": "data.sync", "api_prefixes": ["/api/v1/data/sync"], "optional": ["data_sync"]},
            {
                "id": "data.intelligence",
                "api_prefixes": [
                    "/api/v1/news-intelligence",
                    "/api/v1/options-chain",
                    "/api/v1/scanners",
                ],
                "optional": [],
            },
        ],
    },
    {
        "id": "research",
        "label": "Strategy Research",
        "capabilities": [
            {"id": "research.strategies", "api_prefixes": ["/api/v1/strategy"], "optional": []},
            {"id": "research.workspaces", "api_prefixes": ["/api/v1/workspace"], "optional": []},
            {"id": "research.backtests", "api_prefixes": ["/api/v1/backtests"], "optional": []},
            {
                "id": "research.optimization",
                "api_prefixes": ["/api/v1/optimization", "/api/v1/workspace"],
                "optional": [],
            },
            {
                "id": "research.trust",
                "api_prefixes": ["/api/v1/strategy/score", "/api/v1/strategy/overfitting"],
                "optional": [],
            },
        ],
    },
    {
        "id": "trading",
        "label": "Trading Operations",
        "capabilities": [
            {"id": "trading.live", "api_prefixes": ["/api/v1/live-trading"], "optional": []},
            {
                "id": "trading.simulation",
                "api_prefixes": ["/api/v1/simulation", "/api/v1/paper-trading"],
                "optional": ["paper_trading"],
            },
            {
                "id": "trading.monitoring",
                "api_prefixes": ["/api/v1/monitoring"],
                "optional": ["monitoring"],
            },
            {
                "id": "trading.ai",
                "api_prefixes": ["/api/v1/ai-trading"],
                "optional": ["ai_trading"],
            },
        ],
    },
    {
        "id": "portfolio",
        "label": "Portfolio & Risk",
        "capabilities": [
            {"id": "portfolio.overview", "api_prefixes": ["/api/v1/portfolio"], "optional": []},
            {
                "id": "portfolio.risk",
                "api_prefixes": ["/api/v1/risk-analytics"],
                "optional": [],
            },
            {
                "id": "portfolio.attribution",
                "api_prefixes": ["/api/v1/factor-lib", "/api/v1/perf-attribution"],
                "optional": [],
            },
        ],
    },
    {
        "id": "ai",
        "label": "AI Knowledge",
        "capabilities": [
            {
                "id": "ai.knowledge_base",
                "api_prefixes": ["/api/v1/knowledge-base"],
                "optional": ["knowledge_base"],
            },
            {"id": "ai.rag", "api_prefixes": ["/api/v1/rag"], "optional": ["rag"]},
            {"id": "ai.chat", "api_prefixes": ["/api/v1/kb-chat"], "optional": ["kb_chat"]},
            {
                "id": "ai.observability",
                "api_prefixes": ["/api/v1/admin/ai"],
                "optional": [],
                "requires_admin": True,
            },
            {
                "id": "ai.prompt_governance",
                "api_prefixes": ["/api/v1/admin/prompt-templates"],
                "optional": [],
                "requires_admin": True,
            },
        ],
    },
    {
        "id": "admin",
        "label": "Platform Admin",
        "capabilities": [
            {
                "id": "admin.status",
                "api_prefixes": ["/api/v1/status", "/api/v1/health"],
                "optional": [],
                "requires_admin": True,
            },
            {
                "id": "admin.audit",
                "api_prefixes": ["/api/v1/audit"],
                "optional": [],
                "requires_admin": True,
            },
        ],
    },
]


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


def _build_capability_status(
    capability: dict[str, Any],
    optional_router_status: dict[str, dict[str, str | bool | None]],
) -> dict[str, Any]:
    optional_names = capability.get("optional", [])
    unavailable = [
        name
        for name in optional_names
        if not optional_router_status.get(name, {"available": True}).get("available")
    ]
    available = len(unavailable) == 0
    degraded_reason = None
    if unavailable:
        details = []
        for name in unavailable:
            error = optional_router_status.get(name, {}).get("error")
            details.append(f"{name}: {error}" if error else name)
        degraded_reason = "; ".join(details)

    return {
        "id": capability["id"],
        "api_prefixes": capability.get("api_prefixes", []),
        "available": available,
        "requires_admin": bool(capability.get("requires_admin", False)),
        "degraded_reason": degraded_reason,
        "optional_routers": optional_names,
    }


@router.get("/status/capabilities", summary="Product capability status")
async def get_capability_status() -> dict[str, Any]:
    """Return product-domain capability availability.

    This endpoint is a product-level aggregation for workbench pages. It keeps
    `/status/routers` as the router-level source of truth and only reshapes that
    data into the six product domains used by the frontend navigation.
    """
    from app.api.router import optional_router_status

    domains = []
    for domain in CAPABILITY_DOMAINS:
        capability_statuses = [
            _build_capability_status(capability, optional_router_status)
            for capability in domain["capabilities"]
        ]
        domains.append(
            {
                "id": domain["id"],
                "label": domain["label"],
                "status": (
                    "available"
                    if all(capability["available"] for capability in capability_statuses)
                    else "degraded"
                ),
                "capabilities": capability_statuses,
            }
        )

    return {"domains": domains}
