"""
Tests for InstanceStore, WebSocket message classes, ConnectionManager,
and permission utilities.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.instance_store import InstanceStore
from app.websocket_manager import (
    ConnectionManager,
    ErrorMessage,
    LogMessage,
    MessageType,
    ProgressMessage,
    ResultMessage,
)

# ============================================================
# InstanceStore Tests
# ============================================================


class TestInstanceStore:
    """Test JSON-file backed instance store."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a store with a temp file."""
        return InstanceStore(instances_file=tmp_path / "instances.json")

    def test_load_all_empty(self, store):
        """load_all should return empty dict when file doesn't exist."""
        result = store.load_all()
        assert result == {}

    def test_save_and_load(self, store):
        """save_all then load_all should round-trip data."""
        data = {"inst-1": {"name": "test", "status": "running"}}
        store.save_all(data)
        loaded = store.load_all()
        assert loaded == data

    def test_put_creates_entry(self, store):
        """put should create a new entry."""
        store.put("inst-1", {"name": "test", "status": "stopped"})
        result = store.get("inst-1")
        assert result == {"name": "test", "status": "stopped"}

    def test_put_updates_entry(self, store):
        """put should update an existing entry."""
        store.put("inst-1", {"name": "test", "status": "stopped"})
        store.put("inst-1", {"name": "test", "status": "running"})
        result = store.get("inst-1")
        assert result["status"] == "running"

    def test_get_nonexistent(self, store):
        """get should return None for non-existent ID."""
        assert store.get("nonexistent") is None

    def test_delete_existing(self, store):
        """delete should remove an existing entry."""
        store.put("inst-1", {"name": "test"})
        result = store.delete("inst-1")
        assert result is True
        assert store.get("inst-1") is None

    def test_delete_nonexistent(self, store):
        """delete should return False for non-existent ID."""
        result = store.delete("nonexistent")
        assert result is False

    def test_update_fields(self, store):
        """update_fields should update specific fields."""
        store.put("inst-1", {"name": "test", "status": "stopped", "port": 8000})
        result = store.update_fields("inst-1", status="running", port=9000)
        assert result["status"] == "running"
        assert result["port"] == 9000
        assert result["name"] == "test"

    def test_update_fields_nonexistent(self, store):
        """update_fields should return None for non-existent ID."""
        result = store.update_fields("nonexistent", status="running")
        assert result is None

    def test_load_corrupted_file(self, tmp_path):
        """load_all should return empty dict for corrupted JSON."""
        file = tmp_path / "bad.json"
        file.write_text("not valid json {{{", encoding="utf-8")
        store = InstanceStore(instances_file=file)
        assert store.load_all() == {}

    def test_multiple_instances(self, store):
        """Should handle multiple instances correctly."""
        store.put("inst-1", {"name": "first"})
        store.put("inst-2", {"name": "second"})
        store.put("inst-3", {"name": "third"})
        all_data = store.load_all()
        assert len(all_data) == 3
        assert all_data["inst-2"]["name"] == "second"


# ============================================================
# WebSocket Message Classes Tests
# ============================================================


class TestProgressMessage:
    """Test ProgressMessage class."""

    def test_basic_progress(self):
        msg = ProgressMessage(task_id="task-1", progress=50, message="Running...")
        d = msg.to_dict()
        assert d["type"] == "progress"
        assert d["task_id"] == "task-1"
        assert d["progress"] == 50
        assert d["message"] == "Running..."

    def test_progress_with_data(self):
        msg = ProgressMessage(task_id="task-1", progress=75, data={"bar": 100})
        d = msg.to_dict()
        assert d["data"]["bar"] == 100

    def test_progress_defaults(self):
        msg = ProgressMessage(task_id="task-1", progress=0)
        d = msg.to_dict()
        assert d["message"] == ""
        assert d["data"] == {}


class TestResultMessage:
    """Test ResultMessage class."""

    def test_completed_result(self):
        msg = ResultMessage(task_id="task-1", result={"status": "completed", "sharpe": 1.5})
        d = msg.to_dict()
        assert d["type"] == "completed"
        assert d["task_id"] == "task-1"
        assert d["result"]["sharpe"] == 1.5

    def test_failed_result(self):
        msg = ResultMessage(task_id="task-1", result={"status": "failed", "error": "timeout"})
        d = msg.to_dict()
        assert d["type"] == "failed"


class TestErrorMessage:
    """Test ErrorMessage class."""

    def test_basic_error(self):
        msg = ErrorMessage(code="AUTH_FAILED", message="Invalid token")
        d = msg.to_dict()
        assert d["type"] == "error"
        assert d["code"] == "AUTH_FAILED"
        assert d["message"] == "Invalid token"
        assert "task_id" not in d

    def test_error_with_task_id(self):
        msg = ErrorMessage(code="TIMEOUT", message="Timed out", task_id="task-1")
        d = msg.to_dict()
        assert d["task_id"] == "task-1"

    def test_error_with_data(self):
        msg = ErrorMessage(code="ERR", message="fail", data={"detail": "info"})
        d = msg.to_dict()
        assert d["data"]["detail"] == "info"


