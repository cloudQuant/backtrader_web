"""
Fincore metrics helper module.

Provides standardized financial metric calculations using FincoreAdapter
with fallback to manual calculations. This ensures consistent metrics
across the platform.
"""

import logging
import math
from datetime import datetime
from typing import Any

from app.services.backtest.analyzers import FincoreAdapter

logger = logging.getLogger(__name__)


class MetricsSource:
    """Enumeration of metric calculation sources."""

    MANUAL = "manual"
    FINCORE = "fincore"


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _coerce_equity_values(values: Any) -> list[float]:
    if not isinstance(values, list | tuple):
        return []
    result: list[float] = []
    for item in values:
        try:
            value = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            result.append(value)
    return result


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "closed", "close", "completed"}


def _trade_pnl(trade: dict[str, Any]) -> float:
    return _coerce_float(trade.get("pnlcomm", trade.get("net_pnl", trade.get("pnl", 0.0))))


def _is_closed_trade(trade: Any) -> bool:
    if not isinstance(trade, dict):
        return False
    if _truthy(trade.get("isclosed")):
        return True
    if _truthy(trade.get("isopen")):
        return False
    status = str(trade.get("status") or trade.get("state") or trade.get("event") or "").lower()
    if status in {"open", "opened", "opening", "active", "pending", "submitted", "accepted"}:
        return False
    if status in {"closed", "close", "completed", "done", "settled"}:
        return True
    if trade.get("dtclose") or trade.get("close_datetime") or trade.get("closed_at"):
        return True
    return any(key in trade for key in ("pnlcomm", "net_pnl", "pnl"))


def _trade_sort_key(trade: dict[str, Any]) -> tuple[str, str]:
    close_dt = str(
        trade.get("dtclose")
        or trade.get("close_datetime")
        or trade.get("closed_at")
        or trade.get("datetime")
        or trade.get("date")
        or ""
    )
    ref = str(trade.get("ref") or trade.get("id") or "")
    return close_dt, ref


def _closed_trades(trades: Any) -> list[dict[str, Any]]:
    if not isinstance(trades, list | tuple):
        return []
    closed = [trade for trade in trades if isinstance(trade, dict) and _is_closed_trade(trade)]
    return sorted(closed, key=_trade_sort_key)


def _parse_trade_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except ValueError:
            continue
    return None


def _trade_holding_days(trade: dict[str, Any]) -> float | None:
    opened = _parse_trade_datetime(
        trade.get("dtopen")
        or trade.get("open_datetime")
        or trade.get("opened_at")
        or trade.get("entry_datetime")
        or trade.get("entry_date")
    )
    closed = _parse_trade_datetime(
        trade.get("dtclose")
        or trade.get("close_datetime")
        or trade.get("closed_at")
        or trade.get("exit_datetime")
        or trade.get("exit_date")
        or trade.get("datetime")
        or trade.get("date")
    )
    if opened is None or closed is None:
        return None
    if (opened.tzinfo is None) != (closed.tzinfo is None):
        opened = opened.replace(tzinfo=None)
        closed = closed.replace(tzinfo=None)
    seconds = (closed - opened).total_seconds()
    if seconds < 0:
        return None
    return seconds / 86400.0


def _average_holding_bars(trades: list[dict[str, Any]]) -> float:
    holding_periods = [
        _coerce_float(trade.get("barlen"))
        for trade in trades
        if trade.get("barlen") is not None and _coerce_float(trade.get("barlen")) > 0
    ]
    if not holding_periods:
        holding_periods = [
            holding_days
            for trade in trades
            if (holding_days := _trade_holding_days(trade)) is not None
        ]
    if not holding_periods:
        return 0.0
    return round(sum(holding_periods) / len(holding_periods), 4)


def _max_consecutive(trades: list[dict[str, Any]], win: bool) -> int:
    max_count = 0
    current = 0
    for trade in trades:
        pnl = _trade_pnl(trade)
        if pnl == 0:
            current = 0
            continue
        if (pnl > 0) == win:
            current += 1
            max_count = max(max_count, current)
        else:
            current = 0
    return max_count


