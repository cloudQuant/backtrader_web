"""
增强回测 API 测试
"""
import pytest
from httpx import AsyncClient


class TestEnhancedBacktestRun:
    """增强回测运行测试"""

    async def test_run_backtest(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/backtests/run", headers=auth_headers, json={
            "strategy_id": "001_ma_cross",
            "symbol": "000001.SZ",
            "start_date": "2023-01-01T00:00:00",
            "end_date": "2023-06-30T00:00:00",
            "initial_cash": 100000,
            "commission": 0.001,
            "params": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data

    async def test_run_no_auth(self, client: AsyncClient):
        resp = await client.post("/api/v1/backtests/run", json={
            "strategy_id": "001_ma_cross",
            "symbol": "000001.SZ",
            "start_date": "2023-01-01T00:00:00",
            "end_date": "2023-06-30T00:00:00",
        })
        assert resp.status_code == 403


class TestEnhancedBacktestList:
    """增强回测列表测试"""

    async def test_list(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/backtests/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    async def test_list_with_sort(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/backtests/?sort_by=created_at&sort_order=desc", headers=auth_headers)
        assert resp.status_code == 200


class TestEnhancedBacktestResult:
    """增强回测结果测试"""

    async def test_get_result_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/backtests/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404

    async def test_get_status_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/backtests/nonexistent-id/status", headers=auth_headers)
        assert resp.status_code == 404

    async def test_cancel_nonexistent(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/backtests/nonexistent-id/cancel", headers=auth_headers)
        assert resp.status_code in [400, 404]

    async def test_delete_nonexistent(self, client: AsyncClient, auth_headers: dict):
        resp = await client.delete("/api/v1/backtests/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404


class TestEnhancedOptimization:
    """参数优化测试"""

    async def test_optimize_no_auth(self, client: AsyncClient):
        resp = await client.post("/api/v1/backtests/optimize", json={})
        assert resp.status_code in [403, 405, 422]
