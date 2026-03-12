"""
WebSocket Connection Manager Tests.
"""

from unittest.mock import AsyncMock

from app.websocket_manager import (
    ConnectionManager,
    LogMessage,
    MessageType,
    ProgressMessage,
    ResultMessage,
)


class TestConnectionManager:
    """Tests for connection manager."""

    def test_init_empty(self):
        """Test initialization with empty state."""
        mgr = ConnectionManager()
        assert mgr.active_connections == {}
        assert mgr.get_total_connections() == 0

    async def test_connect(self):
        """Test connecting a WebSocket client."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, "task-1", "client-1")
        assert mgr.get_connection_count("task-1") == 1
        ws.accept.assert_called_once()

    async def test_disconnect(self):
        """Test disconnecting a WebSocket client."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, "task-1", "client-1")
        mgr.disconnect(ws, "task-1", "client-1")
        assert mgr.get_connection_count("task-1") == 0

    async def test_disconnect_nonexistent(self):
        """Test disconnecting a non-existent connection."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        mgr.disconnect(ws, "no-task", "no-client")  # should not raise

    async def test_send_to_task(self):
        """Test sending a message to a specific task."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, "task-1", "client-1")
        await mgr.send_to_task("task-1", {"type": "test", "data": "hello"})
        assert ws.send_json.call_count >= 2  # connected + test msg

    async def test_send_to_task_no_connections(self):
        """Test sending to a task with no connections."""
        mgr = ConnectionManager()
        await mgr.send_to_task("no-task", {"type": "test"})  # should not raise

    async def test_send_removes_dead_connections(self):
        """Test that sending removes dead connections."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        ws.send_json.side_effect = Exception("connection closed")
        await mgr.connect(ws, "task-1", "client-1")
        # Reset to make send_json fail
        ws.send_json.side_effect = Exception("connection closed")
        await mgr.send_to_task("task-1", {"type": "test"})
        assert mgr.get_connection_count("task-1") == 0

    async def test_broadcast(self):
        """Test broadcasting to all connections."""
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
        """Test multiple connections for the same task."""
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1, "task-1", "client-1")
        await mgr.connect(ws2, "task-1", "client-2")
        assert mgr.get_connection_count("task-1") == 2
        assert mgr.get_total_connections() == 2

    def test_get_connection_count_no_task(self):
        """Test getting connection count for non-existent task."""
        mgr = ConnectionManager()
        assert mgr.get_connection_count("nonexistent") == 0


class TestMessageTypes:
    """Tests for message type constants."""

    def test_message_type_constants(self):
        """Test that message type constants are correct."""
        assert MessageType.CONNECTED == "connected"
        assert MessageType.PROGRESS == "progress"
        assert MessageType.LOG == "log"
        assert MessageType.COMPLETED == "completed"
        assert MessageType.FAILED == "failed"
        assert MessageType.CANCELLED == "cancelled"


class TestProgressMessage:
    """Tests for progress messages."""

    def test_basic(self):
        """Test basic progress message."""
        msg = ProgressMessage("task-1", 50, "Half complete")
        d = msg.to_dict()
        assert d["type"] == "progress"
        assert d["task_id"] == "task-1"
        assert d["progress"] == 50
        assert d["message"] == "Half complete"
        assert d["data"] == {}

    def test_with_data(self):
        """Test progress message with additional data."""
        msg = ProgressMessage("task-1", 100, "Complete", {"key": "value"})
        d = msg.to_dict()
        assert d["data"] == {"key": "value"}


class TestResultMessage:
    """Tests for result messages."""

    def test_completed(self):
        """Test completed result message."""
        msg = ResultMessage("task-1", {"status": "completed", "return": 15.0})
        d = msg.to_dict()
        assert d["type"] == "completed"
        assert d["task_id"] == "task-1"

    def test_failed(self):
        """Test failed result message."""
        msg = ResultMessage("task-1", {"status": "failed", "error": "boom"})
        d = msg.to_dict()
        assert d["type"] == "failed"


class TestLogMessage:
    """Tests for log messages."""

    def test_basic(self):
        """Test basic log message."""
        msg = LogMessage("task-1", "info", "Everything is normal")
        d = msg.to_dict()
        assert d["type"] == "log"
        assert d["level"] == "info"
        assert d["message"] == "Everything is normal"
        assert d["data"] == {}

    def test_with_data(self):
        """Test log message with additional data."""
        msg = LogMessage("task-1", "error", "Error occurred", {"detail": "xxx"})
        d = msg.to_dict()
        assert d["data"] == {"detail": "xxx"}
