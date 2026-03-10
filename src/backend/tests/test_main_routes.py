"""
Main application route tests - Cover root, health, info routes in main.py.
"""
from httpx import AsyncClient


class TestMainRoutes:
    """Main route tests."""

    async def test_root(self, client: AsyncClient):
        """Test root endpoint."""
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "Backtrader Web API"
        assert data["version"] == "2.0.0"
        assert "features" in data

    async def test_health(self, client: AsyncClient):
        """Test health check endpoint."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ["healthy", "degraded"]
        assert "database" in data

    async def test_info(self, client: AsyncClient):
        """Test API info endpoint."""
        resp = await client.get("/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "2.0.0"
        assert "features" in data
        assert data["features"]["sandbox_execution"] is True
