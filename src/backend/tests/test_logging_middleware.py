"""
Logging middleware tests.

Tests:
- LoggingMiddleware initialization and configuration
- AuditLoggingMiddleware initialization
- PerformanceLoggingMiddleware initialization
- Request context with user_id
"""

import pytest
from fastapi import Response
from starlette.requests import Request


class TestLoggingMiddleware:
    """Tests for LoggingMiddleware."""

    def test_initialization(self):
        """Test middleware initialization."""
        from app.middleware.logging import LoggingMiddleware

        async def app(scope, receive, send):
            del scope, receive, send

        middleware = LoggingMiddleware(app)
        assert middleware.log_body is False
        assert middleware.log_headers is False
        # Iteration 193: default skips moved to prefix matching (_is_skip_path);
        # the legacy per-instance skip set is empty unless passed explicitly.
        assert middleware.skip_paths == frozenset()
        from app.middleware.logging import _is_skip_path

        assert _is_skip_path("/health") is True
        assert _is_skip_path("/health/sub") is True
        assert _is_skip_path("/api/v1/metrics") is True
        assert _is_skip_path("/api/v1/metrics/sub") is True
        assert _is_skip_path("/api/v1/users") is False

    def test_initialization_with_options(self):
        """Test middleware initialization with options."""
        from app.middleware.logging import LoggingMiddleware

        async def app(scope, receive, send):
            del scope, receive, send

        middleware = LoggingMiddleware(app, log_body=True, log_headers=True, skip_paths=["/custom"])
        assert middleware.log_body is True
        assert middleware.log_headers is True
        assert "/custom" in middleware.skip_paths

    @pytest.mark.asyncio
    async def test_logging_includes_user_id_from_request_state(self, monkeypatch):
        """Test that completion logs include user_id from request.state."""
        from app.middleware.logging import LoggingMiddleware

        call_kwargs = []

        class StubLogger:
            def info(self, _message, **kwargs):
                call_kwargs.append(kwargs)

            def error(self, _message, **kwargs):
                call_kwargs.append(kwargs)

        async def app(scope, receive, send):
            del scope, receive, send

        monkeypatch.setattr(
            "app.middleware.logging.bind_request_context",
            lambda **_kwargs: StubLogger(),
            raising=True,
        )

        middleware = LoggingMiddleware(app)
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/auth/me",
                "headers": [],
                "query_string": b"",
            }
        )

        async def call_next(req):
            req.state.user_id = "test_user_123"
            return Response(status_code=200)

        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 200
        assert response.headers["X-Request-ID"]
        assert any(kwargs.get("user_id") == "test_user_123" for kwargs in call_kwargs)

    @pytest.mark.asyncio
    async def test_asgi_call_stores_request_id_in_scope_state(self, monkeypatch):
        """Test ASGI middleware exposes the response request ID to downstream handlers."""
        from app.middleware.logging import LoggingMiddleware

        class StubLogger:
            def info(self, _message, **_kwargs):
                return None

            def error(self, _message, **_kwargs):
                return None

        monkeypatch.setattr(
            "app.middleware.logging.bind_request_context",
            lambda **_kwargs: StubLogger(),
            raising=True,
        )

        observed_state = {}

        async def app(scope, receive, send):
            del receive
            observed_state.update(scope.get("state", {}))
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = LoggingMiddleware(app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/auth/me",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
        }
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await middleware(scope, receive, send)

        response_start = next(
            message for message in messages if message["type"] == "http.response.start"
        )
        headers = dict(response_start["headers"])
        request_id = headers[b"x-request-id"].decode()

        assert len(request_id) == 32
        assert observed_state["request_id"] == request_id


class TestAuditLoggingMiddleware:
    """Tests for AuditLoggingMiddleware."""

    def test_initialization(self):
        """Test audit middleware initialization."""
        from app.middleware.logging import AuditLoggingMiddleware

        async def app(scope, receive, send):
            del scope, receive, send

        middleware = AuditLoggingMiddleware(app)
        assert middleware.audit_logger is not None


class TestPerformanceLoggingMiddleware:
    """Tests for PerformanceLoggingMiddleware."""

    def test_initialization(self):
        """Test performance middleware initialization."""
        from app.middleware.logging import PerformanceLoggingMiddleware

        async def app(scope, receive, send):
            del scope, receive, send

        middleware = PerformanceLoggingMiddleware(app)
        assert middleware.slow_request_threshold == 5.0

    def test_initialization_custom_threshold(self):
        """Test performance middleware with custom threshold."""
        from app.middleware.logging import PerformanceLoggingMiddleware

        async def app(scope, receive, send):
            del scope, receive, send

        middleware = PerformanceLoggingMiddleware(app, slow_request_threshold=2.0)
        assert middleware.slow_request_threshold == 2.0
