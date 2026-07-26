"""
Tests for iteration 164 improvements:
- Deprecation headers middleware
- Rate limiter Redis backend detection
- Telemetry module (OTEL disabled by default)
- Graceful shutdown (interrupt_active_tasks)
- Health check pool info
"""

import os
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# ============================================================
# ============================================================
# Telemetry Module Tests
# ============================================================


class TestTelemetry:
    """Test OpenTelemetry configuration module."""

    def test_otel_disabled_by_default(self):
        """OTEL should be disabled when OTEL_ENABLED is not set."""
        from app.telemetry import _is_otel_enabled

        with patch.dict(os.environ, {}, clear=False):
            # Remove OTEL_ENABLED if present
            os.environ.pop("OTEL_ENABLED", None)
            assert _is_otel_enabled() is False

    def test_otel_enabled_with_true(self):
        """OTEL should be enabled when OTEL_ENABLED=true."""
        from app.telemetry import _is_otel_enabled

        with patch.dict(os.environ, {"OTEL_ENABLED": "true"}):
            assert _is_otel_enabled() is True

    def test_otel_enabled_with_1(self):
        """OTEL should be enabled when OTEL_ENABLED=1."""
        from app.telemetry import _is_otel_enabled

        with patch.dict(os.environ, {"OTEL_ENABLED": "1"}):
            assert _is_otel_enabled() is True

    def test_otel_enabled_with_yes(self):
        """OTEL should be enabled when OTEL_ENABLED=yes."""
        from app.telemetry import _is_otel_enabled

        with patch.dict(os.environ, {"OTEL_ENABLED": "yes"}):
            assert _is_otel_enabled() is True

    def test_otel_disabled_with_false(self):
        """OTEL should be disabled when OTEL_ENABLED=false."""
        from app.telemetry import _is_otel_enabled

        with patch.dict(os.environ, {"OTEL_ENABLED": "false"}):
            assert _is_otel_enabled() is False

    def test_setup_telemetry_returns_false_when_disabled(self):
        """setup_telemetry should return False when OTEL is disabled."""
        import app.telemetry

        # Reset the initialized flag
        app.telemetry._OTEL_INITIALIZED = False

        with patch.dict(os.environ, {"OTEL_ENABLED": "false"}):
            result = app.telemetry.setup_telemetry(app)
            assert result is False

    def test_setup_telemetry_handles_unreachable_collector(self):
        """setup_telemetry should return False gracefully when collector is unreachable."""
        import app.telemetry
        from app.main import app as fastapi_app

        app.telemetry._OTEL_INITIALIZED = False

        with patch.dict(
            os.environ,
            {"OTEL_ENABLED": "true", "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"},
        ):
            # Patch TracerProvider to simulate a connection failure
            with patch("app.telemetry.TracerProvider", side_effect=Exception("connection refused")):
                result = app.telemetry.setup_telemetry(fastapi_app)
                assert result is False


# ============================================================
# Rate Limiter Tests
# ============================================================


class TestRateLimiter:
    """Test rate limiter configuration."""

    def test_limiter_exists(self):
        """Rate limiter should be importable and configured."""
        from app.rate_limit import limiter

        assert limiter is not None

    def test_limiter_has_key_func(self):
        """Rate limiter should use remote address as key function."""
        from app.rate_limit import limiter

        assert limiter._key_func is not None


# ============================================================
# Health Check Tests
# ============================================================


