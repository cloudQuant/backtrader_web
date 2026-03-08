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
        assert "/health" in middleware.skip_paths

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
