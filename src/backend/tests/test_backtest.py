"""
回测 API 测试
"""
import pytest
from httpx import AsyncClient


class TestBacktestRun:
    """回测运行测试"""

    async def test_run_backtest(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/backtest/run", headers=auth_headers, json={
            "strategy_id": "001_ma_cross",
            "symbol": "000001.SZ",
            "start_date": "2023-01-01",
            "end_date": "2023-06-30",
            "initial_cash": 100000,
            "commission": 0.001,
            "params": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data

    async def test_run_backtest_no_auth(self, client: AsyncClient):
        resp = await client.post("/api/v1/backtest/run", json={
            "strategy_id": "001_ma_cross",
            "symbol": "000001.SZ",
            "start_date": "2023-01-01",
            "end_date": "2023-06-30",
        })
        assert resp.status_code == 403


class TestBacktestList:
    """回测列表测试"""

    async def test_list_backtests_empty(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/backtest/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    async def test_list_backtests_with_pagination(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/backtest/?limit=5&offset=0", headers=auth_headers)
        assert resp.status_code == 200

    async def test_list_backtests_no_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/backtest/")
        assert resp.status_code == 403


class TestBacktestResult:
    """回测结果测试"""

    async def test_get_result_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/backtest/nonexistent-task-id", headers=auth_headers)
        assert resp.status_code == 404

    async def test_get_status_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/backtest/nonexistent-task-id/status", headers=auth_headers)
        assert resp.status_code == 404

    async def test_cancel_nonexistent(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/backtest/nonexistent-task-id/cancel", headers=auth_headers)
        assert resp.status_code == 400

    async def test_delete_nonexistent(self, client: AsyncClient, auth_headers: dict):
        resp = await client.delete("/api/v1/backtest/nonexistent-task-id", headers=auth_headers)
        assert resp.status_code == 404
