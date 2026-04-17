"""Brinson attribution analysis for portfolio performance.

Decomposes portfolio excess returns into:
- Allocation effect: returns from overweighting/underweighting sectors
- Selection effect: returns from stock selection within sectors
- Interaction effect: returns from interaction of allocation and selection
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["BrinsonAttribution", "brinson_attribution", "brinson_cumulative", "brinson_results"]


def brinson_attribution(
    portfolio_returns: pd.Series | np.ndarray,
    benchmark_returns: pd.Series | np.ndarray,
    portfolio_weights: pd.Series | np.ndarray | pd.DataFrame,
    benchmark_weights: pd.Series | np.ndarray | pd.DataFrame,
) -> dict[str, float]:
    """Calculate Brinson attribution for a single period.

    Parameters
    ----------
    portfolio_returns : pd.Series or np.ndarray
        Portfolio returns for the period.
    benchmark_returns : pd.Series or np.ndarray
        Benchmark returns for the period.
    portfolio_weights : pd.DataFrame
        Portfolio weights by sector/asset for the period.
        benchmark_weights : pd.DataFrame
        Benchmark weights by sector/asset for the period.

    Returns
    -------
    dict
        Dictionary with attribution breakdown:
        - 'allocation': Allocation effect
        - 'selection': Selection effect
        - 'interaction': Interaction effect
        - 'total': Total active return
        - 'portfolio_return': Portfolio return
        - 'benchmark_return': Benchmark return

    Examples
    --------
    >>> import pandas as pd
    >>> import numpy as np
    >>> portfolio_returns = np.array([0.05, 0.03, -0.02, 0.04])
    >>> benchmark_returns = np.array([0.03, 0.02, -0.01, 0.03])
    >>> portfolio_weights = pd.DataFrame({
    ...     'Sector_A': [0.4, 0.3, 0.2, 0.1],
    ...     'Sector_B': [0.3, 0.3, 0.3, 0.1],
    ... })
    >>> benchmark_weights = pd.DataFrame({
    ...     'Sector_A': [0.5, 0.3, 0.1, 0.1],
    ...     'Sector_B': [0.3, 0.3, 0.3, 0.1],
    ... })
    >>> result = brinson_attribution(
    ...     portfolio_returns, benchmark_returns,
    ...     portfolio_weights, benchmark_weights
    ... )
    >>> print(f"Allocation: {result['allocation']:.2%}")
    """
    rp = np.asarray(portfolio_returns, dtype=float).reshape(-1)
    rb = np.asarray(benchmark_returns, dtype=float).reshape(-1)
    wp = np.asarray(portfolio_weights, dtype=float).reshape(-1)
    wb = np.asarray(benchmark_weights, dtype=float).reshape(-1)

    if not (rp.shape == rb.shape == wp.shape == wb.shape):
        raise ValueError(
            "portfolio_returns, benchmark_returns, portfolio_weights, and benchmark_weights must have the same shape."
        )

    # Portfolio / benchmark returns for the period.
    portfolio_return = float(np.sum(wp * rp))
    benchmark_return = float(np.sum(wb * rb))
    active_return = portfolio_return - benchmark_return

    # BHB: allocation = (wp-wb)*rb, selection = wb*(rp-rb), interaction = (wp-wb)*(rp-rb)
    allocation_effect = float(np.sum((wp - wb) * rb))
    selection_effect = float(np.sum(wb * (rp - rb)))
    interaction_effect = float(np.sum((wp - wb) * (rp - rb)))
    total = allocation_effect + selection_effect + interaction_effect

    result: dict[str, float] = {
        "allocation": allocation_effect,
        "selection": selection_effect,
        "interaction": interaction_effect,
        "total": total,
        "portfolio_return": portfolio_return,
        "benchmark_return": benchmark_return,
    }

    if not np.isclose(total, active_return, rtol=1e-10, atol=1e-12):
        result["residual"] = float(active_return - total)

    return result


def brinson_results(
    portfolio_returns: pd.Series | np.ndarray,
    benchmark_returns: pd.Series | np.ndarray,
    portfolio_weights: pd.DataFrame | np.ndarray,
    benchmark_weights: pd.DataFrame | np.ndarray,
    periods: list[str] | None = None,
) -> pd.DataFrame:
    """Calculate Brinson attribution over multiple periods.

    Parameters
    ----------
    portfolio_returns : pd.Series or np.ndarray
        Portfolio returns (T periods).
    benchmark_returns : pd.Series or np.ndarray
        Benchmark returns (T periods).
    portfolio_weights : pd.DataFrame
        Portfolio weights for each period (T x sectors).
    benchmark_weights : pd.DataFrame
        Benchmark weights for each period (T x sectors).
    periods : list of str, optional
        Period labels. If None, uses integer indices.

    Returns
    -------
    pd.DataFrame
        DataFrame with attribution results for each period.
        Columns: period, allocation, selection, interaction, total, portfolio_return, benchmark_return
    """
    # Convert to arrays
    rp = np.asarray(portfolio_returns, dtype=float)
    rb = np.asarray(benchmark_returns, dtype=float)
    wp = np.asarray(portfolio_weights, dtype=float)
    wb = np.asarray(benchmark_weights, dtype=float)

    # Single period: (n_sectors,) arrays.
    if rp.ndim == 1:
        rp = rp[None, :]
        rb = rb[None, :]

    if wp.ndim == 1:
        wp = np.tile(wp, (rp.shape[0], 1))
    if wb.ndim == 1:
        wb = np.tile(wb, (rp.shape[0], 1))

    n_periods = rp.shape[0]

    if periods is None:
        periods = [str(i) for i in range(n_periods)]

    results = []

    for t in range(n_periods):
        attr = brinson_attribution(rp[t], rb[t], wp[t], wb[t])

        results.append(
            {
                "period": periods[t],
                "allocation": attr["allocation"],
                "selection": attr["selection"],
                "interaction": attr["interaction"],
                "total": attr["total"],
                "portfolio_return": attr["portfolio_return"],
                "benchmark_return": attr["benchmark_return"],
            }
        )

    return pd.DataFrame(results)


def brinson_cumulative(
    portfolio_returns: pd.Series | np.ndarray,
    benchmark_returns: pd.Series | np.ndarray,
    portfolio_weights: pd.DataFrame | np.ndarray,
    benchmark_weights: pd.DataFrame | np.ndarray,
) -> dict[str, float]:
    """Calculate cumulative Brinson attribution.

    This aggregates per-period Brinson effects (arithmetic sum across periods).
    It also reports geometric cumulative portfolio/benchmark returns computed
    from per-period weighted returns.

    Parameters
    ----------
    portfolio_returns : pd.Series or np.ndarray
        Portfolio returns.
    benchmark_returns : pd.Series or np.ndarray
        Benchmark returns.
    portfolio_weights : pd.DataFrame
        Portfolio weights (final weights for cumulative).
    benchmark_weights : pd.DataFrame
        Benchmark weights (final weights for cumulative).

    Returns
    -------
    dict
        Cumulative attribution breakdown.
    """
    rp = np.asarray(portfolio_returns, dtype=float)
    rb = np.asarray(benchmark_returns, dtype=float)
    wp = np.asarray(portfolio_weights, dtype=float)
    wb = np.asarray(benchmark_weights, dtype=float)

    if rp.ndim == 1:
        rp = rp[None, :]
        rb = rb[None, :]
    if wp.ndim == 1:
        wp = np.tile(wp, (rp.shape[0], 1))
    if wb.ndim == 1:
        wb = np.tile(wb, (rp.shape[0], 1))

    if not (rp.shape == rb.shape == wp.shape == wb.shape):
        raise ValueError("portfolio_returns, benchmark_returns, and weights must have consistent shapes.")

    allocation = 0.0
    selection = 0.0
    interaction = 0.0
    total = 0.0

    portfolio_period = np.sum(wp * rp, axis=1)
    benchmark_period = np.sum(wb * rb, axis=1)

    for t in range(rp.shape[0]):
        attr = brinson_attribution(rp[t], rb[t], wp[t], wb[t])
        allocation += float(attr["allocation"])
        selection += float(attr["selection"])
        interaction += float(attr["interaction"])
        total += float(attr["total"])

    portfolio_cum = float(np.prod(1.0 + portfolio_period) - 1.0)
    benchmark_cum = float(np.prod(1.0 + benchmark_period) - 1.0)

    return {
        "allocation": allocation,
        "selection": selection,
        "interaction": interaction,
        "total": total,
        "portfolio_cumulative": portfolio_cum,
        "benchmark_cumulative": benchmark_cum,
    }


class BrinsonAttribution:
    """Brinson attribution calculator with sector mapping support.

    Provides convenient interface for multi-period Brinson attribution
    with sector/asset classification.
    """

    def __init__(
        self,
        sector_mapping: dict[str, list[str]] | None = None,
    ):
        """Initialize Brinson attribution calculator.

        Parameters
        ----------
        sector_mapping : dict, optional
            Mapping from sector name to a list of asset column names.
            Example: {'Technology': ['AAPL', 'MSFT'], 'Financial': ['JPM']}
        """
        self.sector_mapping = sector_mapping or {}

    def calculate(
        self,
        returns: pd.DataFrame,
        benchmark_returns: pd.DataFrame | None = None,
        weights: pd.DataFrame | None = None,
        method: str = "brinson",
    ) -> pd.DataFrame:
        """Calculate Brinson attribution for returns DataFrame.

        Parameters
        ----------
        returns : pd.DataFrame
            Asset returns (T x N assets).
            Columns should be asset names.
        benchmark_returns : pd.DataFrame, optional
            Benchmark returns. If None, uses equal-weighted benchmark.
        weights : pd.DataFrame, optional
            Portfolio weights. If None, uses equal weights.
        method : str, default "brinson"
            Attribution method. Options: 'brinson', 'brinson_hood'.

        Returns
        -------
        pd.DataFrame
            Attribution results by period.
        """
        if method == "brinson_hood":
            raise NotImplementedError("brinson_hood method is not implemented yet.")
        if method != "brinson":
            raise ValueError("Unknown attribution method. Use: 'brinson' or 'brinson_hood'.")

        # Apply sector mapping if provided
        if self.sector_mapping:
            returns = self._apply_sector_mapping(returns, agg="mean")

            if benchmark_returns is not None:
                benchmark_returns = self._apply_sector_mapping(benchmark_returns, agg="mean")

            if weights is not None:
                weights = self._apply_sector_mapping(weights, agg="sum")

        # Use equal weights if not provided
        if weights is None:
            n = returns.shape[1]
            weights_array = np.ones(n) / n
            weights = pd.DataFrame(
                np.tile(weights_array, (returns.shape[0], 1)),
                columns=returns.columns,
                index=returns.index,
            )

        if benchmark_returns is None:
            benchmark_returns = returns

        # Equal-weight benchmark weights unless explicitly supported in the future.
        n_bench = returns.shape[1]
        bench_weights = np.ones(n_bench) / n_bench
        benchmark_weights = pd.DataFrame(
            np.tile(bench_weights, (returns.shape[0], 1)),
            columns=returns.columns,
            index=returns.index,
        )

        # Calculate attribution for each period
        results = []

        for t in range(returns.shape[0]):
            attr = brinson_attribution(
                returns.iloc[t].values,
                benchmark_returns.iloc[t].values,
                weights.iloc[t].values,
                benchmark_weights.iloc[t].values,
            )

            results.append(
                {
                    "period": t,
                    "allocation": attr["allocation"],
                    "selection": attr["selection"],
                    "interaction": attr["interaction"],
                    "total": attr["total"],
                }
            )

        return pd.DataFrame(results)

    def _apply_sector_mapping(
        self,
        df: pd.DataFrame,
        *,
        agg: str,
    ) -> pd.DataFrame:
        """Apply sector mapping to aggregate by sector."""
        if agg not in {"sum", "mean"}:
            raise ValueError("agg must be 'sum' or 'mean'.")

        sector_series: list[pd.Series] = []
        sector_names: list[str] = []

        for sector, assets in self.sector_mapping.items():
            sector_df = df[assets]
            sector_s = sector_df.sum(axis=1) if agg == "sum" else sector_df.mean(axis=1)
            sector_series.append(sector_s)
            sector_names.append(sector)

        out = pd.concat(sector_series, axis=1)
        out.columns = sector_names
        return out

    def __repr__(self) -> str:
        sectors = list(self.sector_mapping.keys()) if self.sector_mapping else []
        return f"BrinsonAttribution({len(sectors)} sectors)"
