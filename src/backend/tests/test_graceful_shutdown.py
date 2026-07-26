"""
Tests for graceful shutdown functionality.

Covers:
1. Health endpoint returns 503 when app.state.shutting_down = True
2. GracefulShutdownManager.initiate() sets the shutting_down flag
3. SHUTDOWN_TIMEOUT config validation (out of range returns 30)
4. Health endpoint returns 200 normally (shutting_down is False)
"""

import pytest
from httpx import AsyncClient

from app.main import app


@pytest.fixture(autouse=True)
def _reset_shutdown_state():
    """Ensure shutting_down is False before and after each test."""
    app.state.shutting_down = False
    yield
    app.state.shutting_down = False


@pytest.mark.asyncio
async def test_health_returns_200_when_not_shutting_down(client: AsyncClient):
    """Health endpoint returns 200 when shutting_down is False."""
    app.state.shutting_down = False
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "unhealthy")
    assert data["version"] == "2.0.0"


@pytest.mark.asyncio
async def test_health_returns_503_when_shutting_down(client: AsyncClient):
    """Health endpoint returns 503 with status 'shutting_down' during shutdown."""
    app.state.shutting_down = True
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "shutting_down"
    assert data["version"] == "2.0.0"
    assert data["database"] == "unknown"
    assert "uptime" in data


@pytest.mark.asyncio
async def test_graceful_shutdown_manager_sets_flag():
    """GracefulShutdownManager.initiate() sets app.state.shutting_down = True."""
    from app.shutdown import GracefulShutdownManager

    app.state.shutting_down = False
    mgr = GracefulShutdownManager()
    assert mgr.is_shutting_down is False

    await mgr.initiate(app)

    assert app.state.shutting_down is True
    assert mgr.is_shutting_down is True


@pytest.mark.asyncio
async def test_shutdown_timeout_config_validation_out_of_range():
    """SHUTDOWN_TIMEOUT out of range (1-300) returns default 30."""
    import os

    from app.config import Settings

    # Test value below range
    os.environ["SHUTDOWN_TIMEOUT"] = "0"
    s = Settings(
        SECRET_KEY="a" * 32,
        JWT_SECRET_KEY="b" * 32,
        ADMIN_PASSWORD="SecurePass123!",
        SHUTDOWN_TIMEOUT=0,
    )
    assert s.SHUTDOWN_TIMEOUT == 30

    # Test value above range
    s2 = Settings(
        SECRET_KEY="a" * 32,
        JWT_SECRET_KEY="b" * 32,
        ADMIN_PASSWORD="SecurePass123!",
        SHUTDOWN_TIMEOUT=999,
    )
    assert s2.SHUTDOWN_TIMEOUT == 30

    # Test valid value
    s3 = Settings(
        SECRET_KEY="a" * 32,
        JWT_SECRET_KEY="b" * 32,
        ADMIN_PASSWORD="SecurePass123!",
        SHUTDOWN_TIMEOUT=60,
    )
    assert s3.SHUTDOWN_TIMEOUT == 60

    # Cleanup
    os.environ.pop("SHUTDOWN_TIMEOUT", None)


@pytest.mark.asyncio
async def test_graceful_shutdown_manager_closes_websockets():
    """GracefulShutdownManager.initiate() calls close_all on websocket manager."""
    from unittest.mock import AsyncMock, patch

    from app.shutdown import GracefulShutdownManager

    app.state.shutting_down = False
    mgr = GracefulShutdownManager()

    with patch("app.shutdown.ws_manager") as mock_ws:
        mock_ws.get_total_connections.return_value = 0
        mock_ws.close_all = AsyncMock(return_value=3)

        await mgr.initiate(app)

        mock_ws.close_all.assert_called_once_with(code=1001, reason="Going Away")
        assert app.state.shutting_down is True