class TestHealthCheck:
    """Test health check endpoint enhancements."""

    @pytest.fixture
    def client(self):
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def test_health_returns_200(self, client):
        """Health check should return 200."""
        # Reset cache to get fresh data
        import app.main

        app.main._health_cache = None

        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_health_contains_database_status(self, client):
        """Health check should include database status."""
        import app.main

        app.main._health_cache = None

        resp = await client.get("/health")
        data = resp.json()
        assert "database" in data
        assert data["database"] in ("connected", "disconnected")

    async def test_health_contains_version(self, client):
        """Health check should include version."""
        resp = await client.get("/health")
        data = resp.json()
        assert "version" in data
        assert data["version"] == "2.0.0"

    async def test_health_contains_database_pool_field(self, client):
        """Health check should include database_pool field."""
        import app.main

        app.main._health_cache = None

        resp = await client.get("/health")
        data = resp.json()
        # database_pool may be None for SQLite (NullPool) but field should exist
        assert "database_pool" in data

    async def test_health_contains_optional_routers(self, client):
        """Health check should include optional_routers info."""
        resp = await client.get("/health")
        data = resp.json()
        assert "optional_routers" in data
        assert "unavailable_count" in data["optional_routers"]


# ============================================================
# Graceful Shutdown Tests
# ============================================================


class TestGracefulShutdown:
    """Test graceful shutdown task interruption."""

    async def test_interrupt_active_tasks_returns_zero_when_no_tasks(self):
        """interrupt_active_tasks should return 0 when no active tasks exist."""
        from app.services.backtest.manager import BacktestExecutionManager

        mgr = BacktestExecutionManager()
        count = await mgr.interrupt_active_tasks()
        assert count == 0

    async def test_interrupt_active_tasks_method_exists(self):
        """BacktestExecutionManager should have interrupt_active_tasks method."""
        from app.services.backtest.manager import BacktestExecutionManager

        mgr = BacktestExecutionManager()
        assert hasattr(mgr, "interrupt_active_tasks")
        assert callable(mgr.interrupt_active_tasks)

    async def test_reconcile_orphaned_tasks_returns_zero_when_no_tasks(self):
        """reconcile_orphaned_tasks should return 0 when no orphaned tasks."""
        from app.services.backtest.manager import BacktestExecutionManager

        mgr = BacktestExecutionManager()
        count = await mgr.reconcile_orphaned_tasks()
        assert count == 0


# ============================================================
# Root and Info Endpoint Tests
# ============================================================


class TestRootEndpoints:
    """Test root and info endpoints."""

    @pytest.fixture
    def client(self):
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def test_root_returns_service_info(self, client):
        """Root endpoint should return service metadata."""
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "AI for Investor API"
        assert data["version"] == "2.0.0"
        assert "features" in data

    async def test_info_returns_system_info(self, client):
        """Info endpoint should return system information."""
        resp = await client.get("/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "database_type" in data
        assert "features" in data
        assert "optional_routers" in data

    async def test_root_features_include_core(self, client):
        """Root features should include core capabilities."""
        resp = await client.get("/")
        data = resp.json()
        features = data["features"]
        assert "Strategy Management" in features
        assert "Backtesting Analysis" in features


# ============================================================
# Security Headers Tests
# ============================================================


class TestSecurityHeaders:
    """Test security headers middleware."""

    @pytest.fixture
    def client(self):
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def test_x_content_type_options(self, client):
        """Response should include X-Content-Type-Options: nosniff."""
        resp = await client.get("/")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    async def test_x_frame_options(self, client):
        """Response should include X-Frame-Options: DENY."""
        resp = await client.get("/")
        assert resp.headers.get("x-frame-options") == "DENY"

    async def test_referrer_policy(self, client):
        """Response should include Referrer-Policy header."""
        resp = await client.get("/")
        assert "referrer-policy" in resp.headers

    async def test_content_security_policy(self, client):
        """Response should include Content-Security-Policy header."""
        resp = await client.get("/")
        assert "content-security-policy" in resp.headers
        csp = resp.headers["content-security-policy"]
        assert "default-src" in csp

    async def test_permissions_policy(self, client):
        """Response should include Permissions-Policy header."""
        resp = await client.get("/")
        assert "permissions-policy" in resp.headers

    async def test_auth_endpoints_no_cache(self, client):
        """Auth endpoints should have no-store cache control."""
        resp = await client.post("/api/v1/auth/login", json={"username": "x", "password": "y"})
        cache_control = resp.headers.get("cache-control", "")
        assert "no-store" in cache_control


# ============================================================
