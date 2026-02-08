"""
组合管理 API 测试
"""
import pytest
from httpx import AsyncClient


class TestPortfolioAPI:
    """组合管理接口测试"""

    async def test_get_overview(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/portfolio/overview", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_assets" in data
        assert "strategies" in data

    async def test_get_positions(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/portfolio/positions", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "positions" in data

    async def test_get_trades(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/portfolio/trades", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "trades" in data

    async def test_get_equity(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/portfolio/equity", headers=auth_headers)
        assert resp.status_code == 200

    async def test_get_allocation(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/portfolio/allocation", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    async def test_no_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/portfolio/overview")
        assert resp.status_code == 403
