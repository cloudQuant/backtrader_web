"""
回测API测试
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_run_backtest(client: AsyncClient, auth_headers: dict):
    """测试运行回测"""
    response = await client.post(
        "/api/v1/backtest/run",
        headers=auth_headers,
        json={
            "strategy_id": "ma_cross",
            "symbol": "000001.SZ",
            "start_date": "2023-01-01T00:00:00",
            "end_date": "2024-01-01T00:00:00",
            "initial_cash": 100000,
            "commission": 0.001,
            "params": {"fast_period": 5, "slow_period": 20}
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_run_backtest_without_auth(client: AsyncClient):
    """测试未认证运行回测"""
    response = await client.post(
        "/api/v1/backtest/run",
        json={
            "strategy_id": "ma_cross",
            "symbol": "000001.SZ",
            "start_date": "2023-01-01T00:00:00",
            "end_date": "2024-01-01T00:00:00"
        }
    )
    
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_backtests(client: AsyncClient, auth_headers: dict):
    """测试列出回测历史"""
    response = await client.get(
        "/api/v1/backtest/",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_get_backtest_not_found(client: AsyncClient, auth_headers: dict):
    """测试获取不存在的回测"""
    response = await client.get(
        "/api/v1/backtest/nonexistent-id",
        headers=auth_headers
    )
    
    assert response.status_code == 404
