"""
Cache layer - Redis is optional, falls back to memory cache if not configured.
"""
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.config import get_settings


class MemoryCache:
    """In-memory cache - Default implementation, no Redis required.

    Suitable for single-machine deployment or development environments.

    Features:
    - Maximum cache entries limit to prevent unbounded memory growth
    - Periodic cleanup of expired entries to avoid scanning on every write
    - Uses instance variables instead of class variables to avoid sharing across instances
    """
    MAX_ENTRIES = 10000
    CLEANUP_INTERVAL = 300

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._last_cleanup: datetime = datetime.now()

    def _cleanup_expired(self):
        """Clean up expired entries."""
        now = datetime.now()
        if (now - self._last_cleanup).total_seconds() < self.CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        expired_keys = [
            k for k, v in self._cache.items()
            if v.get("expire_at") and now > v["expire_at"]
        ]
        for k in expired_keys:
            del self._cache[k]

    async def get(self, key: str) -> Optional[Any]:
        """Get cached value.

        Args:
            key: Cache key.

        Returns:
            The cached value, or None if not found or expired.
        """
        if key not in self._cache:
            return None

        entry = self._cache[key]
        if entry.get("expire_at") and datetime.now() > entry["expire_at"]:
            del self._cache[key]
            return None

        return entry["value"]

    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Set cached value.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Time-to-live in seconds (0 for no expiration).
        """
        # Periodically cleanup expired entries
        self._cleanup_expired()
        # Remove oldest entry if max entries exceeded
        if len(self._cache) >= self.MAX_ENTRIES:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
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
        self._cache.clear()


class RedisCache:
    """Redis cache - Optional, enabled when REDIS_URL is configured.

    Suitable for distributed deployment.
    """
    def __init__(self, url: str):
        import redis.asyncio as redis
        self.redis = redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Optional[Any]:
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
