"""Strategy API tests."""
import pytest
from httpx import AsyncClient


SAMPLE_CODE = "import backtrader as bt\nclass TestStrategy(bt.Strategy): pass"


class TestStrategyCreate:
    """Tests for strategy creation endpoint."""

    async def test_create_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test creating a new strategy.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        resp = await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "Test Strategy",
            "description": "Test strategy description",
            "code": SAMPLE_CODE,
            "params": {},
            "category": "custom",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Strategy"
        assert data["category"] == "custom"
        assert "id" in data

    async def test_create_without_auth(self, client: AsyncClient):
        """Test creating a strategy without authentication.

        Args:
            client: Async HTTP client.

        Returns:
            None
        """
        resp = await client.post("/api/v1/strategy/", json={
            "name": "NoAuth", "code": SAMPLE_CODE,
        })
        assert resp.status_code == 403

    async def test_create_empty_name(self, client: AsyncClient, auth_headers: dict):
        """Test creating a strategy with an empty name.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        resp = await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "", "code": SAMPLE_CODE,
        })
        assert resp.status_code == 422


class TestStrategyList:
    """Tests for strategy list endpoint."""

    async def test_list_strategies(self, client: AsyncClient, auth_headers: dict):
        """Test listing all strategies.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "List Strategy", "code": SAMPLE_CODE,
        })
        resp = await client.get("/api/v1/strategy/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 1

    async def test_list_with_category_filter(self, client: AsyncClient, auth_headers: dict):
        """Test listing strategies filtered by category.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "Trend Strategy", "code": SAMPLE_CODE, "category": "trend",
        })
        await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "Mean Reversion", "code": SAMPLE_CODE, "category": "mean_reversion",
        })
        resp = await client.get("/api/v1/strategy/?category=trend", headers=auth_headers)
        assert resp.status_code == 200


class TestStrategyTemplates:
    """Tests for strategy template endpoints."""

    async def test_get_templates(self, client: AsyncClient):
        """Test getting all strategy templates.

        Args:
            client: Async HTTP client.

        Returns:
            None
        """
        resp = await client.get("/api/v1/strategy/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        assert "total" in data

    async def test_get_nonexistent_template_detail(self, client: AsyncClient):
        """Test getting a non-existent template detail.

        Args:
            client: Async HTTP client.

        Returns:
            None
        """
        resp = await client.get("/api/v1/strategy/templates/nonexistent_strategy_id")
        assert resp.status_code == 404


class TestStrategyCRUD:
    """Tests for strategy CRUD operations."""

    async def test_get_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test getting a strategy by ID.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        create_resp = await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "Get Strategy", "code": SAMPLE_CODE,
        })
        sid = create_resp.json()["id"]
        resp = await client.get(f"/api/v1/strategy/{sid}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Strategy"

    async def test_get_nonexistent_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test getting a non-existent strategy.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        resp = await client.get("/api/v1/strategy/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404

    async def test_update_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test updating a strategy.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        create_resp = await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "Update Strategy", "code": SAMPLE_CODE,
        })
        sid = create_resp.json()["id"]
        resp = await client.put(f"/api/v1/strategy/{sid}", headers=auth_headers, json={
            "name": "Updated Strategy",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Strategy"

    async def test_update_nonexistent_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test updating a non-existent strategy.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        resp = await client.put("/api/v1/strategy/nonexistent-id", headers=auth_headers, json={
            "name": "Update Nonexistent",
        })
        assert resp.status_code == 404

    async def test_delete_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test deleting a strategy.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        create_resp = await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "Delete Strategy", "code": SAMPLE_CODE,
        })
        sid = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/strategy/{sid}", headers=auth_headers)
        assert resp.status_code == 200
        # Verify deleted
        get_resp = await client.get(f"/api/v1/strategy/{sid}", headers=auth_headers)
        assert get_resp.status_code == 404

    async def test_delete_nonexistent_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test deleting a non-existent strategy.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        resp = await client.delete("/api/v1/strategy/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404
