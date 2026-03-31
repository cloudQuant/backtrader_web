"""
Backtest service tests aligned with the current task-manager + task-runner design.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.backtest import BacktestResultModel, BacktestTask
from app.schemas.backtest import BacktestRequest, BacktestResponse, BacktestResult, TaskStatus
from app.services.backtest_manager import BacktestExecutionManager
from app.services.backtest_runner import BacktestExecutionRunner
from app.services.backtest_service import BacktestService


def make_request(**overrides) -> BacktestRequest:
    """Create a standard backtest request for tests."""
    payload = {
        "strategy_id": "test_strategy",
        "symbol": "000001.SZ",
        "start_date": "2024-01-01T00:00:00",
        "end_date": "2024-06-30T00:00:00",
        "initial_cash": 100000,
        "commission": 0.001,
        "params": {},
    }
    payload.update(overrides)
    return BacktestRequest(**payload)


class TestBacktestServiceHelpers:
    """Helper method tests."""

    def test_has_custom_params_default(self):
        svc = BacktestService()
        assert svc._has_custom_params(make_request()) is False

    def test_has_custom_params_when_overrides_exist(self):
        svc = BacktestService()
        assert svc._has_custom_params(make_request(initial_cash=200000)) is True
        assert svc._has_custom_params(make_request(commission=0.002)) is True
        assert svc._has_custom_params(make_request(params={"period": 20})) is True

    def test_strip_asserts(self, tmp_path: Path):
        run_py = tmp_path / "run.py"
        run_py.write_text("x = 1\nassert x == 1\nassert(x > 0)\ny = 2\n", encoding="utf-8")
        BacktestService._strip_asserts(run_py)
        content = run_py.read_text(encoding="utf-8")
        assert "assert x == 1" not in content
        assert "assert(x > 0)" not in content
        assert "pass  # assert removed for web backtest" in content
        assert "x = 1" in content
        assert "y = 2" in content

    def test_write_temp_config(self, tmp_path: Path):
        svc = BacktestService()
        config_path = tmp_path / "config.yaml"
        svc._write_temp_config(
            config_path,
            make_request(
                symbol="600519.SH", initial_cash=200000, commission=0.002, params={"period": 30}
            ),
            None,
        )
        content = config_path.read_text(encoding="utf-8")
        assert "200000" in content
        assert "0.002" in content
        assert "period" in content
        assert "600519.SH" in content

    def test_build_backtest_result_falls_back_to_created_at_when_request_dates_missing(self):
        created_at = datetime(2024, 1, 15)
        task = BacktestTask(
            id="task123",
            user_id="user1",
            strategy_id="test_strategy",
            symbol="000001.SZ",
            status=TaskStatus.COMPLETED,
            request_data={"strategy_id": "test_strategy", "symbol": "000001.SZ"},
            created_at=created_at,
        )

        result = BacktestService._build_backtest_result(task, None)

        assert result.start_date == created_at
        assert result.end_date == created_at


@pytest.mark.asyncio
class TestRunBacktest:
    """Backtest submission tests."""

    async def test_run_backtest_uses_task_manager_and_runner(self):
        task_manager = MagicMock(spec=BacktestExecutionManager)
        task_manager.create_task = AsyncMock(
            return_value=BacktestTask(
                id="task123",
                user_id="user1",
                strategy_id="test_strategy",
                symbol="000001.SZ",
                status=TaskStatus.PENDING,
            )
        )
        task_runner = MagicMock(spec=BacktestExecutionRunner)
        svc = BacktestService(task_manager=task_manager, task_runner=task_runner)

        response = await svc.run_backtest("user1", make_request())

        assert response == BacktestResponse(
            task_id="task123",
            status=TaskStatus.PENDING,
            message="Backtest task created",
        )
        task_manager.create_task.assert_awaited_once()
        task_runner.schedule.assert_called_once()
        scheduled_task_id, scheduled_execution = task_runner.schedule.call_args.args
        assert scheduled_task_id == "task123"
        scheduled_execution.close()

    async def test_run_backtest_propagates_task_limit_errors(self):
        task_manager = MagicMock(spec=BacktestExecutionManager)
        task_manager.create_task = AsyncMock(side_effect=ValueError("limit reached"))
        svc = BacktestService(
            task_manager=task_manager, task_runner=MagicMock(spec=BacktestExecutionRunner)
        )

        with pytest.raises(ValueError, match="limit reached"):
            await svc.run_backtest("user1", make_request())


@pytest.mark.asyncio
class TestRunStrategySubprocess:
    """Subprocess execution tests."""

    async def test_run_strategy_subprocess_registers_local_process(self):
        task_runner = MagicMock(spec=BacktestExecutionRunner)
        svc = BacktestService(task_runner=task_runner)

        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            (work_dir / "run.py").write_text("print('success')", encoding="utf-8")

            process = MagicMock()
            process.returncode = 0
            process.communicate.return_value = ("output", "")

            with patch("subprocess.Popen", return_value=process):
                with patch("app.config.get_settings") as mock_settings:
                    mock_settings.return_value = MagicMock(BACKTEST_TIMEOUT=60)
                    result = await svc._run_strategy_subprocess(work_dir, task_id="task123")

        assert result == {"stdout": "output", "stderr": ""}
        task_runner.register_process.assert_called_once_with("task123", process)
        task_runner.unregister_process.assert_called_once_with("task123")

    async def test_run_strategy_subprocess_raises_on_failure(self):
        svc = BacktestService(task_runner=MagicMock(spec=BacktestExecutionRunner))

        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            (work_dir / "run.py").write_text("raise Exception('error')", encoding="utf-8")

            process = MagicMock()
            process.returncode = 1
            process.communicate.return_value = ("", "error message")

            with patch("subprocess.Popen", return_value=process):
                with patch("app.config.get_settings") as mock_settings:
                    mock_settings.return_value = MagicMock(BACKTEST_TIMEOUT=60)
                    with pytest.raises(RuntimeError, match="run.py execution failed"):
                        await svc._run_strategy_subprocess(work_dir, task_id="task123")


@pytest.mark.asyncio
class TestGetResult:
    """Result retrieval tests."""

    async def test_get_result_returns_cached_payload_when_authorized(self):
        svc = BacktestService()
        task = BacktestTask(
            id="task123",
            user_id="user1",
            strategy_id="test_strategy",
            symbol="000001.SZ",
            status=TaskStatus.COMPLETED,
            request_data={},
            created_at=datetime(2024, 1, 1),
        )
        cached = {
            "task_id": "task123",
            "strategy_id": "test_strategy",
            "symbol": "000001.SZ",
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-06-30T00:00:00",
            "status": TaskStatus.COMPLETED,
            "total_return": 20.0,
            "annual_return": 15.0,
            "sharpe_ratio": 1.2,
            "max_drawdown": -5.0,
            "win_rate": 55.0,
            "total_trades": 50,
            "profitable_trades": 28,
            "losing_trades": 22,
            "equity_curve": [100000, 101000],
            "equity_dates": ["2024-01-01", "2024-01-02"],
            "drawdown_curve": [0, -0.5],
            "trades": [],
            "created_at": "2024-01-01T00:00:00",
        }

        with patch.object(svc.task_repo, "get_by_id", return_value=task):
            with patch.object(svc.cache, "get", return_value=cached):
                result = await svc.get_result("task123", "user1")

        assert result is not None
        assert result.total_return == 20.0

    async def test_get_result_rejects_wrong_user(self):
        svc = BacktestService()
        task = BacktestTask(
            id="task123",
            user_id="user2",
            strategy_id="test_strategy",
            symbol="000001.SZ",
            status=TaskStatus.COMPLETED,
            request_data={},
            created_at=datetime(2024, 1, 1),
        )

        with patch.object(svc.task_repo, "get_by_id", return_value=task):
            result = await svc.get_result("task123", "user1")

        assert result is None

    async def test_get_result_builds_response_and_caches_completed_result(self):
        svc = BacktestService()
        task = BacktestTask(
            id="task123",
            user_id="user1",
            strategy_id="test_strategy",
            symbol="000001.SZ",
            status=TaskStatus.COMPLETED,
            request_data={"start_date": "2024-01-01", "end_date": "2024-06-30"},
            created_at=datetime(2024, 1, 1),
        )
        result_model = BacktestResultModel(
            id="result123",
            task_id="task123",
            total_return=15.5,
            annual_return=12.0,
            sharpe_ratio=1.5,
            max_drawdown=-8.0,
            win_rate=60.0,
            total_trades=100,
            profitable_trades=60,
            losing_trades=40,
            equity_curve=[100000, 101000],
            equity_dates=["2024-01-01", "2024-01-02"],
            drawdown_curve=[0, -0.5],
            trades=[],
            metrics_source="manual",
        )

        with patch.object(svc.task_repo, "get_by_id", return_value=task):
            with patch.object(svc.cache, "get", return_value=None):
                with patch.object(svc.result_repo, "list", return_value=[result_model]):
                    with patch.object(svc.cache, "set") as mock_cache_set:
                        result = await svc.get_result("task123", "user1")

        assert result is not None
        assert result.total_return == 15.5
        mock_cache_set.assert_awaited_once()


@pytest.mark.asyncio
class TestCancelTask:
    """Cancellation boundary tests."""

    async def test_cancel_task_requires_process_local_handle_for_running_task(self):
        task_runner = MagicMock(spec=BacktestExecutionRunner)
        task_runner.cancel_local_execution.return_value = False
        task_manager = MagicMock(spec=BacktestExecutionManager)
        task_manager.update_task_status = AsyncMock()
        svc = BacktestService(task_manager=task_manager, task_runner=task_runner)

        running_task = BacktestTask(id="task123", user_id="user1", status=TaskStatus.RUNNING)
        with patch.object(svc.task_repo, "get_by_id", return_value=running_task):
            result = await svc.cancel_task("task123", "user1")

        assert result is False
        task_manager.update_task_status.assert_not_awaited()

    async def test_cancel_task_marks_pending_task_cancelled(self):
        task_runner = MagicMock(spec=BacktestExecutionRunner)
        task_runner.cancel_local_execution.return_value = False
        task_manager = MagicMock(spec=BacktestExecutionManager)
        task_manager.update_task_status = AsyncMock()
        svc = BacktestService(task_manager=task_manager, task_runner=task_runner)

        pending_task = BacktestTask(id="task123", user_id="user1", status=TaskStatus.PENDING)
        with patch.object(svc.task_repo, "get_by_id", return_value=pending_task):
            result = await svc.cancel_task("task123", "user1")

        assert result is True
        task_manager.update_task_status.assert_awaited_once_with(
            "task123",
            TaskStatus.CANCELLED,
            error_message="User cancelled task",
        )

    async def test_cancel_task_cancels_local_running_execution(self):
        task_runner = MagicMock(spec=BacktestExecutionRunner)
        task_runner.cancel_local_execution.return_value = True
        task_manager = MagicMock(spec=BacktestExecutionManager)
        task_manager.update_task_status = AsyncMock()
        svc = BacktestService(task_manager=task_manager, task_runner=task_runner)

        running_task = BacktestTask(id="task123", user_id="user1", status=TaskStatus.RUNNING)
        with patch.object(svc.task_repo, "get_by_id", return_value=running_task):
            result = await svc.cancel_task("task123", "user1")

        assert result is True
        task_manager.update_task_status.assert_awaited_once()


@pytest.mark.asyncio
class TestListAndDeleteResults:
    """Result list and deletion tests."""

    async def test_list_results_uses_pagination_and_get_result(self):
        svc = BacktestService()
        tasks = [
            BacktestTask(
                id="task1",
                user_id="user1",
                strategy_id="s1",
                symbol="000001.SZ",
                status=TaskStatus.COMPLETED,
                request_data={},
                created_at=datetime(2024, 1, 1),
            ),
            BacktestTask(
                id="task2",
                user_id="user1",
                strategy_id="s2",
                symbol="000002.SZ",
                status=TaskStatus.COMPLETED,
                request_data={},
                created_at=datetime(2024, 1, 2),
            ),
        ]
        _mock_result = BacktestResult(  # noqa: F841 - created for test fixture reference
            task_id="task1",
            strategy_id="s1",
            symbol="000001.SZ",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 6, 30),
            status=TaskStatus.COMPLETED,
            total_return=10.0,
            annual_return=8.0,
            sharpe_ratio=1.0,
            max_drawdown=-5.0,
            win_rate=50.0,
            total_trades=50,
            profitable_trades=25,
            losing_trades=25,
            equity_curve=[],
            equity_dates=[],
            drawdown_curve=[],
            trades=[],
            created_at=datetime(2024, 1, 1),
            error_message=None,
            metrics_source="manual",
        )

        with patch.object(svc.task_repo, "list", return_value=tasks) as mock_list:
            with patch.object(svc.task_repo, "count", return_value=2):
                with patch.object(svc.result_repo, "list", return_value=[]):
                    response = await svc.list_results("user1", limit=2, offset=0)

        mock_list.assert_awaited_once_with(
            filters={"user_id": "user1"},
            skip=0,
            limit=2,
            order_by="created_at",
            order_desc=True,
        )
        assert response.total == 2
        assert len(response.items) == 2

    async def test_delete_result_deletes_logs_and_clears_cache(self):
        task_manager = MagicMock(spec=BacktestExecutionManager)
        task_manager.delete_task_and_result = AsyncMock(return_value=True)
        svc = BacktestService(task_manager=task_manager)
        task = BacktestTask(id="task123", user_id="user1", log_dir="/tmp/logs/task123")

        with patch.object(svc.task_repo, "get_by_id", return_value=task):
            with patch("pathlib.Path.is_dir", return_value=True):
                with patch("shutil.rmtree", side_effect=RuntimeError("rm boom")):
                    with patch.object(svc.cache, "delete") as mock_cache_delete:
                        result = await svc.delete_result("task123", "user1")

        assert result is True
        task_manager.delete_task_and_result.assert_awaited_once_with("task123", "user1")
        mock_cache_delete.assert_awaited_once_with("backtest:result:task123")

    async def test_delete_result_wrong_user_skips_log_cleanup(self):
        """Deletion by wrong user should not clean up logs."""
        task_manager = MagicMock(spec=BacktestExecutionManager)
        task_manager.delete_task_and_result = AsyncMock(return_value=False)
        svc = BacktestService(task_manager=task_manager)
        task = BacktestTask(id="task123", user_id="user2", log_dir="/tmp/logs/task123")

        with patch.object(svc.task_repo, "get_by_id", return_value=task):
            with patch.object(svc.cache, "delete") as mock_cache_delete:
                result = await svc.delete_result("task123", "user1")

        assert result is False
        mock_cache_delete.assert_not_awaited()

    async def test_list_results_empty_returns_zero(self):
        """Listing results for a user with no tasks returns empty list."""
        svc = BacktestService()

        with patch.object(svc.task_repo, "list", return_value=[]):
            with patch.object(svc.task_repo, "count", return_value=0):
                response = await svc.list_results("user1")

        assert response.total == 0
        assert len(response.items) == 0


@pytest.mark.asyncio
class TestGetResultErrorPaths:
    """Error path tests for get_result."""

    async def test_get_result_returns_none_for_missing_task(self):
        svc = BacktestService()
        with patch.object(svc.task_repo, "get_by_id", return_value=None):
            result = await svc.get_result("nonexistent")
        assert result is None

    async def test_get_result_no_result_model_returns_zero_metrics(self):
        """When task exists but no result model, metrics should default to zero."""
        svc = BacktestService()
        task = BacktestTask(
            id="task123",
            user_id="user1",
            strategy_id="s1",
            symbol="000001.SZ",
            status=TaskStatus.RUNNING,
            request_data={},
            created_at=datetime(2024, 1, 1),
        )
        with patch.object(svc.task_repo, "get_by_id", return_value=task):
            with patch.object(svc.cache, "get", return_value=None):
                with patch.object(svc.result_repo, "list", return_value=[]):
                    result = await svc.get_result("task123", "user1")

        assert result is not None
        assert result.total_return == 0
        assert result.sharpe_ratio == 0
        assert result.equity_curve == []

    async def test_get_result_running_task_not_cached(self):
        """Running tasks should not be cached."""
        svc = BacktestService()
        task = BacktestTask(
            id="task123",
            user_id="user1",
            strategy_id="s1",
            symbol="000001.SZ",
            status=TaskStatus.RUNNING,
            request_data={},
            created_at=datetime(2024, 1, 1),
        )
        with patch.object(svc.task_repo, "get_by_id", return_value=task):
            with patch.object(svc.cache, "get", return_value=None):
                with patch.object(svc.result_repo, "list", return_value=[]):
                    with patch.object(svc.cache, "set") as mock_set:
                        await svc.get_result("task123", "user1")
        mock_set.assert_not_awaited()


@pytest.mark.asyncio
class TestCancelTaskErrorPaths:
    """Error path tests for cancel_task."""

    async def test_cancel_nonexistent_task_returns_false(self):
        svc = BacktestService()
        with patch.object(svc.task_repo, "get_by_id", return_value=None):
            result = await svc.cancel_task("nonexistent", "user1")
        assert result is False

    async def test_cancel_wrong_user_returns_false(self):
        svc = BacktestService()
        task = BacktestTask(id="task123", user_id="user2", status=TaskStatus.RUNNING)
        with patch.object(svc.task_repo, "get_by_id", return_value=task):
            result = await svc.cancel_task("task123", "user1")
        assert result is False

    async def test_cancel_completed_task_returns_false(self):
        svc = BacktestService()
        task = BacktestTask(id="task123", user_id="user1", status=TaskStatus.COMPLETED)
        with patch.object(svc.task_repo, "get_by_id", return_value=task):
            result = await svc.cancel_task("task123", "user1")
        assert result is False

    async def test_cancel_already_cancelled_task_returns_false(self):
        svc = BacktestService()
        task = BacktestTask(id="task123", user_id="user1", status=TaskStatus.CANCELLED)
        with patch.object(svc.task_repo, "get_by_id", return_value=task):
            result = await svc.cancel_task("task123", "user1")
        assert result is False


@pytest.mark.asyncio
class TestGetTaskStatusErrorPaths:
    """Error path tests for get_task_status."""

    async def test_get_status_missing_task(self):
        svc = BacktestService()
        with patch.object(svc.task_repo, "get_by_id", return_value=None):
            result = await svc.get_task_status("nonexistent")
        assert result is None

    async def test_get_status_wrong_user(self):
        svc = BacktestService()
        task = BacktestTask(id="task123", user_id="user2", status=TaskStatus.COMPLETED)
        with patch.object(svc.task_repo, "get_by_id", return_value=task):
            result = await svc.get_task_status("task123", "user1")
        assert result is None

    async def test_get_status_correct_user(self):
        svc = BacktestService()
        task = BacktestTask(id="task123", user_id="user1", status=TaskStatus.COMPLETED)
        with patch.object(svc.task_repo, "get_by_id", return_value=task):
            result = await svc.get_task_status("task123", "user1")
        assert result == TaskStatus.COMPLETED

    async def test_get_status_no_user_filter(self):
        """Without user_id filter, any task status is returned."""
        svc = BacktestService()
        task = BacktestTask(id="task123", user_id="user2", status=TaskStatus.RUNNING)
        with patch.object(svc.task_repo, "get_by_id", return_value=task):
            result = await svc.get_task_status("task123")
        assert result == TaskStatus.RUNNING
