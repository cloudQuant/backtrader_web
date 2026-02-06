"""
增强的输入验证测试

测试回测请求和优化请求的验证
"""
import pytest
from datetime import datetime, timedelta
from pydantic import ValidationError

from app.schemas.backtest_enhanced import (
    BacktestRequest,
    TaskStatus,
    OptimizationRequest,
    OptimizationResult,
    TradeRecord,
)


class TestBacktestRequest:
    """测试回测请求验证"""

    def test_valid_backtest_request(self):
        """测试有效的回测请求"""
        request = BacktestRequest(
            strategy_id="ma_cross",
            symbol="000001.SZ",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            initial_cash=100000,
            commission=0.001,
            params={"fast_period": 5, "slow_period": 20}
        )

        assert request.strategy_id == "ma_cross"
        assert request.symbol == "000001.SZ"
        assert request.initial_cash == 100000
        assert request.commission == 0.001

    def test_strategy_id_validation(self):
        """测试策略 ID 验证"""
        # 有效的 ID
        request = BacktestRequest(
            strategy_id="ma_cross",
            symbol="000001.SZ",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
        )
        assert request.strategy_id == "ma_cross"

        # 无效的 ID（包含特殊字符）
        with pytest.raises(ValidationError, match="pattern"):
            BacktestRequest(
                strategy_id="ma-cross",  # 无效：包含连字符
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
            )

    def test_symbol_validation(self):
        """测试股票代码验证"""
        # 有效的代码
        request = BacktestRequest(
            strategy_id="ma_cross",
            symbol="000001.SZ",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
        )
        assert request.symbol == "000001.SZ"

        # 无效的代码（格式错误）
        with pytest.raises(ValidationError, match="pattern"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001",  # 无效：缺少后缀
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
            )

        with pytest.raises(ValidationError, match="pattern"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="ABCDEF.SZ",  # 无效：不是6位数字
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
            )

    def test_date_range_validation(self):
        """测试日期范围验证"""
        # 有效的日期范围
        request = BacktestRequest(
            strategy_id="ma_cross",
            symbol="000001.SZ",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
        )
        assert request.end_date > request.start_date

        # end_date 必须 > start_date
        with pytest.raises(ValidationError, match="end_date 必须晚于 start_date"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 6, 1),
                end_date=datetime(2023, 5, 1),
            )

        # 日期范围不能超过 10 年
        max_end_date = datetime(2023, 1, 1) + timedelta(days=3650)
        with pytest.raises(ValidationError, match="回测时间范围不能超过 10 年"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2013, 1, 1),
                end_date=max_end_date + timedelta(days=1),
            )

        # 不能使用未来日期
        future_date = datetime.utcnow() + timedelta(days=1)
        with pytest.raises(ValidationError, match="end_date 不能是未来日期"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=future_date,
            )

    def test_initial_cash_validation(self):
        """测试初始资金验证"""
        # 有效的初始资金
        request = BacktestRequest(
            strategy_id="ma_cross",
            symbol="000001.SZ",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            initial_cash=100000,
        )
        assert request.initial_cash == 100000

        # 必须大于 0
        with pytest.raises(ValidationError, match="greater than 0"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                initial_cash=0,
            )

        with pytest.raises(ValidationError, match="greater than 0"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                initial_cash=-1000,
            )

        # 最多 1000 万
        with pytest.raises(ValidationError, match="less than or equal to 10000000"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                initial_cash=20000000,
            )

    def test_commission_validation(self):
        """测试手续费率验证"""
        # 有效的手续费率
        request = BacktestRequest(
            strategy_id="ma_cross",
            symbol="000001.SZ",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            commission=0.001,
        )
        assert request.commission == 0.001

        # 必须 >= 0
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                commission=-0.001,
            )

        # 最多 10%
        with pytest.raises(ValidationError, match="less than or equal to 0.1"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                commission=0.2,
            )

    def test_params_validation(self):
        """测试策略参数验证"""
        # 有效的参数
        request = BacktestRequest(
            strategy_id="ma_cross",
            symbol="000001.SZ",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            params={
                "fast_period": 5,
                "slow_period": 20,
            },
        )
        assert request.params == {"fast_period": 5, "slow_period": 20}

        # 未知参数
        with pytest.raises(ValidationError, match="未知参数"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                params={
                    "unknown_param": 10,
                },
            )

        # 参数类型错误
        with pytest.raises(ValidationError, match="fast_period 必须是整数"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                params={
                    "fast_period": "5",  # 应该是 int
                    "slow_period": 20,
                },
            )

        # 参数超出范围
        with pytest.raises(ValidationError, match="fast_period 必须大于等于 2"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                params={
                    "fast_period": 1,  # 太小
                    "slow_period": 20,
                },
            )

    def test_min_backtest_days(self):
        """测试最小回测天数验证"""
        # 至少 30 天
        request = BacktestRequest(
            strategy_id="ma_cross",
            symbol="000001.SZ",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 31),
        )
        # 30 天应该可以
        assert request.end_date > request.start_date

        # 少于 30 天
        with pytest.raises(ValidationError, match="回测时间范围不能少于 30 天"):
            BacktestRequest(
                strategy_id="ma_cross",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 1, 20),
            )


