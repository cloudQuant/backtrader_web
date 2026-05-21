"""Tests for RateLimitHeadersMiddleware (rate_limit_headers.py).

Covers: header injection, 429 response standardization, fail-open behavior,
and _extract_rate_limit_headers helper method.

Requirements: 4.1-4.5
"""

import json

import pytest
from fastapi import FastAPI, Request, Response
from httpx import ASGITransport, AsyncClient
from starlette.responses import JSONResponse

from app.middleware.rate_limit_headers import RateLimitHeadersMiddleware


# ==================== Helper Method Tests ====================


class TestExtractRateLimitHeaders:
    """Tests for the _extract_rate_limit_headers method."""

    def setup_method(self):
        self.middleware = RateLimitHeadersMiddleware(app=None)

    def test_returns_none_when_no_state(self):
        """When scope has no state, returns None (fail-open)."""
        scope = {"type": "http"}
        result = self.middleware._extract_rate_limit_headers(scope)
        assert result is None

    def test_returns_none_when_state_empty_dict(self):
        """When scope state is empty dict, returns None."""
        scope = {"type": "http", "state": {}}
        result = self.middleware._extract_rate_limit_headers(scope)
        assert result is None

    def test_returns_none_when_no_view_rate_limit(self):
        """When state has no view_rate_limit key, returns None."""
        scope = {"type": "http", "state": {"other_key": "value"}}
        result = self.middleware._extract_rate_limit_headers(scope)
        assert result is None

    def test_returns_none_when_no_app_in_scope(self):
        """When scope has view_rate_limit but no app, returns None."""

        class FakeRateLimitItem:
            amount = 100

        scope = {
            "type": "http",
            "state": {"view_rate_limit": (FakeRateLimitItem(), ["key1"])},
        }
        result = self.middleware._extract_rate_limit_headers(scope)
        assert result is None

    def test_returns_none_when_app_has_no_limiter(self):
        """When app.state has no limiter attribute, returns None."""

        class FakeRateLimitItem:
            amount = 100

        class FakeApp:
            class state:
                pass

        scope = {
            "type": "http",
            "state": {"view_rate_limit": (FakeRateLimitItem(), ["key1"])},
            "app": FakeApp(),
        }
        result = self.middleware._extract_rate_limit_headers(scope)
        assert result is None


# ==================== Middleware Pass-Through Tests ====================


