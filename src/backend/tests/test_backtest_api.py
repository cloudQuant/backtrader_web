"""Additional API integration tests for backtest endpoints."""

import pytest
from httpx import AsyncClient


class TestBacktestAPI:
    """Test backtest API endpoints."""

    @pytest.mark.asyncio
    async def test_list_backtests(self, client: AsyncClient, auth_headers: dict):
        """Test listing backtest results."""
        response = await client.get("/api/v1/backtest/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 0
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_submit_backtest(self, client: AsyncClient, auth_headers: dict):
        """Test submitting a backtest task."""
        response = await client.post(
            "/api/v1/backtest/run",
            json={
                "strategy_id": "001_ma_cross",
                "symbol": "000001.SZ",
                "start_date": "2023-01-01",
                "end_date": "2023-01-31",
                "initial_cash": 100000.0,
                "commission": 0.001,
                "params": {},
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_backtest_result_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting non-existent backtest result."""
        response = await client.get("/api/v1/backtest/non-existent-id", headers=auth_headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting status of non-existent task."""
        response = await client.get("/api/v1/backtest/non-existent-id/status", headers=auth_headers)

        assert response.status_code == 404
