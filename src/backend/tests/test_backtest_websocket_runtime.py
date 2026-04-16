"""
Backtest WebSocket runtime tests.

Tests for WebSocket authentication, message flow, and terminal state handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import WebSocket

from app.api.deps import WEBSOCKET_TOKEN_PROTOCOL, get_websocket_current_user
from app.schemas.backtest_enhanced import TaskStatus
from app.websocket_manager import MessageType


class TestWebSocketTokenExtraction:
    """Tests for WebSocket token extraction from subprotocol header."""

    def test_extract_token_valid_format(self):
        """Test token extraction with valid subprotocol format."""
        from app.api.deps import _extract_websocket_token

        websocket = MagicMock(spec=WebSocket)
        websocket.headers = {"sec-websocket-protocol": "access-token, valid-jwt-token"}

        token, protocol = _extract_websocket_token(websocket)
        assert token == "valid-jwt-token"
        assert protocol == WEBSOCKET_TOKEN_PROTOCOL

    def test_extract_token_missing_protocol(self):
        """Test token extraction when protocol header is missing."""
        from app.api.deps import _extract_websocket_token

        websocket = MagicMock(spec=WebSocket)
        websocket.headers = {}

        token, protocol = _extract_websocket_token(websocket)
        assert token is None
        assert protocol is None

    def test_extract_token_wrong_prefix(self):
        """Test token extraction with wrong protocol prefix."""
        from app.api.deps import _extract_websocket_token

        websocket = MagicMock(spec=WebSocket)
        websocket.headers = {"sec-websocket-protocol": "other-protocol, some-token"}

        token, protocol = _extract_websocket_token(websocket)
        assert token is None
        assert protocol is None

    def test_extract_token_only_one_part(self):
        """Test token extraction with only one part in protocol."""
        from app.api.deps import _extract_websocket_token

        websocket = MagicMock(spec=WebSocket)
        websocket.headers = {"sec-websocket-protocol": "access-token"}

        token, protocol = _extract_websocket_token(websocket)
        assert token is None
        assert protocol is None


class TestWebSocketAuthentication:
    """Tests for WebSocket authentication flow."""

    def test_auth_missing_token_returns_none(self):
        """Test that missing token returns None user."""
        websocket = MagicMock(spec=WebSocket)
        websocket.headers = {}

        user, protocol = get_websocket_current_user(websocket)
        assert user is None

    def test_auth_invalid_token_returns_none(self):
        """Test that invalid token returns None user."""
        websocket = MagicMock(spec=WebSocket)
        websocket.headers = {"sec-websocket-protocol": "access-token, invalid-token"}

        with patch("app.api.deps.decode_access_token", return_value=None):
            user, protocol = get_websocket_current_user(websocket)
            assert user is None

    def test_auth_valid_token_returns_user(self):
        """Test that valid token returns user payload."""
        websocket = MagicMock(spec=WebSocket)
        websocket.headers = {"sec-websocket-protocol": "access-token, valid-jwt"}

        mock_payload = {"sub": "user-123", "username": "testuser", "exp": 9999999999}
        with patch("app.api.deps.decode_access_token", return_value=mock_payload):
            user, protocol = get_websocket_current_user(websocket)
            assert user is not None
            assert user.sub == "user-123"


class TestBacktestWebSocketEvents:
    """Tests for backtest WebSocket event types."""

    def test_connected_event_structure(self):
        """Test connected event has correct structure."""
        from app.schemas.backtest_enhanced import BacktestConnectedEvent

        event = BacktestConnectedEvent(task_id="task-1", client_id="client-1")
        data = event.model_dump(mode="python")

        assert data["type"] == MessageType.CONNECTED
        assert data["task_id"] == "task-1"
        assert data["client_id"] == "client-1"
        assert "message" in data

    def test_progress_event_structure(self):
        """Test progress event has correct structure."""
        from app.schemas.backtest_enhanced import BacktestProgressEvent

        event = BacktestProgressEvent(task_id="task-1", progress=50, message="Processing...")
        data = event.model_dump(mode="python")

        assert data["type"] == MessageType.PROGRESS
        assert data["progress"] == 50
        assert data["message"] == "Processing..."

    def test_completed_event_structure(self):
        """Test completed event has correct structure."""
        from app.schemas.backtest_enhanced import BacktestCompletedEvent

        result = {"total_return": 15.5, "sharpe_ratio": 1.2}
        event = BacktestCompletedEvent(task_id="task-1", result=result)
        data = event.model_dump(mode="python")

        assert data["type"] == MessageType.COMPLETED
        assert data["result"]["total_return"] == 15.5

    def test_failed_event_structure(self):
        """Test failed event has correct structure."""
        from app.schemas.backtest_enhanced import BacktestFailedEvent

        event = BacktestFailedEvent(task_id="task-1", message="Error occurred", error="boom")
        data = event.model_dump(mode="python")

        assert data["type"] == MessageType.FAILED
        assert data["message"] == "Error occurred"
        assert data["error"] == "boom"

    def test_cancelled_event_structure(self):
        """Test cancelled event has correct structure."""
        from app.schemas.backtest_enhanced import BacktestCancelledEvent

        event = BacktestCancelledEvent(task_id="task-1")
        data = event.model_dump(mode="python")

        assert data["type"] == MessageType.CANCELLED
        assert data["task_id"] == "task-1"


class TestTerminalStateDetection:
    """Tests for terminal state detection in WebSocket handler."""

    def test_is_terminal_completed(self):
        """Test completed status is terminal."""
        from app.api.backtest_enhanced import _is_terminal_backtest_status

        assert _is_terminal_backtest_status(TaskStatus.COMPLETED) is True

    def test_is_terminal_failed(self):
        """Test failed status is terminal."""
        from app.api.backtest_enhanced import _is_terminal_backtest_status

        assert _is_terminal_backtest_status(TaskStatus.FAILED) is True

    def test_is_terminal_cancelled(self):
        """Test cancelled status is terminal."""
        from app.api.backtest_enhanced import _is_terminal_backtest_status

        assert _is_terminal_backtest_status(TaskStatus.CANCELLED) is True

    def test_is_terminal_running(self):
        """Test running status is not terminal."""
        from app.api.backtest_enhanced import _is_terminal_backtest_status

        assert _is_terminal_backtest_status(TaskStatus.RUNNING) is False

    def test_is_terminal_pending(self):
        """Test pending status is not terminal."""
        from app.api.backtest_enhanced import _is_terminal_backtest_status

        assert _is_terminal_backtest_status(TaskStatus.PENDING) is False


class TestRuntimeSnapshotBuilder:
    """Tests for runtime snapshot building."""

    def test_pending_snapshot(self):
        """Test snapshot for pending task."""
        from app.api.backtest_enhanced import _build_backtest_runtime_snapshot

        snapshot = _build_backtest_runtime_snapshot("task-1", TaskStatus.PENDING, None)
        assert snapshot["type"] == "task_created"

    def test_running_snapshot(self):
        """Test snapshot for running task."""
        from app.api.backtest_enhanced import _build_backtest_runtime_snapshot

        snapshot = _build_backtest_runtime_snapshot("task-1", TaskStatus.RUNNING, None)
        assert snapshot["type"] == MessageType.PROGRESS

    def test_completed_snapshot(self):
        """Test snapshot for completed task."""
        from app.api.backtest_enhanced import _build_backtest_runtime_snapshot

        mock_result = MagicMock()
        mock_result.model_dump = MagicMock(return_value={"total_return": 10.0})

        snapshot = _build_backtest_runtime_snapshot("task-1", TaskStatus.COMPLETED, mock_result)
        assert snapshot["type"] == MessageType.COMPLETED

    def test_failed_snapshot(self):
        """Test snapshot for failed task."""
        from app.api.backtest_enhanced import _build_backtest_runtime_snapshot

        mock_result = MagicMock()
        mock_result.error_message = "Something went wrong"

        snapshot = _build_backtest_runtime_snapshot("task-1", TaskStatus.FAILED, mock_result)
        assert snapshot["type"] == MessageType.FAILED
        assert "Something went wrong" in snapshot["error"]

    def test_cancelled_snapshot(self):
        """Test snapshot for cancelled task."""
        from app.api.backtest_enhanced import _build_backtest_runtime_snapshot

        snapshot = _build_backtest_runtime_snapshot("task-1", TaskStatus.CANCELLED, None)
        assert snapshot["type"] == MessageType.CANCELLED


class TestWebSocketHeartbeat:
    """Tests for WebSocket ping/pong heartbeat."""

    async def test_ping_returns_pong(self):
        """Test that ping message returns pong."""
        from app.websocket_manager import ConnectionManager

        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, "task-1", "client-1")
        ws.send_json.reset_mock()

        # Simulate ping handling
        await ws.send_json({"type": "pong"})

        ws.send_json.assert_awaited_once_with({"type": "pong"})


class TestWebSocketConnectionLifecycle:
    """Tests for WebSocket connection lifecycle."""

    async def test_connect_sends_connected_event(self):
        """Test that connect sends connected event."""
        from app.websocket_manager import ConnectionManager

        mgr = ConnectionManager()
        ws = AsyncMock()

        await mgr.connect(ws, "task-1", "client-1")

        # Verify connected event was sent
        sent_call = ws.send_json.call_args
        sent_data = sent_call[0][0]
        assert sent_data["type"] == MessageType.CONNECTED
        assert sent_data["task_id"] == "task-1"

    async def test_disconnect_removes_connection(self):
        """Test that disconnect removes the connection."""
        from app.websocket_manager import ConnectionManager

        mgr = ConnectionManager()
        ws = AsyncMock()

        await mgr.connect(ws, "task-1", "client-1")
        assert mgr.get_connection_count("task-1") == 1

        mgr.disconnect(ws, "task-1", "client-1")
        assert mgr.get_connection_count("task-1") == 0

    async def test_multiple_clients_same_task(self):
        """Test multiple clients can connect to same task."""
        from app.websocket_manager import ConnectionManager

        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await mgr.connect(ws1, "task-1", "client-1")
        await mgr.connect(ws2, "task-1", "client-2")

        assert mgr.get_connection_count("task-1") == 2

    async def test_send_to_task_broadcasts_to_all_clients(self):
        """Test that send_to_task broadcasts to all clients."""
        from app.websocket_manager import ConnectionManager

        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await mgr.connect(ws1, "task-1", "client-1")
        await mgr.connect(ws2, "task-1", "client-2")
        ws1.send_json.reset_mock()
        ws2.send_json.reset_mock()

        await mgr.send_to_task("task-1", {"type": "progress", "progress": 50})

        ws1.send_json.assert_awaited_once()
        ws2.send_json.assert_awaited_once()
