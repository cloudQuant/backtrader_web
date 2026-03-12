"""Cache layer tests."""

from datetime import datetime, timedelta

from app.db.cache import MemoryCache, get_cache


class TestMemoryCache:
    """Tests for in-memory cache implementation."""

    async def test_get_nonexistent(self):
        """Test getting a non-existent key.

        Returns:
            None
        """
        cache = MemoryCache()
        cache._cache.clear()
        assert await cache.get("nope") is None

    async def test_set_and_get(self):
        """Test setting and getting a value.

        Returns:
            None
        """
        cache = MemoryCache()
        cache._cache.clear()
        await cache.set("key1", {"data": 123}, ttl=60)
        result = await cache.get("key1")
        assert result == {"data": 123}

    async def test_delete(self):
        """Test deleting a key.

        Returns:
            None
        """
        cache = MemoryCache()
        cache._cache.clear()
        await cache.set("key2", "val")
        assert await cache.delete("key2") is True
        assert await cache.get("key2") is None

    async def test_delete_nonexistent(self):
        """Test deleting a non-existent key.

        Returns:
            None
        """
        cache = MemoryCache()
        cache._cache.clear()
        assert await cache.delete("nope") is False

    async def test_exists(self):
        """Test checking if a key exists.

        Returns:
            None
        """
        cache = MemoryCache()
        cache._cache.clear()
        await cache.set("key3", "val")
        assert await cache.exists("key3") is True
        assert await cache.exists("nope") is False

    async def test_clear(self):
        """Test clearing the cache.

        Returns:
            None
        """
        cache = MemoryCache()
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.clear()
        assert await cache.get("a") is None
        assert await cache.get("b") is None

    async def test_ttl_expiry(self):
        """Test TTL expiration.

        Returns:
            None
        """
        cache = MemoryCache()
        cache._cache.clear()
        # Set with immediate expiry
        cache._cache["expired"] = {
            "value": "old",
            "expire_at": datetime.now() - timedelta(seconds=1),
        }
        assert await cache.get("expired") is None

    async def test_set_no_ttl(self):
        """Test setting a value without TTL.

        Returns:
            None
        """
        cache = MemoryCache()
        cache._cache.clear()
        await cache.set("forever", "val", ttl=0)
        assert await cache.get("forever") == "val"


class TestGetCache:
    """Tests for cache factory function."""

    def test_returns_memory_cache(self):
        """Test that get_cache returns MemoryCache instance.

        Returns:
            None
        """
        cache = get_cache()
        assert cache is not None
        assert isinstance(cache, MemoryCache)