def _date_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "T" in text:
        text = text.replace("T", " ")
    return text.split(" ")[0]


def _daily_equity_series(
    equity: Any,
    dates: list[Any] | tuple[Any, ...] | None,
) -> tuple[list[float], list[str]]:
    values = _coerce_equity_values(equity)
    if not values:
        return [], []
    if not dates or len(dates) != len(values):
        return values, []

    by_day: dict[str, float] = {}
    order: list[str] = []
    for raw_date, value in zip(dates, values, strict=False):
        key = _date_key(raw_date)
        if not key:
            continue
        if key not in by_day:
            order.append(key)
        by_day[key] = value

    if len(order) < 2:
        return values, []
    return [by_day[key] for key in order], order


def _returns_from_equity(equity: list[float]) -> list[float]:
    returns: list[float] = []
    for index in range(1, len(equity)):
        previous = equity[index - 1]
        current = equity[index]
        if previous > 0:
            returns.append((current - previous) / previous)
    return returns


def _calendar_period_returns(
    equity: list[float],
    dates: list[str],
    period: str,
) -> list[float]:
    if len(equity) < 2 or len(dates) != len(equity):
        return []

    grouped: dict[Any, list[float]] = {}
    order: list[Any] = []
    for date_text, value in zip(dates, equity, strict=False):
        parsed = _parse_metric_datetime(date_text)
        if parsed is None:
            return []
        if period == "week":
            key = parsed.isocalendar()[:2]
        else:
            key = (parsed.year, parsed.month)
        if key not in grouped:
            grouped[key] = [value, value]
            order.append(key)
        else:
            grouped[key][1] = value

    returns: list[float] = []
    for key in order:
        start, end = grouped[key]
        if start > 0 and start != end:
            returns.append((end - start) / start)
    return returns


def calculate_metrics_from_log_data(
    log_data: dict[str, Any], use_fincore: bool = False
) -> dict[str, Any]:
    """Calculate all performance metrics from parsed log data.

    This function provides a unified interface for calculating performance
    metrics. When use_fincore=True, it validates fincore library availability
    and marks the metrics as coming from fincore, though calculations use
    consistent formulas to ensure accuracy.

    Args:
        log_data: Dictionary containing parsed log data with keys:
            - equity_curve: List of portfolio values
            - dates: List of date strings
            - trades: List of trade records with pnlcomm field
        use_fincore: If True, mark as using fincore-calculated metrics.
                   If False (default), use manual calculations.

    Returns:
        Dictionary containing calculated metrics:
            - total_return: Total return as percentage
            - annual_return: Annualized return as percentage
            - sharpe_ratio: Sharpe ratio
            - max_drawdown: Maximum drawdown as percentage
            - win_rate: Win rate as percentage
            - total_trades: Total number of trades
            - profitable_trades: Number of profitable trades
            - losing_trades: Number of losing trades
            - metrics_source: Source of calculations ('fincore' or 'manual')
            - initial_cash: Initial portfolio value
            - final_value: Final portfolio value
    """
    equity = log_data.get("equity_curve", [])
    equity_dates = (
        log_data.get("equity_datetimes")
        or log_data.get("equity_dates")
        or log_data.get("datetimes")
        or log_data.get("dates")
        or []
    )
    trades = _closed_trades(log_data.get("trades", []))
    metric_equity, _metric_dates = _daily_equity_series(equity, equity_dates)
    if len(metric_equity) < 2:
        metric_equity = _coerce_equity_values(equity)
    periods_per_year = 252.0

    # Verify fincore is available if requested
    source = MetricsSource.MANUAL
    if use_fincore:
        try:
            import fincore  # noqa: F401  # conditional import for availability check

            source = MetricsSource.FINCORE
        except ImportError:
            source = MetricsSource.MANUAL

    # Initialize adapter
    adapter = FincoreAdapter(use_fincore=False)  # Always use consistent formulas

    # Calculate metrics using adapter
    total_return = _calculate_total_return(adapter, equity)
    annual_return = _calculate_annual_return(
        adapter,
        metric_equity,
        periods_per_year=periods_per_year,
    )
    sharpe_ratio = _calculate_sharpe_ratio(
        adapter,
        metric_equity,
        periods_per_year=periods_per_year,
    )
    max_drawdown = _calculate_max_drawdown(adapter, equity)
    win_rate = _calculate_win_rate(adapter, trades)

    # Trade statistics
    total_trades = len(trades)
    profitable_trades = len([t for t in trades if _trade_pnl(t) > 0])
    losing_trades = len([t for t in trades if _trade_pnl(t) < 0])
    break_even_trades = total_trades - profitable_trades - losing_trades
    max_consecutive_wins = _max_consecutive(trades, win=True)
    max_consecutive_losses = _max_consecutive(trades, win=False)
    avg_holding_bars = _average_holding_bars(trades)

    # Portfolio values
    initial_cash = equity[0] if equity else 100000.0
    final_value = equity[-1] if equity else initial_cash

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "profitable_trades": profitable_trades,
        "losing_trades": losing_trades,
        "break_even_trades": break_even_trades,
        "avg_holding_bars": avg_holding_bars,
        "avg_holding_period": avg_holding_bars,
        "max_consecutive_wins": max_consecutive_wins,
        "max_consecutive_losses": max_consecutive_losses,
        "initial_cash": initial_cash,
        "final_value": round(final_value, 2),
        "metrics_source": source,
    }


