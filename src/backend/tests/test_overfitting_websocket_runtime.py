from unittest.mock import MagicMock

from app.schemas.overfitting import OverfittingRiskLevel
from app.websocket_manager import MessageType


class TestOverfittingWebSocketRoute:
    def test_websocket_overfitting_route_exists(self) -> None:
        from app.main import app

        routes = [route for route in app.routes if hasattr(route, "path")]
        ws_routes = [route for route in routes if "/ws/overfitting/" in route.path]
        assert len(ws_routes) > 0


class TestOverfittingTerminalStateDetection:
    def test_terminal_completed(self) -> None:
        from app.api.overfitting import _is_terminal_overfitting_status

        assert _is_terminal_overfitting_status("completed") is True

    def test_terminal_failed(self) -> None:
        from app.api.overfitting import _is_terminal_overfitting_status

        assert _is_terminal_overfitting_status("failed") is True

    def test_terminal_running(self) -> None:
        from app.api.overfitting import _is_terminal_overfitting_status

        assert _is_terminal_overfitting_status("running") is False


class TestOverfittingRuntimeSnapshotBuilder:
    def test_pending_snapshot(self) -> None:
        from app.api.overfitting import _build_overfitting_runtime_snapshot

        snapshot = _build_overfitting_runtime_snapshot("ot-1", "pending", None)
        assert snapshot["type"] == "task_created"
        assert snapshot["task_id"] == "ot-1"

    def test_running_snapshot(self) -> None:
        from app.api.overfitting import _build_overfitting_runtime_snapshot

        snapshot = _build_overfitting_runtime_snapshot("ot-1", "running", None)
        assert snapshot["type"] == MessageType.PROGRESS

    def test_completed_snapshot(self) -> None:
        from app.api.overfitting import _build_overfitting_runtime_snapshot

        mock_result = MagicMock()
        mock_result.summary = "检测完成"
        mock_result.model_dump = MagicMock(return_value={"robustness_score": 81.5})

        snapshot = _build_overfitting_runtime_snapshot("ot-1", "completed", mock_result)
        assert snapshot["type"] == MessageType.COMPLETED
        assert snapshot["result"]["robustness_score"] == 81.5

    def test_failed_snapshot(self) -> None:
        from app.api.overfitting import _build_overfitting_runtime_snapshot

        mock_result = MagicMock()
        mock_result.summary = "检测失败"
        mock_result.error_message = "boom"

        snapshot = _build_overfitting_runtime_snapshot("ot-1", "failed", mock_result)
        assert snapshot["type"] == MessageType.FAILED
        assert snapshot["error"] == "boom"

    def test_completed_result_level_available(self) -> None:
        from app.api.overfitting import _build_overfitting_runtime_snapshot

        mock_result = MagicMock()
        mock_result.summary = "检测完成"
        mock_result.overall_level = OverfittingRiskLevel.LOW
        mock_result.model_dump = MagicMock(return_value={"overall_level": "low"})

        snapshot = _build_overfitting_runtime_snapshot("ot-1", "completed", mock_result)
        assert snapshot["result"]["overall_level"] == "low"
