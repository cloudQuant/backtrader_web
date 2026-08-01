"""Honest, action-specific performance summaries for stored signals."""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from typing import Any

from app.models.stock_signal import StockSignalPrediction


def _return_for_horizon(record: StockSignalPrediction, horizon: int) -> float | None:
    return getattr(record, f"horizon_{horizon}d_return", None)


def _excess_for_horizon(record: StockSignalPrediction, horizon: int) -> float | None:
    return getattr(record, f"excess_{horizon}d_return", None)


def _success(record: StockSignalPrediction, horizon: int) -> bool | None:
    value = _return_for_horizon(record, horizon)
    if value is None:
        return None
    if record.signal_action == "BUY":
        if horizon == 20 and record.buy_is_correct_20d is not None:
            return record.buy_is_correct_20d
        try:
            threshold = float((record.policy_snapshot_json or {}).get("buy_success_threshold_bps", 0.0))
        except (TypeError, ValueError):
            threshold = 0.0
        return value > threshold / 10000.0
    if record.signal_action == "SELL":
        if horizon == 20 and record.sell_is_correct_20d is not None:
            return record.sell_is_correct_20d
        try:
            threshold = float((record.policy_snapshot_json or {}).get("sell_success_threshold_bps", 0.0))
        except (TypeError, ValueError):
            threshold = 0.0
        return value < -threshold / 10000.0
    return None


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _action_summary(records: list[StockSignalPrediction], action: str, horizon: int) -> dict[str, Any]:
    action_records = [record for record in records if record.signal_action == action]
    scorable = [record for record in action_records if _success(record, horizon) is not None]
    successes = [record for record in scorable if _success(record, horizon) is True]
    returns = [value for record in scorable if (value := _return_for_horizon(record, horizon)) is not None]
    excess = [value for record in scorable if (value := _excess_for_horizon(record, horizon)) is not None]
    return {
        "action": action,
        "generated_count": len(action_records),
        "scorable_count": len(scorable),
        "success_count": len(successes),
        "success_rate": len(successes) / len(scorable) if scorable else None,
        "average_return": _mean(returns),
        "median_return": _median(returns),
        "average_excess_return": _mean(excess),
    }


def _confidence_bins(records: list[StockSignalPrediction], horizon: int) -> list[dict[str, Any]]:
    bins = ((0.0, 0.55, "低"), (0.55, 0.7, "中"), (0.7, 1.01, "高"))
    payload: list[dict[str, Any]] = []
    actioned = [record for record in records if record.signal_action in {"BUY", "SELL"}]
    for lower, upper, label in bins:
        selected = [
            record
            for record in actioned
            if lower <= float(record.confidence_score or 0.0) < upper and _success(record, horizon) is not None
        ]
        successes = [record for record in selected if _success(record, horizon) is True]
        payload.append(
            {
                "label": label,
                "lower": lower,
                "upper": min(upper, 1.0),
                "scorable_count": len(selected),
                "success_rate": len(successes) / len(selected) if selected else None,
            }
        )
    return payload


def build_performance_summary(
    records: Iterable[StockSignalPrediction], *, symbol: str, horizon: int = 20
) -> dict[str, Any]:
    """Return explicit denominators; `WATCH` never inflates action success rate."""
    items = list(records)
    action_summaries = [_action_summary(items, action, horizon) for action in ("BUY", "SELL", "WATCH")]
    actioned = [item for item in action_summaries if item["action"] in {"BUY", "SELL"}]
    actioned_generated = sum(item["generated_count"] for item in actioned)
    actioned_scorable = sum(item["scorable_count"] for item in actioned)
    actioned_successes = sum(item["success_count"] for item in actioned)
    eligible_count = sum(1 for item in items if item.eligibility_status == "eligible")
    mature_count = sum(1 for item in items if item.outcome_status == "scored")
    return {
        "symbol": symbol,
        "horizon": horizon,
        "actioned_generated_count": actioned_generated,
        "actioned_scorable_count": actioned_scorable,
        "actioned_success_count": actioned_successes,
        "actioned_success_rate": actioned_successes / actioned_scorable if actioned_scorable else None,
        "coverage_rate": eligible_count / len(items) if items else None,
        "maturity_rate": mature_count / len(items) if items else None,
        "actions": action_summaries,
        "confidence_bins": _confidence_bins(items, horizon),
    }
