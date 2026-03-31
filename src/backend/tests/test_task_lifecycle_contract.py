"""
Task lifecycle contract tests (Iteration 123-A T3).

Verifies that both backtest and optimization task systems honour the
unified task status contract defined in docs/contracts/task-status-contract.md.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.backtest import BacktestTask
from app.schemas.backtest import TaskStatus
from app.services.backtest_manager import BacktestExecutionManager
from app.services.backtest_runner import BacktestExecutionRunner
from app.services.backtest_service import BacktestService
from app.services.param_optimization_service import (
    _get_task,
    _set_task,
    _update_task,
    cancel_optimization,
    get_optimization_progress,
)


class TestTaskStatusEnumContract:
    """Verify TaskStatus enum defines all required states."""

    def test_enum_has_all_required_states(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"

    def test_enum_has_exactly_five_states(self):
        assert len(TaskStatus) == 5

    def test_enum_values_are_lowercase_strings(self):
        for status in TaskStatus:
            assert status.value == status.value.lower()
            assert isinstance(status.value, str)


class TestBacktestTaskLifecycle:
    """Verify backtest task status transitions follow the contract."""

    @pytest.mark.asyncio
    async def test_create_task_starts_as_pending(self):
        manager = BacktestExecutionManager()
        from app.schemas.backtest import BacktestRequest

        request = BacktestRequest(
            strategy_id="test",
            symbol="000001.SZ",
            start_date="2024-01-01T00:00:00",
            end_date="2024-06-30T00:00:00",
        )
        task = await manager.create_task("user1", request)
        assert task.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_transition_pending_to_running(self):
        manager = BacktestExecutionManager()
        from app.schemas.backtest import BacktestRequest

        request = BacktestRequest(
            strategy_id="test",
            symbol="000001.SZ",
            start_date="2024-01-01T00:00:00",
            end_date="2024-06-30T00:00:00",
        )
        task = await manager.create_task("user1", request)
        updated = await manager.update_task_status(task.id, TaskStatus.RUNNING)
        assert updated is not None
        assert updated.status == TaskStatus.RUNNING

    @pytest.mark.asyncio
    async def test_transition_running_to_completed(self):
        manager = BacktestExecutionManager()
        from app.schemas.backtest import BacktestRequest

        request = BacktestRequest(
            strategy_id="test",
            symbol="000001.SZ",
            start_date="2024-01-01T00:00:00",
            end_date="2024-06-30T00:00:00",
        )
        task = await manager.create_task("user1", request)
        await manager.update_task_status(task.id, TaskStatus.RUNNING)
        updated = await manager.update_task_status(task.id, TaskStatus.COMPLETED)
        assert updated is not None
        assert updated.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_transition_running_to_failed_with_error(self):
        manager = BacktestExecutionManager()
        from app.schemas.backtest import BacktestRequest

        request = BacktestRequest(
            strategy_id="test",
            symbol="000001.SZ",
            start_date="2024-01-01T00:00:00",
            end_date="2024-06-30T00:00:00",
        )
        task = await manager.create_task("user1", request)
        await manager.update_task_status(task.id, TaskStatus.RUNNING)
        updated = await manager.update_task_status(
            task.id, TaskStatus.FAILED, error_message="subprocess error"
        )
        assert updated is not None
        assert updated.status == TaskStatus.FAILED
        assert updated.error_message == "subprocess error"

    @pytest.mark.asyncio
    async def test_cancel_pending_task(self):
        task_runner = MagicMock(spec=BacktestExecutionRunner)
        task_runner.cancel_local_execution.return_value = False
        task_manager = MagicMock(spec=BacktestExecutionManager)
        task_manager.update_task_status = AsyncMock()
        svc = BacktestService(task_manager=task_manager, task_runner=task_runner)

        pending_task = BacktestTask(id="task1", user_id="user1", status=TaskStatus.PENDING)
        with patch.object(svc.task_repo, "get_by_id", return_value=pending_task):
            result = await svc.cancel_task("task1", "user1")

        assert result is True
        task_manager.update_task_status.assert_awaited_once_with(
            "task1", TaskStatus.CANCELLED, error_message="User cancelled task"
        )

    @pytest.mark.asyncio
    async def test_cancel_completed_task_returns_false(self):
        task_runner = MagicMock(spec=BacktestExecutionRunner)
        task_manager = MagicMock(spec=BacktestExecutionManager)
        svc = BacktestService(task_manager=task_manager, task_runner=task_runner)

        completed_task = BacktestTask(id="task1", user_id="user1", status=TaskStatus.COMPLETED)
        with patch.object(svc.task_repo, "get_by_id", return_value=completed_task):
            result = await svc.cancel_task("task1", "user1")

        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_task_returns_false(self):
        task_runner = MagicMock(spec=BacktestExecutionRunner)
        task_manager = MagicMock(spec=BacktestExecutionManager)
        svc = BacktestService(task_manager=task_manager, task_runner=task_runner)

        cancelled_task = BacktestTask(id="task1", user_id="user1", status=TaskStatus.CANCELLED)
        with patch.object(svc.task_repo, "get_by_id", return_value=cancelled_task):
            result = await svc.cancel_task("task1", "user1")

        assert result is False

    @pytest.mark.asyncio
    async def test_query_nonexistent_task_returns_none(self):
        svc = BacktestService()
        with patch.object(svc.task_repo, "get_by_id", return_value=None):
            result = await svc.get_result("nonexistent", "user1")
        assert result is None


class TestOptimizationTaskLifecycle:
    """Verify optimization task status transitions follow the contract."""

    def test_submit_sets_running_status(self):
        from pathlib import Path

        param_ranges = {"p": {"start": 1, "end": 2, "step": 1, "type": "int"}}
        with patch("app.services.strategy_service.STRATEGIES_DIR", Path("/tmp/strategies")):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("threading.Thread"):
                    task_id = __import__(
                        "app.services.param_optimization_service", fromlist=["submit_optimization"]
                    ).submit_optimization("test", param_ranges)

        task = _get_task(task_id)
        assert task is not None
        assert task["status"] == TaskStatus.RUNNING.value
        assert task["param_ranges"] == param_ranges
        assert task["error"] is None

    def test_cancel_sets_cancelled_status(self):
        task_id = "lifecycle_cancel_test"
        _set_task(task_id, {"status": TaskStatus.RUNNING.value})

        result = cancel_optimization(task_id, use_db=False)

        assert result is True
        task = _get_task(task_id)
        assert task["status"] == TaskStatus.CANCELLED.value

    def test_cancel_nonexistent_returns_false(self):
        result = cancel_optimization("does_not_exist_xyz", use_db=False)
        assert result is False

    def test_manual_completion_uses_completed_status(self):
        task_id = "lifecycle_complete_test"
        _set_task(
            task_id,
            {
                "status": TaskStatus.RUNNING.value,
                "strategy_id": "test",
                "total": 1,
                "completed": 0,
                "failed": 0,
                "results": [],
                "n_workers": 1,
                "created_at": "2024-01-01",
            },
        )
        _update_task(task_id, status=TaskStatus.COMPLETED.value, completed=1)

        task = _get_task(task_id)
        assert task["status"] == TaskStatus.COMPLETED.value

    def test_error_uses_failed_status(self):
        task_id = "lifecycle_failed_test"
        _set_task(task_id, {"status": TaskStatus.RUNNING.value})
        _update_task(task_id, status=TaskStatus.FAILED.value, error="something broke")

        task = _get_task(task_id)
        assert task["status"] == TaskStatus.FAILED.value
        assert task["error"] == "something broke"

    def test_progress_query_returns_correct_status(self):
        task_id = "lifecycle_progress_test"
        _set_task(
            task_id,
            {
                "status": TaskStatus.RUNNING.value,
                "strategy_id": "test",
                "total": 10,
                "completed": 5,
                "failed": 0,
                "n_workers": 2,
                "created_at": "2024-01-01",
            },
        )

        progress = get_optimization_progress(task_id, use_db=False)
        assert progress is not None
        assert progress["status"] == TaskStatus.RUNNING.value
        assert progress["progress"] == 50.0

    def test_progress_query_nonexistent_returns_none(self):
        progress = get_optimization_progress("does_not_exist_xyz2", use_db=False)
        assert progress is None


class TestBacktestRunnerCancellation:
    """Verify BacktestExecutionRunner cancellation contract."""

    def test_cancel_with_local_handle_returns_true(self):
        runner = BacktestExecutionRunner()
        task = MagicMock()
        task.done.return_value = False
        runner._tasks["t1"] = task

        assert runner.cancel_local_execution("t1") is True
        task.cancel.assert_called_once()

    def test_cancel_without_local_handle_returns_false(self):
        runner = BacktestExecutionRunner()
        assert runner.cancel_local_execution("no_such_task") is False

    @pytest.mark.asyncio
    async def test_schedule_and_cleanup(self):
        runner = BacktestExecutionRunner()
        done = asyncio.Event()

        async def work():
            done.set()

        task = runner.schedule("t1", work())
        await done.wait()
        await task
        assert runner.get_task("t1") is None
