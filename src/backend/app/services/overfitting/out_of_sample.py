from __future__ import annotations

import math
import statistics
from collections.abc import Awaitable, Callable
from datetime import timedelta

from app.schemas.backtest import BacktestRequest, BacktestResult
from app.schemas.overfitting import OverfittingMethod, OverfittingMethodResult, OverfittingRiskLevel

SliceExecutor = Callable[[BacktestRequest], Awaitable[BacktestResult]]


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


def _equity_returns(result: BacktestResult) -> list[float]:
    points = [float(item) for item in result.equity_curve]
    if len(points) < 2:
        return []
    returns: list[float] = []
    for previous, current in zip(points, points[1:], strict=False):
        if abs(previous) <= 1e-6:
            continue
        returns.append((current - previous) / previous)
    return returns


def _welch_t_test_normal_approx(
    sample_a: list[float], sample_b: list[float]
) -> dict[str, float | str]:
    if len(sample_a) < 2 or len(sample_b) < 2:
        return {
            "test_method": "welch_t_test_normal_approx",
            "p_value": 1.0,
            "t_statistic": 0.0,
            "degrees_of_freedom": 0.0,
        }
    mean_a = statistics.fmean(sample_a)
    mean_b = statistics.fmean(sample_b)
    var_a = statistics.variance(sample_a)
    var_b = statistics.variance(sample_b)
    term_a = var_a / len(sample_a)
    term_b = var_b / len(sample_b)
    denominator = math.sqrt(term_a + term_b)
    if denominator <= 1e-9:
        return {
            "test_method": "welch_t_test_normal_approx",
            "p_value": 1.0,
            "t_statistic": 0.0,
            "degrees_of_freedom": 0.0,
        }
    t_statistic = (mean_a - mean_b) / denominator
    numerator = (term_a + term_b) ** 2
    denominator_df = 0.0
    if len(sample_a) > 1:
        denominator_df += (term_a**2) / (len(sample_a) - 1)
    if len(sample_b) > 1:
        denominator_df += (term_b**2) / (len(sample_b) - 1)
    degrees_of_freedom = numerator / denominator_df if denominator_df > 0 else 0.0
    p_value = max(0.0, min(1.0, math.erfc(abs(t_statistic) / math.sqrt(2.0))))
    return {
        "test_method": "welch_t_test_normal_approx",
        "p_value": round(p_value, 4),
        "t_statistic": round(t_statistic, 4),
        "degrees_of_freedom": round(degrees_of_freedom, 2),
    }


async def run_out_of_sample_analysis(
    base_request: BacktestRequest,
    *,
    execute_slice: SliceExecutor,
    out_of_sample_ratio: float,
) -> OverfittingMethodResult:
    total_duration = base_request.end_date - base_request.start_date
    total_seconds = total_duration.total_seconds()
    if total_seconds <= 0:
        return OverfittingMethodResult(
            method=OverfittingMethod.OUT_OF_SAMPLE,
            status="completed",
            risk_level=OverfittingRiskLevel.MEDIUM,
            score=50.0,
            explanation="样本区间无效，暂无法完成样本外验证。",
            metrics={"status": "invalid_date_range"},
            degraded=True,
        )

    split_seconds = total_seconds * (1.0 - out_of_sample_ratio)
    split_point = base_request.start_date + timedelta(seconds=split_seconds)
    if split_point <= base_request.start_date or split_point >= base_request.end_date:
        return OverfittingMethodResult(
            method=OverfittingMethod.OUT_OF_SAMPLE,
            status="completed",
            risk_level=OverfittingRiskLevel.MEDIUM,
            score=50.0,
            explanation="样本外切分比例无效，暂按中位分处理。",
            metrics={"status": "invalid_split_ratio"},
            degraded=True,
        )

    is_request = base_request.model_copy(
        update={
            "start_date": base_request.start_date,
            "end_date": split_point,
        }
    )
    oos_request = base_request.model_copy(
        update={
            "start_date": split_point,
            "end_date": base_request.end_date,
        }
    )
    is_result = await execute_slice(is_request)
    oos_result = await execute_slice(oos_request)

    sharpe_decay_pct = _decay_pct(float(is_result.sharpe_ratio), float(oos_result.sharpe_ratio))
    return_decay_pct = _decay_pct(float(is_result.annual_return), float(oos_result.annual_return))
    worst_decay_pct = max(sharpe_decay_pct, return_decay_pct)
    risk_level = _risk_level_from_decay(worst_decay_pct)
    score = _score_from_decay(worst_decay_pct)
    t_test = _welch_t_test_normal_approx(_equity_returns(is_result), _equity_returns(oos_result))

    if risk_level is OverfittingRiskLevel.LOW:
        explanation = "样本外收益与风险表现接近样本内，结果相对稳健。"
    elif risk_level is OverfittingRiskLevel.MEDIUM:
        explanation = "样本外表现较样本内出现一定衰减，建议结合更多检测方法判断。"
    else:
        explanation = "样本外表现明显弱于样本内，存在较高过拟合风险。"

    return OverfittingMethodResult(
        method=OverfittingMethod.OUT_OF_SAMPLE,
        status="completed",
        risk_level=risk_level,
        score=score,
        explanation=explanation,
        metrics={
            "is_start": is_request.start_date.isoformat(),
            "is_end": is_request.end_date.isoformat(),
            "oos_start": oos_request.start_date.isoformat(),
            "oos_end": oos_request.end_date.isoformat(),
            "is_sharpe": round(float(is_result.sharpe_ratio), 4),
            "oos_sharpe": round(float(oos_result.sharpe_ratio), 4),
            "is_annual_return": round(float(is_result.annual_return), 4),
            "oos_annual_return": round(float(oos_result.annual_return), 4),
            "sharpe_decay_pct": sharpe_decay_pct,
            "return_decay_pct": return_decay_pct,
            **t_test,
        },
        degraded=False,
    )
