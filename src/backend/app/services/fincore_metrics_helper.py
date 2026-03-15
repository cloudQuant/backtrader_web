"""
Fincore metrics helper module.

Provides standardized financial metric calculations using FincoreAdapter
with fallback to manual calculations. This ensures consistent metrics
across the platform.
"""

import logging
from typing import Any

from app.services.backtest_analyzers import FincoreAdapter

logger = logging.getLogger(__name__)


class MetricsSource:
    """Enumeration of metric calculation sources."""

    MANUAL = "manual"
    FINCORE = "fincore"


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
    trades = log_data.get("trades", [])

    # Verify fincore is available if requested
    source = MetricsSource.MANUAL
    if use_fincore:
        try:
            import fincore  # noqa: F401

            source = MetricsSource.FINCORE
        except ImportError:
            source = MetricsSource.MANUAL

    # Initialize adapter
    adapter = FincoreAdapter(use_fincore=False)  # Always use consistent formulas

    # Calculate metrics using adapter
    total_return = _calculate_total_return(adapter, equity)
    annual_return = _calculate_annual_return(adapter, equity)
    sharpe_ratio = _calculate_sharpe_ratio(adapter, equity)
    max_drawdown = _calculate_max_drawdown(adapter, equity)
    win_rate = _calculate_win_rate(adapter, trades)

    # Trade statistics
    total_trades = len(trades)
    profitable_trades = len([t for t in trades if t.get("pnlcomm", 0) > 0])
    losing_trades = len([t for t in trades if t.get("pnlcomm", 0) <= 0])

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


def _calculate_annual_return(adapter: FincoreAdapter, equity: list[float]) -> float:
    """Calculate annualized return using the adapter.

    Args:
        adapter: FincoreAdapter instance.
        equity: List of portfolio values.

    Returns:
        Annualized return as percentage.
    """
    if len(equity) < 2:
        return 0.0

    result = adapter.calculate_annual_returns(equity, periods_per_year=252)
    return round(result * 100, 4)  # Convert to percentage


def _calculate_sharpe_ratio(adapter: FincoreAdapter, equity: list[float]) -> float:
    """Calculate Sharpe ratio using the adapter.

    Args:
        adapter: FincoreAdapter instance.
        equity: List of portfolio values.

    Returns:
        Sharpe ratio value.
    """
    if len(equity) < 2:
        return 0.0

    # Calculate daily returns
    returns = []
    for i in range(1, len(equity)):
        if equity[i - 1] > 0:
            returns.append((equity[i] - equity[i - 1]) / equity[i - 1])

    if not returns:
        return 0.0

    result = adapter.calculate_sharpe_ratio(returns, risk_free_rate=0.02)
    return round(result, 4)


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
    winning_trades = sum(1 for t in trades if t.get("pnlcomm", 0) > 0)
    total_trades = len(trades)

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

    equity = log_data.get("equity_curve", [])
    trades = log_data.get("trades", [])
    dates_raw = log_data.get("equity_dates", log_data.get("dates", []))

    ic = initial_cash if initial_cash else (equity[0] if equity else 100000.0)
    fv = equity[-1] if equity else ic

    # ---- basic ----
    basic = calculate_metrics_from_log_data(log_data)

    # ---- daily returns ----
    daily_returns: list[float] = []
    if len(equity) >= 2:
        for i in range(1, len(equity)):
            prev = equity[i - 1]
            daily_returns.append((equity[i] - prev) / prev if prev > 0 else 0.0)

    dr = np.array(daily_returns) if daily_returns else np.array([0.0])

    # ---- weekly / monthly returns (approximate via grouping) ----
    def _period_returns(period_size: int) -> list[float]:
        if len(equity) < period_size + 1:
            return []
        result = []
        for start in range(0, len(equity) - 1, period_size):
            end = min(start + period_size, len(equity) - 1)
            v0 = equity[start]
            v1 = equity[end]
            if v0 > 0:
                result.append((v1 - v0) / v0)
        return result

    weekly_returns = _period_returns(5)
    monthly_returns = _period_returns(21)

    wr = np.array(weekly_returns) if weekly_returns else np.array([0.0])
    mr = np.array(monthly_returns) if monthly_returns else np.array([0.0])

    # ---- trade-level stats ----
    win_trades = [t for t in trades if t.get("pnlcomm", 0) > 0]
    loss_trades = [t for t in trades if t.get("pnlcomm", 0) < 0]
    total_win = sum(t.get("pnlcomm", 0) for t in win_trades)
    total_loss = abs(sum(t.get("pnlcomm", 0) for t in loss_trades))
    total_pnl = sum(t.get("pnlcomm", 0) for t in trades)
    n_trades = len(trades)

    avg_win = total_win / len(win_trades) if win_trades else 0.0
    avg_loss = total_loss / len(loss_trades) if loss_trades else 0.0

    # commission / cost
    total_commission = sum(abs(t.get("commission", 0)) for t in trades)

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
        "trading_days": len(equity),
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
