from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta

from app.schemas.backtest import BacktestRequest, BacktestResult
from app.schemas.overfitting import OverfittingMethod, OverfittingMethodResult, OverfittingRiskLevel

SliceExecutor = Callable[[BacktestRequest], Awaitable[BacktestResult]]
ProgressCallback = Callable[[int, int], Awaitable[None]]


def _decay_pct(in_sample_value: float, out_of_sample_value: float) -> float:
    baseline = abs(in_sample_value)
    if baseline <= 1e-6:
        return 0.0
    return round(max(0.0, ((in_sample_value - out_of_sample_value) / baseline) * 100), 2)


def _score_from_decay(decay_pct: float) -> float:
    return round(max(0.0, min(100.0, 100.0 - decay_pct)), 2)


def _risk_level_from_decay(decay_pct: float) -> OverfittingRiskLevel:
    if decay_pct > 50:
        return OverfittingRiskLevel.HIGH
    if decay_pct >= 30:
        return OverfittingRiskLevel.MEDIUM
    return OverfittingRiskLevel.LOW


async def run_walk_forward_analysis(
    base_request: BacktestRequest,
    *,
    execute_slice: SliceExecutor,
    train_days: int,
    test_days: int,
    step_days: int,
    max_concurrency: int = 4,
    progress_callback: ProgressCallback | None = None,
) -> OverfittingMethodResult:
    cursor = base_request.start_date
    window_requests: list[tuple[BacktestRequest, BacktestRequest]] = []
    train_delta = timedelta(days=train_days)
    test_delta = timedelta(days=test_days)
    step_delta = timedelta(days=step_days)

    while cursor + train_delta + test_delta <= base_request.end_date:
        train_request = base_request.model_copy(
            update={
                'start_date': cursor,
                'end_date': cursor + train_delta,
            }
        )
        test_request = base_request.model_copy(
            update={
                'start_date': cursor + train_delta,
                'end_date': cursor + train_delta + test_delta,
            }
        )
        window_requests.append((train_request, test_request))
        cursor += step_delta

    if not window_requests:
        return OverfittingMethodResult(
            method=OverfittingMethod.WALK_FORWARD,
            status='completed',
            risk_level=OverfittingRiskLevel.MEDIUM,
            score=50.0,
            explanation='样本区间不足以构造有效的 Walk-forward 窗口，先按中位分处理。',
            metrics={'window_count': 0},
            degraded=True,
        )

    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    completed_windows = 0

    async def run_window(
        index: int,
        requests: tuple[BacktestRequest, BacktestRequest],
    ) -> dict[str, float | int | str]:
        nonlocal completed_windows
        train_request, test_request = requests
        async with semaphore:
            is_result = await execute_slice(train_request)
        async with semaphore:
            oos_result = await execute_slice(test_request)
        completed_windows += 1
        if progress_callback is not None:
            await progress_callback(completed_windows, len(window_requests))
        return {
            'index': index + 1,
            'train_start': train_request.start_date.isoformat(),
            'train_end': train_request.end_date.isoformat(),
            'test_start': test_request.start_date.isoformat(),
            'test_end': test_request.end_date.isoformat(),
            'is_sharpe': round(float(is_result.sharpe_ratio), 4),
            'oos_sharpe': round(float(oos_result.sharpe_ratio), 4),
            'is_annual_return': round(float(is_result.annual_return), 4),
            'oos_annual_return': round(float(oos_result.annual_return), 4),
        }

    windows = await asyncio.gather(
        *(run_window(index, requests) for index, requests in enumerate(window_requests))
    )

    if not windows:
        return OverfittingMethodResult(
            method=OverfittingMethod.WALK_FORWARD,
            status='completed',
            risk_level=OverfittingRiskLevel.MEDIUM,
            score=50.0,
            explanation='样本区间不足以构造有效的 Walk-forward 窗口，先按中位分处理。',
            metrics={'window_count': 0},
            degraded=True,
        )

    avg_is_sharpe = sum(float(item['is_sharpe']) for item in windows) / len(windows)
    avg_oos_sharpe = sum(float(item['oos_sharpe']) for item in windows) / len(windows)
    avg_is_return = sum(float(item['is_annual_return']) for item in windows) / len(windows)
    avg_oos_return = sum(float(item['oos_annual_return']) for item in windows) / len(windows)
    sharpe_decay_pct = _decay_pct(avg_is_sharpe, avg_oos_sharpe)
    return_decay_pct = _decay_pct(avg_is_return, avg_oos_return)
    worst_decay_pct = max(sharpe_decay_pct, return_decay_pct)
    risk_level = _risk_level_from_decay(worst_decay_pct)
    score = _score_from_decay(worst_decay_pct)

    if risk_level is OverfittingRiskLevel.LOW:
        explanation = 'Walk-forward 各窗口 OOS 表现与样本内接近，策略稳健性较好。'
    elif risk_level is OverfittingRiskLevel.MEDIUM:
        explanation = 'Walk-forward 样本外表现相对样本内有一定衰减，需要结合更多证据确认。'
    else:
        explanation = 'Walk-forward 样本外表现相对样本内明显衰减，存在较高过拟合风险。'

    return OverfittingMethodResult(
        method=OverfittingMethod.WALK_FORWARD,
        status='completed',
        risk_level=risk_level,
        score=score,
        explanation=explanation,
        metrics={
            'window_count': len(windows),
            'avg_is_sharpe': round(avg_is_sharpe, 4),
            'avg_oos_sharpe': round(avg_oos_sharpe, 4),
            'avg_is_annual_return': round(avg_is_return, 4),
            'avg_oos_annual_return': round(avg_oos_return, 4),
            'sharpe_decay_pct': sharpe_decay_pct,
            'return_decay_pct': return_decay_pct,
            'windows': windows,
        },
        degraded=False,
    )