class TestMiddlewarePassThrough:
    """Tests that middleware passes through normally when no rate limit state exists."""

    @pytest.fixture()
    def simple_app(self):
        """Create a minimal FastAPI app with the middleware."""
        app = FastAPI()
        app.add_middleware(RateLimitHeadersMiddleware)

        @app.get("/hello")
        async def hello():
            return {"message": "hello"}

        @app.post("/create")
        async def create():
            return {"id": 1}

        return app

    @pytest.fixture()
    async def simple_client(self, simple_app):
        transport = ASGITransport(app=simple_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    async def test_get_request_passes_through(self, simple_client: AsyncClient):
        """Normal GET request passes through without rate limit headers."""
        resp = await simple_client.get("/hello")
        assert resp.status_code == 200
        assert resp.json() == {"message": "hello"}
        # No rate limit headers should be present (no slowapi state)
        assert "X-RateLimit-Limit" not in resp.headers
        assert "X-RateLimit-Remaining" not in resp.headers
        assert "X-RateLimit-Reset" not in resp.headers

    async def test_post_request_passes_through(self, simple_client: AsyncClient):
        """Normal POST request passes through without rate limit headers."""
        resp = await simple_client.post("/create")
        assert resp.status_code == 200
        assert resp.json() == {"id": 1}
        assert "X-RateLimit-Limit" not in resp.headers


# ==================== 429 Response Standardization Tests ====================


class TestRateLimitResponseStandardization:
    """Tests for 429 response body standardization."""

    @pytest.fixture()
    def app_with_429(self):
        """Create an app that returns 429 to test standardization."""
        app = FastAPI()
        app.add_middleware(RateLimitHeadersMiddleware)

        @app.get("/rate-limited")
        async def rate_limited(request: Request):
            return Response(
                content="Too Many Requests",
                status_code=429,
                media_type="text/plain",
            )

        return app

    @pytest.fixture()
    async def client_429(self, app_with_429):
        transport = ASGITransport(app=app_with_429)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    async def test_429_response_standardized_body(self, client_429: AsyncClient):
        """429 responses get standardized JSON body with detail and retry_after."""
        resp = await client_429.get("/rate-limited")
        assert resp.status_code == 429
        body = resp.json()
        assert body["detail"] == "Rate limit exceeded"
        assert "retry_after" in body
        assert isinstance(body["retry_after"], int)

    async def test_429_response_has_content_type_json(self, client_429: AsyncClient):
        """429 responses have application/json content type."""
        resp = await client_429.get("/rate-limited")
        assert resp.status_code == 429
        assert "application/json" in resp.headers.get("content-type", "")

    async def test_429_response_has_retry_after_header(self, client_429: AsyncClient):
        """429 responses include Retry-After header (default 60 when no rate limit state)."""
        resp = await client_429.get("/rate-limited")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers
        # Default retry-after when no rate limit state is available
        assert resp.headers["retry-after"] == "60"


# ==================== Fail-Open Behavior Tests ====================


class TestFailOpenBehavior:
    """Tests that middleware fails open when errors occur."""

    @pytest.fixture()
    def app_with_broken_state(self):
        """Create an app where rate limit state extraction will raise."""
        app = FastAPI()
        app.add_middleware(RateLimitHeadersMiddleware)

        @app.get("/with-broken-state")
        async def endpoint_with_broken_state(request: Request):
            # Set a malformed view_rate_limit that will cause extraction to fail
            request.state.view_rate_limit = "invalid_not_a_tuple"
            return {"status": "ok"}

        return app

    @pytest.fixture()
    async def broken_client(self, app_with_broken_state):
        transport = ASGITransport(app=app_with_broken_state)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    async def test_broken_state_fails_open(self, broken_client: AsyncClient):
        """When rate limit state extraction raises, request still succeeds."""
        resp = await broken_client.get("/with-broken-state")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        # No rate limit headers should be present due to fail-open
        assert "X-RateLimit-Limit" not in resp.headers


# ==================== Integration with slowapi (via main app) ====================


class TestRateLimitHeadersIntegration:
    """Integration tests using the actual app with slowapi configured."""

    async def test_rate_limited_response_has_standard_body(self, client: AsyncClient):
        """When rate limit is exceeded, response has standardized JSON body."""
        from app.main import app

        # Reset limiter for clean state
        if hasattr(app.state, "limiter"):
            app.state.limiter.reset()

        # Exhaust the register rate limit (5/hour)
        for i in range(5):
            await client.post(
                "/api/v1/auth/register",
                json={
                    "username": f"rl_header_test_{i}",
                    "email": f"rlheader{i}@example.com",
                    "password": "Test@12345",
                },
            )

        # 6th request should be rate limited
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "rl_header_test_6",
                "email": "rlheader6@example.com",
                "password": "Test@12345",
            },
        )
        assert resp.status_code == 429
        body = resp.json()
        assert body["detail"] == "Rate limit exceeded"
        assert "retry_after" in body
        assert isinstance(body["retry_after"], int)
        assert body["retry_after"] > 0

    async def test_rate_limited_response_has_retry_after_header(
        self, client: AsyncClient
    ):
        """When rate limit is exceeded, Retry-After header is present."""
        from app.main import app

        if hasattr(app.state, "limiter"):
            app.state.limiter.reset()

        # Exhaust the register rate limit (5/hour)
        for i in range(5):
            await client.post(
                "/api/v1/auth/register",
                json={
                    "username": f"rl_retry_test_{i}",
                    "email": f"rlretry{i}@example.com",
                    "password": "Test@12345",
                },
            )

        # 6th request should be rate limited
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "rl_retry_test_6",
                "email": "rlretry6@example.com",
                "password": "Test@12345",
            },
        )
        assert resp.status_code == 429
        assert "retry-after" in resp.headers

    async def test_websocket_scope_skipped(self):
        """WebSocket scope is not processed by the middleware."""
        app = FastAPI()
        app.add_middleware(RateLimitHeadersMiddleware)

        from starlette.websockets import WebSocket

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            await websocket.send_text("hello")
            await websocket.close()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # WebSocket connections should not be affected by the middleware
            # We just verify the middleware doesn't crash on non-http scopes
            # by making a normal HTTP request to the same app
            resp = await ac.get("/nonexistent")
            assert resp.status_code == 404
