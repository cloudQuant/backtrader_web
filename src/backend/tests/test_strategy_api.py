"""Additional API integration tests for strategy endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login

SAMPLE_CODE = "import backtrader as bt\nclass TestStrategy(bt.Strategy): pass"


class TestStrategyAPI:
    """Test strategy API endpoints."""

    @pytest.mark.asyncio
    async def test_create_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test creating a strategy."""
        response = await client.post(
            "/api/v1/strategy/",
            json={
                "name": "Test Strategy",
                "description": "A test strategy",
                "code": SAMPLE_CODE,
                "params": {"param1": {"type": "int", "default": 10}},
                "category": "custom",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Strategy"
        assert data["description"] == "A test strategy"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_strategies(self, client: AsyncClient, auth_headers: dict):
        """Test listing strategies."""
        # Create a strategy first
        await client.post(
            "/api/v1/strategy/",
            json={
                "name": "List Test Strategy",
                "description": "Test",
                "code": SAMPLE_CODE,
                "category": "custom",
            },
            headers=auth_headers,
        )

        # List strategies
        response = await client.get("/api/v1/strategy/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_get_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test getting a specific strategy."""
        # Create a strategy
        create_response = await client.post(
            "/api/v1/strategy/",
            json={
                "name": "Get Test Strategy",
                "description": "Test",
                "code": SAMPLE_CODE,
                "category": "custom",
            },
            headers=auth_headers,
        )

        strategy_id = create_response.json()["id"]

        # Get the strategy
        response = await client.get(f"/api/v1/strategy/{strategy_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == strategy_id
        assert data["name"] == "Get Test Strategy"

    @pytest.mark.asyncio
    async def test_get_strategy_blocks_cross_user_access(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test that users cannot read strategies owned by another user."""
        create_response = await client.post(
            "/api/v1/strategy/",
            json={
                "name": "Private Strategy",
                "description": "Owner only",
                "code": SAMPLE_CODE,
                "category": "custom",
            },
            headers=auth_headers,
        )
        strategy_id = create_response.json()["id"]

        _, other_headers = await register_and_login(client, username="other_reader")
        response = await client.get(f"/api/v1/strategy/{strategy_id}", headers=other_headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test updating a strategy."""
        # Create a strategy
        create_response = await client.post(
            "/api/v1/strategy/",
            json={
                "name": "Update Test Strategy",
                "description": "Original",
                "code": SAMPLE_CODE,
                "category": "custom",
            },
            headers=auth_headers,
        )

        strategy_id = create_response.json()["id"]

        # Update the strategy
        response = await client.put(
            f"/api/v1/strategy/{strategy_id}",
            json={
                "name": "Updated Strategy",
                "description": "Updated description",
                "code": SAMPLE_CODE,
                "category": "trend",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Strategy"
        assert data["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_delete_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test deleting a strategy."""
        # Create a strategy
        create_response = await client.post(
            "/api/v1/strategy/",
            json={
                "name": "Delete Test Strategy",
                "description": "Test",
                "code": SAMPLE_CODE,
                "category": "custom",
            },
            headers=auth_headers,
        )

        strategy_id = create_response.json()["id"]

        # Delete the strategy
        response = await client.delete(f"/api/v1/strategy/{strategy_id}", headers=auth_headers)

        assert response.status_code == 200

        # Verify it's deleted
        get_response = await client.get(f"/api/v1/strategy/{strategy_id}", headers=auth_headers)

        assert get_response.status_code == 404
