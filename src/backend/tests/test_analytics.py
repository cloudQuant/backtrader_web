"""
分析服务 API 测试
"""
import pytest
from httpx import AsyncClient


class TestAnalyticsAPI:
    """分析 API 测试"""

    async def test_get_backtest_data_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/analytics/nonexistent-task-id", headers=auth_headers)
        assert resp.status_code == 404

    async def test_get_backtest_data_no_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/analytics/some-task-id")
        assert resp.status_code in [403, 404]  # depends on route resolution order
