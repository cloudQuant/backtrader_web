"""Tests for API response cache decorator (response_cache.py).

Covers: cache hit/miss, TTL expiry, Redis error fallback, write-operation invalidation,
GET-only caching, and X-Cache header behavior.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.utils.response_cache import (
    MemoryCacheBackend,
    _build_cache_key,
    cache_response,
    invalidate_cache,
)

# ==================== MemoryCacheBackend Unit Tests ====================


class TestMemoryCacheBackend:
    """Tests for the in-memory cache backend."""

    @pytest.fixture()
    def backend(self) -> MemoryCacheBackend:
        return MemoryCacheBackend()

    async def test_get_nonexistent_returns_none(self, backend: MemoryCacheBackend):
        assert await backend.get("nonexistent") is None

    async def test_set_and_get(self, backend: MemoryCacheBackend):
        await backend.set("key1", b'{"data": 1}', ttl=60)
        result = await backend.get("key1")
        assert result == b'{"data": 1}'

    async def test_ttl_expiry(self, backend: MemoryCacheBackend):
        await backend.set("expire_me", b"value", ttl=1)
        # Manually expire the entry
        async with backend._lock:
            backend._cache["expire_me"]["expires_at"] = time.monotonic() - 1
        assert await backend.get("expire_me") is None

    async def test_exists(self, backend: MemoryCacheBackend):
        await backend.set("exists_key", b"val", ttl=60)
        assert await backend.exists("exists_key") is True
        assert await backend.exists("nope") is False

    async def test_delete_pattern(self, backend: MemoryCacheBackend):
        await backend.set("api:/path:abc", b"1", ttl=60)
        await backend.set("api:/path:def", b"2", ttl=60)
        await backend.set("other:/path:ghi", b"3", ttl=60)
        deleted = await backend.delete_pattern("api:*")
        assert deleted == 2
        assert await backend.get("other:/path:ghi") == b"3"

    async def test_max_entries_eviction(self, backend: MemoryCacheBackend):
        backend.MAX_ENTRIES = 5
        for i in range(6):
            await backend.set(f"key{i}", f"val{i}".encode(), ttl=60)
        # First entry should be evicted
        assert await backend.get("key0") is None
        assert await backend.get("key5") == b"val5"


# ==================== Cache Key Building Tests ====================


class TestBuildCacheKey:
    """Tests for cache key generation."""

    def test_basic_key_format(self):
        key = _build_cache_key("api", "/v1/strategies", {"page": "1", "size": "10"})
        assert key.startswith("api:/v1/strategies:")
        # MD5 hash is 32 hex chars
        hash_part = key.split(":")[-1]
        assert len(hash_part) == 32

    def test_sorted_params_produce_same_key(self):
        key1 = _build_cache_key("api", "/path", {"b": "2", "a": "1"})
        key2 = _build_cache_key("api", "/path", {"a": "1", "b": "2"})
        assert key1 == key2

    def test_different_params_produce_different_keys(self):
        key1 = _build_cache_key("api", "/path", {"a": "1"})
        key2 = _build_cache_key("api", "/path", {"a": "2"})
        assert key1 != key2

    def test_empty_params(self):
        key = _build_cache_key("prefix", "/path", {})
        assert key.startswith("prefix:/path:")


# ==================== Decorator Integration Tests ====================


@pytest.fixture()
def test_app():
    """Create a minimal FastAPI app with cached endpoints for testing."""
    import app.utils.response_cache as rc_module

    # Reset the singleton for each test
    rc_module._cache_backend = None

    test_app = FastAPI()
    call_count = {"value": 0}

    @test_app.get("/cached")
    @cache_response(ttl=60, key_prefix="test")
    async def cached_endpoint(request: Request):
        call_count["value"] += 1
        return {"message": "hello", "count": call_count["value"]}

    @test_app.post("/write")
    @cache_response(ttl=60, key_prefix="test")
    async def write_endpoint(request: Request):
        call_count["value"] += 1
        return {"message": "written", "count": call_count["value"]}

    test_app.state.call_count = call_count
    return test_app


@pytest.fixture()
async def test_client(test_app):
    """Create test client for the test app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestCacheResponseDecorator:
    """Integration tests for the @cache_response decorator."""

    async def test_first_request_returns_miss(self, test_client: AsyncClient):
        resp = await test_client.get("/cached")
        assert resp.status_code == 200
        assert resp.headers.get("x-cache") == "MISS"
        assert resp.json()["message"] == "hello"

    async def test_second_request_returns_hit(self, test_client: AsyncClient):
        # First request - MISS
        resp1 = await test_client.get("/cached")
        assert resp1.headers.get("x-cache") == "MISS"

        # Second request - HIT (same params)
        resp2 = await test_client.get("/cached")
        assert resp2.headers.get("x-cache") == "HIT"
        assert resp2.json() == resp1.json()

    async def test_different_params_different_cache(self, test_client: AsyncClient):
        resp1 = await test_client.get("/cached?page=1")
        assert resp1.headers.get("x-cache") == "MISS"

        resp2 = await test_client.get("/cached?page=2")
        assert resp2.headers.get("x-cache") == "MISS"

        # Same params as first request - HIT
        resp3 = await test_client.get("/cached?page=1")
        assert resp3.headers.get("x-cache") == "HIT"

    async def test_post_request_not_cached(self, test_client: AsyncClient):
        resp = await test_client.post("/write")
        assert resp.status_code == 200
        # POST should not have X-Cache header
        assert "x-cache" not in resp.headers

    async def test_handler_not_called_on_cache_hit(self, test_client: AsyncClient, test_app):
        call_count = test_app.state.call_count
        initial = call_count["value"]

        await test_client.get("/cached")
        assert call_count["value"] == initial + 1

        await test_client.get("/cached")
        # Handler should NOT be called again
        assert call_count["value"] == initial + 1


class TestCacheInvalidation:
    """Tests for cache invalidation."""

    async def test_invalidate_clears_cache(self, test_client: AsyncClient, test_app):
        # First request - MISS
        resp1 = await test_client.get("/cached")
        assert resp1.headers.get("x-cache") == "MISS"

        # Second request - HIT
        resp2 = await test_client.get("/cached")
        assert resp2.headers.get("x-cache") == "HIT"

        # Invalidate
        deleted = await invalidate_cache("test")
        assert deleted >= 1

        # Next request should be MISS again
        resp3 = await test_client.get("/cached")
        assert resp3.headers.get("x-cache") == "MISS"


class TestCacheFailOpen:
    """Tests for fail-open behavior when cache backend errors occur."""

    async def test_cache_read_error_falls_through(self):
        """When cache.get raises, handler should still execute."""
        import app.utils.response_cache as rc_module

        rc_module._cache_backend = None

        app_instance = FastAPI()

        @app_instance.get("/fallback")
        @cache_response(ttl=60, key_prefix="fail")
        async def fallback_endpoint(request: Request):
            return {"status": "ok"}

        # Patch get_cache_backend to return a broken backend
        broken_backend = AsyncMock()
        broken_backend.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        broken_backend.set = AsyncMock(side_effect=ConnectionError("Redis down"))

        with patch.object(rc_module, "get_cache_backend", return_value=broken_backend):
            transport = ASGITransport(app=app_instance)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/fallback")
                assert resp.status_code == 200
                assert resp.json() == {"status": "ok"}
                assert resp.headers.get("x-cache") == "MISS"
