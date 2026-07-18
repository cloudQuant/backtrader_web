"""
API response cache decorator with Redis/Memory backend.

Provides a `@cache_response(ttl, key_prefix)` decorator for FastAPI route handlers
that caches GET responses and adds X-Cache: HIT/MISS headers.

Supports Redis (when REDIS_URL is configured) with fail-open on errors,
and falls back to an in-memory cache otherwise.
"""

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, Protocol, TypeVar

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
TResponse = TypeVar("TResponse", bound=Response)


class CacheBackend(Protocol):
    """Cache backend protocol supporting Redis and memory implementations."""

    async def get(self, key: str) -> bytes | None:
        """Get cached value. Returns None if not found or expired."""
        ...

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        """Set cached value with TTL in seconds."""
        ...

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching the given pattern. Returns count deleted."""
        ...

    async def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        ...


class RedisCacheBackend:
    """Redis-based cache backend using redis.asyncio."""

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._redis = redis.from_url(url, decode_responses=False)

    async def get(self, key: str) -> bytes | None:
        """Get cached value from Redis."""
        result = await self._redis.get(key)
        return result

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        """Set cached value in Redis with TTL."""
        await self._redis.setex(key, ttl, value)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern using SCAN + DEL."""
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                deleted += await self._redis.delete(*keys)
            if cursor == 0:
                break
        return deleted

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        return bool(await self._redis.exists(key))


