"""
参数优化服务测试

测试网格搜索和贝叶斯优化功能
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.services.optimization_service import OptimizationService
from app.schemas.backtest_enhanced import (
    OptimizationRequest,
    OptimizationResult,
    BacktestRequest,
    TaskStatus,
)


@pytest.fixture
def backtest_service_mock():
    """Mock BacktestService"""
    mock = AsyncMock(spec=OptimizationService._backtest_service)

    # Mock run_backtest 方法
    async def mock_run_backtest(user_id, request):
        """模拟运行回测"""
        return OptimizationService().BacktestResponse(
            task_id=f"task-{user_id}-{hash(str(request))}",
            status=TaskStatus.PENDING,
            message="回测任务已创建",
        )

    mock.run_backtest = mock_run_backtest

    # Mock get_result 方法
    async def mock_get_result(task_id):
        """模拟获取回测结果"""
        # 返回一个完成的回测结果
        from app.schemas.backtest_enhanced import BacktestResult

        # 根据参数模拟不同的结果
        if "test" in task_id:
            return BacktestResult(
                task_id=task_id,
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                status=TaskStatus.COMPLETED,
                total_return=15.5,
                annual_return=15.5,
                sharpe_ratio=1.5,
                max_drawdown=10.0,
                win_rate=60.0,
                total_trades=20,
                profitable_trades=12,
                losing_trades=8,
                equity_curve=[100000, 101550, 103100, 104650],
                equity_dates=["2023-01-01", "2023-06-30", "2023-09-30", "2023-12-31"],
                drawdown_curve=[0, -2.0, -5.0, -10.0],
                trades=[],
                created_at=datetime.utcnow(),
            )
        else:
            return BacktestResult(
                task_id=task_id,
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                status=TaskStatus.FAILED,
                total_return=0,
                annual_return=0,
                sharpe_ratio=0,
                max_drawdown=0,
                win_rate=0,
                total_trades=0,
                profitable_trades=0,
                losing_trades=0,
                equity_curve=[],
                equity_dates=[],
                drawdown_curve=[],
                trades=[],
                created_at=datetime.utcnow(),
                error_message="回测失败",
            )

    mock.get_result = mock_get_result

    # Mock get_task_status 方法
    async def mock_get_task_status(task_id):
        """模拟获取任务状态"""
        if "test" in task_id:
            return TaskStatus.COMPLETED
        else:
            return TaskStatus.FAILED

    mock.get_task_status = mock_get_task_status

    return mock


@pytest.fixture
def optimization_service(backtest_service_mock):
    """创建 OptimizationService 实例"""
    return OptimizationService()


class TestGenerateParamCombinations:
    """测试参数组合生成"""

    def test_single_param(self, optimization_service):
        """测试单个参数的参数组合"""
        param_grid = {"fast_period": [5, 10, 15]}

        combinations = optimization_service._generate_param_combinations(param_grid)

        assert len(combinations) == 3
        assert combinations[0] == {"fast_period": 5}
        assert combinations[1] == {"fast_period": 10}
        assert combinations[2] == {"fast_period": 15}

    def test_two_params(self, optimization_service):
        """测试两个参数的参数组合（笛卡尔积）"""
        param_grid = {
            "fast_period": [5, 10],
            "slow_period": [20, 30, 40],
        }

        combinations = optimization_service._generate_param_combinations(param_grid)

        # 2 * 3 = 6 种组合
        assert len(combinations) == 6

        # 验证所有组合
        expected_combinations = [
            {"fast_period": 5, "slow_period": 20},
            {"fast_period": 5, "slow_period": 30},
            {"fast_period": 5, "slow_period": 40},
            {"fast_period": 10, "slow_period": 20},
            {"fast_period": 10, "slow_period": 30},
            {"fast_period": 10, "slow_period": 40},
        ]

        for combo in expected_combinations:
            assert combo in combinations

    def test_empty_param_grid(self, optimization_service):
        """测试空的参数网格"""
        param_grid = {}

        combinations = optimization_service._generate_param_combinations(param_grid)

        assert len(combinations) == 1
        assert combinations[0] == {}


class TestGridSearch:
    """测试网格搜索优化"""

    @pytest.mark.asyncio
    async def test_grid_search_basic(self, optimization_service, backtest_service_mock):
        """测试基本的网格搜索"""
        # 模拟 BacktestService
        optimization_service.backtest_service = backtest_service_mock

        request = OptimizationRequest(
            strategy_id="ma_cross",
            method="grid",
            metric="sharpe_ratio",
            backtest_config=BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                initial_cash=100000,
                commission=0.001,
            ),
            param_grid={
                "fast_period": [5, 10],
                "slow_period": [20, 30],
            },
        )

        # 运行网格搜索
        result = await optimization_service.run_grid_search(
            user_id="test-user",
            param_grid=request.param_grid,
            backtest_config=request.backtest_config,
            metric=request.metric,
        )

        # 验证结果
        assert result is not None
        assert "best_params" in result
        assert "best_metrics" in result
        assert "all_results" in result
        assert "n_trials" in result

        # 2 * 2 = 4 个参数组合
        assert result["n_trials"] == 4
        assert len(result["all_results"]) == 4

        # 验证结果按优化目标排序
        if result["all_results"]:
            best_sharpe = max(
                r["metrics"]["sharpe_ratio"]
                for r in result["all_results"]
                if r["metrics"]["sharpe_ratio"] is not None
            )
            assert result["best_metrics"]["sharpe_ratio"] == best_sharpe

    @pytest.mark.asyncio
    async def test_grid_search_maximizing_sharpe(self, optimization_service, backtest_service_mock):
        """测试最大化夏普比率的网格搜索"""
        optimization_service.backtest_service = backtest_service_mock

        request = OptimizationRequest(
            strategy_id="ma_cross",
            method="grid",
            metric="sharpe_ratio",
            backtest_config=BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                initial_cash=100000,
                commission=0.001,
            ),
            param_grid={
                "fast_period": [5, 10],
                "slow_period": [20, 30],
            },
        )

        result = await optimization_service.run_grid_search(
            user_id="test-user",
            param_grid=request.param_grid,
            backtest_config=request.backtest_config,
            metric=request.metric,
        )

        # 验证结果按夏普比率降序排序
        if result["all_results"]:
            sharpes = [r["metrics"]["sharpe_ratio"] for r in result["all_results"]]
            assert sharpes == sorted(sharpes, reverse=True)

    @pytest.mark.asyncio
    async def test_grid_search_minimizing_drawdown(self, optimization_service, backtest_service_mock):
        """测试最小化最大回撤的网格搜索"""
        optimization_service.backtest_service = backtest_service_mock

        request = OptimizationRequest(
            strategy_id="ma_cross",
            method="grid",
            metric="max_drawdown",
            backtest_config=BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                initial_cash=100000,
                commission=0.001,
            ),
            param_grid={
                "fast_period": [5, 10],
                "slow_period": [20, 30],
            },
        )

        result = await optimization_service.run_grid_search(
            user_id="test-user",
            param_grid=request.param_grid,
            backtest_config=request.backtest_config,
            metric=request.metric,
        )

        # 验证结果按最大回撤升序排序（最小化）
        if result["all_results"]:
            drawdowns = [r["metrics"]["max_drawdown"] for r in result["all_results"]]
            assert drawdowns == sorted(drawdowns)


class TestGetOptimizationMetric:
    """测试获取优化指标"""

    def test_get_sharpe_metric(self, optimization_service):
        """测试获取夏普比率指标"""
        result = {
            "metrics": {
                "sharpe_ratio": 1.5,
                "total_return": 20.0,
                "max_drawdown": 10.0,
            }
        }

        metric_value = optimization_service._get_optimization_metric(
            result, "sharpe_ratio"
        )

        # 最大化夏普比率，所以返回负值
        assert metric_value == -1.5

    def test_get_max_drawdown_metric(self, optimization_service):
        """测试获取最大回撤指标"""
        result = {
            "metrics": {
                "sharpe_ratio": 1.5,
                "total_return": 20.0,
                "max_drawdown": 10.0,
            }
        }

        metric_value = optimization_service._get_optimization_metric(
            result, "max_drawdown"
        )

        # 最小化最大回撤，所以返回正值的回撤
        assert metric_value == 10.0

    def test_get_total_return_metric(self, optimization_service):
        """测试获取总收益率指标"""
        result = {
            "metrics": {
                "sharpe_ratio": 1.5,
                "total_return": 20.0,
                "max_drawdown": 10.0,
            }
        }

        metric_value = optimization_service._get_optimization_metric(
            result, "total_return"
        )

        # 最大化收益率，所以返回负值
        assert metric_value == -20.0

    def test_get_default_metric(self, optimization_service):
        """测试默认指标（夏普比率）"""
        result = {
            "metrics": {
                "sharpe_ratio": 1.5,
                "total_return": 20.0,
            }
        }

        metric_value = optimization_service._get_optimization_metric(
            result, "unknown_metric"
        )

        # 默认使用夏普比率
        assert metric_value == -1.5


class TestWaitForBacktest:
    """测试等待回测完成"""

    @pytest.mark.asyncio
    async def test_wait_for_completed_backtest(self, optimization_service, backtest_service_mock):
        """测试等待回测完成"""
        optimization_service.backtest_service = backtest_service_mock

        task_id = "task-test-123"

        # 应该立即返回，因为任务已标记为完成
        result = await optimization_service._wait_for_backtest(task_id, timeout=60)

        assert result is not None
        assert result.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_wait_for_failed_backtest(self, optimization_service, backtest_service_mock):
        """测试等待回测失败"""
        optimization_service.backtest_service = backtest_service_mock

        task_id = "task-failed-456"

        # 应该抛出异常
        with pytest.raises(RuntimeError, match="回测失败"):
            await optimization_service._wait_for_backtest(task_id, timeout=60)

    @pytest.mark.asyncio
    async def test_wait_timeout(self, optimization_service, backtest_service_mock):
        """测试等待超时"""
        optimization_service.backtest_service = backtest_service_mock

        task_id = "task-timeout-789"

        # 模拟一个永不完成的任务
        async def mock_get_status(task_id):
            """始终返回 running 状态"""
            return TaskStatus.RUNNING

        backtest_service_mock.get_task_status = mock_get_status

        # 应该在 1 秒后超时
        with pytest.raises(RuntimeError, match="回测任务超时"):
            await optimization_service._wait_for_backtest(task_id, timeout=1)
