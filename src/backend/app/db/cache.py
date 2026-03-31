"""
Cache layer - Redis is optional, falls back to memory cache if not configured.
"""

import asyncio
import json
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any

from app.config import get_settings


class MemoryCache:
    """In-memory cache - Default implementation, no Redis required.

    Suitable for single-machine deployment or development environments.

    Features:
    - Maximum cache entries limit to prevent unbounded memory growth
    - Periodic cleanup of expired entries to avoid scanning on every write
    - Uses instance variables instead of class variables to avoid sharing across instances
    - Observability: hit/miss counts and capacity metrics
    - Thread-safe with asyncio.Lock for async context
    """

    MAX_ENTRIES = 10000
    CLEANUP_INTERVAL = 300

    def __init__(self):
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._last_cleanup: datetime = datetime.now()
        self._lock = asyncio.Lock()
        # Observability metrics
        self._hits = 0
        self._misses = 0

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics for observability.

        Returns:
            Dictionary with hit_rate, hits, misses, entries, max_entries.
        """
        async with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 4),
                "entries": len(self._cache),
                "max_entries": self.MAX_ENTRIES,
                "type": "memory",
            }

    def _cleanup_expired_unlocked(self):
        """Clean up expired entries (must be called while holding lock)."""
        now = datetime.now()
        if (now - self._last_cleanup).total_seconds() < self.CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        expired_keys = [
            k for k, v in self._cache.items() if v.get("expire_at") and now > v["expire_at"]
        ]
        for k in expired_keys:
            del self._cache[k]

    async def get(self, key: str) -> Any | None:
        """Get cached value.

        Args:
            key: Cache key.

        Returns:
            The cached value, or None if not found or expired.
        """
        async with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]
            if entry.get("expire_at") and datetime.now() > entry["expire_at"]:
                del self._cache[key]
                self._misses += 1
                return None

            self._cache.move_to_end(key)
            self._hits += 1
            return entry["value"]

    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Set cached value.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Time-to-live in seconds (0 for no expiration).
        """
        async with self._lock:
            self._cleanup_expired_unlocked()
            if key in self._cache:
                del self._cache[key]
            elif len(self._cache) >= self.MAX_ENTRIES:
                self._cache.popitem(last=False)
            expire_at = datetime.now() + timedelta(seconds=ttl) if ttl > 0 else None
            self._cache[key] = {
                "value": value,
                "expire_at": expire_at,
            }

    async def delete(self, key: str) -> bool:
        """Delete cached value.

        Args:
            key: Cache key.

        Returns:
            True if the key was deleted, False otherwise.
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists.

        Args:
            key: Cache key.

        Returns:
            True if key exists and is not expired.
        """
        return await self.get(key) is not None

    async def clear(self):
        """Clear all cached values."""
        async with self._lock:
            self._cache.clear()


class RedisCache:
    """Redis cache - Optional, enabled when REDIS_URL is configured.

    Suitable for distributed deployment.
    """

    def __init__(self, url: str):
        import redis.asyncio as redis

        self.redis = redis.from_url(url, decode_responses=True)

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics for observability.

        Returns:
            Dictionary with Redis info.
        """
        try:
            info = await self.redis.info("memory")
            dbsize = await self.redis.dbsize()
            return {
                "type": "redis",
                "used_memory": info.get("used_memory_human", "unknown"),
                "entries": dbsize,
                "connected_clients": info.get("connected_clients", 0),
            }
        except (ConnectionError, TimeoutError, OSError):
            return {"type": "redis", "error": "unable to get stats"}

    async def get(self, key: str) -> Any | None:
        """Get cached value.

        Args:
            key: Cache key.

        Returns:
            The cached value, or None if not found.
        """
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        return None

    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Set cached value.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Time-to-live in seconds (0 for no expiration).
        """
        data = json.dumps(value, default=str)
        if ttl > 0:
            await self.redis.setex(key, ttl, data)
        else:
            await self.redis.set(key, data)

    async def delete(self, key: str) -> bool:
        """Delete cached value.

        Args:
            key: Cache key.

        Returns:
            True if the key was deleted, False otherwise.
        """
        return await self.redis.delete(key) > 0

    async def exists(self, key: str) -> bool:
        """Check if key exists.

        Args:
            key: Cache key.

        Returns:
            True if key exists.
        """
        return await self.redis.exists(key) > 0


# Cache singleton
_cache_instance = None


def get_cache():
    """Get cache instance - Uses Redis if available, otherwise memory cache.

    Returns:
        The cache instance (RedisCache or MemoryCache).
    """
    global _cache_instance

    if _cache_instance is None:
        settings = get_settings()
        if settings.REDIS_URL:
            _cache_instance = RedisCache(settings.REDIS_URL)
        else:
            _cache_instance = MemoryCache()

    return _cache_instance