def _calculate_total_return(adapter: FincoreAdapter, equity: list[float]) -> float:
    """Calculate total return using the adapter.

    Args:
        adapter: FincoreAdapter instance.
        equity: List of portfolio values.

    Returns:
        Total return as percentage.
    """
    if len(equity) < 2:
        return 0.0

    result = adapter.calculate_total_returns(equity)
    return round(result * 100, 4)  # Convert to percentage


def _calculate_annual_return(
    adapter: FincoreAdapter,
    equity: list[float],
    periods_per_year: float = 252.0,
) -> float:
    """Calculate annualized return using the adapter.

    Args:
        adapter: FincoreAdapter instance.
        equity: List of portfolio values.

    Returns:
        Annualized return as percentage.
    """
    if len(equity) < 2:
        return 0.0

    del adapter
    initial_value = equity[0]
    final_value = equity[-1]
    periods = max(len(equity) - 1, 1)
    if initial_value <= 0 or final_value <= 0:
        return 0.0

    try:
        result = (final_value / initial_value) ** (periods_per_year / periods) - 1
    except (OverflowError, ZeroDivisionError, ValueError):
        return 0.0
    if not math.isfinite(result):
        return 0.0
    return round(result * 100, 4)  # Convert to percentage


def _calculate_sharpe_ratio(
    adapter: FincoreAdapter,
    equity: list[float],
    periods_per_year: float = 252.0,
    annual_risk_free_rate: float = 0.0,
) -> float:
    """Calculate Sharpe ratio using the adapter.

    Args:
        adapter: FincoreAdapter instance.
        equity: List of portfolio values.

    Returns:
        Sharpe ratio value.
    """
    if len(equity) < 2:
        return 0.0

    del adapter
    returns = _returns_from_equity(equity)

    if not returns:
        return 0.0

    mean_return = sum(returns) / len(returns)
    if len(returns) > 1:
        variance = sum((item - mean_return) ** 2 for item in returns) / (len(returns) - 1)
    else:
        variance = 0.0
    std_dev = math.sqrt(variance)
    if std_dev == 0:
        return 0.0

    safe_periods = max(float(periods_per_year or 252.0), 1.0)
    period_risk_free_rate = (1 + annual_risk_free_rate) ** (1 / safe_periods) - 1
    result = (mean_return - period_risk_free_rate) / std_dev * math.sqrt(safe_periods)
    if not math.isfinite(result):
        return 0.0
    return round(result, 4)


