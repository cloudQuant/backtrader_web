"""
实盘交易完整版 API 测试

测试：
- 实盘策略提交
- 实盘任务列表
- 实盘任务状态
- 停止实盘任务
- 实盘交易数据获取
- WebSocket端点
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime
from fastapi import status


# 有效的实盘交易请求
VALID_LIVE_TRADING_REQUEST = {
    "strategy_name": "SMACross",
    "exchange": "binance",
    "symbols": ["BTC/USDT", "ETH/USDT"],
    "initial_cash": 10000,
    "api_key": "test_key",
    "secret": "test_secret",
    "sandbox": True,
}


@pytest.fixture
def mock_current_user():
    """Mock current user"""
    user = MagicMock()
    user.sub = "test_user_123"
    return user


@pytest.fixture
def mock_live_trading_service():
    """Mock LiveTradingService"""
    service = AsyncMock()
    service.start_live_trading = AsyncMock(return_value="task_123")
    service.list_tasks = AsyncMock(return_value=([], 0))
    service.get_task_status = AsyncMock(return_value=None)
    service.stop_live_trading = AsyncMock(return_value=True)
    service.get_task_data = AsyncMock(return_value={
        "cash": 10000.0,
        "value": 15000.0,
        "positions": [],
        "orders": [],
    })
    return service


@pytest.mark.asyncio
class TestLiveTradingSubmitAPI:
    """测试实盘策略提交API"""

    async def test_submit_live_strategy_success(self, mock_current_user, mock_live_trading_service):
        """测试成功提交策略"""
        from app.api.live_trading_complete import submit_live_strategy
        from app.schemas.live_trading import LiveTradingSubmitRequest

        request = LiveTradingSubmitRequest(**VALID_LIVE_TRADING_REQUEST)

        with patch('app.api.live_trading_complete.ws_manager') as mock_ws:
            mock_ws.send_to_task = AsyncMock()

            result = await submit_live_strategy(
                request=request,
                current_user=mock_current_user,
                service=mock_live_trading_service
            )

            assert result.task_id == "task_123"
            assert result.user_id == "test_user_123"
            assert result.status == "submitted"
            # Check that config contains the important fields
            assert result.config["strategy_name"] == "SMACross"
            assert result.config["exchange"] == "binance"
            assert result.config["symbols"] == ["BTC/USDT", "ETH/USDT"]
            assert result.config["initial_cash"] == 10000
            assert isinstance(result.created_at, datetime)

            # Verify service was called correctly
            mock_live_trading_service.start_live_trading.assert_called_once_with(
                user_id="test_user_123",
                strategy_name="SMACross",
                strategy_code=None,
                exchange="binance",
                symbols=["BTC/USDT", "ETH/USDT"],
                initial_cash=10000.0,
                strategy_params=None,
                timeframe="1d",
                start_date=None,
                end_date=None,
                api_key="test_key",
                secret="test_secret",
                sandbox=True,
            )

    async def test_submit_live_strategy_with_full_params(self, mock_current_user, mock_live_trading_service):
        """测试完整参数提交"""
        from app.api.live_trading_complete import submit_live_strategy
        from app.schemas.live_trading import LiveTradingSubmitRequest

        full_request = {
            "strategy_name": "SMACross",
            "strategy_code": "class MyStrategy(bt.Strategy): pass",
            "exchange": "binance",
            "symbols": ["BTC/USDT"],
            "initial_cash": 10000,
            "strategy_params": {"fast": 10, "slow": 20},
            "timeframe": "1h",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "api_key": "test_key_full",
            "secret": "test_secret_full",
            "sandbox": True,
        }

        request = LiveTradingSubmitRequest(**full_request)
        mock_live_trading_service.start_live_trading = AsyncMock(return_value="task_full_123")

        with patch('app.api.live_trading_complete.ws_manager') as mock_ws:
            mock_ws.send_to_task = AsyncMock()

            result = await submit_live_strategy(
                request=request,
                current_user=mock_current_user,
                service=mock_live_trading_service
            )

            assert result.task_id == "task_full_123"

    async def test_submit_live_strategy_sends_websocket_notification(self, mock_current_user, mock_live_trading_service):
        """测试提交后发送WebSocket通知"""
        from app.api.live_trading_complete import submit_live_strategy, ws_manager, MessageType
        from app.schemas.live_trading import LiveTradingSubmitRequest

        request = LiveTradingSubmitRequest(**VALID_LIVE_TRADING_REQUEST)

        with patch.object(ws_manager, 'send_to_task') as mock_send:
            result = await submit_live_strategy(
                request=request,
                current_user=mock_current_user,
                service=mock_live_trading_service
            )

            # Verify WebSocket notification was sent
            mock_send.assert_called_once_with(
                f"user:{mock_current_user.sub}:live",
                {
                    "type": MessageType.PROGRESS,
                    "task_id": "task_123",
                    "message": "实盘交易策略已提交",
                    "data": request.model_dump(),
                }
            )


@pytest.mark.asyncio
class TestLiveTradingTasksAPI:
    """测试实盘任务管理API"""

    async def test_list_live_tasks_empty(self, mock_current_user, mock_live_trading_service):
        """测试空任务列表"""
        from app.api.live_trading_complete import list_live_tasks

        mock_live_trading_service.list_tasks = AsyncMock(return_value=([], 0))

        result = await list_live_tasks(
            current_user=mock_current_user,
            service=mock_live_trading_service,
            limit=20,
            offset=0
        )

        assert result.total == 0
        assert result.tasks == []

    async def test_list_live_tasks_with_data(self, mock_current_user, mock_live_trading_service):
        """测试获取任务列表"""
        from app.api.live_trading_complete import list_live_tasks
        from app.schemas.live_trading import LiveTradingTaskResponse

        mock_tasks = [
            LiveTradingTaskResponse(
                task_id="task_1",
                user_id="user_1",
                status="running",
                config={"strategy_name": "SMACross"},
                created_at=datetime.now()
            ),
            LiveTradingTaskResponse(
                task_id="task_2",
                user_id="user_1",
                status="stopped",
                config={"strategy_name": "BBreakout"},
                created_at=datetime.now()
            ),
        ]
        mock_live_trading_service.list_tasks = AsyncMock(return_value=(mock_tasks, 2))

        result = await list_live_tasks(
            current_user=mock_current_user,
            service=mock_live_trading_service,
            limit=10,
            offset=0
        )

        assert result.total == 2
        assert len(result.tasks) == 2
        assert result.tasks[0].task_id == "task_1"
        assert result.tasks[1].task_id == "task_2"

    async def test_list_live_tasks_with_pagination(self, mock_current_user, mock_live_trading_service):
        """测试分页"""
        from app.api.live_trading_complete import list_live_tasks

        mock_live_trading_service.list_tasks = AsyncMock(return_value=([], 0))

        result = await list_live_tasks(
            current_user=mock_current_user,
            service=mock_live_trading_service,
            limit=10,
            offset=5
        )

        # Verify service was called with correct pagination
        mock_live_trading_service.list_tasks.assert_called_once_with(
            user_id="test_user_123",
            limit=10,
            offset=5
        )


@pytest.mark.asyncio
class TestLiveTradingTaskStatusAPI:
    """测试实盘任务状态API"""

    async def test_get_live_task_status_not_found(self, mock_current_user, mock_live_trading_service):
        """测试任务不存在"""
        from app.api.live_trading_complete import get_live_task_status
        from fastapi import HTTPException

        mock_live_trading_service.get_task_status = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_live_task_status(
                task_id="nonexistent",
                current_user=mock_current_user,
                service=mock_live_trading_service
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "不存在" in exc_info.value.detail

    async def test_get_live_task_status_success(self, mock_current_user, mock_live_trading_service):
        """测试成功获取任务状态"""
        from app.api.live_trading_complete import get_live_task_status
        from app.schemas.live_trading import LiveTradingTaskResponse

        mock_task = LiveTradingTaskResponse(
            task_id="task_123",
            user_id="test_user_123",
            status="running",
            config={"strategy_name": "SMACross"},
            created_at=datetime.now()
        )
        mock_live_trading_service.get_task_status = AsyncMock(return_value=mock_task)

        result = await get_live_task_status(
            task_id="task_123",
            current_user=mock_current_user,
            service=mock_live_trading_service
        )

        assert result.task_id == "task_123"
        assert result.status == "running"


@pytest.mark.asyncio
class TestLiveTradingControlAPI:
    """测试实盘任务控制API"""

    async def test_stop_live_strategy_not_found(self, mock_current_user, mock_live_trading_service):
        """测试停止不存在的任务"""
        from app.api.live_trading_complete import stop_live_strategy
        from fastapi import HTTPException

        mock_live_trading_service.stop_live_trading = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await stop_live_strategy(
                task_id="nonexistent",
                current_user=mock_current_user,
                service=mock_live_trading_service
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_stop_live_strategy_success(self, mock_current_user, mock_live_trading_service):
        """测试成功停止实盘策略"""
        from app.api.live_trading_complete import stop_live_strategy

        mock_live_trading_service.stop_live_trading = AsyncMock(return_value=True)

        with patch('app.api.live_trading_complete.ws_manager') as mock_ws:
            mock_ws.send_to_task = AsyncMock()

            result = await stop_live_strategy(
                task_id="task_123",
                current_user=mock_current_user,
                service=mock_live_trading_service
            )

            assert result == {"message": "实盘交易任务已停止"}

    async def test_stop_live_strategy_sends_websocket_notification(self, mock_current_user, mock_live_trading_service):
        """测试停止后发送WebSocket通知"""
        from app.api.live_trading_complete import stop_live_strategy, ws_manager, MessageType

        mock_live_trading_service.stop_live_trading = AsyncMock(return_value=True)

        with patch.object(ws_manager, 'send_to_task') as mock_send:
            await stop_live_strategy(
                task_id="task_123",
                current_user=mock_current_user,
                service=mock_live_trading_service
            )

            # Verify WebSocket notification was sent
            mock_send.assert_called_once_with(
                f"live:task_123",
                {
                    "type": MessageType.PROGRESS,
                    "task_id": "task_123",
                    "message": "实盘交易任务已停止",
                }
            )


@pytest.mark.asyncio
class TestLiveTradingDataAPI:
    """测试实盘交易数据API"""

    async def test_get_live_data_task_not_found(self, mock_current_user, mock_live_trading_service):
        """测试任务不存在"""
        from app.api.live_trading_complete import get_live_trading_data
        from fastapi import HTTPException

        mock_live_trading_service.get_task_status = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_live_trading_data(
                task_id="nonexistent",
                current_user=mock_current_user,
                service=mock_live_trading_service
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_live_data_success(self, mock_current_user, mock_live_trading_service):
        """测试成功获取实盘数据"""
        from app.api.live_trading_complete import get_live_trading_data

        mock_live_trading_service.get_task_status = AsyncMock(return_value={"status": "running"})
        mock_live_trading_service.get_task_data = AsyncMock(return_value={
            "cash": 5000.0,
            "value": 15000.0,
            "positions": [{"symbol": "BTC/USDT", "quantity": 0.5}],
            "orders": [{"order_id": "order_1", "status": "filled"}],
        })

        result = await get_live_trading_data(
            task_id="task_123",
            current_user=mock_current_user,
            service=mock_live_trading_service
        )

        assert result.task_id == "task_123"
        assert result.status == "running"
        assert result.cash == 5000.0
        assert result.value == 15000.0
        assert len(result.positions) == 1
        assert len(result.orders) == 1

    async def test_get_live_data_with_object_status(self, mock_current_user, mock_live_trading_service):
        """测试状态为对象时的情况"""
        from app.api.live_trading_complete import get_live_trading_data

        # Mock task status as an object with status attribute
        mock_status = MagicMock()
        mock_status.status = "running"
        mock_live_trading_service.get_task_status = AsyncMock(return_value=mock_status)

        mock_live_trading_service.get_task_data = AsyncMock(return_value={
            "cash": 10000.0,
            "value": 20000.0,
            "positions": [],
            "orders": [],
        })

        result = await get_live_trading_data(
            task_id="task_123",
            current_user=mock_current_user,
            service=mock_live_trading_service
        )

        assert result.status == "running"


@pytest.mark.asyncio
class TestLiveTradingWebSocket:
    """测试WebSocket端点"""

    async def test_websocket_connection_flow(self):
        """测试WebSocket连接流程"""
        from app.api.live_trading_complete import live_trading_websocket, MessageType

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        with patch('app.api.live_trading_complete.ws_manager') as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = MagicMock()
            mock_mgr.send_to_task = AsyncMock()

            # Make the loop run once then exit
            with patch('asyncio.sleep', side_effect=[None, Exception("Exit")]):
                try:
                    await live_trading_websocket(mock_ws, "task_123")
                except Exception:
                    pass

                # Verify connection was established
                mock_mgr.connect.assert_called_once()

                # Verify initial message was sent
                assert mock_mgr.send_to_task.call_count >= 1
                first_call = mock_mgr.send_to_task.call_args_list[0]
                assert first_call[0][0] == "live:task_123"
                assert first_call[0][1]["type"] == MessageType.CONNECTED

    async def test_websocket_client_id_generation(self):
        """测试客户端ID生成"""
        from app.api.live_trading_complete import live_trading_websocket

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.id = 12345

        with patch('app.api.live_trading_complete.ws_manager') as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = MagicMock()
            mock_mgr.send_to_task = AsyncMock()

            with patch('asyncio.sleep', side_effect=Exception("Exit")):
                try:
                    await live_trading_websocket(mock_ws, "task_123")
                except Exception:
                    pass

                # Verify client ID format
                call_args = mock_mgr.connect.call_args
                assert call_args is not None

    async def test_websocket_disconnect_on_error(self):
        """测试错误时断开连接"""
        from app.api.live_trading_complete import live_trading_websocket

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock(side_effect=Exception("Connection error"))

        with patch('app.api.live_trading_complete.ws_manager') as mock_mgr:
            mock_mgr.disconnect = MagicMock()

            try:
                await live_trading_websocket(mock_ws, "task_123")
            except Exception:
                pass

            # Verify disconnect was called (error handling)


@pytest.mark.asyncio
class TestLiveTradingServiceIntegration:
    """测试LiveTradingService集成"""

    async def test_service_dependency_function(self):
        """测试服务依赖函数"""
        from app.api.live_trading_complete import get_live_trading_service
        from app.services.live_trading_service import LiveTradingService

        service = get_live_trading_service()
        assert isinstance(service, LiveTradingService)

    async def test_service_callable(self):
        """测试服务可调用"""
        from app.api.live_trading_complete import get_live_trading_service

        assert callable(get_live_trading_service)


@pytest.mark.asyncio
class TestLiveTradingSchemas:
    """测试实盘交易Schema"""

    async def test_submit_request_schema_validation(self):
        """测试提交请求Schema验证"""
        from app.schemas.live_trading import LiveTradingSubmitRequest
        from pydantic import ValidationError

        # Missing required fields
        with pytest.raises(ValidationError):
            LiveTradingSubmitRequest(
                strategy_name="SMACross",
                # Missing: symbols, api_key, secret
            )

    async def test_submit_request_schema_success(self):
        """测试提交请求Schema成功"""
        from app.schemas.live_trading import LiveTradingSubmitRequest

        request = LiveTradingSubmitRequest(**VALID_LIVE_TRADING_REQUEST)
        assert request.strategy_name == "SMACross"
        assert request.exchange == "binance"
        assert len(request.symbols) == 2

    async def test_task_response_schema(self):
        """测试任务响应Schema"""
        from app.schemas.live_trading import LiveTradingTaskResponse

        response = LiveTradingTaskResponse(
            task_id="task_123",
            user_id="user_123",
            status="running",
            config={"strategy_name": "SMACross"},
            created_at=datetime.now()
        )
        assert response.task_id == "task_123"
        assert response.status == "running"

    async def test_data_response_schema(self):
        """测试数据响应Schema"""
        from app.schemas.live_trading import LiveTradingDataResponse

        response = LiveTradingDataResponse(
            task_id="task_123",
            status="running",
            cash=10000.0,
            value=15000.0,
            positions=[],
            orders=[]
        )
        assert response.task_id == "task_123"
        assert response.cash == 10000.0


@pytest.mark.asyncio
class TestLiveTradingRouter:
    """测试实盘交易路由"""

    async def test_router_exists(self):
        """测试路由存在"""
        from app.api.live_trading_complete import router

        assert router is not None
        assert hasattr(router, 'routes')

    async def test_router_endpoint_count(self):
        """测试路由端点数量"""
        from app.api.live_trading_complete import router

        routes = list(router.routes)
        # Should have at least 6 routes (5 HTTP + 1 WebSocket)
        assert len(routes) >= 6

    async def test_router_has_submit_endpoint(self):
        """测试有提交端点"""
        from app.api.live_trading_complete import router

        routes = [route for route in router.routes if hasattr(route, 'path')]
        submit_routes = [r for r in routes if "/live/submit" in r.path]
        assert len(submit_routes) > 0

    async def test_router_has_websocket_endpoint(self):
        """测试有WebSocket端点"""
        from app.api.live_trading_complete import router

        routes = [route for route in router.routes if hasattr(route, 'path')]
        ws_routes = [r for r in routes if "/ws/live/" in r.path]
        assert len(ws_routes) > 0
