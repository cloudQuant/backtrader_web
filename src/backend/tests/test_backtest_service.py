"""
Backtest service unit tests
"""
import asyncio
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.backtest import BacktestResultModel, BacktestTask
from app.schemas.backtest import BacktestRequest, TaskStatus
from app.services.backtest_service import BacktestService, _running_processes, _running_tasks


class TestBacktestServiceHelpers:
    """Backtest service helper method tests"""

    def test_has_custom_params_default(self):
        svc = BacktestService()
        req = BacktestRequest(
            strategy_id="test", symbol="000001.SZ",
            start_date="2024-01-01T00:00:00", end_date="2024-06-30T00:00:00",
            initial_cash=100000, commission=0.001, params={},
        )
        assert svc._has_custom_params(req) is False

    def test_has_custom_params_custom_cash(self):
        svc = BacktestService()
        req = BacktestRequest(
            strategy_id="test", symbol="000001.SZ",
            start_date="2024-01-01T00:00:00", end_date="2024-06-30T00:00:00",
            initial_cash=200000, commission=0.001, params={},
        )
        assert svc._has_custom_params(req) is True

    def test_has_custom_params_with_params(self):
        svc = BacktestService()
        req = BacktestRequest(
            strategy_id="test", symbol="000001.SZ",
            start_date="2024-01-01T00:00:00", end_date="2024-06-30T00:00:00",
            initial_cash=100000, commission=0.001, params={"period": 20},
        )
        assert svc._has_custom_params(req) is True

    def test_has_custom_params_custom_commission(self):
        svc = BacktestService()
        req = BacktestRequest(
            strategy_id="test", symbol="000001.SZ",
            start_date="2024-01-01T00:00:00", end_date="2024-06-30T00:00:00",
            initial_cash=100000, commission=0.002, params={},
        )
        assert svc._has_custom_params(req) is True

    def test_strip_asserts(self, tmp_path: Path):
        run_py = tmp_path / "run.py"
        run_py.write_text("x = 1\nassert x == 1\nassert(x > 0)\ny = 2\n")
        BacktestService._strip_asserts(run_py)
        content = run_py.read_text()
        assert "assert x == 1" not in content
        assert "assert(x > 0)" not in content
        assert "x = 1" in content
        assert "y = 2" in content

    def test_strip_asserts_no_file(self, tmp_path: Path):
        BacktestService._strip_asserts(tmp_path / "nonexistent.py")  # should not raise

    def test_write_temp_config(self, tmp_path: Path):
        svc = BacktestService()
        config_path = tmp_path / "config.yaml"
        req = BacktestRequest(
            strategy_id="test", symbol="600519.SH",
            start_date="2024-01-01T00:00:00", end_date="2024-06-30T00:00:00",
            initial_cash=200000, commission=0.002, params={"period": 30},
        )
        svc._write_temp_config(config_path, req, None)
        content = config_path.read_text()
        assert "200000" in content
        assert "0.002" in content
        assert "period" in content
        assert "600519.SH" in content

    def test_write_temp_config_with_existing(self, tmp_path: Path):
        svc = BacktestService()
        config_path = tmp_path / "config.yaml"
        original = "strategy:\n  name: test\nparams:\n  old_param: 10\n"
        svc._write_temp_config(config_path, BacktestRequest(
            strategy_id="test", symbol="000001.SZ",
            start_date="2024-01-01T00:00:00", end_date="2024-06-30T00:00:00",
            initial_cash=100000, commission=0.001, params={"new_param": 5},
        ), original)
        content = config_path.read_text()
        assert "new_param" in content


