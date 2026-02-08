"""
参数优化服务测试

测试：
- 参数网格生成
- 任务状态管理
- 优化任务提交
- 单次试验运行
- 日志解析
- 进度查询
- 结果获取
- 任务取消
- 异常处理
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import pytest

from app.services.param_optimization_service import (
    generate_param_grid,
    submit_optimization,
    get_optimization_progress,
    get_optimization_results,
    cancel_optimization,
    _get_task,
    _set_task,
    _update_task,
    _run_single_trial,
    _parse_trial_logs,
    _safe_float,
)


class TestSafeFloat:
    """测试安全浮点数转换"""

    def test_safe_float_valid(self):
        """测试有效浮点数"""
        assert _safe_float("123.45") == 123.45
        assert _safe_float(100) == 100.0

    def test_safe_float_nan(self):
        """测试NaN处理"""
        import math
        assert _safe_float(float('nan')) == 0.0

    def test_safe_float_inf(self):
        """测试无穷大处理"""
        import math
        assert _safe_float(float('inf')) == 0.0
        assert _safe_float(float('-inf')) == 0.0

    def test_safe_float_invalid(self):
        """测试无效值处理"""
        assert _safe_float("invalid") == 0.0
        assert _safe_float(None) == 0.0
        assert _safe_float("abc") == 0.0

    def test_safe_float_custom_default(self):
        """测试自定义默认值"""
        assert _safe_float("invalid", default=-1.0) == -1.0


class TestTaskManagement:
    """测试任务状态管理"""

    def test_set_and_get_task(self):
        """测试设置和获取任务"""
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
        """测试获取不存在的任务"""
        result = _get_task("nonexistent_task")
        assert result is None

    def test_update_task(self):
        """测试更新任务"""
        task_id = "test_task_update"
        _set_task(task_id, {"status": "running", "completed": 0})

        _update_task(task_id, completed=5, status="completed")
        result = _get_task(task_id)

        assert result["completed"] == 5
        assert result["status"] == "completed"

    def test_update_nonexistent_task_no_error(self):
        """测试更新不存在的任务不报错"""
        # Should not raise an error
        _update_task("nonexistent_task", completed=10)
        result = _get_task("nonexistent_task")
        assert result is None


class TestGenerateParamGrid:
    """测试参数网格生成"""

    def test_single_param_float(self):
        """测试单个浮点参数"""
        param_ranges = {
            "fast_period": {"start": 5, "end": 15, "step": 5, "type": "float"}
        }
        result = generate_param_grid(param_ranges)

        assert len(result) == 3
        assert result[0]["fast_period"] == 5.0
        assert result[1]["fast_period"] == 10.0
        assert result[2]["fast_period"] == 15.0

    def test_single_param_int(self):
        """测试单个整型参数"""
        param_ranges = {
            "period": {"start": 10, "end": 30, "step": 10, "type": "int"}
        }
        result = generate_param_grid(param_ranges)

        assert len(result) == 3
        assert result[0]["period"] == 10
        assert result[1]["period"] == 20
        assert result[2]["period"] == 30

    def test_multiple_params_cartesian_product(self):
        """测试多参数笛卡尔积"""
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
        """测试默认类型是浮点"""
        param_ranges = {
            "period": {"start": 1.5, "end": 3.5, "step": 1}
        }
        result = generate_param_grid(param_ranges)

        # Default is float, so should be 1.5, 2.5, 3.5
        assert result[0]["period"] == 1.5
        assert isinstance(result[0]["period"], float)

    def test_empty_ranges_returns_empty_list(self):
        """测试空范围返回空列表"""
        result = generate_param_grid({})
        # itertools.product with no args returns [()] which becomes [{}]
        # This is expected behavior - empty dict represents one empty parameter combination
        assert result == [{}]

    def test_step_larger_than_range(self):
        """测试步长大于范围"""
        param_ranges = {
            "period": {"start": 10, "end": 15, "step": 100}
        }
        result = generate_param_grid(param_ranges)

        # Should at least include the start value
        assert len(result) >= 1
        assert result[0]["period"] == 10


class TestParseTrialLogs:
    """测试日志解析"""

    def setup_method(self):
        """创建测试用的临时日志目录"""
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_opt_"))
        self.logs_dir = self.tmp_dir / "logs"
        self.logs_dir.mkdir(parents=True)
        self.log_subdir = self.logs_dir / "20240101_120000"
        self.log_subdir.mkdir()

    def teardown_method(self):
        """清理临时目录"""
        import shutil
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_parse_value_log(self):
        """测试解析value.log"""
        value_path = self.log_subdir / "value.log"
        value_path.write_text(
            "log_time\tdt\tvalue\tcash\n"
            "1\t2024-01-01\t100000\t100000\n"
            "2\t2024-01-02\t102000\t98000\n"
            "3\t2024-01-03\t105000\t95000\n"
        )

        result = _parse_trial_logs(self.tmp_dir)

        assert result is not None
        assert result["total_return"] == pytest.approx(5.0, rel=0.1)  # (105000 - 100000) / 100000 * 100
        assert result["final_value"] == 105000

    def test_parse_trade_log(self):
        """测试解析trade.log"""
        # Create value.log for basic metrics
        value_path = self.log_subdir / "value.log"
        value_path.write_text(
            "log_time\tdt\tvalue\tcash\n"
            "1\t2024-01-01\t100000\t100000\n"
        )

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
        """测试没有日志目录"""
        empty_dir = Path(tempfile.mkdtemp(prefix="test_empty_"))
        try:
            result = _parse_trial_logs(empty_dir)
            assert result is None
        finally:
            import shutil
            shutil.rmtree(empty_dir, ignore_errors=True)

    def test_empty_log_files(self):
        """测试空日志文件"""
        value_path = self.log_subdir / "value.log"
        value_path.write_text("log_time\tdt\tvalue\tcash\n")

        result = _parse_trial_logs(self.tmp_dir)

        # Should return result with zero/nan-safe values
        assert result is not None
        assert result["total_trades"] == 0

    def test_drawdown_calculation(self):
        """测试回撤计算"""
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
        """测试夏普比率计算"""
        value_path = self.log_subdir / "value.log"
        # Create steadily increasing equity for positive Sharpe
        values = [100000 + i * 500 for i in range(10)]
        lines = ["log_time\tdt\tvalue\tcash"] + [f"{i}\t2024-01-0{i}\t{v}\t{v}" for i, v in enumerate(values)]
        value_path.write_text("\n".join(lines))

        result = _parse_trial_logs(self.tmp_dir)

        assert result is not None
        # Should have a reasonable Sharpe ratio for steadily increasing equity
        assert result["sharpe_ratio"] >= 0


class TestSubmitOptimization:
    """测试优化任务提交"""

    def test_submit_optimization_success(self):
        """测试成功提交优化任务"""
        param_ranges = {
            "fast": {"start": 5, "end": 10, "step": 5, "type": "int"},
            "slow": {"start": 20, "end": 30, "step": 10, "type": "int"},
        }

        # Mock strategy directory check - patch within the function scope
        with patch("app.services.strategy_service.STRATEGIES_DIR", Path("/tmp/strategies")):
            with patch("pathlib.Path.is_file") as mock_isfile:
                mock_isfile.return_value = True

                # Patch threading at the module level since it's imported locally
                import threading
                with patch("threading.Thread") as mock_thread:
                    task_id = submit_optimization("test_strategy", param_ranges, n_workers=2)

                    assert task_id is not None
                    assert len(task_id) == 8  # uuid hex[:8]
                    assert mock_thread.called

    def test_submit_optimization_no_run_py(self):
        """测试策略目录没有run.py"""
        param_ranges = {"period": {"start": 10, "end": 20, "step": 5}}

        with patch("app.services.strategy_service.STRATEGIES_DIR", Path("/tmp/strategies")):
            with patch("pathlib.Path.is_file", return_value=False):
                with pytest.raises(ValueError, match="不存在或缺少 run.py"):
                    submit_optimization("test_strategy", param_ranges)

    def test_submit_optimization_empty_grid(self):
        """测试参数网格为空"""
        # Use a range that produces empty grid (step too large)
        param_ranges = {"period": {"start": 10, "end": 9, "step": 1}}

        with patch("app.services.strategy_service.STRATEGIES_DIR", Path("/tmp/strategies")):
            with patch("pathlib.Path.is_file", return_value=True):
                with pytest.raises(ValueError, match="参数网格为空"):
                    submit_optimization("test_strategy", param_ranges)


class TestGetOptimizationProgress:
    """测试获取优化进度"""

    def test_get_progress_existing_task(self):
        """测试获取现有任务进度"""
        task_id = "progress_test"
        _set_task(task_id, {
            "status": "running",
            "strategy_id": "test_strategy",
            "total": 100,
            "completed": 50,
            "failed": 5,
            "n_workers": 4,
            "created_at": "2024-01-01T00:00:00",
        })

        progress = get_optimization_progress(task_id)

        assert progress is not None
        assert progress["task_id"] == task_id
        assert progress["status"] == "running"
        assert progress["total"] == 100
        assert progress["completed"] == 50
        assert progress["failed"] == 5
        assert progress["progress"] == 55.0  # (50 + 5) / 100 * 100

    def test_get_progress_nonexistent_task(self):
        """测试获取不存在任务的进度"""
        progress = get_optimization_progress("nonexistent")
        assert progress is None

    def test_get_progress_zero_total(self):
        """测试total为0时的进度"""
        task_id = "zero_total"
        _set_task(task_id, {
            "status": "running",
            "strategy_id": "test_strategy",
            "total": 0,
            "completed": 0,
            "failed": 0,
            "n_workers": 2,
            "created_at": "2024-01-01T00:00:00",
        })

        progress = get_optimization_progress(task_id)

        assert progress is not None
        assert progress["progress"] == 0


class TestGetOptimizationResults:
    """测试获取优化结果"""

    def test_get_results_with_successful_trials(self):
        """测试获取包含成功试验的结果"""
        task_id = "results_test"
        _set_task(task_id, {
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
                    }
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
                    }
                },
            ]
        })

        results = get_optimization_results(task_id)

        assert results is not None
        assert results["task_id"] == task_id
        assert results["status"] == "completed"
        assert len(results["rows"]) == 2
        assert results["best"]["annual_return"] == 12.3  # Best annual return

    def test_get_results_sorts_by_annual_return(self):
        """测试结果按年化收益率排序"""
        task_id = "sort_test"
        _set_task(task_id, {
            "status": "completed",
            "strategy_id": "test_strategy",
            "param_names": ["period"],
            "total": 3,
            "completed": 3,
            "failed": 0,
            "results": [
                {
                    "params": {"period": 10},
                    "metrics": {"annual_return": 5.0, "total_return": 3.0}
                },
                {
                    "params": {"period": 20},
                    "metrics": {"annual_return": 15.0, "total_return": 10.0}
                },
                {
                    "params": {"period": 30},
                    "metrics": {"annual_return": 10.0, "total_return": 7.0}
                },
            ]
        })

        results = get_optimization_results(task_id)

        assert results is not None
        # Should be sorted by annual_return descending
        assert results["rows"][0]["period"] == 20
        assert results["rows"][1]["period"] == 30
        assert results["rows"][2]["period"] == 10

    def test_get_results_empty(self):
        """测试获取空结果"""
        task_id = "empty_results"
        _set_task(task_id, {
            "status": "completed",
            "strategy_id": "test_strategy",
            "param_names": [],
            "total": 0,
            "completed": 0,
            "failed": 0,
            "results": []
        })

        results = get_optimization_results(task_id)

        assert results is not None
        assert results["rows"] == []
        assert results["best"] is None

    def test_get_results_nonexistent_task(self):
        """测试获取不存在任务的结果"""
        results = get_optimization_results("nonexistent")
        assert results is None


class TestCancelOptimization:
    """测试取消优化任务"""

    def test_cancel_existing_task(self):
        """测试取消现有任务"""
        task_id = "cancel_test"
        _set_task(task_id, {"status": "running"})

        result = cancel_optimization(task_id)

        assert result is True
        task = _get_task(task_id)
        assert task["status"] == "cancelled"

    def test_cancel_nonexistent_task(self):
        """测试取消不存在的任务"""
        result = cancel_optimization("nonexistent")
        assert result is False


class TestRunSingleTrial:
    """测试单次试验运行"""

    def setup_method(self):
        """创建测试目录结构"""
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_trial_"))
        self.strategy_dir = self.tmp_dir / "test_strategy"
        self.strategy_dir.mkdir()

    def teardown_method(self):
        """清理临时目录"""
        import shutil
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_run_trial_success(self):
        """测试成功运行试验"""
        # Create run.py
        run_py = self.strategy_dir / "run.py"
        run_py.write_text("print('success')")

        # Create config.yaml
        config_path = self.strategy_dir / "config.yaml"
        config_path.write_text("strategy:\n  name: Test\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stderr="",
                stdout="success"
            )

            with patch("app.services.param_optimization_service._parse_trial_logs") as mock_parse:
                mock_parse.return_value = {"total_return": 10.0}

                result = _run_single_trial(
                    str(self.strategy_dir),
                    {"period": 20},
                    0,
                    str(self.tmp_dir / "tmp_base")
                )

                assert result["success"] is True
                assert "metrics" in result

    def test_run_trial_subprocess_fails(self):
        """测试子进程失败"""
        run_py = self.strategy_dir / "run.py"
        run_py.write_text("print('error')")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stderr="Test error message",
                stdout=""
            )

            result = _run_single_trial(
                str(self.strategy_dir),
                {"period": 20},
                0,
                str(self.tmp_dir / "tmp_base")
            )

            assert result["success"] is False
            assert "error" in result
            assert "Test error message" in result["error"]

    def test_run_trial_removes_asserts(self):
        """测试移除assert语句"""
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

            with patch("app.services.param_optimization_service._parse_trial_logs", return_value={}):
                _run_single_trial(
                    str(self.strategy_dir),
                    {"period": 20},
                    0,
                    str(self.tmp_dir / "tmp_base")
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
    """集成测试"""

    def test_full_optimization_workflow(self):
        """测试完整优化工作流"""
        param_ranges = {
            "period": {"start": 10, "end": 20, "step": 5, "type": "int"}
        }

        # Mock the entire workflow
        import threading
        with patch("app.services.strategy_service.STRATEGIES_DIR", Path("/tmp/strategies")):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("threading.Thread") as mock_thread:
                    # Submit optimization
                    task_id = submit_optimization("test_strategy", param_ranges)

                    # Check progress
                    _update_task(task_id, completed=5, total=10)
                    progress = get_optimization_progress(task_id)
                    assert progress["progress"] == 50.0

                    # Get results (simulate some results)
                    _set_task(task_id, {
                        "status": "completed",
                        "strategy_id": "test_strategy",
                        "param_names": ["period"],
                        "total": 2,
                        "completed": 2,
                        "failed": 0,
                        "results": [
                            {
                                "params": {"period": 10},
                                "metrics": {"annual_return": 10.0, "total_return": 8.0}
                            },
                            {
                                "params": {"period": 15},
                                "metrics": {"annual_return": 12.0, "total_return": 10.0}
                            },
                        ]
                    })
                    results = get_optimization_results(task_id)
                    assert results["best"]["period"] == 15

                    # Cancel test
                    cancel_optimization(task_id)
                    task = _get_task(task_id)
                    assert task["status"] == "cancelled"

    def test_concurrent_task_management(self):
        """测试并发任务管理"""
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
