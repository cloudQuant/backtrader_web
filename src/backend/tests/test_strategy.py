"""
策略 API 测试
"""
import pytest
from httpx import AsyncClient


SAMPLE_CODE = "import backtrader as bt\nclass TestStrategy(bt.Strategy): pass"


class TestStrategyCreate:
    """创建策略测试"""

    async def test_create_strategy(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "测试策略",
            "description": "测试策略描述",
            "code": SAMPLE_CODE,
            "params": {},
            "category": "custom",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "测试策略"
        assert data["category"] == "custom"
        assert "id" in data

    async def test_create_without_auth(self, client: AsyncClient):
        resp = await client.post("/api/v1/strategy/", json={
            "name": "NoAuth", "code": SAMPLE_CODE,
        })
        assert resp.status_code == 403

    async def test_create_empty_name(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "", "code": SAMPLE_CODE,
        })
        assert resp.status_code == 422


class TestStrategyList:
    """列出策略测试"""

    async def test_list_strategies(self, client: AsyncClient, auth_headers: dict):
        await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "列表策略", "code": SAMPLE_CODE,
        })
        resp = await client.get("/api/v1/strategy/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 1

    async def test_list_with_category_filter(self, client: AsyncClient, auth_headers: dict):
        await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "趋势策略", "code": SAMPLE_CODE, "category": "trend",
        })
        await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "均值回归", "code": SAMPLE_CODE, "category": "mean_reversion",
        })
        resp = await client.get("/api/v1/strategy/?category=trend", headers=auth_headers)
        assert resp.status_code == 200


class TestStrategyTemplates:
    """策略模板测试"""

    async def test_get_templates(self, client: AsyncClient):
        resp = await client.get("/api/v1/strategy/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        assert "total" in data

    async def test_get_nonexistent_template_detail(self, client: AsyncClient):
        resp = await client.get("/api/v1/strategy/templates/nonexistent_strategy_id")
        assert resp.status_code == 404


class TestStrategyCRUD:
    """策略 CRUD 测试"""

    async def test_get_strategy(self, client: AsyncClient, auth_headers: dict):
        create_resp = await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "获取策略", "code": SAMPLE_CODE,
        })
        sid = create_resp.json()["id"]
        resp = await client.get(f"/api/v1/strategy/{sid}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "获取策略"

    async def test_get_nonexistent_strategy(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/strategy/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404

    async def test_update_strategy(self, client: AsyncClient, auth_headers: dict):
        create_resp = await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "更新策略", "code": SAMPLE_CODE,
        })
        sid = create_resp.json()["id"]
        resp = await client.put(f"/api/v1/strategy/{sid}", headers=auth_headers, json={
            "name": "更新后策略",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "更新后策略"

    async def test_update_nonexistent_strategy(self, client: AsyncClient, auth_headers: dict):
        resp = await client.put("/api/v1/strategy/nonexistent-id", headers=auth_headers, json={
            "name": "更新不存在",
        })
        assert resp.status_code == 404

    async def test_delete_strategy(self, client: AsyncClient, auth_headers: dict):
        create_resp = await client.post("/api/v1/strategy/", headers=auth_headers, json={
            "name": "删除策略", "code": SAMPLE_CODE,
        })
        sid = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/strategy/{sid}", headers=auth_headers)
        assert resp.status_code == 200
        # 验证已删除
        get_resp = await client.get(f"/api/v1/strategy/{sid}", headers=auth_headers)
        assert get_resp.status_code == 404

    async def test_delete_nonexistent_strategy(self, client: AsyncClient, auth_headers: dict):
        resp = await client.delete("/api/v1/strategy/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404
