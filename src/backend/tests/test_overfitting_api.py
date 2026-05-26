from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestOverfittingApi:
    async def test_create_overfitting_task_requires_auth(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/strategy/overfitting/bt-001",
            json={"methods": ["monte_carlo"]},
        )

        assert response.status_code == 401

    async def test_create_overfitting_task(self, client: AsyncClient, auth_headers: dict):
        with patch(
            "app.api.overfitting.OverfittingService.schedule_analysis",
            new_callable=AsyncMock,
        ) as mock_schedule:
            mock_schedule.return_value = {
                "task_id": "ot-001",
                "backtest_id": "bt-001",
                "status": "pending",
                "methods": ["monte_carlo"],
            }

            response = await client.post(
                "/api/v1/strategy/overfitting/bt-001",
                headers=auth_headers,
                json={
                    "methods": ["walk_forward", "monte_carlo"],
                    "walk_forward_max_concurrency": 2,
                    "monte_carlo_iterations": 100,
                },
            )

        assert response.status_code == 200
        scheduled_request = mock_schedule.call_args.kwargs["request"]
        assert scheduled_request.walk_forward_max_concurrency == 2
        payload = response.json()
        assert payload["task_id"] == "ot-001"
        assert payload["backtest_id"] == "bt-001"
        assert payload["status"] == "pending"

    async def test_get_overfitting_task(self, client: AsyncClient, auth_headers: dict):
        with patch(
            "app.api.overfitting.OverfittingService.get_task_result",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {
                "task_id": "ot-001",
                "backtest_id": "bt-001",
                "status": "completed",
                "overall_level": "medium",
                "robustness_score": 58.2,
                "methods": [],
                "summary": "Monte Carlo 检测完成。",
            }

            response = await client.get(
                "/api/v1/strategy/overfitting/task/ot-001",
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json()["task_id"] == "ot-001"
