"""
Logging middleware tests.

Tests:
- LoggingMiddleware initialization and configuration
- AuditLoggingMiddleware initialization
- PerformanceLoggingMiddleware initialization
"""
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestLoggingMiddleware:
    """Tests for LoggingMiddleware."""

    def test_initialization(self):
        """Test middleware initialization."""
        from app.middleware.logging import LoggingMiddleware

        async def app(scope, receive, send):
            pass

        middleware = LoggingMiddleware(app)
        assert middleware.log_body is False
        assert middleware.log_headers is False
        assert "/health" in middleware.skip_paths

    def test_initialization_with_options(self):
        """Test middleware initialization with options."""
        from app.middleware.logging import LoggingMiddleware

        async def app(scope, receive, send):
            pass

        middleware = LoggingMiddleware(
            app,
            log_body=True,
            log_headers=True,
            skip_paths=["/custom"]
        )
        assert middleware.log_body is True
        assert middleware.log_headers is True
        assert "/custom" in middleware.skip_paths


class TestAuditLoggingMiddleware:
    """Tests for AuditLoggingMiddleware."""

    def test_initialization(self):
        """Test audit middleware initialization."""
        from app.middleware.logging import AuditLoggingMiddleware

        async def app(scope, receive, send):
            pass

        middleware = AuditLoggingMiddleware(app)
        assert middleware.audit_logger is not None


class TestPerformanceLoggingMiddleware:
    """Tests for PerformanceLoggingMiddleware."""

    def test_initialization(self):
        """Test performance middleware initialization."""
        from app.middleware.logging import PerformanceLoggingMiddleware

        async def app(scope, receive, send):
            pass

        middleware = PerformanceLoggingMiddleware(app)
        assert middleware.slow_request_threshold == 5.0

    def test_initialization_custom_threshold(self):
        """Test performance middleware with custom threshold."""
        from app.middleware.logging import PerformanceLoggingMiddleware

        async def app(scope, receive, send):
            pass

        middleware = PerformanceLoggingMiddleware(app, slow_request_threshold=2.0)
        assert middleware.slow_request_threshold == 2.0