class TestLogMessage:
    """Test LogMessage class."""

    def test_info_log(self):
        msg = LogMessage(task_id="task-1", level="info", message="Started backtest")
        d = msg.to_dict()
        assert d["type"] == "log"
        assert d["level"] == "info"
        assert d["message"] == "Started backtest"

    def test_error_log_with_data(self):
        msg = LogMessage(task_id="task-1", level="error", message="Failed", data={"line": 42})
        d = msg.to_dict()
        assert d["data"]["line"] == 42


class TestMessageType:
    """Test MessageType constants."""

    def test_message_types_exist(self):
        assert MessageType.CONNECTED == "connected"
        assert MessageType.PROGRESS == "progress"
        assert MessageType.LOG == "log"
        assert MessageType.COMPLETED == "completed"
        assert MessageType.FAILED == "failed"
        assert MessageType.CANCELLED == "cancelled"
        assert MessageType.ERROR == "error"


# ============================================================
# ConnectionManager Tests
# ============================================================


class TestConnectionManager:
    """Test WebSocket ConnectionManager."""

    def test_initial_state(self):
        mgr = ConnectionManager()
        assert mgr.get_total_connections() == 0
        assert mgr.get_connection_count("any-task") == 0

    def test_disconnect_removes_connection(self):
        mgr = ConnectionManager()
        ws = MagicMock()
        # Manually add a connection
        mgr.active_connections["task-1"] = [(ws, "client-1")]
        assert mgr.get_connection_count("task-1") == 1

        mgr.disconnect(ws, "task-1", "client-1")
        assert mgr.get_connection_count("task-1") == 0
        assert "task-1" not in mgr.active_connections

    def test_disconnect_nonexistent_task(self):
        """Disconnecting from non-existent task should not raise."""
        mgr = ConnectionManager()
        ws = MagicMock()
        mgr.disconnect(ws, "nonexistent", "client-1")  # Should not raise

    def test_get_connection_count(self):
        mgr = ConnectionManager()
        ws1 = MagicMock()
        ws2 = MagicMock()
        mgr.active_connections["task-1"] = [(ws1, "c1"), (ws2, "c2")]
        assert mgr.get_connection_count("task-1") == 2

    def test_get_total_connections(self):
        mgr = ConnectionManager()
        mgr.active_connections["task-1"] = [(MagicMock(), "c1")]
        mgr.active_connections["task-2"] = [(MagicMock(), "c2"), (MagicMock(), "c3")]
        assert mgr.get_total_connections() == 3

    async def test_send_to_task_no_connections(self):
        """send_to_task with no connections should not raise."""
        mgr = ConnectionManager()
        await mgr.send_to_task("nonexistent", {"type": "test"})

    async def test_send_to_connection_success(self):
        """send_to_connection should return True on success."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        result = await mgr.send_to_connection(ws, {"type": "test"})
        assert result is True
        ws.send_json.assert_called_once_with({"type": "test"})

    async def test_send_to_connection_failure(self):
        """send_to_connection should return False on failure."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        ws.send_json.side_effect = Exception("connection closed")
        result = await mgr.send_to_connection(ws, {"type": "test"})
        assert result is False

    async def test_send_to_closed_connection(self):
        """send_to_connection should return False for known-closed connections."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        mgr._closed_connections.add(ws)
        result = await mgr.send_to_connection(ws, {"type": "test"})
        assert result is False
        ws.send_json.assert_not_called()


# ============================================================
# Permission Utilities Tests
# ============================================================


class TestPermissionUtils:
    """Test permission checking utilities."""

    def test_has_permission_import(self):
        """has_permission should be importable."""
        from app.api._dependencies import has_permission
        assert callable(has_permission)

    def test_has_permission_with_admin_role(self):
        """Admin role should have all permissions."""
        from app.api._dependencies import has_permission
        from app.models.permission import Permission, Role

        # Create a mock user with admin role
        user = MagicMock()
        role_mock = MagicMock()
        role_mock.role = Role.ADMIN.value
        user.roles = [role_mock]

        # Admin should have CREATE_STRATEGY permission
        result = has_permission(user, Permission.CREATE_STRATEGY)
        assert result is True

    def test_has_permission_without_role(self):
        """User with no roles should have no permissions."""
        from app.api._dependencies import has_permission
        from app.models.permission import Permission

        user = MagicMock()
        user.roles = []

        result = has_permission(user, Permission.CREATE_STRATEGY)
        assert result is False

    def test_require_permission_creates_dependency(self):
        """require_permission should return a callable."""
        from app.api._dependencies import require_permission
        from app.models.permission import Permission

        dep = require_permission(Permission.RUN_BACKTEST)
        assert callable(dep)

    def test_require_any_permission_creates_dependency(self):
        """require_any_permission should return a callable."""
        from app.api._dependencies import require_any_permission
        from app.models.permission import Permission

        dep = require_any_permission(Permission.CREATE_STRATEGY, Permission.RUN_BACKTEST)
        assert callable(dep)