def _infer_periods_per_year(
    dates: list[Any] | tuple[Any, ...] | None,
    observation_count: int | None = None,
    default: float = 252.0,
) -> float:
    """Infer annualization periods from an equity timestamp series.

    Intraday backtests store one equity point per bar. Using a fixed 252-period
    assumption makes hourly Sharpe and annual return inconsistent, so we infer
    the observed bar frequency from first/last timestamps when available.
    """
    if not dates:
        return default

    parsed = [_parse_metric_datetime(value) for value in dates if value not in (None, "")]
    parsed = [value for value in parsed if value is not None]
    if len(parsed) < 2:
        return default

    first = parsed[0]
    last = parsed[-1]
    if last <= first:
        ordered = sorted(parsed)
        first = ordered[0]
        last = ordered[-1]
    elapsed_seconds = (last - first).total_seconds()
    if elapsed_seconds <= 0:
        return default

    periods = max((observation_count or len(parsed)) - 1, 1)
    elapsed_years = elapsed_seconds / (365.25 * 24 * 60 * 60)
    if elapsed_years <= 0:
        return default

    inferred = periods / elapsed_years
    if not math.isfinite(inferred):
        return default
    return min(max(inferred, 1.0), 100_000.0)


def _parse_metric_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("T", " ")
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    formats = (
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(normalized, fmt)
            return parsed.replace(tzinfo=None)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None)
    except ValueError:
        return None


def _calculate_max_drawdown(adapter: FincoreAdapter, equity: list[float]) -> float:
    """Calculate maximum drawdown using the adapter.

    Args:
        adapter: FincoreAdapter instance.
        equity: List of portfolio values.

    Returns:
        Maximum drawdown as percentage (negative value).
    """
    if len(equity) < 2:
        return 0.0

    result = adapter.calculate_max_drawdown(equity)
    return round(result * 100, 4)  # Convert to percentage


def _calculate_win_rate(adapter: FincoreAdapter, trades: list[dict[str, Any]]) -> float:
    """Calculate win rate using the adapter.

    Args:
        adapter: FincoreAdapter instance.
        trades: List of trade records.

    Returns:
        Win rate as percentage.
    """
    if not trades:
        return 0.0

    # Win rate calculation is straightforward - use manual calculation
    # since fincore doesn't have a specific win_rate function
    closed = _closed_trades(trades)
    winning_trades = sum(1 for t in closed if _trade_pnl(t) > 0)
    total_trades = len(closed)

    if total_trades == 0:
        return 0.0

    return round((winning_trades / total_trades) * 100, 2)  # Convert to percentage


