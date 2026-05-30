from datetime import datetime, timezone

from app.schemas.backtest import BacktestResult, TaskStatus, TradeRecord
from app.schemas.overfitting import (
    OverfittingAnalysisRequest,
    OverfittingMethod,
    OverfittingRiskLevel,
)
from app.services.overfitting import OverfittingService


def build_backtest_result(task_id: str = "bt-overfit-001") -> BacktestResult:
    return BacktestResult(
        task_id=task_id,
        strategy_id="strat-001",
        symbol="000001.SZ",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        status=TaskStatus.COMPLETED,
        total_return=28.5,
        annual_return=22.1,
        sharpe_ratio=1.42,
        max_drawdown=-11.4,
        win_rate=61.0,
        total_trades=8,
        profitable_trades=5,
        losing_trades=3,
        equity_curve=[100000, 104000, 107000, 103000, 111000, 118000, 124500],
        equity_dates=[
            "2024-01-02",
            "2024-02-15",
            "2024-04-01",
            "2024-05-20",
            "2024-07-08",
            "2024-10-10",
            "2024-12-31",
        ],
        drawdown_curve=[0.0, -1.0, -2.3, -4.7, -1.8, -0.6, 0.0],
        trades=[
            TradeRecord(
                type="buy", price=10.0, size=100, value=1000.0, pnl=80.0, pnlcomm=79.0, barlen=5
            ),
            TradeRecord(
                type="sell", price=11.0, size=120, value=1320.0, pnl=120.0, pnlcomm=118.0, barlen=8
            ),
            TradeRecord(
                type="buy", price=9.8, size=90, value=882.0, pnl=-45.0, pnlcomm=-46.0, barlen=4
            ),
            TradeRecord(
                type="sell", price=12.2, size=110, value=1342.0, pnl=140.0, pnlcomm=138.0, barlen=9
            ),
            TradeRecord(
                type="buy", price=8.5, size=150, value=1275.0, pnl=-30.0, pnlcomm=-31.0, barlen=6
            ),
            TradeRecord(
                type="sell", price=13.4, size=100, value=1340.0, pnl=160.0, pnlcomm=159.0, barlen=11
            ),
            TradeRecord(
                type="buy", price=14.0, size=80, value=1120.0, pnl=-20.0, pnlcomm=-21.0, barlen=3
            ),
            TradeRecord(
                type="sell", price=15.0, size=85, value=1275.0, pnl=95.0, pnlcomm=94.0, barlen=7
            ),
        ],
        created_at=datetime(2025, 1, 15, tzinfo=timezone.utc),
        error_message=None,
    )


class TestOverfittingMonteCarlo:
    async def test_calculate_analysis_returns_completed_monte_carlo_result(self):
        service = OverfittingService()

        result = await service.calculate_analysis(
            build_backtest_result(),
            OverfittingAnalysisRequest(
                methods=[OverfittingMethod.MONTE_CARLO],
                monte_carlo_iterations=120,
            ),
        )

        assert result.backtest_id == "bt-overfit-001"
        assert result.robustness_score >= 0
        assert result.robustness_score <= 100
        assert result.overall_level in {
            OverfittingRiskLevel.LOW,
            OverfittingRiskLevel.MEDIUM,
            OverfittingRiskLevel.HIGH,
        }
        assert len(result.methods) == 1
        method = result.methods[0]
        assert method.method == OverfittingMethod.MONTE_CARLO
        assert method.status == "completed"
        assert "actual_compound_return_pct" in method.metrics
        assert "bootstrap_percentile" in method.metrics
        assert "bootstrap_distribution_pct" in method.metrics
        assert len(method.metrics["bootstrap_distribution_pct"]) <= 60
        assert method.degraded is False
