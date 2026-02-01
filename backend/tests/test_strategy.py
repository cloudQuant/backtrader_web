"""
策略API测试
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_strategy(client: AsyncClient, auth_headers: dict):
    """测试创建策略"""
    response = await client.post(
        "/api/v1/strategy/",
        headers=auth_headers,
        json={
            "name": "测试策略",
            "description": "这是一个测试策略",
            "code": "class TestStrategy(bt.Strategy): pass",
            "params": {
                "period": {
                    "type": "int",
                    "default": 10,
                    "min": 5,
                    "max": 50,
                    "description": "周期"
                }
            },
            "category": "test"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "测试策略"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_strategies(client: AsyncClient, auth_headers: dict):
    """测试列出策略"""
    response = await client.get(
        "/api/v1/strategy/",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data


@pytest.mark.asyncio
async def test_get_templates(client: AsyncClient):
    """测试获取策略模板"""
    response = await client.get("/api/v1/strategy/templates")
    
    assert response.status_code == 200
    data = response.json()
    assert "templates" in data
    assert len(data["templates"]) > 0


@pytest.mark.asyncio
async def test_get_strategy_not_found(client: AsyncClient, auth_headers: dict):
    """测试获取不存在的策略"""
    response = await client.get(
        "/api/v1/strategy/nonexistent-id",
        headers=auth_headers
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_strategy(client: AsyncClient, auth_headers: dict):
    """测试更新策略"""
    # 先创建策略
    create_response = await client.post(
        "/api/v1/strategy/",
        headers=auth_headers,
        json={
            "name": "待更新策略",
            "description": "原始描述",
            "code": "class UpdateStrategy(bt.Strategy): pass",
            "params": {},
            "category": "test"
        }
    )
    strategy_id = create_response.json()["id"]
    
    # 更新策略
    response = await client.put(
        f"/api/v1/strategy/{strategy_id}",
        headers=auth_headers,
        json={
            "name": "已更新策略",
            "description": "更新后的描述"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "已更新策略"
    assert data["description"] == "更新后的描述"


@pytest.mark.asyncio
async def test_delete_strategy(client: AsyncClient, auth_headers: dict):
    """测试删除策略"""
    # 先创建策略
    create_response = await client.post(
        "/api/v1/strategy/",
        headers=auth_headers,
        json={
            "name": "待删除策略",
            "description": "将被删除",
            "code": "class DeleteStrategy(bt.Strategy): pass",
            "params": {},
            "category": "test"
        }
    )
    strategy_id = create_response.json()["id"]
    
    # 删除策略
    response = await client.delete(
        f"/api/v1/strategy/{strategy_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    
    # 确认已删除
    get_response = await client.get(
        f"/api/v1/strategy/{strategy_id}",
        headers=auth_headers
    )
    assert get_response.status_code == 404
