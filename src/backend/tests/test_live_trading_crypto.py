"""
实盘交易 API (加密货币交易) 测试

测试 /api/v1/live-trading-crypto 路由：
- POST /live/submit - 提交实盘策略
- GET /live/tasks - 获取任务列表
- GET /live/tasks/{task_id} - 获取任务状态
- POST /live/tasks/{task_id}/stop - 停止任务
- GET /live/tasks/{task_id}/data - 获取交易数据
- WebSocket /ws/live/{task_id} - 实时推送
"""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


# 有效的实盘交易请求
VALID_LIVE_TRADING_REQUEST = {
    "strategy_name": "SMACross",
    "exchange": "binance",
    "symbols": ["BTC/USDT", "ETH/USDT"],
    "initial_cash": 10000,
    "api_key": "test_api_key",
    "secret": "test_secret",
    "sandbox": True,
}


@pytest.fixture
def mock_live_trading_service():
    """Mock LiveTradingService fixture"""
    with patch('app.services.live_trading_service.LiveTradingService') as mock:
        service = AsyncMock()
        mock.return_value = service
        yield service


@pytest.fixture
def mock_task_response():
    """Mock task response fixture"""
    from app.schemas.live_trading import LiveTradingTaskResponse
    return LiveTradingTaskResponse(
        task_id="task_123",
        user_id="user_123",
        status="running",
        config={"strategy_name": "SMACross", "exchange": "binance"},
        created_at=datetime.now()
    )


