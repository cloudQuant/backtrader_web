"""
WebSocket 连接管理器测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.websocket_manager import (
    ConnectionManager,
    MessageType,
    ProgressMessage,
    ResultMessage,
    LogMessage,
)


class TestConnectionManager:
    """连接管理器测试"""

    def test_init_empty(self):
        mgr = ConnectionManager()
        assert mgr.active_connections == {}
        assert mgr.get_total_connections() == 0

    async def test_connect(self):
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, "task-1", "client-1")
        assert mgr.get_connection_count("task-1") == 1
        ws.accept.assert_called_once()

    async def test_disconnect(self):
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, "task-1", "client-1")
        mgr.disconnect(ws, "task-1", "client-1")
        assert mgr.get_connection_count("task-1") == 0

    async def test_disconnect_nonexistent(self):
        mgr = ConnectionManager()
        ws = AsyncMock()
        mgr.disconnect(ws, "no-task", "no-client")  # should not raise

    async def test_send_to_task(self):
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, "task-1", "client-1")
        await mgr.send_to_task("task-1", {"type": "test", "data": "hello"})
        assert ws.send_json.call_count >= 2  # connected + test msg

    async def test_send_to_task_no_connections(self):
        mgr = ConnectionManager()
        await mgr.send_to_task("no-task", {"type": "test"})  # should not raise

    async def test_send_removes_dead_connections(self):
        mgr = ConnectionManager()
        ws = AsyncMock()
        ws.send_json.side_effect = Exception("connection closed")
        await mgr.connect(ws, "task-1", "client-1")
        # Reset to make send_json fail
        ws.send_json.side_effect = Exception("connection closed")
        await mgr.send_to_task("task-1", {"type": "test"})
        assert mgr.get_connection_count("task-1") == 0

    async def test_broadcast(self):
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1, "task-1", "client-1")
        await mgr.connect(ws2, "task-2", "client-2")
        await mgr.broadcast({"type": "global"})
        # Both connections should receive the message
        assert ws1.send_json.call_count >= 2
        assert ws2.send_json.call_count >= 2

    async def test_multiple_connections_per_task(self):
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1, "task-1", "client-1")
        await mgr.connect(ws2, "task-1", "client-2")
        assert mgr.get_connection_count("task-1") == 2
        assert mgr.get_total_connections() == 2

    def test_get_connection_count_no_task(self):
        mgr = ConnectionManager()
        assert mgr.get_connection_count("nonexistent") == 0


class TestMessageTypes:
    """消息类型测试"""

    def test_message_type_constants(self):
        assert MessageType.CONNECTED == "connected"
        assert MessageType.PROGRESS == "progress"
        assert MessageType.LOG == "log"
        assert MessageType.COMPLETED == "completed"
        assert MessageType.FAILED == "failed"
        assert MessageType.CANCELLED == "cancelled"


class TestProgressMessage:
    """进度消息测试"""

    def test_basic(self):
        msg = ProgressMessage("task-1", 50, "半完成")
        d = msg.to_dict()
        assert d["type"] == "progress"
        assert d["task_id"] == "task-1"
        assert d["progress"] == 50
        assert d["message"] == "半完成"
        assert d["data"] == {}

    def test_with_data(self):
        msg = ProgressMessage("task-1", 100, "完成", {"key": "value"})
        d = msg.to_dict()
        assert d["data"] == {"key": "value"}


class TestResultMessage:
    """结果消息测试"""

    def test_completed(self):
        msg = ResultMessage("task-1", {"status": "completed", "return": 15.0})
        d = msg.to_dict()
        assert d["type"] == "completed"
        assert d["task_id"] == "task-1"

    def test_failed(self):
        msg = ResultMessage("task-1", {"status": "failed", "error": "boom"})
        d = msg.to_dict()
        assert d["type"] == "failed"


class TestLogMessage:
    """日志消息测试"""

    def test_basic(self):
        msg = LogMessage("task-1", "info", "一切正常")
        d = msg.to_dict()
        assert d["type"] == "log"
        assert d["level"] == "info"
        assert d["message"] == "一切正常"
        assert d["data"] == {}

    def test_with_data(self):
        msg = LogMessage("task-1", "error", "出错了", {"detail": "xxx"})
        d = msg.to_dict()
        assert d["data"] == {"detail": "xxx"}
