from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.schemas.backtest import BacktestResult, TaskStatus, TradeRecord
from app.schemas.overfitting import (
    OverfittingMethod,
    OverfittingMethodResult,
    OverfittingRiskLevel,
    OverfittingTaskResult,
)
from app.services.strategy_score import StrategyScoreService


def build_backtest_result(
    *,
    task_id: str = "bt-001",
    annual_return: float = 18.4,
    total_return: float = 23.5,
    sharpe_ratio: float = 1.35,
    max_drawdown: float = -12.8,
    win_rate: float = 58.3,
    total_trades: int = 42,
    profitable_trades: int = 24,
    losing_trades: int = 18,
    equity_curve: list[float] | None = None,
    equity_dates: list[str] | None = None,
) -> BacktestResult:
    return BacktestResult(
        task_id=task_id,
        strategy_id="strat-001",
        symbol="000001.SZ",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        status=TaskStatus.COMPLETED,
        total_return=total_return,
        annual_return=annual_return,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        total_trades=total_trades,
        profitable_trades=profitable_trades,
        losing_trades=losing_trades,
        equity_curve=equity_curve or [100000, 103000, 101500, 109000, 123500],
        equity_dates=equity_dates or [
            "2024-01-02",
            "2024-03-01",
            "2024-06-03",
            "2024-09-02",
            "2024-12-31",
        ],
        drawdown_curve=[0.0, -1.2, -3.4, -2.1, 0.0],
        trades=[
            TradeRecord(
                datetime="2024-01-15T00:00:00+00:00",
                dtopen="2024-01-10T00:00:00+00:00",
                dtclose="2024-01-15T00:00:00+00:00",
                direction="long",
                type="buy",
                price=10.0,
                size=100,
                value=1000,
                commission=1.0,
                pnl=120.0,
                pnlcomm=119.0,
                barlen=5,
            ),
            TradeRecord(
                datetime="2024-03-20T00:00:00+00:00",
                dtopen="2024-03-12T00:00:00+00:00",
                dtclose="2024-03-20T00:00:00+00:00",
                direction="long",
                type="sell",
                price=11.0,
                size=100,
                value=1100,
                commission=1.0,
                pnl=-80.0,
                pnlcomm=-81.0,
                barlen=8,
            ),
        ],
        created_at=datetime(2025, 1, 15, tzinfo=timezone.utc),
        error_message=None,
    )


class TestStrategyScoreService:
    def test_calculate_score_returns_six_dimensions_and_degraded_overfitting(self):
        service = StrategyScoreService()

        result = service.calculate_score(build_backtest_result())

        assert result.backtest_id == "bt-001"
        assert len(result.dimensions) == 6
        assert result.total_score >= 0
        assert result.total_score <= 100
        assert result.level in {"S", "A", "B", "C", "D"}
        overfitting = next(item for item in result.dimensions if item.key == "overfitting_risk")
        assert overfitting.degraded is True

    def test_calculate_score_assigns_lower_level_to_weaker_result(self):
        service = StrategyScoreService()

        result = service.calculate_score(
            build_backtest_result(
                task_id="bt-weak",
                annual_return=-5.0,
                total_return=-8.0,
                sharpe_ratio=-0.4,
                max_drawdown=-35.0,
                win_rate=32.0,
                total_trades=4,
                profitable_trades=1,
                losing_trades=3,
            )
        )

        assert result.backtest_id == "bt-weak"
        assert result.level in {"C", "D"}
        assert result.total_score < 55

    async def test_score_backtest_uses_real_overfitting_result_when_available(self):
        service = StrategyScoreService()
        service.overfitting_service.get_cached_analysis = AsyncMock(
            return_value=OverfittingTaskResult(
                task_id="ot-001",
                backtest_id="bt-001",
                status="completed",
                overall_level=OverfittingRiskLevel.LOW,
                robustness_score=82.0,
                summary="Monte Carlo 显示策略收益高于大部分随机路径。",
                methods=[
                    OverfittingMethodResult(
                        method=OverfittingMethod.MONTE_CARLO,
                        status="completed",
                        risk_level=OverfittingRiskLevel.LOW,
                        score=82.0,
                        explanation="实际收益位于 bootstrap 分布高分位。",
                        metrics={"bootstrap_percentile": 96.0},
                        degraded=False,
                    )
                ],
            )
        )

        result = await service.score_backtest(backtest_result=build_backtest_result())

        overfitting = next(item for item in result.dimensions if item.key == "overfitting_risk")
        assert overfitting.degraded is False
        assert overfitting.score == 82.0
        assert overfitting.sub_metrics["overall_level"] == "low"

    def test_risk_control_dimension_includes_var_cvar_when_history_is_available(self):
        service = StrategyScoreService()
        equity_curve = [100000 + index * 100 for index in range(31)]
        equity_dates = [f"2024-01-{day:02d}" for day in range(1, 32)]

        result = service.calculate_score(
            build_backtest_result(equity_curve=equity_curve, equity_dates=equity_dates)
        )

        risk_control = next(item for item in result.dimensions if item.key == "risk_control")
        assert risk_control.sub_metrics["var_cvar_status"] == "ok"
        assert "var_95" in risk_control.sub_metrics
        assert "cvar_95" in risk_control.sub_metrics

    def test_risk_control_dimension_penalizes_worse_tail_risk(self):
        service = StrategyScoreService()
        dates = [f"2024-01-{day:02d}" for day in range(1, 32)]
        mild_equity = [100000 + index * 100 for index in range(31)]
        tail_risk_equity = [
            100000,
            99000,
            98000,
            97000,
            96000,
            84000,
            85000,
            86000,
            87000,
            88000,
            89000,
            90000,
            91000,
            92000,
            93000,
            94000,
            95000,
            96000,
            97000,
            98000,
            99000,
            100000,
            101000,
            100000,
            99000,
            98000,
            97000,
            96000,
            95000,
            94000,
            93000,
        ]

        mild_score = service.calculate_score(
            build_backtest_result(equity_curve=mild_equity, equity_dates=dates)
        )
        tail_risk_score = service.calculate_score(
            build_backtest_result(equity_curve=tail_risk_equity, equity_dates=dates)
        )

        mild_risk = next(item for item in mild_score.dimensions if item.key == "risk_control")
        tail_risk = next(item for item in tail_risk_score.dimensions if item.key == "risk_control")
        assert tail_risk.score < mild_risk.score
        assert tail_risk.sub_metrics["cvar_95"] < mild_risk.sub_metrics["cvar_95"]