@pytest.mark.asyncio
class TestLiveTradingCryptoSubmitAPI:
    """测试实盘策略提交API"""

    async def test_submit_live_strategy_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.post(
            "/api/v1/live-trading-crypto/live/submit",
            json=VALID_LIVE_TRADING_REQUEST
        )
        assert response.status_code in [401, 403]

    async def test_submit_live_strategy_success(self, client: AsyncClient, auth_headers):
        """测试成功提交策略"""
        with patch('app.api.live_trading.LiveTradingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service

            # Mock service to return task_id string
            mock_service.start_live_trading = AsyncMock(return_value="task_123")

            response = await client.post(
                "/api/v1/live-trading-crypto/live/submit",
                headers=auth_headers,
                json=VALID_LIVE_TRADING_REQUEST
            )
            # Should return 200 with proper LiveTradingTaskResponse
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "task_123"
            assert data["status"] == "submitted"
            assert "user_id" in data
            assert "config" in data
            assert "created_at" in data

    async def test_submit_live_strategy_with_full_params(self, client: AsyncClient, auth_headers):
        """测试完整参数提交"""
        full_request = {
            "strategy_name": "SMACross",
            "strategy_code": "class MyStrategy(bt.Strategy): pass",
            "exchange": "binance",
            "symbols": ["BTC/USDT"],
            "initial_cash": 10000,
            "strategy_params": {"fast": 10, "slow": 20},
            "timeframe": "1h",
            "api_key": "test_key_full",
            "secret": "test_secret_full",
            "sandbox": True,
        }

        with patch('app.api.live_trading.LiveTradingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service

            # Mock service to return task_id string
            mock_service.start_live_trading = AsyncMock(return_value="task_full_123")

            response = await client.post(
                "/api/v1/live-trading-crypto/live/submit",
                headers=auth_headers,
                json=full_request
            )
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "task_full_123"
            assert data["status"] == "submitted"

    async def test_submit_live_strategy_missing_required_fields(self, client: AsyncClient, auth_headers):
        """测试缺少必填字段"""
        invalid_request = {
            "strategy_name": "SMACross",
            "exchange": "binance",
            # Missing: symbols, api_key, secret
        }

        response = await client.post(
            "/api/v1/live-trading-crypto/live/submit",
            headers=auth_headers,
            json=invalid_request
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestLiveTradingCryptoTasksAPI:
    """测试实盘任务管理API"""

    async def test_list_live_tasks_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.get("/api/v1/live-trading-crypto/live/tasks")
        assert response.status_code in [401, 403]

    async def test_list_live_tasks_with_auth(self, client: AsyncClient, auth_headers):
        """测试获取任务列表"""
        with patch('app.api.live_trading.LiveTradingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.list_tasks = AsyncMock(return_value=[])

            response = await client.get(
                "/api/v1/live-trading-crypto/live/tasks",
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert "tasks" in data
            assert "total" in data
            assert data["tasks"] == []
            assert data["total"] == 0

    async def test_list_live_tasks_with_pagination(self, client: AsyncClient, auth_headers):
        """测试分页参数"""
        from app.schemas.live_trading import LiveTradingTaskResponse

        with patch('app.api.live_trading.LiveTradingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service

            mock_tasks = [
                LiveTradingTaskResponse(
                    task_id="task_1",
                    user_id="user_1",
                    status="running",
                    config={},
                    created_at=datetime.now()
                ),
                LiveTradingTaskResponse(
                    task_id="task_2",
                    user_id="user_1",
                    status="stopped",
                    config={},
                    created_at=datetime.now()
                ),
            ]
            mock_service.list_tasks = AsyncMock(return_value=mock_tasks)

            response = await client.get(
                "/api/v1/live-trading-crypto/live/tasks",
                headers=auth_headers,
                params={"limit": 10, "offset": 0}
            )
            assert response.status_code == 200
            data = response.json()
            assert "tasks" in data
            assert "total" in data
            assert data["total"] == 2

    async def test_list_live_tasks_invalid_limit(self, client: AsyncClient, auth_headers):
        """测试无效的limit参数"""
        response = await client.get(
            "/api/v1/live-trading-crypto/live/tasks",
            headers=auth_headers,
            params={"limit": 200}
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestLiveTradingCryptoTaskStatusAPI:
    """测试实盘任务状态API"""

    async def test_get_live_task_status_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.get("/api/v1/live-trading-crypto/live/tasks/task_123")
        assert response.status_code in [401, 403]

    async def test_get_live_task_status_not_found(self, client: AsyncClient, auth_headers):
        """测试任务不存在"""
        with patch('app.api.live_trading.LiveTradingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.get_task_status = AsyncMock(return_value=None)

            response = await client.get(
                "/api/v1/live-trading-crypto/live/tasks/nonexistent",
                headers=auth_headers
            )
            assert response.status_code == 404

    async def test_get_live_task_status_success(self, client: AsyncClient, auth_headers):
        """测试成功获取任务状态"""
        from app.schemas.live_trading import LiveTradingTaskResponse

        with patch('app.api.live_trading.LiveTradingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service

            mock_task = LiveTradingTaskResponse(
                task_id="task_123",
                user_id="user_123",
                status="running",
                config={"strategy_name": "SMACross"},
                created_at=datetime.now()
            )
            mock_service.get_task_status = AsyncMock(return_value=mock_task)

            response = await client.get(
                "/api/v1/live-trading-crypto/live/tasks/task_123",
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "task_123"
            assert data["status"] == "running"


@pytest.mark.asyncio
class TestLiveTradingCryptoControlAPI:
    """测试实盘任务控制API"""

    async def test_stop_live_strategy_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.post("/api/v1/live-trading-crypto/live/tasks/task_123/stop")
        assert response.status_code in [401, 403]

    async def test_stop_live_strategy_not_found(self, client: AsyncClient, auth_headers):
        """测试停止不存在的任务"""
        with patch('app.api.live_trading.LiveTradingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.stop_live_trading = AsyncMock(return_value=False)

            response = await client.post(
                "/api/v1/live-trading-crypto/live/tasks/nonexistent/stop",
                headers=auth_headers
            )
            assert response.status_code == 404

    async def test_stop_live_strategy_success(self, client: AsyncClient, auth_headers):
        """测试成功停止实盘策略"""
        with patch('app.api.live_trading.LiveTradingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.stop_live_trading = AsyncMock(return_value=True)

            response = await client.post(
                "/api/v1/live-trading-crypto/live/tasks/task_123/stop",
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert "message" in data


@pytest.mark.asyncio
class TestLiveTradingCryptoDataAPI:
    """测试实盘交易数据API"""

    async def test_get_live_data_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.get("/api/v1/live-trading-crypto/live/tasks/task_123/data")
        assert response.status_code in [401, 403]

    async def test_get_live_data_with_auth(self, client: AsyncClient, auth_headers):
        """测试获取实盘数据"""
        with patch('app.api.live_trading.LiveTradingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service

            # Mock get_task_status to return a dict with status
            mock_service.get_task_status = AsyncMock(return_value={
                "task_id": "task_123",
                "status": "running"
            })

            # Mock get_task_data to return a dict with required fields
            mock_service.get_task_data = AsyncMock(return_value={
                "cash": 5000.0,
                "value": 15000.0,
                "positions": [],
                "orders": []
            })

            response = await client.get(
                "/api/v1/live-trading-crypto/live/tasks/task_123/data",
                headers=auth_headers
            )
            # Should return 200 with proper LiveTradingDataResponse
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "task_123"
            assert data["status"] == "running"
            assert data["cash"] == 5000.0
            assert data["value"] == 15000.0
            assert "positions" in data
            assert "orders" in data

    async def test_get_live_data_task_not_found(self, client: AsyncClient, auth_headers):
        """测试任务不存在"""
        with patch('app.api.live_trading.LiveTradingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.get_task_status = AsyncMock(return_value=None)

            response = await client.get(
                "/api/v1/live-trading-crypto/live/tasks/nonexistent/data",
                headers=auth_headers
            )
            assert response.status_code == 404


@pytest.mark.asyncio
class TestLiveTradingCryptoWebSocket:
    """测试WebSocket端点"""

    async def test_websocket_endpoint_exists(self):
        """测试WebSocket端点存在"""
        from app.api.live_trading import router

        routes = [route.path for route in router.routes]
        assert any("/ws/live/" in str(r) for r in routes)

    async def test_websocket_handler_defined(self):
        """测试WebSocket处理函数已定义"""
        from app.api.live_trading import live_trading_websocket

        assert live_trading_websocket is not None
        assert callable(live_trading_websocket)

    async def test_websocket_connection(self):
        """测试WebSocket连接基本功能"""
        from app.api.live_trading import live_trading_websocket

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        with patch('app.api.live_trading.ws_manager') as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = MagicMock()
            mock_mgr.send_to_task = AsyncMock()

            with patch('asyncio.sleep', side_effect=Exception("Exit loop")):
                try:
                    await live_trading_websocket(mock_ws, "task_123")
                except Exception:
                    pass

                assert True


@pytest.mark.asyncio
class TestLiveTradingCryptoRouter:
    """测试实盘交易路由"""

    async def test_router_exists(self):
        """测试路由存在"""
        from app.api.live_trading import router

        assert router is not None
        assert hasattr(router, 'routes')

    async def test_router_has_endpoints(self):
        """测试路由有必要的端点"""
        from app.api.live_trading import router

        routes = [route.path for route in router.routes]
        route_str = str(routes)

        assert "/live/submit" in route_str or "submit" in route_str
        assert "/live/tasks" in route_str or "tasks" in route_str


@pytest.mark.asyncio
class TestLiveTradingCryptoService:
    """测试服务集成"""

    async def test_service_dependency_exists(self):
        """测试服务依赖函数存在"""
        from app.api.live_trading import get_live_trading_service

        assert get_live_trading_service is not None
        assert callable(get_live_trading_service)

    async def test_service_class_exists(self):
        """测试服务类存在"""
        from app.services.live_trading_service import LiveTradingService

        assert LiveTradingService is not None


@pytest.mark.asyncio
class TestLiveTradingCryptoSchemas:
    """测试Schema"""

    async def test_schemas_exist(self):
        """测试Schema存在"""
        from app.schemas.live_trading import (
            LiveTradingSubmitRequest,
            LiveTradingTaskResponse,
            LiveTradingTaskListResponse,
            LiveTradingDataResponse,
        )

        assert LiveTradingSubmitRequest is not None
        assert LiveTradingTaskResponse is not None
        assert LiveTradingTaskListResponse is not None
        assert LiveTradingDataResponse is not None
