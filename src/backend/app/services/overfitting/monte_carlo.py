from __future__ import annotations

import hashlib
import math
import random
import statistics
from collections.abc import Iterable

from app.schemas.backtest import BacktestResult
from app.schemas.overfitting import OverfittingMethod, OverfittingMethodResult, OverfittingRiskLevel


def _compound_return(returns: Iterable[float]) -> float:
    total = 1.0
    for item in returns:
        total *= 1.0 + item
    return total - 1.0


def _seed_from_backtest_id(backtest_id: str) -> int:
    digest = hashlib.sha256(backtest_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _trade_returns(backtest_result: BacktestResult) -> list[float]:
    returns: list[float] = []
    for trade in backtest_result.trades:
        pnl = trade.pnlcomm if trade.pnlcomm is not None else trade.pnl
        if pnl is None or trade.value is None:
            continue
        try:
            base_value = abs(float(trade.value))
            pnl_value = float(pnl)
        except (TypeError, ValueError):
            continue
        if base_value <= 0:
            continue
        returns.append(pnl_value / base_value)
    return returns


def _percentile_rank(sorted_values: list[float], value: float) -> float:
    if not sorted_values:
        return 50.0
    below_or_equal = sum(1 for item in sorted_values if item <= value)
    return round((below_or_equal / len(sorted_values)) * 100, 2)


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = max(0.0, min(1.0, q)) * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _sample_distribution_pct(sorted_values: list[float], max_points: int = 60) -> list[float]:
    if not sorted_values:
        return []
    if len(sorted_values) <= max_points:
        return [round(item * 100, 4) for item in sorted_values]
    step = (len(sorted_values) - 1) / (max_points - 1)
    return [round(sorted_values[round(index * step)] * 100, 4) for index in range(max_points)]


def _risk_level_from_percentile(percentile: float) -> OverfittingRiskLevel:
    if percentile >= 95:
        return OverfittingRiskLevel.LOW
    if percentile >= 75:
        return OverfittingRiskLevel.MEDIUM
    return OverfittingRiskLevel.HIGH


def run_monte_carlo_analysis(
    backtest_result: BacktestResult,
    *,
    iterations: int,
    random_seed: int | None = None,
) -> OverfittingMethodResult:
    trade_returns = _trade_returns(backtest_result)
    if len(trade_returns) < 3:
        return OverfittingMethodResult(
            method=OverfittingMethod.MONTE_CARLO,
            status="completed",
            risk_level=OverfittingRiskLevel.MEDIUM,
            score=50.0,
            explanation="交易样本过少，暂无法形成稳定的 Monte Carlo 分布，先按中位分处理。",
            metrics={
                "trade_return_count": len(trade_returns),
                "actual_compound_return_pct": round(_compound_return(trade_returns) * 100, 4),
            },
            degraded=True,
        )

    rng = random.Random(random_seed if random_seed is not None else _seed_from_backtest_id(backtest_result.task_id))
    actual_compound_return = _compound_return(trade_returns)
    bootstrap_returns: list[float] = []
    for _ in range(iterations):
        sample = [rng.choice(trade_returns) for _ in range(len(trade_returns))]
        bootstrap_returns.append(_compound_return(sample))

    bootstrap_returns.sort()
    percentile = _percentile_rank(bootstrap_returns, actual_compound_return)
    risk_level = _risk_level_from_percentile(percentile)
    score = round(max(0.0, min(100.0, percentile)), 2)
    percentile_75 = _quantile(bootstrap_returns, 0.75)
    percentile_95 = _quantile(bootstrap_returns, 0.95)
    bootstrap_mean = statistics.fmean(bootstrap_returns)
    bootstrap_std = statistics.pstdev(bootstrap_returns) if len(bootstrap_returns) >= 2 else 0.0

    if risk_level is OverfittingRiskLevel.LOW:
        explanation = "实际收益位于 bootstrap 随机分布高分位，策略结果相对稳健。"
    elif risk_level is OverfittingRiskLevel.MEDIUM:
        explanation = "实际收益高于大部分随机样本，但尚未明显拉开到极高分位。"
    else:
        explanation = "实际收益未明显优于随机 bootstrap 分布，存在较高过拟合风险。"

    return OverfittingMethodResult(
        method=OverfittingMethod.MONTE_CARLO,
        status="completed",
        risk_level=risk_level,
        score=score,
        explanation=explanation,
        metrics={
            "trade_return_count": len(trade_returns),
            "iterations": iterations,
            "actual_compound_return_pct": round(actual_compound_return * 100, 4),
            "bootstrap_mean_return_pct": round(bootstrap_mean * 100, 4),
            "bootstrap_std_return_pct": round(bootstrap_std * 100, 4),
            "bootstrap_percentile": percentile,
            "bootstrap_p75_return_pct": round(percentile_75 * 100, 4),
            "bootstrap_p95_return_pct": round(percentile_95 * 100, 4),
            "bootstrap_distribution_pct": _sample_distribution_pct(bootstrap_returns),
        },
        degraded=False,
    )
