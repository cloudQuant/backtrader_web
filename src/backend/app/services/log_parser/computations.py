"""Higher-level computations used by log parsing.

These helpers are *not* file readers — they consume already-parsed log rows
and project them onto an equity / cash / drawdown curve, or look up the
strategy's configured initial cash.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.services.log_parser.normalize import normalize_dt_text, safe_float

logger = logging.getLogger(__name__)


def load_strategy_config(strategy_dir: Path) -> dict[str, Any]:
    """Load ``config.yaml`` from a strategy directory; ``{}`` on any error."""
    config_path = strategy_dir / "config.yaml"
    if not config_path.is_file():
        return {}
    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, Exception) as e:  # noqa: BLE001 - tolerate yaml errors too
        logger.warning("Failed to load strategy config from %s: %s", config_path, e)
        return {}


def initial_cash_for_strategy(
    strategy_dir: Path, run_info: dict[str, Any] | None = None
) -> float:
    """Resolve the initial cash for a strategy run.

    Order of precedence: ``run_info`` keys (``initial_cash`` /
    ``starting_cash`` / ``initial_capital``) → ``config.yaml`` (``simulate``
    or ``backtest`` section) → fallback ``100_000.0``.
    """
    run_info = run_info or {}
    for key in ("initial_cash", "starting_cash", "initial_capital"):
        value = run_info.get(key)
        if value is not None:
            cash = safe_float(value, 0.0)
            if cash > 0:
                return cash

    config = load_strategy_config(strategy_dir)
    for section in ("simulate", "backtest"):
        value = (config.get(section) or {}).get("initial_cash")
        cash = safe_float(value, 0.0)
        if cash > 0:
            return cash
    return 100000.0


def synthesize_value_curve(
    strategy_dir: Path,
    kline_data: dict[str, Any],
    position_rows: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    run_info: dict[str, Any],
) -> dict[str, Any]:
    """Reconstruct an equity/cash/drawdown curve when ``value.log`` is empty.

    Used by simulate/workspace runs that only emit pipe / json position and
    trade logs without the dense daily ``value.log`` snapshots emitted by the
    legacy backtester.
    """
    initial_cash = initial_cash_for_strategy(strategy_dir, run_info)
    realized_by_date: dict[str, float] = {}
    for trade in trades:
        close_dt = normalize_dt_text(trade.get("dtclose") or trade.get("datetime"))
        if not close_dt:
            continue
        realized_by_date[close_dt] = realized_by_date.get(close_dt, 0.0) + safe_float(
            trade.get("pnlcomm", trade.get("pnl", 0.0)),
            0.0,
        )

    position_by_date: dict[str, dict[str, Any]] = {}
    for row in position_rows:
        dt = normalize_dt_text(row.get("datetime") or row.get("dt"))
        if dt:
            position_by_date[dt] = row

    ordered_dates: list[str] = []
    seen_dates: set[str] = set()
    for dt in kline_data.get("dates", []):
        if dt and dt not in seen_dates:
            ordered_dates.append(dt)
            seen_dates.add(dt)
    for dt in sorted(position_by_date):
        if dt not in seen_dates:
            ordered_dates.append(dt)
            seen_dates.add(dt)
    for dt in sorted(realized_by_date):
        if dt not in seen_dates:
            ordered_dates.append(dt)
            seen_dates.add(dt)

    if not ordered_dates:
        return {"dates": [], "equity_curve": [], "cash_curve": [], "drawdown_curve": []}

    realized = 0.0
    equity: list[float] = []
    cash_curve: list[float] = []
    peak = initial_cash
    drawdown_curve: list[float] = []
    for dt in ordered_dates:
        realized += realized_by_date.get(dt, 0.0)
        pos = position_by_date.get(dt, {})
        size = safe_float(pos.get("size", 0.0), 0.0)
        avg_price = safe_float(pos.get("price", 0.0), 0.0)
        market_value = safe_float(pos.get("value", pos.get("market_value", 0.0)), 0.0)
        cost_basis = size * avg_price
        unrealized = market_value - cost_basis
        total_assets = initial_cash + realized + unrealized
        cash_value = total_assets - market_value
        equity.append(round(total_assets, 4))
        cash_curve.append(round(cash_value, 4))
        if total_assets > peak:
            peak = total_assets
        dd = ((peak - total_assets) / peak * 100) if peak > 0 else 0.0
        drawdown_curve.append(round(dd, 4))

    return {
        "dates": ordered_dates,
        "equity_curve": equity,
        "cash_curve": cash_curve,
        "drawdown_curve": drawdown_curve,
    }
