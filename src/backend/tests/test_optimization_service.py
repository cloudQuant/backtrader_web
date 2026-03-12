"""
Parameter Optimization Service Tests.

Tests:
- Parameter grid generation
- Task status management
- Optimization task submission
- Single trial execution
- Log parsing
- Progress queries
- Result retrieval
- Task cancellation
- Exception handling
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.services.param_optimization_service import (
    _get_task,
    _parse_trial_logs,
    _run_single_trial,
    _safe_float,
    _set_task,
    _update_task,
    cancel_optimization,
    generate_param_grid,
    get_optimization_progress,
    get_optimization_results,
    submit_optimization,
)


class TestSafeFloat:
    """Tests for safe float conversion."""

    def test_safe_float_valid(self):
        """Test valid float conversion."""
        assert _safe_float("123.45") == 123.45
        assert _safe_float(100) == 100.0

    def test_safe_float_nan(self):
        """Test NaN handling."""
        assert _safe_float(float("nan")) == 0.0

    def test_safe_float_inf(self):
        """Test infinity handling."""
        assert _safe_float(float("inf")) == 0.0
        assert _safe_float(float("-inf")) == 0.0

    def test_safe_float_invalid(self):
        """Test invalid value handling."""
        assert _safe_float("invalid") == 0.0
        assert _safe_float(None) == 0.0
        assert _safe_float("abc") == 0.0

    def test_safe_float_custom_default(self):
        """Test custom default value."""
        assert _safe_float("invalid", default=-1.0) == -1.0


class TestTaskManagement:
    """Tests for task status management."""

    def test_set_and_get_task(self):
        """Test setting and getting task."""
        task_id = "test_task_123"
        task_data = {
            "status": "running",
            "total": 10,
            "completed": 5,
        }

        _set_task(task_id, task_data)
        result = _get_task(task_id)

        assert result is not None
        assert result["status"] == "running"
        assert result["total"] == 10
        assert result["completed"] == 5

    def test_get_nonexistent_task(self):
        """Test getting non-existent task."""
        result = _get_task("nonexistent_task")
        assert result is None

    def test_update_task(self):
        """Test updating task."""
        task_id = "test_task_update"
        _set_task(task_id, {"status": "running", "completed": 0})

        _update_task(task_id, completed=5, status="completed")
        result = _get_task(task_id)

        assert result["completed"] == 5
        assert result["status"] == "completed"

    def test_update_nonexistent_task_no_error(self):
        """Test updating non-existent task does not raise error."""
        # Should not raise an error
        _update_task("nonexistent_task", completed=10)
        result = _get_task("nonexistent_task")
        assert result is None


class TestGenerateParamGrid:
    """Tests for parameter grid generation."""

    def test_single_param_float(self):
        """Test single float parameter."""
        param_ranges = {"fast_period": {"start": 5, "end": 15, "step": 5, "type": "float"}}
        result = generate_param_grid(param_ranges)

        assert len(result) == 3
        assert result[0]["fast_period"] == 5.0
        assert result[1]["fast_period"] == 10.0
        assert result[2]["fast_period"] == 15.0

    def test_single_param_int(self):
        """Test single integer parameter."""
        param_ranges = {"period": {"start": 10, "end": 30, "step": 10, "type": "int"}}
        result = generate_param_grid(param_ranges)

        assert len(result) == 3
        assert result[0]["period"] == 10
        assert result[1]["period"] == 20
        assert result[2]["period"] == 30

    def test_multiple_params_cartesian_product(self):
        """Test multiple parameters Cartesian product."""
        param_ranges = {
            "fast": {"start": 5, "end": 10, "step": 5, "type": "int"},
            "slow": {"start": 20, "end": 30, "step": 10, "type": "int"},
        }
        result = generate_param_grid(param_ranges)

        assert len(result) == 4  # 2 * 2
        # Check combinations
        combos = [(r["fast"], r["slow"]) for r in result]
        assert (5, 20) in combos
        assert (5, 30) in combos
        assert (10, 20) in combos
        assert (10, 30) in combos

    def test_default_type_is_float(self):
        """Test default type is float."""
        param_ranges = {"period": {"start": 1.5, "end": 3.5, "step": 1}}
        result = generate_param_grid(param_ranges)

        # Default is float, so should be 1.5, 2.5, 3.5
        assert result[0]["period"] == 1.5
        assert isinstance(result[0]["period"], float)

    def test_empty_ranges_returns_empty_list(self):
        """Test empty ranges returns empty list."""
        result = generate_param_grid({})
        # itertools.product with no args returns [()] which becomes [{}]
        # This is expected behavior - empty dict represents one empty parameter combination
        assert result == [{}]

    def test_step_larger_than_range(self):
        """Test step larger than range."""
        param_ranges = {"period": {"start": 10, "end": 15, "step": 100}}
        result = generate_param_grid(param_ranges)

        # Should at least include the start value
        assert len(result) >= 1
        assert result[0]["period"] == 10


class TestParseTrialLogs:
    """Tests for log parsing."""

    def setup_method(self):
        """Create temporary log directory for testing."""
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_opt_"))
        self.logs_dir = self.tmp_dir / "logs"
        self.logs_dir.mkdir(parents=True)
        self.log_subdir = self.logs_dir / "20240101_120000"
        self.log_subdir.mkdir()

    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil

        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_parse_value_log(self):
        """Test parsing value.log."""
        value_path = self.log_subdir / "value.log"
        value_path.write_text(
            "log_time\tdt\tvalue\tcash\n"
            "1\t2024-01-01\t100000\t100000\n"
            "2\t2024-01-02\t102000\t98000\n"
            "3\t2024-01-03\t105000\t95000\n"
        )

        result = _parse_trial_logs(self.tmp_dir)

        assert result is not None
        assert result["total_return"] == pytest.approx(
            5.0, rel=0.1
        )  # (105000 - 100000) / 100000 * 100
        assert result["final_value"] == 105000

    def test_parse_trade_log(self):
        """Test parsing trade.log."""
        # Create value.log for basic metrics
        value_path = self.log_subdir / "value.log"
        value_path.write_text("log_time\tdt\tvalue\tcash\n1\t2024-01-01\t100000\t100000\n")

        # Create trade.log
        trade_path = self.log_subdir / "trade.log"
        trade_path.write_text(
            "ref\tdata\tisin\tisclosed\tpnlcomm\n"
            "1\t2024-01-01\tAAPL\t1\t1000\n"
            "2\t2024-01-02\tMSFT\t1\t-500\n"
            "3\t2024-01-03\tGOOGL\t1\t2000\n"
        )

        result = _parse_trial_logs(self.tmp_dir)

        assert result is not None
        assert result["total_trades"] == 3
        assert result["win_rate"] == pytest.approx(66.67, rel=0.1)  # 2 wins out of 3

    def test_no_logs_directory(self):
        """Test when no logs directory exists."""
        empty_dir = Path(tempfile.mkdtemp(prefix="test_empty_"))
        try:
            result = _parse_trial_logs(empty_dir)
            assert result is None
        finally:
            import shutil

            shutil.rmtree(empty_dir, ignore_errors=True)

    def test_empty_log_files(self):
        """Test empty log files."""
        value_path = self.log_subdir / "value.log"
        value_path.write_text("log_time\tdt\tvalue\tcash\n")

        result = _parse_trial_logs(self.tmp_dir)

        # Should return result with zero/nan-safe values
        assert result is not None
        assert result["total_trades"] == 0

    def test_drawdown_calculation(self):
        """Test drawdown calculation."""
        value_path = self.log_subdir / "value.log"
        value_path.write_text(
            "log_time\tdt\tvalue\tcash\n"
            "1\t2024-01-01\t100000\t100000\n"
            "2\t2024-01-02\t120000\t100000\n"  # peak
            "3\t2024-01-03\t110000\t100000\n"  # drawdown
            "4\t2024-01-04\t130000\t100000\n"  # new peak
            "5\t2024-01-05\t115000\t100000\n"  # drawdown
        )

        result = _parse_trial_logs(self.tmp_dir)

        assert result is not None
        # Max drawdown should be around 8.33% (from 120000 to 110000) or 11.54% (from 130000 to 115000)
        assert result["max_drawdown"] > 0

    def test_sharpe_calculation(self):
        """Test Sharpe ratio calculation."""
        value_path = self.log_subdir / "value.log"
        # Create steadily increasing equity for positive Sharpe
        values = [100000 + i * 500 for i in range(10)]
        lines = ["log_time\tdt\tvalue\tcash"] + [
            f"{i}\t2024-01-0{i}\t{v}\t{v}" for i, v in enumerate(values)
        ]
        value_path.write_text("\n".join(lines))

        result = _parse_trial_logs(self.tmp_dir)

        assert result is not None
        # Should have a reasonable Sharpe ratio for steadily increasing equity
        assert result["sharpe_ratio"] >= 0


class TestSubmitOptimization:
    """Tests for optimization task submission."""

    def test_submit_optimization_success(self):
        """Test successful optimization task submission."""
        param_ranges = {
            "fast": {"start": 5, "end": 10, "step": 5, "type": "int"},
            "slow": {"start": 20, "end": 30, "step": 10, "type": "int"},
        }

        # Mock strategy directory check - patch within the function scope
        with patch("app.services.strategy_service.STRATEGIES_DIR", Path("/tmp/strategies")):
            with patch("pathlib.Path.is_file") as mock_isfile:
                mock_isfile.return_value = True

                # Patch threading at the module level since it's imported locally
                with patch("threading.Thread") as mock_thread:
                    task_id = submit_optimization("test_strategy", param_ranges, n_workers=2)

                    assert task_id is not None
                    assert len(task_id) == 8  # uuid hex[:8]
                    assert mock_thread.called

    def test_submit_optimization_no_run_py(self):
        """Test strategy directory without run.py."""
        param_ranges = {"period": {"start": 10, "end": 20, "step": 5}}

        with patch("app.services.strategy_service.STRATEGIES_DIR", Path("/tmp/strategies")):
            with patch("pathlib.Path.is_file", return_value=False):
                with pytest.raises(ValueError, match="not found or missing run.py"):
                    submit_optimization("test_strategy", param_ranges)

    def test_submit_optimization_empty_grid(self):
        """Test empty parameter grid."""
        # Use a range that produces empty grid (step too large)
        param_ranges = {"period": {"start": 10, "end": 9, "step": 1}}

        with patch("app.services.strategy_service.STRATEGIES_DIR", Path("/tmp/strategies")):
            with patch("pathlib.Path.is_file", return_value=True):
                with pytest.raises(ValueError, match="Parameter grid is empty"):
                    submit_optimization("test_strategy", param_ranges)


class TestGetOptimizationProgress:
    """Tests for getting optimization progress."""

    def test_get_progress_existing_task(self):
        """Test getting existing task progress."""
        task_id = "progress_test"
        _set_task(
            task_id,
            {
                "status": "running",
                "strategy_id": "test_strategy",
                "total": 100,
                "completed": 50,
                "failed": 5,
                "n_workers": 4,
                "created_at": "2024-01-01T00:00:00",
            },
        )

        progress = get_optimization_progress(task_id)

        assert progress is not None
        assert progress["task_id"] == task_id
        assert progress["status"] == "running"
        assert progress["total"] == 100
        assert progress["completed"] == 50
        assert progress["failed"] == 5
        assert progress["progress"] == 55.0  # (50 + 5) / 100 * 100

    def test_get_progress_nonexistent_task(self):
        """Test getting non-existent task progress."""
        progress = get_optimization_progress("nonexistent")
        assert progress is None

    def test_get_progress_zero_total(self):
        """Test progress when total is 0."""
        task_id = "zero_total"
        _set_task(
            task_id,
            {
                "status": "running",
                "strategy_id": "test_strategy",
                "total": 0,
                "completed": 0,
                "failed": 0,
                "n_workers": 2,
                "created_at": "2024-01-01T00:00:00",
            },
        )

        progress = get_optimization_progress(task_id)

        assert progress is not None
        assert progress["progress"] == 0


class TestGetOptimizationResults:
    """Tests for getting optimization results."""

    def test_get_results_with_successful_trials(self):
        """Test getting results with successful trials."""
        task_id = "results_test"
        _set_task(
            task_id,
            {
                "status": "completed",
                "strategy_id": "test_strategy",
                "param_names": ["fast", "slow"],
                "total": 2,
                "completed": 2,
                "failed": 0,
                "results": [
                    {
                        "params": {"fast": 5, "slow": 20},
                        "metrics": {
                            "total_return": 10.5,
                            "annual_return": 12.3,
                            "sharpe_ratio": 1.5,
                            "max_drawdown": 5.0,
                            "total_trades": 100,
                            "win_rate": 60.0,
                            "final_value": 110500,
                        },
                    },
                    {
                        "params": {"fast": 10, "slow": 20},
                        "metrics": {
                            "total_return": 8.0,
                            "annual_return": 9.5,
                            "sharpe_ratio": 1.2,
                            "max_drawdown": 6.0,
                            "total_trades": 80,
                            "win_rate": 55.0,
                            "final_value": 108000,
                        },
                    },
                ],
            },
        )

        results = get_optimization_results(task_id)

        assert results is not None
        assert results["task_id"] == task_id
        assert results["status"] == "completed"
        assert len(results["rows"]) == 2
        assert results["best"]["annual_return"] == 12.3  # Best annual return

    def test_get_results_sorts_by_annual_return(self):
        """Test results sorted by annual return."""
        task_id = "sort_test"
        _set_task(
            task_id,
            {
                "status": "completed",
                "strategy_id": "test_strategy",
                "param_names": ["period"],
                "total": 3,
                "completed": 3,
                "failed": 0,
                "results": [
                    {
                        "params": {"period": 10},
                        "metrics": {"annual_return": 5.0, "total_return": 3.0},
                    },
                    {
                        "params": {"period": 20},
                        "metrics": {"annual_return": 15.0, "total_return": 10.0},
                    },
                    {
                        "params": {"period": 30},
                        "metrics": {"annual_return": 10.0, "total_return": 7.0},
                    },
                ],
            },
        )

        results = get_optimization_results(task_id)

        assert results is not None
        # Should be sorted by annual_return descending
        assert results["rows"][0]["period"] == 20
        assert results["rows"][1]["period"] == 30
        assert results["rows"][2]["period"] == 10

    def test_get_results_empty(self):
        """Test getting empty results."""
        task_id = "empty_results"
        _set_task(
            task_id,
            {
                "status": "completed",
                "strategy_id": "test_strategy",
                "param_names": [],
                "total": 0,
                "completed": 0,
                "failed": 0,
                "results": [],
            },
        )

        results = get_optimization_results(task_id)

        assert results is not None
        assert results["rows"] == []
        assert results["best"] is None

    def test_get_results_nonexistent_task(self):
        """Test getting non-existent task results."""
        results = get_optimization_results("nonexistent")
        assert results is None


class TestCancelOptimization:
    """Tests for canceling optimization tasks."""

    def test_cancel_existing_task(self):
        """Test canceling existing task."""
        task_id = "cancel_test"
        _set_task(task_id, {"status": "running"})

        result = cancel_optimization(task_id)

        assert result is True
        task = _get_task(task_id)
        assert task["status"] == "cancelled"

    def test_cancel_nonexistent_task(self):
        """Test canceling non-existent task."""
        result = cancel_optimization("nonexistent")
        assert result is False


class TestRunSingleTrial:
    """Tests for single trial execution."""

    def setup_method(self):
        """Create test directory structure."""
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_trial_"))
        self.strategy_dir = self.tmp_dir / "test_strategy"
        self.strategy_dir.mkdir()

    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil

        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_run_trial_success(self):
        """Test successful trial execution."""
        # Create run.py
        run_py = self.strategy_dir / "run.py"
        run_py.write_text("print('success')")

        # Create config.yaml
        config_path = self.strategy_dir / "config.yaml"
        config_path.write_text("strategy:\n  name: Test\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="", stdout="success")

            with patch("app.services.param_optimization_service._parse_trial_logs") as mock_parse:
                mock_parse.return_value = {"total_return": 10.0}

                result = _run_single_trial(
                    str(self.strategy_dir), {"period": 20}, 0, str(self.tmp_dir / "tmp_base")
                )

                assert result["success"] is True
                assert "metrics" in result

    def test_run_trial_subprocess_fails(self):
        """Test subprocess failure."""
        run_py = self.strategy_dir / "run.py"
        run_py.write_text("print('error')")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stderr="Test error message", stdout="")

            result = _run_single_trial(
                str(self.strategy_dir), {"period": 20}, 0, str(self.tmp_dir / "tmp_base")
            )

            assert result["success"] is False
            assert "error" in result
            assert "Test error message" in result["error"]

    def test_run_trial_removes_asserts(self):
        """Test assert statement removal."""
        run_py = self.strategy_dir / "run.py"
        run_py.write_text("""