class TestOptimizationRequest:
    """测试参数优化请求验证"""

    def test_valid_grid_optimization(self):
        """测试有效的网格搜索优化"""
        request = OptimizationRequest(
            strategy_id="ma_cross",
            method="grid",
            metric="sharpe_ratio",
            backtest_config={
                "strategy_id": "ma_cross",
                "symbol": "000001.SZ",
                "start_date": datetime(2023, 1, 1),
                "end_date": datetime(2023, 12, 31),
                "initial_cash": 100000,
                "commission": 0.001,
            },
            param_grid={
                "fast_period": [5, 10, 15],
                "slow_period": [20, 30, 40],
            },
        )

        assert request.method == "grid"
        assert request.metric == "sharpe_ratio"
        assert len(request.param_grid["fast_period"]) == 3

    def test_grid_search_requires_param_grid(self):
        """测试网格搜索需要参数网格"""
        with pytest.raises(ValidationError, match="网格搜索需要 param_grid"):
            OptimizationRequest(
                strategy_id="ma_cross",
                method="grid",
                metric="sharpe_ratio",
                backtest_config={
                    "strategy_id": "ma_cross",
                    "symbol": "000001.SZ",
                    "start_date": datetime(2023, 1, 1),
                    "end_date": datetime(2023, 12, 31),
                    "initial_cash": 100000,
                    "commission": 0.001,
                },
                # 缺少 param_grid
            )

    def test_valid_bayesian_optimization(self):
        """测试有效的贝叶斯优化"""
        request = OptimizationRequest(
            strategy_id="ma_cross",
            method="bayesian",
            metric="sharpe_ratio",
            n_trials=100,
            backtest_config={
                "strategy_id": "ma_cross",
                "symbol": "000001.SZ",
                "start_date": datetime(2023, 1, 1),
                "end_date": datetime(2023, 12, 31),
                "initial_cash": 100000,
                "commission": 0.001,
            },
            param_bounds={
                "fast_period": {"type": "int", "min": 5, "max": 20},
                "slow_period": {"type": "int", "min": 20, "max": 60},
            },
        )

        assert request.method == "bayesian"
        assert request.n_trials == 100
        assert "fast_period" in request.param_bounds

    def test_bayesian_optimization_requires_param_bounds(self):
        """测试贝叶斯优化需要参数边界"""
        with pytest.raises(ValidationError, match="贝叶斯优化需要 param_bounds"):
            OptimizationRequest(
                strategy_id="ma_cross",
                method="bayesian",
                metric="sharpe_ratio",
                backtest_config={
                    "strategy_id": "ma_cross",
                    "symbol": "000001.SZ",
                    "start_date": datetime(2023, 1, 1),
                    "end_date": datetime(2023, 12, 31),
                    "initial_cash": 100000,
                    "commission": 0.001,
                },
                # 缺少 param_bounds
            )

    def test_n_trials_validation(self):
        """测试试验次数验证"""
        # 有效范围
        request = OptimizationRequest(
            strategy_id="ma_cross",
            method="bayesian",
            metric="sharpe_ratio",
            n_trials=100,
            backtest_config={
                "strategy_id": "ma_cross",
                "symbol": "000001.SZ",
                "start_date": datetime(2023, 1, 1),
                "end_date": datetime(2023, 12, 31),
                "initial_cash": 100000,
                "commission": 0.001,
            },
            param_bounds={
                "fast_period": {"type": "int", "min": 5, "max": 20},
            },
        )
        assert request.n_trials == 100

        # 最少 10 次
        with pytest.raises(ValidationError, match="greater than or equal to 10"):
            OptimizationRequest(
                strategy_id="ma_cross",
                method="bayesian",
                metric="sharpe_ratio",
                n_trials=5,
                backtest_config={
                    "strategy_id": "ma_cross",
                    "symbol": "000001.SZ",
                    "start_date": datetime(2023, 1, 1),
                    "end_date": datetime(2023, 12, 31),
                    "initial_cash": 100000,
                    "commission": 0.001,
                },
                param_bounds={
                    "fast_period": {"type": "int", "min": 5, "max": 20},
                },
            )

        # 最多 1000 次
        with pytest.raises(ValidationError, match="less than or equal to 1000"):
            OptimizationRequest(
                strategy_id="ma_cross",
                method="bayesian",
                metric="sharpe_ratio",
                n_trials=2000,
                backtest_config={
                    "strategy_id": "ma_cross",
                    "symbol": "000001.SZ",
                    "start_date": datetime(2023, 1, 1),
                    "end_date": datetime(2023, 12, 31),
                    "initial_cash": 100000,
                    "commission": 0.001,
                },
                param_bounds={
                    "fast_period": {"type": "int", "min": 5, "max": 20},
                },
            )

    def test_method_validation(self):
        """测试优化方法验证"""
        # 有效的优化方法
        for method in ["grid", "bayesian"]:
            request = OptimizationRequest(
                strategy_id="ma_cross",
                method=method,
                metric="sharpe_ratio",
                backtest_config={
                    "strategy_id": "ma_cross",
                    "symbol": "000001.SZ",
                    "start_date": datetime(2023, 1, 1),
                    "end_date": datetime(2023, 12, 31),
                    "initial_cash": 100000,
                    "commission": 0.001,
                },
                param_grid={},
            )
            assert request.method == method

    def test_metric_validation(self):
        """测试优化目标验证"""
        # 有效的优化目标
        for metric in ["sharpe_ratio", "max_drawdown", "total_return"]:
            request = OptimizationRequest(
                strategy_id="ma_cross",
                method="bayesian",
                metric=metric,
                backtest_config={
                    "strategy_id": "ma_cross",
                    "symbol": "000001.SZ",
                    "start_date": datetime(2023, 1, 1),
                    "end_date": datetime(2023, 12, 31),
                    "initial_cash": 100000,
                    "commission": 0.001,
                },
                param_bounds={
                    "fast_period": {"type": "int", "min": 5, "max": 20},
                },
            )
            assert request.metric == metric


