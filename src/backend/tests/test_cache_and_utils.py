"""
Tests for cache decorator, cache layer, and utility modules.

Covers:
- cache_response decorator
- generate_cache_key utility
- MemoryCache operations
- WebSocket manager basic operations
"""

import pytest

from app.db.cache import MemoryCache
from app.utils.cache_decorator import cache_response, generate_cache_key

# ============================================================
# Cache Decorator Tests
# ============================================================


class TestCacheDecorator:
    """Test cache_response decorator."""

    async def test_cache_response_caches_result(self):
        """Decorated function should cache its result."""
        call_count = 0

        @cache_response(ttl=60, key_prefix="test")
        async def my_func():
            nonlocal call_count
            call_count += 1
            return {"data": "hello"}

        # First call - should execute function
        result1 = await my_func()
        assert result1 == {"data": "hello"}
        assert call_count == 1

        # Second call - should return cached result
        result2 = await my_func()
        assert result2 == {"data": "hello"}
        assert call_count == 1  # Not called again

    async def test_cache_response_vary_by_params(self):
        """Cache should vary by specified parameters."""
        call_count = 0

        @cache_response(ttl=60, key_prefix="test_vary", vary_by_params=["user_id"])
        async def get_data(user_id: str = "default"):
            nonlocal call_count
            call_count += 1
            return {"user": user_id}

        # Different params should result in different cache entries
        result1 = await get_data(user_id="user1")
        assert result1 == {"user": "user1"}
        assert call_count == 1

        result2 = await get_data(user_id="user2")
        assert result2 == {"user": "user2"}
        assert call_count == 2

        # Same param should hit cache
        result3 = await get_data(user_id="user1")
        assert result3 == {"user": "user1"}
        assert call_count == 2  # Not called again


class TestGenerateCacheKey:
    """Test generate_cache_key utility."""

    def test_generates_stable_key(self):
        """Same data should produce same key."""
        key1 = generate_cache_key("test", {"a": 1, "b": 2})
        key2 = generate_cache_key("test", {"a": 1, "b": 2})
        assert key1 == key2

    def test_different_data_different_key(self):
        """Different data should produce different keys."""
        key1 = generate_cache_key("test", {"a": 1})
        key2 = generate_cache_key("test", {"a": 2})
        assert key1 != key2

    def test_key_has_prefix(self):
        """Generated key should start with prefix."""
        key = generate_cache_key("myprefix", {"data": "value"})
        assert key.startswith("myprefix:")

    def test_order_independent(self):
        """Key should be the same regardless of dict key order."""
        key1 = generate_cache_key("test", {"b": 2, "a": 1})
        key2 = generate_cache_key("test", {"a": 1, "b": 2})
        assert key1 == key2


# ============================================================
# MemoryCache Tests
# ============================================================


class TestMemoryCache:
    """Test MemoryCache implementation."""

    @pytest.fixture
    def cache(self):
        return MemoryCache()

    async def test_get_returns_none_for_missing_key(self, cache):
        """get() should return None for non-existent keys."""
        result = await cache.get("nonexistent")
        assert result is None

    async def test_set_and_get(self, cache):
        """set() followed by get() should return the value."""
        await cache.set("key1", {"data": "value"}, ttl=60)
        result = await cache.get("key1")
        assert result == {"data": "value"}

    async def test_delete_removes_key(self, cache):
        """delete() should remove the key."""
        await cache.set("key1", "value1", ttl=60)
        deleted = await cache.delete("key1")
        assert deleted is True
        result = await cache.get("key1")
        assert result is None

    async def test_delete_nonexistent_returns_false(self, cache):
        """delete() should return False for non-existent keys."""
        deleted = await cache.delete("nonexistent")
        assert deleted is False

    async def test_exists_returns_true_for_existing(self, cache):
        """exists() should return True for existing keys."""
        await cache.set("key1", "value1", ttl=60)
        assert await cache.exists("key1") is True

    async def test_exists_returns_false_for_missing(self, cache):
        """exists() should return False for non-existent keys."""
        assert await cache.exists("nonexistent") is False

    async def test_clear_removes_all(self, cache):
        """clear() should remove all entries."""
        await cache.set("key1", "value1", ttl=60)
        await cache.set("key2", "value2", ttl=60)
        await cache.clear()
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    async def test_max_entries_eviction(self, cache):
        """Cache should evict oldest entries when max is reached."""
        cache.MAX_ENTRIES = 5
        for i in range(7):
            await cache.set(f"key{i}", f"value{i}", ttl=60)

        # First two should be evicted
        assert await cache.get("key0") is None
        assert await cache.get("key1") is None
        # Later ones should still exist
        assert await cache.get("key6") == "value6"

    async def test_get_stats(self, cache):
        """get_stats() should return cache statistics."""
        await cache.set("key1", "value1", ttl=60)
        await cache.get("key1")  # hit
        await cache.get("missing")  # miss

        stats = await cache.get_stats()
        assert stats["type"] == "memory"
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["entries"] == 1
        assert stats["hit_rate"] == 0.5

    async def test_ttl_zero_means_no_expiration(self, cache):
        """ttl=0 should mean no expiration."""
        await cache.set("permanent", "value", ttl=0)
        result = await cache.get("permanent")
        assert result == "value"


# ============================================================
# WebSocket Manager Tests
# ============================================================


class TestWebSocketManager:
    """Test WebSocket manager basic operations."""

    def test_manager_importable(self):
        """WebSocket manager should be importable."""
        from app.websocket_manager import manager

        assert manager is not None

    def test_manager_has_connect_method(self):
        """Manager should have connect method."""
        from app.websocket_manager import manager

        assert hasattr(manager, "connect")
        assert callable(manager.connect)

    def test_manager_has_disconnect_method(self):
        """Manager should have disconnect method."""
        from app.websocket_manager import manager

        assert hasattr(manager, "disconnect")
        assert callable(manager.disconnect)

    def test_manager_has_send_to_task_method(self):
        """Manager should have send_to_task method."""
        from app.websocket_manager import manager

        assert hasattr(manager, "send_to_task")
        assert callable(manager.send_to_task)
