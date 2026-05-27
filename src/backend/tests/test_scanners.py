import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_scanner_runs_safe_condition_dsl(client: AsyncClient):
    _, headers = await register_and_login(client, username="scanner_user")

    response = await client.post(
        "/api/v1/scanners/run",
        headers=headers,
        json={
            "universe": ["RB2510", "IF2510"],
            "condition": (
                "indicator > 0.6 and news_sentiment > 0.5 "
                "and lookback_days >= 20 and timeframe == '1d'"
            ),
            "lookback_days": 20,
            "timeframe": "1d",
        },
    )
    task = await client.get(
        f"/api/v1/scanners/tasks/{response.json()['task_id']}",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["task_id"]
    assert data["lookback_days"] == 20
    assert data["timeframe"] == "1d"
    assert all("symbol" in item for item in data["matches"])
    assert all("indicator" in item for item in data["matches"])
    assert task.status_code == 200
    assert task.json()["task_id"] == data["task_id"]
    assert task.json()["status"] == "completed"
    assert task.json()["matches"] == data["matches"]


@pytest.mark.asyncio
async def test_scanner_rejects_unsafe_expression(client: AsyncClient):
    _, headers = await register_and_login(client, username="scanner_unsafe")

    response = await client.post(
        "/api/v1/scanners/run",
        headers=headers,
        json={"universe": ["RB2510"], "condition": "__import__('os').system('x')"},
    )

    assert response.status_code == 400
