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
        ws.send_json.assert_awaited_once_with(
            {
                "type": MessageType.CONNECTED,
                "task_id": "task-1",
                "client_id": "client-1",
                "message": "WebSocket connected successfully",
            }
        )

    async def test_connect_does_not_broadcast_connected_to_existing_connections(self):
        """Test that connection acknowledgement is sent only to the new connection."""
        mgr = ConnectionManager()
        existing_ws = AsyncMock()
        new_ws = AsyncMock()

        await mgr.connect(existing_ws, "task-1", "client-1")
        existing_ws.send_json.reset_mock()

        await mgr.connect(new_ws, "task-1", "client-2")

        existing_ws.send_json.assert_not_called()
        new_ws.send_json.assert_awaited_once_with(
            {
                "type": MessageType.CONNECTED,
                "task_id": "task-1",
                "client_id": "client-2",
                "message": "WebSocket connected successfully",
            }
        )

    async def test_disconnect(self):
        """Test disconnecting a WebSocket client."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, "task-1", "client-1")
        mgr.disconnect(ws, "task-1", "client-1")
        assert mgr.get_connection_count("task-1") == 0

    async def test_disconnect_preserves_other_connections_for_same_task(self):
        """Test disconnecting one client does not remove other clients on the same task."""
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await mgr.connect(ws1, "task-1", "client-1")
        await mgr.connect(ws2, "task-1", "client-2")

        mgr.disconnect(ws1, "task-1", "client-1")

        assert mgr.get_connection_count("task-1") == 1
        assert mgr.active_connections["task-1"] == [(ws2, "client-2")]

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
        ws.send_json.reset_mock()
        await mgr.send_to_task("task-1", {"type": "test", "data": "hello"})
        ws.send_json.assert_awaited_once_with({"type": "test", "data": "hello"})

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
        ws1.send_json.reset_mock()
        ws2.send_json.reset_mock()
        await mgr.broadcast({"type": "global"})
        # Both connections should receive the message
        ws1.send_json.assert_awaited_once_with({"type": "global"})
        ws2.send_json.assert_awaited_once_with({"type": "global"})

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


class TestConnectionManagerAdvanced:
    """Advanced tests for connection manager edge cases."""

    async def test_connect_with_subprotocol(self):
        """Test connecting with a subprotocol."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, "task-1", "client-1", subprotocol="custom-protocol")
        ws.accept.assert_called_once_with(subprotocol="custom-protocol")
        assert mgr.get_connection_count("task-1") == 1

    async def test_send_to_connection_failure(self):
        """Test send_to_connection handles failures."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        ws.send_json.side_effect = Exception("Connection lost")
        result = await mgr.send_to_connection(ws, {"type": "test"})
        assert result is False

    async def test_send_to_connection_success(self):
        """Test send_to_connection success."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        result = await mgr.send_to_connection(ws, {"type": "test"})
        assert result is True
        ws.send_json.assert_awaited_once()

    async def test_broadcast_removes_dead_connections(self):
        """Test broadcast removes dead connections."""
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws2.send_json.side_effect = Exception("Connection lost")
        await mgr.connect(ws1, "task-1", "client-1")
        await mgr.connect(ws2, "task-2", "client-2")
        await mgr.broadcast({"type": "global"})
        # ws2 should be disconnected
        assert mgr.get_connection_count("task-2") == 0
        assert mgr.get_connection_count("task-1") == 1

    async def test_disconnect_removes_empty_task(self):
        """Test disconnect removes task entry when no connections remain."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, "task-1", "client-1")
        mgr.disconnect(ws, "task-1", "client-1")
        assert "task-1" not in mgr.active_connections

    async def test_multiple_disconnects_same_task(self):
        """Test multiple disconnects on same task."""
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1, "task-1", "client-1")
        await mgr.connect(ws2, "task-1", "client-2")
        mgr.disconnect(ws1, "task-1", "client-1")
        mgr.disconnect(ws2, "task-1", "client-2")
        assert "task-1" not in mgr.active_connections
        assert mgr.get_total_connections() == 0

    async def test_send_to_task_multiple_connections(self):
        """Test send_to_task sends to all connections for a task."""
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1, "task-1", "client-1")
        await mgr.connect(ws2, "task-1", "client-2")
        ws1.send_json.reset_mock()
        ws2.send_json.reset_mock()
        await mgr.send_to_task("task-1", {"type": "test"})
        ws1.send_json.assert_awaited_once()
        ws2.send_json.assert_awaited_once()

    async def test_disconnect_wrong_client_id(self):
        """Test disconnect with wrong client_id doesn't remove other clients."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, "task-1", "client-1")
        mgr.disconnect(ws, "task-1", "wrong-client")
        assert mgr.get_connection_count("task-1") == 1

    async def test_disconnect_wrong_websocket(self):
        """Test disconnect with wrong websocket doesn't remove other clients."""
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1, "task-1", "client-1")
        mgr.disconnect(ws2, "task-1", "client-1")
        assert mgr.get_connection_count("task-1") == 1


class TestProgressMessageAdvanced:
    """Advanced tests for progress messages."""

    def test_default_data(self):
        """Test default empty data dict."""
        msg = ProgressMessage("task-1", 50)
        assert msg.data == {}
        assert msg.message == ""

    def test_progress_bounds(self):
        """Test progress at boundaries."""
        msg0 = ProgressMessage("task-1", 0)
        msg100 = ProgressMessage("task-1", 100)
        assert msg0.progress == 0
        assert msg100.progress == 100


class TestResultMessageAdvanced:
    """Advanced tests for result messages."""

    def test_status_determination_completed(self):
        """Test type is 'completed' when status is completed."""
        from app.schemas.backtest_enhanced import TaskStatus
        msg = ResultMessage("task-1", {"status": TaskStatus.COMPLETED, "value": 100})
        assert msg.type == "completed"

    def test_status_determination_failed(self):
        """Test type is 'failed' when status is not completed."""
        msg = ResultMessage("task-1", {"status": "failed", "error": "boom"})
        assert msg.type == "failed"

    def test_status_determination_running(self):
        """Test type is 'failed' for non-completed statuses."""
        msg = ResultMessage("task-1", {"status": "running"})
        assert msg.type == "failed"


class TestLogMessageAdvanced:
    """Advanced tests for log messages."""

    def test_various_levels(self):
        """Test various log levels."""
        for level in ["info", "warning", "error", "debug"]:
            msg = LogMessage("task-1", level, "message")
            assert msg.level == level

    def test_default_data(self):
        """Test default empty data dict."""
        msg = LogMessage("task-1", "info", "message")
        assert msg.data == {}