class MemoryCacheBackend:
    """In-memory cache backend with TTL support.

    Uses an OrderedDict for LRU-style eviction and asyncio.Lock for safety.
    """

    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> bytes | None:
        """Get cached value from memory."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.monotonic() > entry["expires_at"]:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return entry["value"]

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        """Set cached value in memory with TTL."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
            elif len(self._cache) >= self.MAX_ENTRIES:
                self._cache.popitem(last=False)
            self._cache[key] = {
                "value": value,
                "expires_at": time.monotonic() + ttl,
            }

    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching a simple prefix pattern (prefix*)."""
        import fnmatch

        async with self._lock:
            keys_to_delete = [k for k in self._cache if fnmatch.fnmatch(k, pattern)]
            for k in keys_to_delete:
                del self._cache[k]
            return len(keys_to_delete)

    async def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return await self.get(key) is not None


# Singleton cache backend instance
_cache_backend: CacheBackend | None = None


def get_cache_backend() -> CacheBackend:
    """Get or create the cache backend singleton.

    Uses Redis if REDIS_URL is configured, otherwise falls back to memory.
    """
    global _cache_backend
    if _cache_backend is None:
        settings = get_settings()
        if settings.REDIS_URL:
            try:
                _cache_backend = RedisCacheBackend(settings.REDIS_URL)
                logger.info("Response cache using Redis backend")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize Redis cache backend: {type(e).__name__}: {e}. "
                    "Falling back to memory cache."
                )
                _cache_backend = MemoryCacheBackend()
        else:
            _cache_backend = MemoryCacheBackend()
            logger.info("Response cache using in-memory backend")
    return _cache_backend


def _build_cache_key(key_prefix: str, path: str, query_params: dict[str, Any]) -> str:
    """Build cache key from prefix, path, and sorted query params MD5.

    Format: {key_prefix}:{path}:{md5(sorted_query_params)}
    """
    sorted_params = sorted(query_params.items())
    params_str = json.dumps(sorted_params, sort_keys=True, default=str)
    params_hash = hashlib.md5(params_str.encode(), usedforsecurity=False).hexdigest()
    return f"{key_prefix}:{path}:{params_hash}"


def cache_response(
    ttl: int = 60, key_prefix: str = "api"
) -> Callable[[Callable[P, Awaitable[TResponse]]], Callable[P, Awaitable[Response]]]:
    """API response cache decorator for FastAPI route handlers.

    Caches GET request responses and adds X-Cache: HIT/MISS headers.
    Non-GET requests are passed through without caching.
    On cache backend errors, fails open (executes handler directly).

    Args:
        ttl: Cache expiration time in seconds (1-86400).
        key_prefix: Cache key prefix, max 64 characters.

    Returns:
        Decorator function.

    Example:
        @router.get("/strategies")
        @cache_response(ttl=30, key_prefix="strategies")
        async def list_strategies(request: Request):
            ...
    """
    # Validate parameters
    ttl = max(1, min(86400, ttl))
    key_prefix = key_prefix[:64] if key_prefix else "api"

    def decorator(func: Callable[P, Awaitable[TResponse]]) -> Callable[P, Awaitable[Response]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Response:
            # Extract Request from args/kwargs (FastAPI injects it)
            request_obj = kwargs.get("request")
            request: Request | None = request_obj if isinstance(request_obj, Request) else None
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            # Only cache GET requests
            if request is None or request.method.upper() != "GET":
                return await func(*args, **kwargs)

            # Build cache key
            path = request.url.path
            query_params = dict(request.query_params)
            cache_key = _build_cache_key(key_prefix, path, query_params)

            backend = get_cache_backend()

            # Try to get from cache
            try:
                cached_data = await backend.get(cache_key)
                if cached_data is not None:
                    cached = json.loads(cached_data)
                    response = JSONResponse(
                        content=cached["body"],
                        status_code=cached["status_code"],
                    )
                    response.headers["X-Cache"] = "HIT"
                    return response
            except Exception as e:
                logger.warning(f"Cache read error for key '{cache_key}': {type(e).__name__}: {e}")

            # Cache miss - execute handler
            result = await func(*args, **kwargs)

            # Store result in cache
            try:
                # Handle different response types
                if isinstance(result, Response):
                    # For Response objects, extract body and status
                    if isinstance(result, JSONResponse):
                        body = result.body
                        status_code = result.status_code
                        # Decode body for storage
                        body_content = json.loads(body)
                    else:
                        # Add X-Cache header and return as-is for non-JSON
                        result.headers["X-Cache"] = "MISS"
                        return result
                else:
                    # For dict/list returns (FastAPI auto-converts to JSON)
                    # Handle Pydantic models by converting to dict
                    from pydantic import BaseModel as _BaseModel

                    if isinstance(result, _BaseModel):
                        body_content = result.model_dump(mode="json")
                    else:
                        body_content = result
                    status_code = 200

                cache_entry = json.dumps(
                    {
                        "body": body_content,
                        "status_code": status_code,
                    }
                ).encode()

                await backend.set(cache_key, cache_entry, ttl)

                # Build response with X-Cache: MISS
                response = JSONResponse(
                    content=body_content,
                    status_code=status_code,
                )
                response.headers["X-Cache"] = "MISS"
                return response

            except Exception as e:
                logger.warning(f"Cache write error for key '{cache_key}': {type(e).__name__}: {e}")
                # Fail-open: return original result
                if isinstance(result, Response):
                    result.headers["X-Cache"] = "MISS"
                    return result
                response = JSONResponse(content=result, status_code=200)
                response.headers["X-Cache"] = "MISS"
                return response

        return wrapper

    return decorator


async def invalidate_cache(key_prefix: str, pattern: str | None = None) -> int:
    """Invalidate cached entries by prefix/pattern.

    Args:
        key_prefix: The cache key prefix to invalidate.
        pattern: Optional glob pattern to match. If None, invalidates all
                 keys with the given prefix.

    Returns:
        Number of keys deleted.
    """
    backend = get_cache_backend()
    full_pattern = f"{key_prefix}:{pattern}" if pattern else f"{key_prefix}:*"

    try:
        deleted = await backend.delete_pattern(full_pattern)
        if deleted > 0:
            logger.info(f"Invalidated {deleted} cache entries matching '{full_pattern}'")
        return deleted
    except Exception as e:
        logger.warning(
            f"Cache invalidation error for pattern '{full_pattern}': {type(e).__name__}: {e}"
        )
        return 0