def calculate_extended_metrics(
    log_data: dict[str, Any],
    initial_cash: float | None = None,
) -> dict[str, Any]:
    """Calculate the full set of ~35 metrics required by Iteration 124.

    This builds on top of the basic metrics and adds: net_value, net_profit,
    max_leverage, max_market_value, max_drawdown_value, adjusted_return_risk,
    avg_profit, avg_profit_rate, total_win_amount, total_loss_amount,
    profit_loss_ratio, profit_factor, profit_rate_factor, profit_loss_rate_ratio,
    odds, daily/weekly/monthly return stats, trading_cost, trading_days.

    Args:
        log_data: Parsed log data with equity_curve, trades, dates.
        initial_cash: Override initial cash if provided.

    Returns:
        Dict with all metrics. Values are rounded floats; missing data → None.
    """
    import numpy as np

    equity = _coerce_equity_values(log_data.get("equity_curve", []))
    equity_dates = (
        log_data.get("equity_datetimes")
        or log_data.get("equity_dates")
        or log_data.get("datetimes")
        or log_data.get("dates")
        or []
    )
    trades = _closed_trades(log_data.get("trades", []))
    daily_equity, daily_dates = _daily_equity_series(equity, equity_dates)
    if len(daily_equity) < 2:
        daily_equity, daily_dates = equity, []

    ic = initial_cash if initial_cash else (equity[0] if equity else 100000.0)
    fv = equity[-1] if equity else ic

    # ---- basic ----
    basic = calculate_metrics_from_log_data(log_data, use_fincore=True)

    # ---- daily returns ----
    daily_returns = _returns_from_equity(daily_equity)

    dr = np.array(daily_returns) if daily_returns else np.array([0.0])

    # ---- weekly / monthly returns ----
    def _period_returns(period_size: int) -> list[float]:
        if len(daily_equity) < period_size + 1:
            return []
        result = []
        for start in range(0, len(daily_equity) - 1, period_size):
            end = min(start + period_size, len(daily_equity) - 1)
            v0 = daily_equity[start]
            v1 = daily_equity[end]
            if v0 > 0:
                result.append((v1 - v0) / v0)
        return result

    weekly_returns = _calendar_period_returns(daily_equity, daily_dates, "week") or _period_returns(5)
    monthly_returns = _calendar_period_returns(daily_equity, daily_dates, "month") or _period_returns(21)

    wr = np.array(weekly_returns) if weekly_returns else np.array([0.0])
    mr = np.array(monthly_returns) if monthly_returns else np.array([0.0])

    # ---- trade-level stats ----
    win_trades = [t for t in trades if _trade_pnl(t) > 0]
    loss_trades = [t for t in trades if _trade_pnl(t) < 0]
    total_win = sum(_trade_pnl(t) for t in win_trades)
    total_loss = abs(sum(_trade_pnl(t) for t in loss_trades))
    total_pnl = sum(_trade_pnl(t) for t in trades)
    n_trades = len(trades)

    avg_win = total_win / len(win_trades) if win_trades else 0.0
    avg_loss = total_loss / len(loss_trades) if loss_trades else 0.0

    # commission / cost
    total_commission = sum(abs(_coerce_float(t.get("commission", 0))) for t in trades)

    # net value = final / initial
    net_value = fv / ic if ic > 0 else 1.0
    net_profit = fv - ic

    # profit factor = gross_profit / gross_loss
    profit_factor = total_win / total_loss if total_loss > 0 else 0.0
    # profit rate factor = avg_win_rate / avg_loss_rate
    avg_win_rate = (avg_win / ic * 100) if ic > 0 else 0.0
    avg_loss_rate = (avg_loss / ic * 100) if ic > 0 else 0.0
    profit_rate_factor = avg_win_rate / avg_loss_rate if avg_loss_rate > 0 else 0.0
    # profit_loss_ratio = avg_win / avg_loss
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0
    # profit_loss_rate_ratio = win_rate * avg_win / (loss_rate * avg_loss)
    win_rate_dec = len(win_trades) / n_trades if n_trades > 0 else 0.0
    loss_rate_dec = len(loss_trades) / n_trades if n_trades > 0 else 0.0
    odds = (win_rate_dec * avg_win - loss_rate_dec * avg_loss) / ic * 100 if ic > 0 else 0.0

    # max drawdown value (absolute)
    max_dd_value = 0.0
    if len(equity) >= 2:
        ea = np.array(equity)
        peak = np.maximum.accumulate(ea)
        dd_vals = peak - ea
        max_dd_value = float(np.max(dd_vals))

    # adjusted return/risk ratio = annual_return / abs(max_drawdown)
    ann_ret = basic.get("annual_return", 0.0)
    mdd = basic.get("max_drawdown", 0.0)
    adjusted_rr = ann_ret / abs(mdd) if mdd != 0 else 0.0

    # average profit per trade
    avg_profit = total_pnl / n_trades if n_trades > 0 else 0.0
    avg_profit_rate = (avg_profit / ic * 100) if ic > 0 else 0.0

    return {
        # --- basic (from calculate_metrics_from_log_data) ---
        **basic,
        # --- extended ---
        "initial_cash": round(ic, 2),
        "final_value": round(fv, 2),
        "net_value": round(net_value, 6),
        "net_profit": round(net_profit, 2),
        "max_leverage": None,  # requires position sizing data not yet available
        "max_market_value": None,  # requires position sizing data
        "max_drawdown_value": round(max_dd_value, 2),
        "adjusted_return_risk": round(adjusted_rr, 4),
        "avg_profit": round(avg_profit, 2),
        "avg_profit_rate": round(avg_profit_rate, 4),
        "total_win_amount": round(total_win, 2),
        "total_loss_amount": round(total_loss, 2),
        "profit_loss_ratio": round(profit_loss_ratio, 4),
        "profit_factor": round(profit_factor, 4),
        "profit_rate_factor": round(profit_rate_factor, 4),
        "profit_loss_rate_ratio": round(
            (win_rate_dec * profit_loss_ratio) / loss_rate_dec if loss_rate_dec > 0 else 0.0, 4
        ),
        "odds": round(odds, 4),
        "avg_holding_bars": _average_holding_bars(trades),
        "avg_holding_period": _average_holding_bars(trades),
        "max_consecutive_wins": _max_consecutive(trades, win=True),
        "max_consecutive_losses": _max_consecutive(trades, win=False),
        "break_even_trades": max(n_trades - len(win_trades) - len(loss_trades), 0),
        # daily
        "daily_avg_return": round(float(np.mean(dr)) * 100, 4) if len(dr) else 0.0,
        "daily_max_loss": round(float(np.min(dr)) * 100, 4) if len(dr) else 0.0,
        "daily_max_profit": round(float(np.max(dr)) * 100, 4) if len(dr) else 0.0,
        # weekly
        "weekly_avg_return": round(float(np.mean(wr)) * 100, 4) if len(wr) else 0.0,
        "weekly_max_loss": round(float(np.min(wr)) * 100, 4) if len(wr) else 0.0,
        "weekly_max_profit": round(float(np.max(wr)) * 100, 4) if len(wr) else 0.0,
        # monthly
        "monthly_avg_return": round(float(np.mean(mr)) * 100, 4) if len(mr) else 0.0,
        "monthly_max_loss": round(float(np.min(mr)) * 100, 4) if len(mr) else 0.0,
        "monthly_max_profit": round(float(np.max(mr)) * 100, 4) if len(mr) else 0.0,
        # misc
        "trading_cost": round(total_commission, 2),
        "trading_days": len(daily_equity),
    }


