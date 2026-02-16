import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_memory_cache_cleanup_expired_entries():
    from app.db.cache import MemoryCache

    cache = MemoryCache()
    cache._cache.clear()

    # Force cleanup to run by making last cleanup "old enough".
    cache._last_cleanup = datetime.now() - timedelta(seconds=cache.CLEANUP_INTERVAL + 1)
    cache._cache["expired"] = {"value": 1, "expire_at": datetime.now() - timedelta(seconds=1)}

    await cache.set("k", "v", ttl=60)
    assert "expired" not in cache._cache


@pytest.mark.asyncio
async def test_memory_cache_max_entries_eviction(monkeypatch):
    from app.db.cache import MemoryCache

    cache = MemoryCache()
    cache._cache.clear()
    monkeypatch.setattr(cache, "MAX_ENTRIES", 2, raising=True)

    await cache.set("k1", 1, ttl=60)
    await cache.set("k2", 2, ttl=60)
    await cache.set("k3", 3, ttl=60)

    # Oldest should be evicted.
    assert await cache.get("k1") is None
    assert await cache.get("k2") == 2
    assert await cache.get("k3") == 3


@pytest.mark.asyncio
async def test_redis_cache_get_set_branches(monkeypatch):
    from app.db.cache import RedisCache

    calls = {"setex": 0, "set": 0}

    class FakeRedis:
        async def get(self, key):
            if key == "k":
                return json.dumps({"a": 1})
            return None

        async def setex(self, key, ttl, data):
            calls["setex"] += 1

        async def set(self, key, data):
            calls["set"] += 1

        async def delete(self, key):
            return 1

        async def exists(self, key):
            return 1

    # Patch redis.asyncio.from_url used inside RedisCache.__init__
    import redis.asyncio as redis_asyncio

    monkeypatch.setattr(redis_asyncio, "from_url", lambda *_args, **_kwargs: FakeRedis(), raising=True)

    cache = RedisCache("redis://localhost:6379/0")
    assert await cache.get("k") == {"a": 1}
    assert await cache.get("missing") is None

    await cache.set("k", {"b": 2}, ttl=10)
    await cache.set("k", {"b": 2}, ttl=0)
    assert calls["setex"] == 1
    assert calls["set"] == 1

    assert await cache.delete("k") is True
    assert await cache.exists("k") is True


def test_get_cache_uses_redis_when_configured(monkeypatch):
    import app.db.cache as cache_module

    cache_module._cache_instance = None
    monkeypatch.setattr(cache_module, "get_settings", lambda: SimpleNamespace(REDIS_URL="redis://x"), raising=True)

    # Avoid touching a real Redis client, patch the RedisCache class constructor.
    class DummyRedisCache:
        def __init__(self, url: str):
            self.url = url

    monkeypatch.setattr(cache_module, "RedisCache", DummyRedisCache, raising=True)

    cache = cache_module.get_cache()
    assert isinstance(cache, DummyRedisCache)
    assert cache.url == "redis://x"

