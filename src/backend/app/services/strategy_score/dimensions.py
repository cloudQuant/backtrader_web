"""Dimension scoring helpers for strategy scoring."""

from __future__ import annotations

import statistics
from collections.abc import Iterable

from app.schemas.backtest import BacktestResult
from app.schemas.overfitting import OverfittingTaskResult
from app.schemas.strategy_score import ScoreDimension
from app.services.risk_analytics import VarCvarService


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _normalize(value: float, lower: float, upper: float) -> float:
    if upper <= lower:
        return 50.0
    ratio = (value - lower) / (upper - lower)
    return _clamp_score(ratio * 100)


def _inverse_normalize(value: float, lower: float, upper: float) -> float:
    return _clamp_score(100 - _normalize(value, lower, upper))


def _safe_mean(values: Iterable[float], default: float = 0.0) -> float:
    items = list(values)
    if not items:
        return default
    return float(sum(items) / len(items))


def _equity_returns(equity_curve: list[float]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(equity_curve, equity_curve[1:], strict=False):
        if previous > 0:
            returns.append((current - previous) / previous)
    return returns


def _average_holding_bars(backtest_result: BacktestResult) -> float:
    bars = [float(trade.barlen) for trade in backtest_result.trades if trade.barlen is not None]
    return _safe_mean(bars, default=0.0)


def score_profitability_dimension(backtest_result: BacktestResult, weight: float) -> ScoreDimension:
    annual_score = _normalize(backtest_result.annual_return, -10.0, 30.0)
    sharpe_score = _normalize(backtest_result.sharpe_ratio, -1.0, 2.5)
    total_return_score = _normalize(backtest_result.total_return, -15.0, 40.0)
    score = annual_score * 0.4 + sharpe_score * 0.35 + total_return_score * 0.25
    return ScoreDimension(
        key="profitability",
        label="收益质量",
        score=_clamp_score(score),
        weight=weight,
        explanation="综合年化收益、总收益和夏普比率评估收益质量。",
        sub_metrics={
            "annual_return": backtest_result.annual_return,
            "total_return": backtest_result.total_return,
            "sharpe_ratio": backtest_result.sharpe_ratio,
        },
    )


def score_risk_control_dimension(backtest_result: BacktestResult, weight: float) -> ScoreDimension:
    drawdown_score = _inverse_normalize(abs(backtest_result.max_drawdown), 5.0, 35.0)
    loss_ratio = 1 - (backtest_result.win_rate / 100.0)
    loss_ratio_score = _inverse_normalize(loss_ratio, 0.25, 0.8)
    var_cvar = VarCvarService().calculate_from_equity_curve(backtest_result.equity_curve)
    sub_metrics = {
        "max_drawdown": backtest_result.max_drawdown,
        "win_rate": backtest_result.win_rate,
        "var_cvar_status": var_cvar.status,
        "var_cvar_reason": var_cvar.reason,
        "var_cvar_observation_count": var_cvar.observation_count,
    }
    if var_cvar.status == "ok" and var_cvar.var_95 is not None and var_cvar.cvar_95 is not None:
        var_score = _inverse_normalize(abs(var_cvar.var_95) * 100, 5.0, 10.0)
        cvar_score = _inverse_normalize(abs(var_cvar.cvar_95) * 100, 5.0, 15.0)
        score = (
            drawdown_score * 0.45
            + loss_ratio_score * 0.25
            + var_score * 0.2
            + cvar_score * 0.1
        )
        sub_metrics.update(
            {
                "var_95": var_cvar.var_95,
                "cvar_95": var_cvar.cvar_95,
                "var_95_score": var_score,
                "cvar_95_score": cvar_score,
            }
        )
    else:
        score = drawdown_score * 0.65 + loss_ratio_score * 0.35
    return ScoreDimension(
        key="risk_control",
        label="风险控制",
        score=_clamp_score(score),
        weight=weight,
        explanation="结合最大回撤、亏损占比与 VaR/CVaR 尾部风险，衡量策略风险承受情况。",
        sub_metrics=sub_metrics,
    )


def score_stability_dimension(backtest_result: BacktestResult, weight: float) -> ScoreDimension:
    returns = _equity_returns(backtest_result.equity_curve)
    volatility = statistics.pstdev(returns) if len(returns) >= 2 else 0.0
    volatility_score = _inverse_normalize(volatility * 100, 1.0, 8.0)
    sample_score = _normalize(float(backtest_result.total_trades), 5.0, 80.0)
    score = volatility_score * 0.55 + sample_score * 0.45
    return ScoreDimension(
        key="stability",
        label="稳定性",
        score=_clamp_score(score),
        weight=weight,
        explanation="利用资金曲线波动和样本交易数，评估结果稳定性。",
        sub_metrics={
            "equity_return_volatility_pct": round(volatility * 100, 4),
            "total_trades": backtest_result.total_trades,
        },
    )


def score_overfitting_risk_dimension(
    backtest_result: BacktestResult,
    weight: float,
    analysis: OverfittingTaskResult | None = None,
) -> ScoreDimension:
    if analysis is not None and analysis.status == "completed":
        method_metrics = {
            item.method.value: item.metrics
            for item in analysis.methods
        }
        return ScoreDimension(
            key="overfitting_risk",
            label="过拟合风险",
            score=_clamp_score(analysis.robustness_score),
            weight=weight,
            explanation=analysis.summary,
            sub_metrics={
                "status": analysis.status,
                "overall_level": analysis.overall_level.value,
                "method_metrics": method_metrics,
            },
            degraded=any(item.degraded for item in analysis.methods),
        )
    return ScoreDimension(
        key="overfitting_risk",
        label="过拟合风险",
        score=50.0,
        weight=weight,
        explanation="尚未完成 Walk-forward / OOS / Monte Carlo 检测，暂按中位分处理。",
        sub_metrics={"status": "pending_detection", "backtest_id": backtest_result.task_id},
        degraded=True,
    )


def score_executability_dimension(backtest_result: BacktestResult, weight: float) -> ScoreDimension:
    trade_count_score = _normalize(float(backtest_result.total_trades), 5.0, 80.0)
    holding_score = _normalize(_average_holding_bars(backtest_result), 2.0, 20.0)
    score = trade_count_score * 0.6 + holding_score * 0.4
    return ScoreDimension(
        key="executability",
        label="可执行性",
        score=_clamp_score(score),
        weight=weight,
        explanation="根据交易样本量和平均持仓周期，给出可执行性初评。",
        sub_metrics={
            "total_trades": backtest_result.total_trades,
            "avg_holding_bars": round(_average_holding_bars(backtest_result), 2),
        },
    )


def score_benchmark_comparison_dimension(backtest_result: BacktestResult, weight: float) -> ScoreDimension:
    return ScoreDimension(
        key="benchmark_comparison",
        label="基准对比",
        score=55.0,
        weight=weight,
        explanation="当前版本尚未接入真实 benchmark，对超额收益和跟踪误差暂作降级处理。",
        sub_metrics={"status": "benchmark_not_connected", "annual_return": backtest_result.annual_return},
        degraded=True,
    )
