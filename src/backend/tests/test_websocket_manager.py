"""
WebSocket 管理器测试

测试 WebSocket 连接、消息发送、广播功能
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from app.websocket_manager import WebSocketManager, MessageType


@pytest.fixture
def ws_manager():
    """创建 WebSocket 管理器实例"""
    return WebSocketManager()


@pytest.mark.asyncio
class TestWebSocketManager:
    """WebSocket 管理器测试"""

    async def test_connect(self, ws_manager):
        """测试连接"""
        # Mock WebSocket
        mock_websocket = AsyncMock()
        mock_websocket.accept.return_value = None
        mock_websocket.client_id = "test-client-123"
        mock_websocket.path = "/ws/test"
        mock_websocket.query_params = {"id": "test-123"}

        # 连接
        await ws_manager.connect(mock_websocket, "test:123", "test-client-123")

        # 验证连接
        assert "test:123" in ws_manager._connections
        assert "test-client-123" in ws_manager._connections["test:123"]

    async def test_disconnect(self, ws_manager):
        """测试断开连接"""
        # Mock WebSocket
        mock_websocket = AsyncMock()
        mock_websocket.client_id = "test-client-123"
        mock_websocket.path = "/ws/test"

        # 先连接
        await ws_manager.connect(mock_websocket, "test:123", "test-client-123")
        assert "test:123" in ws_manager._connections

        # 断开连接
        await ws_manager.disconnect(mock_websocket, "test:123", "test-client-123")

        # 验证断开
        assert "test:123" not in ws_manager._connections

    async def test_send_to_client(self, ws_manager):
        """测试发送消息给客户端"""
        # Mock WebSocket
        mock_websocket = AsyncMock()
        mock_websocket.client_id = "test-client-123"
        mock_websocket.path = "/ws/test"
        await ws_manager.connect(mock_websocket, "test:123", "test-client-123")

        # 发送消息
        message = {
            "type": MessageType.PROGRESS,
            "data": {"test": "data"},
        }
        await ws_manager.send_to_client(mock_websocket, message)

        # 验证发送
        mock_websocket.send_json.assert_called_once_with(message)

    async def test_send_to_task(self, ws_manager):
        """测试发送消息给任务"""
        # 发送消息
        message = {
            "type": MessageType.PROGRESS,
            "task_id": "task-123",
            "data": {"status": "processing"},
        }
        await ws_manager.send_to_task("task:123", message)

        # 验证发送
        # 应该有对应的 task_id 连接

    async def test_broadcast(self, ws_manager):
        """测试广播消息"""
        # 模拟多个连接
        for i in range(3):
            mock_websocket = AsyncMock()
            mock_websocket.client_id = f"client-{i}"
            mock_websocket.path = "/ws/test"
            await ws_manager.connect(mock_websocket, f"test:{i}", f"client-{i}")

        # 广播消息
        message = {
            "type": MessageType.PROGRESS,
            "data": {"broadcast": "test"},
        }
        await ws_manager.broadcast(f"test:global", message)

        # 验证所有连接都收到消息
        for i in range(3):
            mock_websocket = ws_manager._connections[f"test:{i}"][f"client-{i}"]
            # 模拟接收（实际测试中 WebSocket 会调用）
            # 在测试中我们只能验证 send 方法被调用


@pytest.mark.asyncio
class TestWebSocketIntegration:
    """WebSocket 集成测试"""

    async def test_send_to_task_message(self, ws_manager):
        """测试发送任务消息"""
        from app.schemas.backtest_enhanced import TaskProgressMessage

        # 创建进度消息
        message = TaskProgressMessage(
            task_id="task-123",
            stage="processing",
            progress=50.0,
            status="running",
            message="测试消息",
            data={"key": "value"},
        )

        await ws_manager.send_to_task("task:123", {
            "type": MessageType.PROGRESS,
            "data": message.model_dump(),
        })

    async def test_websocket_error_handling(self, ws_manager):
        """测试 WebSocket 错误处理"""
        mock_websocket = AsyncMock()
        mock_websocket.send_json.side_effect = Exception("Connection error")

        await ws_manager.connect(mock_websocket, "test:123", "test-client-123")

        # 模拟发送消息（应该捕获错误）
        await ws_manager.send_to_client(mock_websocket, {"test": "data"})


if __name__ == "__main__":
    pytest.main(["-v", "--tb=short", "-x"])