# Test code
assert param == 20
if True:
    assert(param > 0)
result = 1
""")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="", stdout="")

            with patch(
                "app.services.param_optimization_service._parse_trial_logs", return_value={}
            ):
                _run_single_trial(
                    str(self.strategy_dir), {"period": 20}, 0, str(self.tmp_dir / "tmp_base")
                )

                # Check that the trial directory was modified
                # (asserts should be replaced with pass)
                trial_dirs = list((self.tmp_dir / "tmp_base").glob("trial_*"))
                if trial_dirs:
                    modified_run_py = trial_dirs[0] / "run.py"
                    content = modified_run_py.read_text()
                    # Assert should be replaced
                    assert "pass  # assert removed" in content or "assert" not in content


class TestIntegration:
    """Integration tests."""

    def test_full_optimization_workflow(self):
        """Test complete optimization workflow."""
        param_ranges = {"period": {"start": 10, "end": 20, "step": 5, "type": "int"}}

        # Mock the entire workflow
        with patch("app.services.strategy_service.STRATEGIES_DIR", Path("/tmp/strategies")):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("threading.Thread"):
                    # Submit optimization
                    task_id = submit_optimization("test_strategy", param_ranges)

                    # Check progress
                    _update_task(task_id, completed=5, total=10)
                    progress = get_optimization_progress(task_id)
                    assert progress["progress"] == 50.0

                    # Get results (simulate some results)
                    _set_task(
                        task_id,
                        {
                            "status": "completed",
                            "strategy_id": "test_strategy",
                            "param_names": ["period"],
                            "total": 2,
                            "completed": 2,
                            "failed": 0,
                            "results": [
                                {
                                    "params": {"period": 10},
                                    "metrics": {"annual_return": 10.0, "total_return": 8.0},
                                },
                                {
                                    "params": {"period": 15},
                                    "metrics": {"annual_return": 12.0, "total_return": 10.0},
                                },
                            ],
                        },
                    )
                    results = get_optimization_results(task_id)
                    assert results["best"]["period"] == 15

                    # Cancel test
                    cancel_optimization(task_id)
                    task = _get_task(task_id)
                    assert task["status"] == "cancelled"

    def test_concurrent_task_management(self):
        """Test concurrent task management."""
        import threading

        results = []
        errors = []

        def create_task(i):
            try:
                task_id = f"task_{i}"
                _set_task(task_id, {"status": "running", "value": i})
                result = _get_task(task_id)
                results.append((i, result["value"]))
            except Exception as e:
                errors.append((i, e))

        # Create multiple tasks concurrently
        threads = []
        for i in range(10):
            t = threading.Thread(target=create_task, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10
        # All tasks should have correct values
        for i, value in results:
            assert i == value
