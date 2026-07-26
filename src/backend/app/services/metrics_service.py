"""Unified metrics service for backtest, workspace, and AI research results."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from app.services.fincore_metrics_helper import calculate_metrics_from_log_data

_STANDARD_KEYS = (
    "total_return",
    "annual_return",
    "sharpe_ratio",
    "max_drawdown",
    "win_rate",
    "total_trades",
    "profitable_trades",
    "losing_trades",
    "break_even_trades",
    "avg_holding_bars",
    "avg_holding_period",
    "max_consecutive_wins",
    "max_consecutive_losses",
    "profit_loss_ratio",
    "initial_cash",
    "final_value",
    "metrics_source",
)


class MetricsService:
    """Single entry point for normalized performance metrics."""

    def calculate_from_log_data(
        self,
        log_data: dict[str, Any],
        *,
        use_fincore: bool = True,
    ) -> dict[str, Any]:
        """Calculate and normalize metrics from parsed backtest log data."""
        metrics = calculate_metrics_from_log_data(log_data, use_fincore=use_fincore)
        return self.normalize(metrics, trades=log_data.get("trades", []))

    def normalize(
        self,
        metrics: dict[str, Any],
        *,
        trades: Any = None,
    ) -> dict[str, Any]:
        """Return the canonical metric field set used by all result pages."""
        normalized = {key: metrics.get(key) for key in _STANDARD_KEYS if key in metrics}
        normalized.setdefault("total_return", _float(metrics.get("total_return"), 0.0))
        normalized.setdefault("annual_return", _float(metrics.get("annual_return"), 0.0))
        normalized.setdefault("sharpe_ratio", _float(metrics.get("sharpe_ratio"), 0.0))
        normalized.setdefault("max_drawdown", _float(metrics.get("max_drawdown"), 0.0))
        normalized.setdefault("win_rate", _float(metrics.get("win_rate"), 0.0))
        normalized.setdefault("total_trades", _int(metrics.get("total_trades"), 0))
        normalized.setdefault("profitable_trades", _int(metrics.get("profitable_trades"), 0))
        normalized.setdefault("losing_trades", _int(metrics.get("losing_trades"), 0))
        normalized.setdefault("break_even_trades", _int(metrics.get("break_even_trades"), 0))
        normalized.setdefault("avg_holding_bars", _float(metrics.get("avg_holding_bars"), 0.0))
        normalized.setdefault(
            "avg_holding_period",
            _float(metrics.get("avg_holding_period") or normalized["avg_holding_bars"], 0.0),
        )
        normalized.setdefault(
            "max_consecutive_wins",
            _int(metrics.get("max_consecutive_wins"), 0),
        )
        normalized.setdefault(
            "max_consecutive_losses",
            _int(metrics.get("max_consecutive_losses"), 0),
        )
        normalized.setdefault(
            "profit_loss_ratio",
            _float(metrics.get("profit_loss_ratio"), 0.0),
        )
        if trades is not None:
            normalized["profit_loss_ratio"] = _profit_loss_ratio(trades)
        normalized.setdefault("initial_cash", _float(metrics.get("initial_cash"), 100000.0))
        normalized.setdefault(
            "final_value",
            _float(metrics.get("final_value"), normalized["initial_cash"]),
        )
        normalized.setdefault("metrics_source", str(metrics.get("metrics_source") or "manual"))
        for key in (
            "total_return",
            "annual_return",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "avg_holding_bars",
            "avg_holding_period",
            "profit_loss_ratio",
            "initial_cash",
            "final_value",
        ):
            normalized[key] = _float(normalized.get(key), 0.0)
        for key in (
            "total_trades",
            "profitable_trades",
            "losing_trades",
            "break_even_trades",
            "max_consecutive_wins",
            "max_consecutive_losses",
        ):
            normalized[key] = _int(normalized.get(key), 0)
        normalized["metrics_source"] = str(normalized.get("metrics_source") or "manual")
        return {key: _json_safe(value) for key, value in normalized.items() if value is not None}

    def result_summary(
        self,
        *,
        task_id: str,
        strategy_id: str,
        symbol: str,
        status: str,
        metrics: dict[str, Any],
        data_precheck: dict[str, Any] | None = None,
        robustness: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a compact cached summary for fast result first paint."""
        return {
            "task_id": task_id,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "status": status,
            "metrics": {
                key: metrics.get(key)
                for key in (
                    "total_return",
                    "annual_return",
                    "sharpe_ratio",
                    "max_drawdown",
                    "win_rate",
                    "total_trades",
                    "profit_loss_ratio",
                    "max_consecutive_wins",
                    "max_consecutive_losses",
                    "avg_holding_bars",
                )
            },
            "data_precheck": data_precheck or {},
            "robustness": robustness or {},
        }


def _profit_loss_ratio(trades: Any) -> float:
    if not isinstance(trades, list | tuple):
        return 0.0
    profits: list[float] = []
    losses: list[float] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        pnl = _float(trade.get("pnlcomm", trade.get("net_pnl", trade.get("pnl"))), 0.0)
        if pnl > 0:
            profits.append(pnl)
        elif pnl < 0:
            losses.append(abs(pnl))
    if not profits or not losses:
        return 0.0
    return round((sum(profits) / len(profits)) / (sum(losses) / len(losses)), 6)


def _float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0
    return value


@lru_cache
def get_metrics_service() -> MetricsService:
    return MetricsService()