class TestTradeRecord:
    """测试交易记录验证"""

    def test_valid_buy_trade(self):
        """测试有效的买入交易记录"""
        trade = TradeRecord(
            date=datetime(2023, 1, 1),
            type="buy",
            price=100.5,
            size=1000,
            value=100500,
            pnl=None,
        )

        assert trade.type == "buy"
        assert trade.price == 100.5
        assert trade.size == 1000

    def test_valid_sell_trade(self):
        """测试有效的卖出交易记录"""
        trade = TradeRecord(
            date=datetime(2023, 1, 2),
            type="sell",
            price=105.0,
            size=1000,
            value=105000,
            pnl=4500,
        )

        assert trade.type == "sell"
        assert trade.pnl == 4500

    def test_invalid_trade_type(self):
        """测试无效的交易类型"""
        with pytest.raises(ValidationError, match="not subset of"):
            TradeRecord(
                date=datetime(2023, 1, 1),
                type="hold",  # 无效：只允许 buy 或 sell
                price=100.5,
                size=1000,
                value=100500,
            )

    def test_price_validation(self):
        """测试价格验证"""
        # 价格必须大于 0
        with pytest.raises(ValidationError, match="greater than 0"):
            TradeRecord(
                date=datetime(2023, 1, 1),
                type="buy",
                price=0,
                size=1000,
                value=100500,
            )

        with pytest.raises(ValidationError, match="greater than 0"):
            TradeRecord(
                date=datetime(2023, 1, 1),
                type="buy",
                price=-100,
                size=1000,
                value=100500,
            )

    def test_size_validation(self):
        """测试数量验证"""
        # 数量必须大于 0
        with pytest.raises(ValidationError, match="greater than 0"):
            TradeRecord(
                date=datetime(2023, 1, 1),
                type="buy",
                price=100.5,
                size=0,
                value=100500,
            )

    def test_value_validation(self):
        """测试成交金额验证"""
        # 成交金额必须大于 0
        with pytest.raises(ValidationError, match="greater than 0"):
            TradeRecord(
                date=datetime(2023, 1, 1),
                type="buy",
                price=100.5,
                size=1000,
                value=0,
            )
