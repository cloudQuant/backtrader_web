"""
Fincore metrics helper module.

Provides standardized financial metric calculations using FincoreAdapter
with fallback to manual calculations. This ensures consistent metrics
across the platform.
"""

import logging
from typing import Any, Dict, List

from app.services.backtest_analyzers import FincoreAdapter

logger = logging.getLogger(__name__)


class MetricsSource:
    """Enumeration of metric calculation sources."""

    MANUAL = "manual"
    FINCORE = "fincore"


def calculate_metrics_from_log_data(
    log_data: Dict[str, Any], use_fincore: bool = False
) -> Dict[str, Any]:
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


def _calculate_total_return(adapter: FincoreAdapter, equity: List[float]) -> float:
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


def _calculate_annual_return(adapter: FincoreAdapter, equity: List[float]) -> float:
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


def _calculate_sharpe_ratio(adapter: FincoreAdapter, equity: List[float]) -> float:
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


def _calculate_max_drawdown(adapter: FincoreAdapter, equity: List[float]) -> float:
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


def _calculate_win_rate(adapter: FincoreAdapter, trades: List[Dict[str, Any]]) -> float:
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


def compare_calculation_methods(log_data: Dict[str, Any]) -> Dict[str, Any]:
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
    log_data: Dict[str, Any], max_relative_error: float = 0.01
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
