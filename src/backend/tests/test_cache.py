"""Cache layer tests."""

from datetime import datetime, timedelta

import pytest

from app.db.cache import MemoryCache, get_cache


@pytest.fixture()
def cache():
    """Provide a clean MemoryCache instance for each test."""
    instance = MemoryCache()
    instance._cache.clear()
    instance._hits = 0
    instance._misses = 0
    return instance


class TestMemoryCache:
    """Tests for in-memory cache implementation."""

    async def test_get_nonexistent(self, cache: MemoryCache):
        assert await cache.get("nope") is None

    async def test_set_and_get(self, cache: MemoryCache):
        await cache.set("key1", {"data": 123}, ttl=60)
        result = await cache.get("key1")
        assert result == {"data": 123}

    async def test_delete(self, cache: MemoryCache):
        await cache.set("key2", "val")
        assert await cache.delete("key2") is True
        assert await cache.get("key2") is None

    async def test_delete_nonexistent(self, cache: MemoryCache):
        assert await cache.delete("nope") is False

    async def test_exists(self, cache: MemoryCache):
        await cache.set("key3", "val")
        assert await cache.exists("key3") is True
        assert await cache.exists("nope") is False

    async def test_clear(self, cache: MemoryCache):
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.clear()
        assert await cache.get("a") is None
        assert await cache.get("b") is None

    async def test_ttl_expiry(self, cache: MemoryCache):
        # Set with immediate expiry
        cache._cache["expired"] = {
            "value": "old",
            "expire_at": datetime.now() - timedelta(seconds=1),
        }
        assert await cache.get("expired") is None

    async def test_set_no_ttl(self, cache: MemoryCache):
        await cache.set("forever", "val", ttl=0)
        assert await cache.get("forever") == "val"

    async def test_get_stats(self, cache: MemoryCache):
        await cache.set("key1", "val1")
        await cache.get("key1")  # hit
        await cache.get("nope")  # miss
        stats = await cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["entries"] == 1
        assert stats["type"] == "memory"

    async def test_concurrent_access(self, cache: MemoryCache):
        import asyncio

        async def set_value(i: int):
            await cache.set(f"key{i}", i)

        async def get_value(i: int):
            return await cache.get(f"key{i}")

        # Concurrent writes
        await asyncio.gather(*[set_value(i) for i in range(10)])
        # Concurrent reads
        results = await asyncio.gather(*[get_value(i) for i in range(10)])
        assert all(r == i for r, i in zip(results, range(10), strict=True))


class TestGetCache:
    """Tests for cache factory function."""

    def test_returns_memory_cache(self):
        cache = get_cache()
        assert cache is not None
        assert isinstance(cache, MemoryCache)