class TestRunBacktest:
    """Test running backtest"""

    @pytest.mark.asyncio
    async def test_run_backtest_creates_task(self):
        """Test run_backtest creates task"""
        svc = BacktestService()

        req = BacktestRequest(
            strategy_id="test_strategy",
            symbol="000001.SZ",
            start_date="2024-01-01T00:00:00",
            end_date="2024-06-30T00:00:00",
        )

        mock_task = BacktestTask(
            id="task123",
            user_id="user1",
            strategy_id="test_strategy",
            symbol="000001.SZ",
            status=TaskStatus.PENDING,
        )

        with patch.object(svc.task_repo, 'create', return_value=mock_task) as mock_create:
            with patch('app.services.backtest_service.asyncio.create_task') as mock_create_task:
                # Avoid "coroutine was never awaited" warnings: the coroutine is normally scheduled by create_task.
                def _create_task(coro):
                    coro.close()
                    return AsyncMock()

                mock_create_task.side_effect = _create_task
                response = await svc.run_backtest("user1", req)

                assert response.task_id == "task123"
                assert response.status == TaskStatus.PENDING
                assert "message" in response.__dict__
                mock_create.assert_called_once()
                mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_backtest_stores_task_reference(self):
        """Test run_backtest stores task reference"""
        svc = BacktestService()

        req = BacktestRequest(
            strategy_id="test_strategy",
            symbol="000001.SZ",
            start_date="2024-01-01T00:00:00",
            end_date="2024-06-30T00:00:00",
        )

        mock_task = BacktestTask(
            id="task456",
            user_id="user1",
            strategy_id="test_strategy",
            symbol="000001.SZ",
            status=TaskStatus.PENDING,
        )

        with patch.object(svc.task_repo, 'create', return_value=mock_task):
            with patch('app.services.backtest_service.asyncio.create_task') as mock_create_task:
                def _create_task(coro):
                    coro.close()
                    return AsyncMock()

                mock_create_task.side_effect = _create_task
                await svc.run_backtest("user1", req)

                # Check that task was stored in _running_tasks
                assert "task456" in _running_tasks


