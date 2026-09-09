"""
Backtest service tests aligned with the current task-manager + task-runner design.
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.models.backtest import BacktestResultModel, BacktestTask
from app.schemas.backtest import BacktestRequest, BacktestResponse, BacktestResult, TaskStatus
from app.services.backtest.manager import BacktestExecutionManager
from app.services.backtest.runner import BacktestExecutionRunner
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

    def test_request_rejects_client_runtime_dir(self):
        with pytest.raises(ValidationError, match="BACKTEST_RUNTIME_DIR_CLIENT_FORBIDDEN"):
            make_request(runtime_dir="/tmp/client-selected-runtime")

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

    def test_normalize_trade_logger_params_rewrites_legacy_kwargs(self, tmp_path: Path):
        run_py = tmp_path / "run.py"
        run_py.write_text(
            "cerebro.addobserver(\n"
            "    bt.observers.TradeLogger,\n"
            "    log_data=True,\n"
            "    log_file_enabled=True,\n"
            "    file_format='log',\n"
            "    log_dir=log_dir,\n"
            ")\n",
            encoding="utf-8",
        )
        BacktestService._normalize_trade_logger_params(run_py)
        content = run_py.read_text(encoding="utf-8")
        assert "log_bars=True" in content
        assert "log_data=" not in content
        assert "log_file_enabled" not in content
        assert "file_format=" not in content
        assert "log_format='text'" in content

    def test_normalize_trade_logger_params_noop_on_current_params(self, tmp_path: Path):
        run_py = tmp_path / "run.py"
        original = (
            "cerebro.addobserver(\n"
            "    bt.observers.TradeLogger,\n"
            "    log_bars=True,\n"
            "    log_format='text',\n"
            "    log_dir=str(log_dir),\n"
            ")\n"
        )
        run_py.write_text(original, encoding="utf-8")
        BacktestService._normalize_trade_logger_params(run_py)
        assert run_py.read_text(encoding="utf-8") == original

    def test_copy_log_artifacts_copies_flat_logs_into_task_dir(self, tmp_path: Path):
        source_dir = tmp_path / "logs"
        source_dir.mkdir()
        target_dir = source_dir / "task_task123"
        (source_dir / "bar.log").write_text("bar-data\n", encoding="utf-8")
        (source_dir / "value.log").write_text("value-data\n", encoding="utf-8")

        BacktestService._copy_log_artifacts(source_dir, target_dir)

        assert (target_dir / "bar.log").read_text(encoding="utf-8") == "bar-data\n"
        assert (target_dir / "value.log").read_text(encoding="utf-8") == "value-data\n"

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

    def test_sanitize_trades_normalizes_legacy_trade_records(self):
        trades = BacktestService._sanitize_trades(
            [
                {
                    "datetime": "2024-01-02 09:30:00",
                    "direction": "long",
                    "price": 12.5,
                    "size": 2.0,
                    "value": 25.0,
                    "pnl": 1.5,
                },
                {
                    "date": None,
                    "type": None,
                    "price": 0,
                    "size": 0,
                },
            ]
        )

        assert len(trades) == 1
        assert trades[0]["type"] == "buy"
        assert trades[0]["size"] == 2
        assert trades[0]["price"] == 12.5


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

    async def test_run_backtest_rejects_runtime_dir_even_when_validation_is_bypassed(self):
        task_manager = MagicMock(spec=BacktestExecutionManager)
        task_manager.create_task = AsyncMock()
        svc = BacktestService(
            task_manager=task_manager, task_runner=MagicMock(spec=BacktestExecutionRunner)
        )
        request = BacktestRequest.model_construct(runtime_dir="/tmp/client-selected-runtime")

        with pytest.raises(ValueError, match="BACKTEST_RUNTIME_DIR_CLIENT_FORBIDDEN"):
            await svc.run_backtest("user1", request)

        task_manager.create_task.assert_not_awaited()

    async def test_workspace_submission_uses_server_preflight_and_does_not_serialize_runtime_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from app.services import workspace_unit_runtime

        monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path / "units")
        runtime_dir = workspace_unit_runtime.unit_dir("ws-1", "unit-1")
        runtime_dir.mkdir(parents=True)
        (runtime_dir / "run.py").write_text("print('workspace')", encoding="utf-8")
        preflight_calls: list[str] = []

        async def runtime_preflight() -> Path:
            preflight_calls.append("called")
            return runtime_dir

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

        response = await svc.run_workspace_unit_backtest(
            "user1",
            make_request(),
            workspace_id="ws-1",
            unit_id="unit-1",
            runtime_preflight=runtime_preflight,
        )

        assert response.task_id == "task123"
        assert preflight_calls == ["called"]
        submitted_request = task_manager.create_task.await_args.args[1]
        assert submitted_request.runtime_dir is None
        scheduled_execution = task_runner.schedule.call_args.args[1]
        scheduled_execution.close()

    async def test_workspace_submission_keeps_rejected_runtime_unreachable_without_preflight(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from app.services import workspace_unit_runtime

        monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path / "units")
        runtime_dir = workspace_unit_runtime.unit_dir("ws-1", "unit-1")
        runtime_dir.mkdir(parents=True)
        (runtime_dir / "run.py").write_text("print('stale')", encoding="utf-8")

        async def runtime_preflight() -> Path:
            raise ValueError("MARKET_DATA_BINDING_RUNTIME_REVOKED")

        task_manager = MagicMock(spec=BacktestExecutionManager)
        task_manager.create_task = AsyncMock()
        svc = BacktestService(
            task_manager=task_manager, task_runner=MagicMock(spec=BacktestExecutionRunner)
        )

        with pytest.raises(ValueError, match="MARKET_DATA_BINDING_RUNTIME_REVOKED"):
            await svc.run_workspace_unit_backtest(
                "user1",
                make_request(),
                workspace_id="ws-1",
                unit_id="unit-1",
                runtime_preflight=runtime_preflight,
            )

        # The generic API cannot name this directory and every workspace
        # execution replays the private preflight before spawning.  Retaining
        # it avoids an old rejected request deleting a newer fenced runtime.
        assert runtime_dir.exists()
        assert (runtime_dir / "run.py").is_file()
        task_manager.create_task.assert_not_awaited()

    async def test_workspace_claim_promotion_blocks_schedule_after_queued_stop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A revoked unit lease cancels its persisted task before any runner schedule."""
        from app.services import workspace_unit_runtime

        monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path / "units")
        runtime_dir = workspace_unit_runtime.unit_dir("ws-1", "unit-1")
        runtime_dir.mkdir(parents=True)
        (runtime_dir / "run.py").write_text("print('workspace')", encoding="utf-8")

        async def runtime_preflight() -> Path:
            return runtime_dir

        claim_promoter = AsyncMock(return_value=False)
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
        task_manager.update_task_status = AsyncMock()
        task_runner = MagicMock(spec=BacktestExecutionRunner)
        svc = BacktestService(task_manager=task_manager, task_runner=task_runner)

        with pytest.raises(ValueError, match="WORKSPACE_UNIT_RUN_CLAIM_LOST"):
            await svc.run_workspace_unit_backtest(
                "user1",
                make_request(),
                workspace_id="ws-1",
                unit_id="unit-1",
                runtime_preflight=runtime_preflight,
                claim_promoter=claim_promoter,
            )

        claim_promoter.assert_awaited_once_with("task123")
        task_manager.update_task_status.assert_awaited_once()
        assert task_manager.update_task_status.await_args.args == ("task123", TaskStatus.CANCELLED)
        assert (
            task_manager.update_task_status.await_args.kwargs["error_message"]
            == "Workspace unit run claim was revoked before scheduling"
        )
        task_runner.schedule.assert_not_called()

    async def test_workspace_promoter_cancellation_marks_persisted_task_before_reraising(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Cancellation after create_task cannot leak a PENDING workspace task."""
        from app.services import workspace_unit_runtime

        monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path / "units")
        runtime_dir = workspace_unit_runtime.unit_dir("ws-1", "unit-1")
        runtime_dir.mkdir(parents=True)
        (runtime_dir / "run.py").write_text("print('workspace')", encoding="utf-8")

        async def runtime_preflight() -> Path:
            return runtime_dir

        async def cancelled_promoter(_task_id: str) -> bool:
            raise asyncio.CancelledError

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
        task_manager.update_task_status = AsyncMock()
        task_runner = MagicMock(spec=BacktestExecutionRunner)
        svc = BacktestService(task_manager=task_manager, task_runner=task_runner)

        with pytest.raises(asyncio.CancelledError):
            await svc.run_workspace_unit_backtest(
                "user1",
                make_request(),
                workspace_id="ws-1",
                unit_id="unit-1",
                runtime_preflight=runtime_preflight,
                claim_promoter=cancelled_promoter,
            )

        assert task_manager.update_task_status.await_args.args == ("task123", TaskStatus.CANCELLED)
        assert (
            task_manager.update_task_status.await_args.kwargs["error_message"]
            == "Workspace unit run claim promotion was cancelled"
        )
        task_runner.schedule.assert_not_called()

    async def test_execution_start_claim_is_single_winner_and_never_revives_cancelled_task(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The scheduled coroutine claims PENDING->RUNNING with a DB CAS."""
        import app.services.backtest.service as service_module
        from app.db.database import async_session_maker
        from app.models.user import User

        monkeypatch.setattr(service_module, "async_session_maker", async_session_maker)
        async with async_session_maker() as session:
            session.add_all(
                [
                    User(
                        id="execution-claim-user",
                        username="execution_claim_user",
                        email="execution_claim_user@example.com",
                        hashed_password="hash",
                    ),
                    BacktestTask(
                        id="execution-claim-task",
                        user_id="execution-claim-user",
                        strategy_id="strategy",
                        symbol="000001.SZ",
                        status=TaskStatus.PENDING,
                    ),
                    BacktestTask(
                        id="execution-cancelled-task",
                        user_id="execution-claim-user",
                        strategy_id="strategy",
                        symbol="000001.SZ",
                        status=TaskStatus.CANCELLED,
                    ),
                ]
            )
            await session.commit()

        winners = await asyncio.gather(
            BacktestService._claim_task_execution_start("execution-claim-task"),
            BacktestService._claim_task_execution_start("execution-claim-task"),
        )
        assert sorted(winners) == [False, True]
        assert not await BacktestService._claim_task_execution_start("execution-cancelled-task")

        async with async_session_maker() as session:
            running = await session.get(BacktestTask, "execution-claim-task")
            cancelled = await session.get(BacktestTask, "execution-cancelled-task")
            assert running is not None and running.status == TaskStatus.RUNNING
            assert cancelled is not None and cancelled.status == TaskStatus.CANCELLED

    async def test_workspace_schedule_failure_cancels_promoted_task(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A task promoted before runner failure cannot remain a live workspace run."""
        from app.services import workspace_unit_runtime

        monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path / "units")
        runtime_dir = workspace_unit_runtime.unit_dir("ws-1", "unit-1")
        runtime_dir.mkdir(parents=True)
        (runtime_dir / "run.py").write_text("print('workspace')", encoding="utf-8")

        async def runtime_preflight() -> Path:
            return runtime_dir

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
        task_manager.update_task_status = AsyncMock()
        task_runner = MagicMock(spec=BacktestExecutionRunner)
        task_runner.schedule.side_effect = RuntimeError("runner unavailable")
        svc = BacktestService(task_manager=task_manager, task_runner=task_runner)

        with pytest.raises(RuntimeError, match="runner unavailable"):
            await svc.run_workspace_unit_backtest(
                "user1",
                make_request(),
                workspace_id="ws-1",
                unit_id="unit-1",
                runtime_preflight=runtime_preflight,
                claim_promoter=AsyncMock(return_value=True),
            )

        assert task_manager.update_task_status.await_args.args == ("task123", TaskStatus.CANCELLED)
        assert (
            task_manager.update_task_status.await_args.kwargs["error_message"]
            == "Workspace unit task could not be scheduled"
        )

    async def test_workspace_execution_rechecks_preflight_before_subprocess(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from app.services import workspace_unit_runtime

        monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path / "units")
        runtime_dir = workspace_unit_runtime.unit_dir("ws-1", "unit-1")
        runtime_dir.mkdir(parents=True)
        (runtime_dir / "run.py").write_text("print('workspace')", encoding="utf-8")
        preflight_attempts = 0

        async def runtime_preflight() -> Path:
            nonlocal preflight_attempts
            preflight_attempts += 1
            if preflight_attempts == 3:
                raise ValueError("MARKET_DATA_BINDING_RUNTIME_REVOKED")
            return runtime_dir

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
        task_manager.update_task_status = AsyncMock()
        task_runner = MagicMock(spec=BacktestExecutionRunner)
        svc = BacktestService(task_manager=task_manager, task_runner=task_runner)
        svc._notify_progress = AsyncMock()
        svc._run_strategy_subprocess = AsyncMock()
        svc._claim_task_execution_start = AsyncMock(return_value=True)

        await svc.run_workspace_unit_backtest(
            "user1",
            make_request(),
            workspace_id="ws-1",
            unit_id="unit-1",
            runtime_preflight=runtime_preflight,
        )

        scheduled_execution = task_runner.schedule.call_args.args[1]
        strategy_dir = tmp_path / "strategy"
        with patch("app.services.strategy.core.get_strategy_dir", return_value=strategy_dir):
            await scheduled_execution

        assert preflight_attempts == 3
        svc._run_strategy_subprocess.assert_not_awaited()
        assert runtime_dir.exists()
        assert task_manager.update_task_status.await_args_list[-1].args == (
            "task123",
            TaskStatus.FAILED,
        )
        assert (
            task_manager.update_task_status.await_args_list[-1].kwargs["error_message"]
            == "MARKET_DATA_BINDING_RUNTIME_REVOKED"
        )


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

            with patch("subprocess.Popen", return_value=process) as mock_popen:
                with patch("app.config.get_settings") as mock_settings:
                    mock_settings.return_value = MagicMock(BACKTEST_TIMEOUT=60)
                    result = await svc._run_strategy_subprocess(work_dir, task_id="task123")

        assert result == {"stdout": "output", "stderr": ""}
        task_runner.register_process.assert_called_once_with("task123", process)
        task_runner.unregister_process.assert_called_once_with("task123")
        env = mock_popen.call_args.kwargs["env"]
        assert env["BACKTRADER_LOG_DIR"].endswith("logs/task_task123")

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
