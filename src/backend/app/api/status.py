"""
System status and health check endpoints.

Provides observability for cache, database, and application state.
"""

from fastapi import APIRouter

from app.db.cache import get_cache

router = APIRouter()


@router.get("/health", summary="Health check")
async def health_check():
    """Basic health check endpoint.

    Returns:
        200 if application is running.
    """
    return {"status": "healthy"}


@router.get("/status/cache", summary="Cache statistics")
async def get_cache_status():
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
async def get_router_status():
    """Get status of optional routers.

    Returns:
        Dictionary of optional router availability status.
    """
    from app.api.router import optional_router_status

    return {"optional_routers": optional_router_status}
