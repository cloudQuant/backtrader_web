import asyncio
from datetime import datetime, timezone

import pytest

from app.schemas.backtest import BacktestRequest, BacktestResult, TaskStatus, TradeRecord
from app.schemas.overfitting import OverfittingMethod, OverfittingRiskLevel
from app.services.overfitting.out_of_sample import run_out_of_sample_analysis
from app.services.overfitting.walk_forward import run_walk_forward_analysis


def build_backtest_result(
    *,
    task_id: str,
    annual_return: float,
    sharpe_ratio: float,
    total_return: float | None = None,
    equity_curve: list[float] | None = None,
) -> BacktestResult:
    return BacktestResult(
        task_id=task_id,
        strategy_id='strat-001',
        symbol='000001.SZ',
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        status=TaskStatus.COMPLETED,
        total_return=total_return if total_return is not None else annual_return,
        annual_return=annual_return,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=-12.5,
        win_rate=58.0,
        total_trades=20,
        profitable_trades=12,
        losing_trades=8,
        equity_curve=equity_curve or [100000, 103000, 101000, 105000],
        equity_dates=['2024-01-01', '2024-04-01', '2024-08-01', '2024-12-31'],
        drawdown_curve=[0.0, -2.0, -4.0, -1.0],
        trades=[
            TradeRecord(price=10.0, size=1.0, value=1000.0, pnl=40.0, pnlcomm=38.0),
            TradeRecord(price=10.5, size=1.0, value=1100.0, pnl=25.0, pnlcomm=23.0),
        ],
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_run_walk_forward_analysis_reports_high_risk_when_oos_degrades_sharply() -> None:
    base_request = BacktestRequest(
        strategy_id='strat-001',
        symbol='000001.SZ',
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 9, 1, tzinfo=timezone.utc),
        initial_cash=100000,
        commission=0.001,
        timeframe='1d',
        timeframe_n=1,
        params={'fast_period': 5},
    )
    queued_results = iter(
        [
            build_backtest_result(task_id='wf-is-1', annual_return=24.0, sharpe_ratio=2.1),
            build_backtest_result(task_id='wf-oos-1', annual_return=9.0, sharpe_ratio=0.8),
            build_backtest_result(task_id='wf-is-2', annual_return=22.0, sharpe_ratio=1.9),
            build_backtest_result(task_id='wf-oos-2', annual_return=8.0, sharpe_ratio=0.7),
        ]
    )
    executed_windows: list[tuple[datetime, datetime]] = []

    async def execute_slice(request: BacktestRequest) -> BacktestResult:
        executed_windows.append((request.start_date, request.end_date))
        return next(queued_results)

    result = await run_walk_forward_analysis(
        base_request,
        execute_slice=execute_slice,
        train_days=90,
        test_days=30,
        step_days=90,
    )

    assert result.method == OverfittingMethod.WALK_FORWARD
    assert result.status == 'completed'
    assert result.risk_level == OverfittingRiskLevel.HIGH
    assert result.degraded is False
    assert result.score < 50
    assert result.metrics['window_count'] == 2
    assert result.metrics['avg_is_sharpe'] > result.metrics['avg_oos_sharpe']
    assert result.metrics['sharpe_decay_pct'] > 50
    assert len(executed_windows) == 4


@pytest.mark.asyncio
async def test_run_walk_forward_analysis_limits_concurrency_and_reports_window_progress() -> None:
    base_request = BacktestRequest(
        strategy_id='strat-001',
        symbol='000001.SZ',
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 10, 1, tzinfo=timezone.utc),
        initial_cash=100000,
        commission=0.001,
        timeframe='1d',
        timeframe_n=1,
        params={'fast_period': 5},
    )
    active_slices = 0
    max_active_slices = 0
    progress_events: list[tuple[int, int]] = []

    async def execute_slice(_request: BacktestRequest) -> BacktestResult:
        nonlocal active_slices, max_active_slices
        active_slices += 1
        max_active_slices = max(max_active_slices, active_slices)
        await asyncio.sleep(0.01)
        active_slices -= 1
        return build_backtest_result(task_id='wf-slice', annual_return=12.0, sharpe_ratio=1.2)

    async def progress_callback(completed: int, total: int) -> None:
        progress_events.append((completed, total))

    result = await run_walk_forward_analysis(
        base_request,
        execute_slice=execute_slice,
        train_days=90,
        test_days=30,
        step_days=60,
        max_concurrency=2,
        progress_callback=progress_callback,
    )

    assert result.degraded is False
    assert result.metrics['window_count'] >= 2
    assert max_active_slices <= 2
    assert progress_events
    assert progress_events[-1] == (result.metrics['window_count'], result.metrics['window_count'])


@pytest.mark.asyncio
async def test_run_out_of_sample_analysis_reports_high_risk_when_oos_is_much_weaker() -> None:
    base_request = BacktestRequest(
        strategy_id='strat-001',
        symbol='000001.SZ',
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
        initial_cash=100000,
        commission=0.001,
        timeframe='1d',
        timeframe_n=1,
        params={'fast_period': 5},
    )
    queued_results = iter(
        [
            build_backtest_result(
                task_id='oos-is',
                annual_return=20.0,
                sharpe_ratio=1.8,
                equity_curve=[100000, 104000, 108000, 112000],
            ),
            build_backtest_result(
                task_id='oos-oos',
                annual_return=6.0,
                sharpe_ratio=0.7,
                equity_curve=[112000, 112500, 111800, 112300],
            ),
        ]
    )
    executed_windows: list[tuple[datetime, datetime]] = []

    async def execute_slice(request: BacktestRequest) -> BacktestResult:
        executed_windows.append((request.start_date, request.end_date))
        return next(queued_results)

    result = await run_out_of_sample_analysis(
        base_request,
        execute_slice=execute_slice,
        out_of_sample_ratio=0.3,
    )

    assert result.method == OverfittingMethod.OUT_OF_SAMPLE
    assert result.status == 'completed'
    assert result.risk_level == OverfittingRiskLevel.HIGH
    assert result.degraded is False
    assert result.score < 50
    assert result.metrics['is_sharpe'] > result.metrics['oos_sharpe']
    assert result.metrics['sharpe_decay_pct'] > 50
    assert 0.0 <= result.metrics['p_value'] <= 1.0
    assert result.metrics['test_method'] == 'welch_t_test_normal_approx'
    assert 't_statistic' in result.metrics
    assert 'degrees_of_freedom' in result.metrics
    assert len(executed_windows) == 2
