"""Stress testing scenarios for portfolio analysis.

Generates extreme market scenarios for stress testing portfolios.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["generate_correlation_breakdown", "scenario_table", "stress_test"]


def stress_test(
    returns: pd.Series | np.ndarray,
    scenarios: list[str] | None = None,
    custom_scenarios: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """Perform stress testing on returns under various scenarios.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Historical returns to stress test.
    scenarios : list of str, optional
        Predefined scenarios to apply. Options:
        - 'crash': Sudden market crash (-20% or more)
        - 'spike': Sudden market jump (+10% or more)
        - 'vol_crush': Volatility crush (vol drops 50%)
        - 'vol_spike': Volatility spike (vol doubles)
        - 'correlation_breakdown': Correlation goes to 1
        If None, applies all predefined scenarios.
    custom_scenarios : dict, optional
        Custom scenarios as {name: {params}}.
        Each params dict can contain:
        - 'return_shift': Additive return adjustment
        - 'return_mult': Multiplicative return adjustment
        - 'vol_mult': Volatility multiplier

    Returns
    -------
    dict
        Dictionary with scenario names as keys and results as values.
        Each result contains:
        - 'stressed_returns': The stressed return series
        - 'cumulative': Cumulative stressed return
        - 'max_drawdown': Maximum drawdown under stress
        - 'volatility': Volatility under stress
    """
    arr = np.asarray(returns)
    arr = arr[~np.isnan(arr)]

    if len(arr) == 0:
        raise ValueError("Cannot stress test empty returns")

    if scenarios is None and custom_scenarios is None:
        scenarios = ["crash", "spike", "vol_crush", "vol_spike"]

    result = {}

    # Apply predefined scenarios
    if scenarios:
        predefined = {
            "crash": _apply_crash_scenario,
            "spike": _apply_spike_scenario,
            "vol_crush": _apply_vol_crush_scenario,
            "vol_spike": _apply_vol_spike_scenario,
        }

        for scenario in scenarios:
            if scenario in predefined:
                result[scenario] = predefined[scenario](arr)

    # Apply custom scenarios
    if custom_scenarios:
        for name, params in custom_scenarios.items():
            result[name] = _apply_custom_scenario(arr, params)

    return result


def _apply_crash_scenario(returns: np.ndarray) -> dict:
    """Apply market crash scenario."""
    stressed = returns.copy()
    # Insert a single large loss day
    crash_idx = len(returns) // 2
    stressed[crash_idx] = -0.20  # 20% single-day loss

    return _scenario_summary(stressed, "crash")


def _apply_spike_scenario(returns: np.ndarray) -> dict:
    """Apply market spike scenario."""
    stressed = returns.copy()
    # Insert a single large gain day
    spike_idx = len(returns) // 2
    stressed[spike_idx] = 0.10  # 10% single-day gain

    return _scenario_summary(stressed, "spike")


def _apply_vol_crush_scenario(returns: np.ndarray) -> dict:
    """Apply volatility crush scenario."""
    stressed = returns.copy()
    # Scale down returns (lower volatility)
    stressed = stressed * 0.5

    return _scenario_summary(stressed, "vol_crush")


def _apply_vol_spike_scenario(returns: np.ndarray) -> dict:
    """Apply volatility spike scenario."""
    stressed = returns.copy()
    # Scale up returns (higher volatility)
    stressed = stressed * 2.0

    return _scenario_summary(stressed, "vol_spike")


def _apply_custom_scenario(returns: np.ndarray, params: dict) -> dict:
    """Apply custom stress scenario."""
    stressed = returns.copy()

    # Apply return shift
    if "return_shift" in params:
        stressed = stressed + params["return_shift"]

    # Apply return multiplier
    if "return_mult" in params:
        stressed = stressed * params["return_mult"]

    return _scenario_summary(stressed, "custom")


def _scenario_summary(stressed_returns: np.ndarray, scenario_name: str) -> dict:
    """Generate summary statistics for a stressed scenario."""
    # Cumulative returns
    cum_returns = np.cumprod(1 + stressed_returns) - 1

    # Maximum drawdown
    cum_returns_series = np.cumprod(1 + stressed_returns)
    running_max = np.maximum.accumulate(cum_returns_series)
    drawdown = (cum_returns_series / running_max) - 1
    max_dd = np.min(drawdown)

    # Volatility
    vol = float(np.std(stressed_returns, ddof=1) * np.sqrt(252))

    return {
        "scenario": scenario_name,
        "stressed_returns": stressed_returns,
        "cumulative_return": float(cum_returns[-1]),
        "max_drawdown": float(max_dd),
        "volatility": vol,
        "final_value": float(cum_returns_series[-1]),
    }


def generate_correlation_breakdown(
    n_assets: int,
    target_correlation: float = 1.0,
) -> np.ndarray:
    """Generate correlation matrix for correlation breakdown stress test.

    In correlation breakdown, all assets become perfectly correlated,
    which eliminates diversification benefits.

    Parameters
    ----------
    n_assets : int
        Number of assets.
    target_correlation : float, default 1.0
        Target correlation between all assets.

    Returns
    -------
    np.ndarray, shape (n_assets, n_assets)
        Correlation matrix with uniform correlation.
    """
    corr_matrix = np.ones((n_assets, n_assets)) * target_correlation
    np.fill_diagonal(corr_matrix, 1.0)
    return corr_matrix


def scenario_table(
    stress_results: dict[str, dict],
) -> pd.DataFrame:
    """Format stress test results as a table.

    Parameters
    ----------
    stress_results : dict
        Output from stress_test() function.

    Returns
    -------
    pd.DataFrame
        Summary table of stress test results.
    """
    rows = []

    for scenario, results in stress_results.items():
        rows.append(
            {
                "Scenario": scenario,
                "Cumulative Return": f"{results['cumulative_return']:.2%}",
                "Max Drawdown": f"{results['max_drawdown']:.2%}",
                "Volatility": f"{results['volatility']:.2%}",
                "Final Value": f"{results['final_value']:.4f}",
            }
        )

    return pd.DataFrame(rows)