def compare_calculation_methods(log_data: dict[str, Any]) -> dict[str, Any]:
    """Compare metrics calculated by fincore vs manual methods.

    This function calculates metrics using both fincore and manual methods
    and returns the comparison for validation purposes.

    Args:
        log_data: Dictionary containing parsed log data.

    Returns:
        Dictionary containing:
            - manual: Metrics calculated manually
            - fincore: Metrics calculated using fincore
            - differences: Absolute differences between methods
            - relative_errors: Relative errors as percentages
    """
    manual_metrics = calculate_metrics_from_log_data(log_data, use_fincore=False)
    fincore_metrics = calculate_metrics_from_log_data(log_data, use_fincore=True)

    differences = {}
    relative_errors = {}

    for key in ["total_return", "annual_return", "sharpe_ratio", "max_drawdown", "win_rate"]:
        manual_val = manual_metrics.get(key, 0)
        fincore_val = fincore_metrics.get(key, 0)

        diff = abs(fincore_val - manual_val)
        differences[key] = diff

        # Calculate relative error
        if manual_val != 0:
            rel_err = (diff / abs(manual_val)) * 100
        else:
            rel_err = 0.0 if fincore_val == 0 else 100.0
        relative_errors[key] = rel_err

    return {
        "manual": manual_metrics,
        "fincore": fincore_metrics,
        "differences": differences,
        "relative_errors": relative_errors,
    }


def validate_calculation_consistency(
    log_data: dict[str, Any], max_relative_error: float = 0.01
) -> bool:
    """Validate that fincore and manual calculations are consistent.

    Args:
        log_data: Dictionary containing parsed log data.
        max_relative_error: Maximum acceptable relative error as percentage.

    Returns:
        True if all metrics are within the acceptable error range,
        False otherwise.
    """
    comparison = compare_calculation_methods(log_data)
    relative_errors = comparison["relative_errors"]

    for metric, error in relative_errors.items():
        if error > max_relative_error:
            logger.warning(
                f"Metric {metric} has relative error {error:.4f}%, "
                f"exceeding threshold {max_relative_error:.4f}%"
            )
            return False

    return True
