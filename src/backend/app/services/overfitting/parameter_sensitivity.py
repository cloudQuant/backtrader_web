from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from typing import Any

from app.schemas.backtest import BacktestRequest, BacktestResult
from app.schemas.overfitting import OverfittingMethod, OverfittingMethodResult, OverfittingRiskLevel

SliceExecutor = Callable[[BacktestRequest], Awaitable[BacktestResult]]


async def run_parameter_sensitivity_analysis(
    base_request: BacktestRequest,
    base_result: BacktestResult,
    *,
    execute_slice: SliceExecutor,
    max_parameters: int = 3,
) -> OverfittingMethodResult:
    """Run small +/- perturbations for numeric parameters."""
    numeric_params = [
        (key, value)
        for key, value in dict(base_request.params or {}).items()
        if isinstance(value, int | float) and math.isfinite(float(value))
    ][:max_parameters]
    if not numeric_params:
        return OverfittingMethodResult(
            method=OverfittingMethod.PARAMETER_SENSITIVITY,
            status="completed",
            risk_level=OverfittingRiskLevel.MEDIUM,
            score=50.0,
            explanation="策略未暴露可扰动的数值参数，参数敏感性暂按中位分处理。",
            metrics={"parameter_count": 0},
            degraded=True,
        )

    base_sharpe = float(base_result.sharpe_ratio or 0.0)
    base_return = float(base_result.annual_return or 0.0)
    trials: list[dict[str, Any]] = []
    worst_decay = 0.0
    for key, value in numeric_params:
        original = float(value)
        step = max(abs(original) * 0.1, 1.0 if isinstance(value, int) else 0.01)
        for direction, candidate in (("down", original - step), ("up", original + step)):
            if isinstance(value, int):
                candidate_value: int | float = max(1, int(round(candidate)))
            else:
                candidate_value = round(candidate, 8)
            params = {**dict(base_request.params or {}), key: candidate_value}
            result = await execute_slice(base_request.model_copy(update={"params": params}))
            sharpe = float(result.sharpe_ratio or 0.0)
            annual_return = float(result.annual_return or 0.0)
            sharpe_decay = _decay_pct(base_sharpe, sharpe)
            return_decay = _decay_pct(base_return, annual_return)
            worst_decay = max(worst_decay, sharpe_decay, return_decay)
            trials.append(
                {
                    "parameter": key,
                    "direction": direction,
                    "value": candidate_value,
                    "sharpe_ratio": round(sharpe, 4),
                    "annual_return": round(annual_return, 4),
                    "sharpe_decay_pct": sharpe_decay,
                    "return_decay_pct": return_decay,
                }
            )

    score = round(max(0.0, min(100.0, 100.0 - worst_decay)), 2)
    risk_level = (
        OverfittingRiskLevel.HIGH
        if worst_decay > 50
        else OverfittingRiskLevel.MEDIUM
        if worst_decay >= 30
        else OverfittingRiskLevel.LOW
    )
    explanation = (
        "参数小幅扰动后表现稳定，敏感性风险较低。"
        if risk_level is OverfittingRiskLevel.LOW
        else "参数扰动后表现有明显衰减，需要降低参数过拟合风险。"
        if risk_level is OverfittingRiskLevel.HIGH
        else "参数扰动后表现有一定衰减，建议结合其他稳健性证据。"
    )
    return OverfittingMethodResult(
        method=OverfittingMethod.PARAMETER_SENSITIVITY,
        status="completed",
        risk_level=risk_level,
        score=score,
        explanation=explanation,
        metrics={
            "parameter_count": len(numeric_params),
            "trial_count": len(trials),
            "base_sharpe": round(base_sharpe, 4),
            "base_annual_return": round(base_return, 4),
            "worst_decay_pct": round(worst_decay, 2),
            "trials": trials,
        },
        degraded=False,
    )


def _decay_pct(base_value: float, candidate_value: float) -> float:
    baseline = abs(base_value)
    if baseline <= 1e-9:
        return 0.0
    return round(max(0.0, ((base_value - candidate_value) / baseline) * 100), 2)