class TestExecuteBacktest:
    """Test executing backtest"""

    @pytest.mark.asyncio
    async def test_execute_backtest_success(self):
        """Test successful backtest execution"""
        svc = BacktestService()

        req = BacktestRequest(
            strategy_id="test_strategy",
            symbol="000001.SZ",
            start_date="2024-01-01T00:00:00",
            end_date="2024-06-30T00:00:00",
        )

        # Create a temporary strategy directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            strategy_dir = tmpdir / "strategies" / "test_strategy"
            strategy_dir.mkdir(parents=True)
            (strategy_dir / "run.py").write_text("print('test')")
            (strategy_dir / "config.yaml").write_text("params:\n  period: 20\n")

            # Create datas directory
            datas_dir = tmpdir / "datas"
            datas_dir.mkdir()

            with patch('app.services.strategy_service.STRATEGIES_DIR', tmpdir / "strategies"):
                with patch.object(svc, '_run_strategy_subprocess', return_value={"stdout": "test"}):
                    with patch('app.services.log_parser_service.parse_all_logs', return_value={
                        "total_return": 15.5,
                        "log_dir": str(strategy_dir / "logs"),
                    }):
                        with patch.object(svc.result_repo, 'create'):
                            with patch.object(svc.task_repo, 'update'):
                                with patch('app.services.backtest_service.ws_manager') as mock_ws:
                                    mock_ws.send_to_task = AsyncMock()
                                    await svc._execute_backtest("task123", "user1", req)

                                    # Verify status was updated to COMPLETED
                                    update_calls = svc.task_repo.update.call_args_list
                                    final_call = update_calls[-1]
                                    assert final_call[0][0] == "task123"
                                    assert final_call[0][1]["status"] == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_backtest_no_run_py(self):
        """Test when run.py does not exist"""
        svc = BacktestService()

        req = BacktestRequest(
            strategy_id="missing_strategy",
            symbol="000001.SZ",
            start_date="2024-01-01T00:00:00",
            end_date="2024-06-30T00:00:00",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            strategies_dir = tmpdir / "strategies"
            strategies_dir.mkdir()
            (strategies_dir / "missing_strategy").mkdir()

            with patch('app.services.strategy_service.STRATEGIES_DIR', strategies_dir):
                with patch.object(svc.task_repo, 'update') as mock_update:
                    with patch('app.services.backtest_service.ws_manager') as mock_ws:
                        mock_ws.send_to_task = AsyncMock()
                        await svc._execute_backtest("task123", "user1", req)

                        # Should have updated to FAILED
                        mock_update.assert_called()
                        final_call = mock_update.call_args_list[-1]
                        assert final_call[0][1]["status"] == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_execute_backtest_asyncio_cancelled(self):
        """Test asyncio task cancellation (when cancel_task is called)"""
        svc = BacktestService()

        req = BacktestRequest(
            strategy_id="test_strategy",
            symbol="000001.SZ",
            start_date="2024-01-01T00:00:00",
            end_date="2024-06-30T00:00:00",
        )

        async def mock_execute():
            await svc._execute_backtest("task123", "user1", req)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            strategy_dir = tmpdir / "strategies" / "test_strategy"
            strategy_dir.mkdir(parents=True)
            (strategy_dir / "run.py").write_text("print('test running...')")

            with patch('app.services.strategy_service.STRATEGIES_DIR', tmpdir / "strategies"):
                with patch.object(svc.task_repo, 'update') as mock_update:
                    with patch('app.services.backtest_service.ws_manager') as mock_ws:
                        mock_ws.send_to_task = AsyncMock()
                        # Simulate asyncio.CancelledError being raised during execution
                        with patch.object(svc, '_run_strategy_subprocess',
                                         side_effect=asyncio.CancelledError()):
                            await svc._execute_backtest("task123", "user1", req)

                            # Should have updated to CANCELLED
                            final_call = mock_update.call_args_list[-1]
                            assert final_call[0][1]["status"] == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_execute_backtest_cleanup_on_error(self):
        """Test cleanup of temp directory on error"""
        svc = BacktestService()

        req = BacktestRequest(
            strategy_id="test_strategy",
            symbol="000001.SZ",
            start_date="2024-01-01T00:00:00",
            end_date="2024-06-30T00:00:00",
        )

        cleanup_dirs = []

        original_rmtree = shutil.rmtree
        def mock_rmtree(path, *args, **kwargs):
            cleanup_dirs.append(str(path))
            return original_rmtree(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            strategy_dir = tmpdir / "strategies" / "test_strategy"
            strategy_dir.mkdir(parents=True)
            (strategy_dir / "run.py").write_text("print('test')")

            with patch('app.services.strategy_service.STRATEGIES_DIR', tmpdir / "strategies"):
                with patch.object(svc, '_run_strategy_subprocess', side_effect=RuntimeError("Test error")):
                    with patch.object(svc.task_repo, 'update'):
                        with patch('app.services.backtest_service.ws_manager') as mock_ws:
                            mock_ws.send_to_task = AsyncMock()
                            with patch('shutil.rmtree', side_effect=mock_rmtree):
                                await svc._execute_backtest("task123", "user1", req)

                                # Verify cleanup was called
                                assert len(cleanup_dirs) > 0


class TestRunStrategySubprocess:
    """Test running strategy subprocess"""

    @pytest.mark.asyncio
    async def test_run_strategy_subprocess_success(self):
        """Test successful subprocess execution"""
        svc = BacktestService()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            (tmpdir / "run.py").write_text("print('success')")

            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = ("output", "")

            with patch('subprocess.Popen', return_value=mock_proc):
                with patch('app.config.get_settings') as mock_settings:
                    mock_settings.return_value = MagicMock(BACKTEST_TIMEOUT=60)
                    result = await svc._run_strategy_subprocess(tmpdir)

                    assert result["stdout"] == "output"
                    assert result["stderr"] == ""

    @pytest.mark.asyncio
    async def test_run_strategy_subprocess_failure(self):
        """Test subprocess failure"""
        svc = BacktestService()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            (tmpdir / "run.py").write_text("raise Exception('error')")

            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.communicate.return_value = ("", "error message")

            with patch('subprocess.Popen', return_value=mock_proc):
                with patch('app.config.get_settings') as mock_settings:
                    mock_settings.return_value = MagicMock(BACKTEST_TIMEOUT=60)
                    with pytest.raises(RuntimeError, match="run.py execution failed"):
                        await svc._run_strategy_subprocess(tmpdir)

    @pytest.mark.asyncio
    async def test_run_strategy_subprocess_stores_pid(self):
        """Test storing subprocess PID"""
        svc = BacktestService()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            (tmpdir / "run.py").write_text("print('test')")

            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = ("", "")
            mock_proc.pid = 12345

            with patch('subprocess.Popen', return_value=mock_proc):
                with patch('app.config.get_settings') as mock_settings:
                    mock_settings.return_value = MagicMock(BACKTEST_TIMEOUT=60)
                    await svc._run_strategy_subprocess(tmpdir, task_id="task123")

                    # Check that process was stored
                    assert "task123" in _running_processes
                    assert _running_processes["task123"].pid == 12345


class TestGetResult:
    """Test getting backtest results"""

    @pytest.mark.asyncio
    async def test_get_result_success(self):
        """Test successful result retrieval"""
        svc = BacktestService()

        mock_task = BacktestTask(
            id="task123",
            user_id="user1",
            strategy_id="test_strategy",
            symbol="000001.SZ",
            status=TaskStatus.COMPLETED,
            request_data={"start_date": "2024-01-01", "end_date": "2024-06-30"},
            created_at=datetime(2024, 1, 1),
        )

        mock_result = BacktestResultModel(
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
            equity_curve=[100000, 101000, 102000],
            equity_dates=["2024-01-01", "2024-01-02", "2024-01-03"],
            drawdown_curve=[0, -0.5, -1.0],
            trades=[],
        )

        with patch.object(svc.task_repo, 'get_by_id', return_value=mock_task):
            with patch.object(svc.cache, 'get', return_value=None):
                with patch.object(svc.result_repo, 'list', return_value=[mock_result]):
                    with patch.object(svc.cache, 'set'):
                        result = await svc.get_result("task123", "user1")

                        assert result is not None
                        assert result.task_id == "task123"
                        assert result.total_return == 15.5

    @pytest.mark.asyncio
    async def test_get_result_not_found(self):
        """Test task not found"""
        svc = BacktestService()

        with patch.object(svc.task_repo, 'get_by_id', return_value=None):
            result = await svc.get_result("nonexistent", "user1")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_result_wrong_user(self):
        """Test user mismatch"""
        svc = BacktestService()

        mock_task = BacktestTask(
            id="task123",
            user_id="user2",
            strategy_id="test_strategy",
            symbol="000001.SZ",
            status=TaskStatus.COMPLETED,
            request_data={},
            created_at=datetime(2024, 1, 1),
        )

        with patch.object(svc.task_repo, 'get_by_id', return_value=mock_task):
            result = await svc.get_result("task123", "user1")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_result_from_cache(self):
        """Test getting result from cache"""
        svc = BacktestService()

        mock_task = BacktestTask(
            id="task123",
            user_id="user1",
            strategy_id="test_strategy",
            symbol="000001.SZ",
            status=TaskStatus.COMPLETED,
            request_data={"start_date": "2024-01-01", "end_date": "2024-06-30"},
            created_at=datetime(2024, 1, 1),
        )

        cached_data = {
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

        with patch.object(svc.task_repo, 'get_by_id', return_value=mock_task):
            with patch.object(svc.cache, 'get', return_value=cached_data):
                with patch.object(svc.result_repo, 'list') as mock_list:
                    result = await svc.get_result("task123", "user1")

                    # Should not query database if cache hit
                    mock_list.assert_not_called()
                    assert result.total_return == 20.0

    @pytest.mark.asyncio
    async def test_get_result_caches_completed(self):
        """Test caching completed results"""
        svc = BacktestService()

        mock_task = BacktestTask(
            id="task123",
            user_id="user1",
            strategy_id="test_strategy",
            symbol="000001.SZ",
            status=TaskStatus.COMPLETED,
            request_data={"start_date": "2024-01-01", "end_date": "2024-06-30"},
            created_at=datetime(2024, 1, 1),
        )

        mock_result = BacktestResultModel(
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
        )

        with patch.object(svc.task_repo, 'get_by_id', return_value=mock_task):
            with patch.object(svc.cache, 'get', return_value=None):
                with patch.object(svc.result_repo, 'list', return_value=[mock_result]):
                    with patch.object(svc.cache, 'set') as mock_set:
                        _ = await svc.get_result("task123", "user1")

                        # Should cache the result
                        mock_set.assert_called_once()


class TestCancelTask:
    """Test canceling tasks"""

    @pytest.mark.asyncio
    async def test_cancel_task_success(self):
        """Test successful task cancellation"""
        svc = BacktestService()

        mock_task = BacktestTask(
            id="task123",
            user_id="user1",
            strategy_id="test_strategy",
            status=TaskStatus.RUNNING,
        )

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        _running_processes["task123"] = mock_proc

        mock_async_task = MagicMock()
        mock_async_task.done.return_value = False
        _running_tasks["task123"] = mock_async_task

        with patch.object(svc.task_repo, 'get_by_id', return_value=mock_task):
            with patch.object(svc.task_repo, 'update'):
                result = await svc.cancel_task("task123", "user1")

                assert result is True
                mock_proc.kill.assert_called_once()
                mock_async_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_task_not_found(self):
        """Test task not found"""
        svc = BacktestService()

        with patch.object(svc.task_repo, 'get_by_id', return_value=None):
            result = await svc.cancel_task("nonexistent", "user1")

            assert result is False

    @pytest.mark.asyncio
    async def test_cancel_task_wrong_user(self):
        """Test user mismatch"""
        svc = BacktestService()

        mock_task = BacktestTask(
            id="task123",
            user_id="user2",
            status=TaskStatus.RUNNING,
        )

        with patch.object(svc.task_repo, 'get_by_id', return_value=mock_task):
            result = await svc.cancel_task("task123", "user1")

            assert result is False

    @pytest.mark.asyncio
    async def test_cancel_task_already_completed(self):
        """Test canceling already completed task"""
        svc = BacktestService()

        mock_task = BacktestTask(
            id="task123",
            user_id="user1",
            status=TaskStatus.COMPLETED,
        )

        with patch.object(svc.task_repo, 'get_by_id', return_value=mock_task):
            result = await svc.cancel_task("task123", "user1")

            assert result is False


class TestGetTaskStatus:
    """Test getting task status"""

    @pytest.mark.asyncio
    async def test_get_task_status_success(self):
        """Test successful status retrieval"""
        svc = BacktestService()

        mock_task = BacktestTask(
            id="task123",
            user_id="user1",
            status=TaskStatus.RUNNING,
        )

        with patch.object(svc.task_repo, 'get_by_id', return_value=mock_task):
            status = await svc.get_task_status("task123", "user1")

            assert status == TaskStatus.RUNNING

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self):
        """Test task not found"""
        svc = BacktestService()

        with patch.object(svc.task_repo, 'get_by_id', return_value=None):
            status = await svc.get_task_status("nonexistent", "user1")

            assert status is None

    @pytest.mark.asyncio
    async def test_get_task_status_wrong_user(self):
        """Test user mismatch"""
        svc = BacktestService()

        mock_task = BacktestTask(
            id="task123",
            user_id="user2",
            status=TaskStatus.RUNNING,
        )

        with patch.object(svc.task_repo, 'get_by_id', return_value=mock_task):
            status = await svc.get_task_status("task123", "user1")

            assert status is None

    @pytest.mark.asyncio
    async def test_get_task_status_no_user_filter(self):
        """Test without user filter"""
        svc = BacktestService()

        mock_task = BacktestTask(
            id="task123",
            user_id="user2",
            status=TaskStatus.RUNNING,
        )

        with patch.object(svc.task_repo, 'get_by_id', return_value=mock_task):
            status = await svc.get_task_status("task123")

            assert status == TaskStatus.RUNNING


class TestListResults:
    """Test listing backtest results"""

    @pytest.mark.asyncio
    async def test_list_results_success(self):
        """Test successful result listing"""
        svc = BacktestService()

        mock_tasks = [
            BacktestTask(id="task1", user_id="user1", strategy_id="s1", symbol="000001.SZ",
                        status=TaskStatus.COMPLETED, request_data={}, created_at=datetime(2024, 1, 1)),
            BacktestTask(id="task2", user_id="user1", strategy_id="s2", symbol="000002.SZ",
                        status=TaskStatus.COMPLETED, request_data={}, created_at=datetime(2024, 1, 2)),
        ]

        mock_result1 = MagicMock(
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
        )
        mock_result2 = MagicMock(
            task_id="task2",
            strategy_id="s2",
            symbol="000002.SZ",
            start_date=datetime(2024, 1, 2),
            end_date=datetime(2024, 6, 30),
            status=TaskStatus.COMPLETED,
            total_return=20.0,
            annual_return=15.0,
            sharpe_ratio=1.5,
            max_drawdown=-8.0,
            win_rate=60.0,
            total_trades=60,
            profitable_trades=36,
            losing_trades=24,
            equity_curve=[],
            equity_dates=[],
            drawdown_curve=[],
            trades=[],
            created_at=datetime(2024, 1, 2),
            error_message=None,
        )

        with patch.object(svc.task_repo, 'list', return_value=mock_tasks):
            with patch.object(svc.task_repo, 'count', return_value=2):
                with patch.object(svc, 'get_result', side_effect=[mock_result1, mock_result2]):
                    result = await svc.list_results("user1")

                    assert result.total == 2
                    assert len(result.items) == 2

    @pytest.mark.asyncio
    async def test_list_results_empty(self):
        """Test empty list"""
        svc = BacktestService()

        with patch.object(svc.task_repo, 'list', return_value=[]):
            with patch.object(svc.task_repo, 'count', return_value=0):
                result = await svc.list_results("user1")

                assert result.total == 0
                assert result.items == []

    @pytest.mark.asyncio
    async def test_list_results_with_pagination(self):
        """Test pagination"""
        svc = BacktestService()

        mock_tasks = [
            BacktestTask(id=f"task{i}", user_id="user1", strategy_id="s1", symbol="000001.SZ",
                        status=TaskStatus.COMPLETED, request_data={}, created_at=datetime(2024, 1, i))
            for i in range(1, 6)
        ]

        mock_result = MagicMock(
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
        )

        with patch.object(svc.task_repo, 'list') as mock_list:
            mock_list.return_value = mock_tasks[:2]
            with patch.object(svc.task_repo, 'count', return_value=5):
                with patch.object(svc, 'get_result', return_value=mock_result):
                    result = await svc.list_results("user1", limit=2, offset=0)

                    mock_list.assert_called_once_with(
                        filters={"user_id": "user1"},
                        skip=0,
                        limit=2,
                        order_by="created_at",
                        order_desc=True,
                    )
                    assert len(result.items) == 2


class TestDeleteResult:
    """Test deleting backtest results"""

    @pytest.mark.asyncio
    async def test_delete_result_success(self):
        """Test successful deletion"""
        svc = BacktestService()

        mock_task = BacktestTask(
            id="task123",
            user_id="user1",
            log_dir="/tmp/logs/task123",
        )

        with patch.object(svc.task_repo, 'get_by_id', return_value=mock_task):
            with patch('pathlib.Path.is_dir', return_value=True):
                with patch('shutil.rmtree'):
                    with patch.object(svc.result_repo, 'list', return_value=[MagicMock(id="result123")]):
                        with patch.object(svc.result_repo, 'delete'):
                            with patch.object(svc.task_repo, 'delete'):
                                with patch.object(svc.cache, 'delete'):
                                    result = await svc.delete_result("task123", "user1")

                                    assert result is True

    @pytest.mark.asyncio
    async def test_delete_result_not_found(self):
        """Test task not found"""
        svc = BacktestService()

        with patch.object(svc.task_repo, 'get_by_id', return_value=None):
            result = await svc.delete_result("nonexistent", "user1")

            assert result is False

    @pytest.mark.asyncio
    async def test_delete_result_wrong_user(self):
        """Test user mismatch"""
        svc = BacktestService()

        mock_task = BacktestTask(
            id="task123",
            user_id="user2",
        )

        with patch.object(svc.task_repo, 'get_by_id', return_value=mock_task):
            result = await svc.delete_result("task123", "user1")

            assert result is False

    @pytest.mark.asyncio
    async def test_delete_result_clears_cache(self):
        """Test cache clearing"""
        svc = BacktestService()

        mock_task = BacktestTask(
            id="task123",
            user_id="user1",
        )

        with patch.object(svc.task_repo, 'get_by_id', return_value=mock_task):
            with patch('pathlib.Path.is_dir', return_value=False):
                with patch.object(svc.result_repo, 'list', return_value=[]):
                    with patch.object(svc.task_repo, 'delete'):
                        with patch.object(svc.cache, 'delete') as mock_cache_delete:
                            result = await svc.delete_result("task123", "user1")

                            assert result is True
                            mock_cache_delete.assert_called_once_with("backtest:result:task123")
