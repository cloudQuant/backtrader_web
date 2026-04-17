"""Style analysis for portfolio returns.

Analyzes portfolio returns by style characteristics:
- Size (large-cap, mid-cap, small-cap)
- Value (value, growth)
    Momentum (winner, loser)
    Volatility (high, low)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "StyleResult",
    "analyze_performance_by_style",
    "calculate_regression_attribution",
    "calculate_style_tilts",
    "fetch_style_factors",
    "style_analysis",
]


class StyleResult:
    """Container for style analysis results."""

    def __init__(
        self,
        exposures: pd.DataFrame,
        returns_by_style: pd.DataFrame,
        overall_returns: pd.Series,
    ):
        """Initialize style result.

        Parameters
        ----------
        exposures : pd.DataFrame
            Style exposures (N assets x S styles).
        returns_by_style : pd.DataFrame
            Returns for each style (styles x 1).
        overall_returns : pd.Series
            Overall portfolio returns.
        """
        self.exposures = exposures
        self.returns_by_style = returns_by_style
        self.overall_returns = overall_returns

    @property
    def style_summary(self) -> dict[str, float]:
        """Get summary of style returns."""
        summary = {}

        # Handle both Series and DataFrame for returns_by_style
        if isinstance(self.returns_by_style, pd.Series):
            # Series: index contains styles
            for style in self.returns_by_style.index:
                summary[style] = float(self.returns_by_style[style])
        else:
            # DataFrame: either 'style' column or index contains styles
            if "style" in self.returns_by_style.columns:
                # Style is a column
                for _, row in self.returns_by_style.iterrows():
                    summary[row["style"]] = float(row["return"])
            else:
                # Index contains styles
                for style in self.returns_by_style.index:
                    val = self.returns_by_style.loc[style]
                    # Normalize common pandas selection outcomes:
                    # - Series (unique index label): row of columns
                    # - DataFrame (duplicate index label): multiple rows
                    # - scalar (rare): already a value
                    if isinstance(val, pd.DataFrame):
                        if val.empty:
                            scalar = 0.0
                        elif "return" in val.columns:
                            scalar = val["return"].iloc[0]
                        else:
                            scalar = val.iloc[0, 0]
                    elif isinstance(val, pd.Series):
                        if len(val) == 0:
                            scalar = 0.0
                        elif "return" in val.index:
                            scalar = val["return"]
                        else:
                            scalar = val.iloc[0]
                    else:
                        scalar = val

                    summary[style] = float(scalar)

        return summary

    def __contains__(self, key: str) -> bool:
        """Support ``key in result`` syntax."""
        return key in self._as_dict()

    def __getitem__(self, key: str):
        """Support ``result[key]`` syntax."""
        return self._as_dict()[key]

    def _as_dict(self) -> dict:
        """Internal dict representation."""
        return {
            "exposures": self.exposures,
            "returns_by_style": self.returns_by_style,
            "overall_returns": self.overall_returns,
            "style_summary": self.style_summary,
        }

    def to_dict(self) -> dict:
        """Convert results to dictionary."""
        return {
            "exposures": self.exposures.to_dict(),
            "returns_by_style": self.returns_by_style.to_dict(),
            "overall_returns": self.overall_returns.to_dict(),
        }


def style_analysis(
    returns: pd.DataFrame,
    market_caps: pd.Series | None = None,
    book_to_price: pd.Series | None = None,
    momentum_window: int = 252,
    size_quantiles: list[float] | None = None,
    value_scores: pd.Series | None = None,
) -> StyleResult:
    """Perform comprehensive style analysis on portfolio returns.

    Parameters
    ----------
    returns : pd.DataFrame
        Asset returns (T x N). Columns should be asset names.
    market_caps : pd.Series, optional
        Market capitalizations for size classification.
        If None, market_cap weighted returns used.
    book_to_price : pd.Series, optional
        Book-to-price ratios for value classification.
        If None, assumes all equity.
    momentum_window : int, default 252
        Lookback period for momentum calculation.
    size_quantiles : list of float, default [0.5, 0.5]
        Quantiles for size classification.
    value_scores : pd.Series, optional
        Fundamental value scores for value classification.
        If provided, used instead of book_to_price.

    Returns
    -------
    StyleResult
        Style analysis results with exposures and returns by style.
    """
    if size_quantiles is None:
        size_quantiles = [0.5, 0.5]

    _n_periods, n_assets = returns.shape

    # exposures_data maps style_name -> {asset -> weight}
    exposures_data: dict[str, dict[str, float]] = {}
    assets = list(returns.columns)

    def _add_style(style: str, raw: pd.Series) -> None:
        # Normalize weights for this style (sum to 1 when possible).
        w = raw.reindex(assets).fillna(0.0).astype(float).clip(lower=0.0)
        total = float(w.sum())
        if total > 0:
            w = w / total
        exposures_data[style] = w.to_dict()

    # 1. Size Classification
    if market_caps is not None:
        size_exposure = _calculate_size_exposure(market_caps.reindex(assets).dropna(), size_quantiles)
        for style in size_exposure.columns:
            _add_style(style, size_exposure[style])
    else:
        # Equal weight size exposure
        _add_style("equal_weight", pd.Series(1.0, index=assets))

    # 2. Momentum Classification - simplified
    # Use recent returns to classify momentum
    recent_returns = returns.tail(min(momentum_window, len(returns)))
    cumulative_returns = (1.0 + recent_returns).prod() - 1.0
    mom_threshold = cumulative_returns.median()
    _add_style("winner", (cumulative_returns >= mom_threshold).astype(float))
    _add_style("loser", (cumulative_returns < mom_threshold).astype(float))

    # 3. Value Classification
    if value_scores is not None:
        value_exposure = _value_from_scores(value_scores.reindex(assets).dropna())
        for style in value_exposure.columns:
            _add_style(style, value_exposure[style])
    elif book_to_price is not None:
        # Use B/P as value proxy: higher B/P tends to indicate "value".
        bp = book_to_price.reindex(assets).astype(float)
        threshold = bp.median()
        _add_style("value", (bp >= threshold).astype(float))
        _add_style("growth", (bp < threshold).astype(float))
    else:
        # Equal weight value exposure
        _add_style("value", pd.Series(1.0, index=assets))
        _add_style("growth", pd.Series(1.0, index=assets))

    # 4. Volatility Classification
    rolling_vol = returns.rolling(window=60, min_periods=20).std(ddof=0)
    vol_median = rolling_vol.median()
    vol_at_end = rolling_vol.iloc[-1]
    high_mask = (vol_at_end >= vol_median).astype(float)
    low_mask = (vol_at_end < vol_median).astype(float)
    _add_style("high", high_mask)
    _add_style("low", low_mask)

    # Build exposures DataFrame
    all_exposures = pd.DataFrame.from_dict(exposures_data, orient="columns").reindex(index=assets).fillna(0.0)

    # Calculate returns by style
    returns_by_style = {}

    for style in all_exposures.columns:
        weights = all_exposures[style].reindex(assets).fillna(0.0).astype(float)
        total = float(weights.sum())
        if total <= 0:
            returns_by_style[style] = np.nan
            continue
        weights = weights / total
        returns_by_style[style] = float((returns.mul(weights, axis=1)).sum(axis=1).mean())

    # Overall portfolio returns (equal-weighted)
    equal_weights = pd.Series(np.ones(n_assets) / n_assets, index=returns.columns)
    overall_returns = returns.mul(equal_weights, axis=1).sum(axis=1)

    # Convert returns_by_style dict to DataFrame
    returns_by_style_df = pd.DataFrame(list(returns_by_style.items()), columns=["style", "return"])
    returns_by_style_df = returns_by_style_df.set_index("style")

    return StyleResult(
        exposures=all_exposures,
        returns_by_style=returns_by_style_df,
        overall_returns=overall_returns,
    )


def _calculate_size_exposure(
    market_caps: pd.Series,
    quantiles: list[float],
) -> pd.DataFrame:
    """Calculate size factor exposures based on market cap quantiles.

    Parameters
    ----------
    market_caps : pd.Series
        Market capitalizations (N assets).
    quantiles : list of float
        Quantile thresholds [e.g., 0.3, 0.7].

    Returns
    -------
    pd.DataFrame
        Binary exposure matrix (N x categories).
        Columns: small, mid, large (using first two quantiles).
    """
    if len(quantiles) < 2 or not all(0 <= q <= 1 for q in quantiles[:2]):
        raise ValueError(f"quantiles must have at least 2 elements in [0, 1]; got quantiles={quantiles}")
    exposures = pd.DataFrame(index=market_caps.index)

    exposures["large"] = (market_caps >= np.percentile(market_caps, quantiles[1] * 100)).astype(int)
    exposures["mid"] = (
        (market_caps >= np.percentile(market_caps, quantiles[0] * 100))
        & (market_caps < np.percentile(market_caps, quantiles[1] * 100))
    ).astype(int)
    exposures["small"] = (market_caps < np.percentile(market_caps, quantiles[0] * 100)).astype(int)

    return exposures


def _calculate_momentum(
    returns: pd.DataFrame,
    window: int,
) -> pd.DataFrame:
    """Calculate momentum signal for each asset.

    Parameters
    ----------
    returns : pd.DataFrame
        Asset returns (T x N).
    window : int
        Lookback window.

    Returns
    -------
    pd.DataFrame
        Momentum scores (1 if positive, 0 if negative).
    """
    # Cumulative returns over window
    cum_returns = (1 + returns).cumsum()

    # Momentum: position relative to window periods ago
    momentum = cum_returns.shift(window) / cum_returns.shift(window) - 1

    # Current momentum signal
    current_momentum = momentum.iloc[-1]

    return (current_momentum > 0).astype(int).to_frame().T


def _exposure_from_lookback(
    data: pd.DataFrame,
    periods: int,
    direction: str = "positive",
) -> pd.DataFrame:
    """Calculate exposure weights based on past performance.

    Parameters
    ----------
    data : pd.DataFrame
        Performance data (T x N).
    periods : int
        Number of lookback periods.
    direction : str, default "positive"
        'positive': high performers get 1, low get 0
        'negative': low performers get 1, high get 0

    Returns
    -------
    pd.DataFrame
        Binary exposure matrix.
    """
    # Calculate cumulative performance over periods
    cum_data = (1 + data).cumsum()

    # Performance over lookback periods
    if direction == "positive":
        # Top performers get 1
        lookback_perf = cum_data.shift(periods).iloc[-1]
        exposure = (cum_data.iloc[-1] >= lookback_perf).astype(int).to_frame().T
    else:
        # Bottom performers get 1
        lookback_perf = cum_data.shift(periods).iloc[-1]
        exposure = (cum_data.iloc[-1] <= lookback_perf).astype(int).to_frame().T

    return exposure


def _value_from_scores(book_to_price: pd.Series) -> pd.DataFrame:
    """Calculate value exposure from generic value scores.

    Parameters
    ----------
    book_to_price : pd.Series
        Value scores for each asset (higher -> more "value"-like).

    Returns
    -------
    pd.DataFrame
        Binary exposure matrix (N x 2): value, growth.
    """
    scores = book_to_price.astype(float)
    threshold = scores.median()
    exposures = pd.DataFrame(index=scores.index)
    exposures["value"] = (scores >= threshold).astype(int)
    exposures["growth"] = (scores < threshold).astype(int)
    return exposures


def calculate_style_tilts(
    returns: pd.DataFrame,
    factor_returns: pd.DataFrame | None = None,
    window: int = 252,
) -> pd.DataFrame:
    """Calculate rolling style exposures (size, value, momentum).

    Parameters
    ----------
    returns : pd.DataFrame
        Asset returns (T x N).
    factor_returns : pd.DataFrame, optional
        Factor returns for calculating style relative to factor.
        If None, uses cross-sectional ranking.
    window : int, default 252
        Rolling window size.

    Returns
    -------
    pd.DataFrame
        Time series of style exposures for each asset.
        Index: dates, Columns: {asset}_{style} format.
    """
    n_periods, n_assets = returns.shape

    # Clamp window to available data (need at least 2 periods beyond window)
    effective_window = min(window, n_periods - 1)
    if effective_window < 2:
        return pd.DataFrame()

    # Build result DataFrame
    result_df = pd.DataFrame(index=returns.index[effective_window:])

    for t in range(effective_window, n_periods):
        # Get historical returns
        hist_returns = returns.iloc[:t]

        # Size: use returns ranking as proxy for market cap
        latest_returns = hist_returns.iloc[-1]
        size_ranks = latest_returns.rank(ascending=True)
        # Top third = large, bottom third = small
        for asset in returns.columns:
            rank = size_ranks[asset]
            result_df.loc[returns.index[t], f"{asset}_large"] = 1 if rank <= n_assets / 3 else 0
            result_df.loc[returns.index[t], f"{asset}_small"] = 1 if rank > 2 * n_assets / 3 else 0

        # Momentum: use cumulative returns over window
        mom_returns = hist_returns.tail(window)
        cum_returns = (1 + mom_returns).prod() - 1
        for asset in returns.columns:
            result_df.loc[returns.index[t], f"{asset}_winner"] = 1 if cum_returns[asset] > 0 else 0
            result_df.loc[returns.index[t], f"{asset}_loser"] = 1 if cum_returns[asset] <= 0 else 0

        # Value: use ranking as proxy (higher returns = value outperformers)
        value_ranks = cum_returns.rank(ascending=True)
        for asset in returns.columns:
            result_df.loc[returns.index[t], f"{asset}_value"] = 1 if value_ranks[asset] <= n_assets / 2 else 0
            result_df.loc[returns.index[t], f"{asset}_growth"] = 1 if value_ranks[asset] > n_assets / 2 else 0

        # Volatility: use rolling std
        vol_returns = hist_returns.tail(60)
        vol_std = vol_returns.std()
        vol_median = vol_std.median()
        for asset in returns.columns:
            result_df.loc[returns.index[t], f"{asset}_high_vol"] = 1 if vol_std[asset] >= vol_median else 0
            result_df.loc[returns.index[t], f"{asset}_low_vol"] = 1 if vol_std[asset] < vol_median else 0

    return result_df


def _size_rank_to_exposure(ranks: pd.Series) -> pd.DataFrame:
    """Convert size ranks to binary exposures."""
    exposure = pd.DataFrame(index=ranks.index)

    exposure["large"] = (ranks <= 2 / 3).astype(int)  # Top 33%
    exposure["small"] = (ranks > 1 / 3).astype(int) & (ranks <= 2 / 3).astype(int)  # Middle 34%

    return exposure.T


def calculate_regression_attribution(
    portfolio_returns: pd.Series | pd.DataFrame,
    style_returns: pd.DataFrame | None = None,
    style_exposures: pd.DataFrame | None = None,
) -> dict[str, float]:
    """Attribute portfolio returns using style exposures.

    If ``style_returns`` and ``style_exposures`` are not provided, they are
    derived automatically by running :func:`style_analysis` on
    ``portfolio_returns`` (which must be a DataFrame of asset returns in
    that case).

    Parameters
    ----------
    portfolio_returns : pd.Series or pd.DataFrame
        Portfolio returns (Series) or asset returns (DataFrame).
        If DataFrame and ``style_returns``/``style_exposures`` are None,
        a style analysis is run automatically.
    style_returns : pd.DataFrame, optional
        Returns for each style factor (T x S).
    style_exposures : pd.DataFrame, optional
        Style exposures (N x S) or (T x S).

    Returns
    -------
    dict
        Attribution by style factor, including 'residual'.
    """
    # Auto-derive from DataFrame if style data not provided
    if style_returns is None or style_exposures is None:
        if isinstance(portfolio_returns, pd.DataFrame):
            result = style_analysis(portfolio_returns)
            style_exposures = result.exposures
            # Build style return series from the exposures + asset returns
            _asset_returns = portfolio_returns
            _style_ret_dict = {}
            for style in style_exposures.columns:
                weights = style_exposures[style].reindex(_asset_returns.columns, fill_value=0).astype(float)
                total = float(weights.sum())
                if total > 0:
                    weights = weights / total
                _style_ret_dict[style] = (_asset_returns.mul(weights, axis=1)).sum(axis=1)
            style_returns = pd.DataFrame(_style_ret_dict)
            # Compute equal-weighted portfolio returns
            port_ret = _asset_returns.mean(axis=1)
        else:
            raise TypeError(
                "When style_returns/style_exposures are not provided, "
                "portfolio_returns must be a DataFrame of asset returns."
            )
    else:
        port_ret = portfolio_returns if isinstance(portfolio_returns, pd.Series) else portfolio_returns.mean(axis=1)

    portfolio_return = float(np.mean(port_ret))
    attributions = {}

    for style in style_returns.columns:
        if style_exposures is not None and style not in style_exposures.columns:
            continue

        # Align lengths
        common_idx = port_ret.index.intersection(style_returns[style].index)
        if len(common_idx) < 3:
            attributions[style] = 0.0
            continue

        pr = port_ret.loc[common_idx].values
        sr = style_returns[style].loc[common_idx].values
        valid_mask = ~(np.isnan(pr) | np.isnan(sr))
        if valid_mask.sum() < 3:
            attributions[style] = 0.0
            continue

        pr_valid = pr[valid_mask]
        sr_valid = sr[valid_mask]

        if np.std(pr_valid) < 1e-15 or np.std(sr_valid) < 1e-15:
            style_beta = 0.0
        else:
            with np.errstate(invalid="ignore", divide="ignore"):
                corr = np.corrcoef(pr_valid, sr_valid)[0, 1]
            style_beta = float(corr) if np.isfinite(corr) else 0.0

        # Average style return * beta as contribution
        avg_style_ret = float(np.mean(sr_valid))
        style_contribution = style_beta * avg_style_ret

        attributions[style] = style_contribution

    total_attributed = sum(attributions.values())
    attributions["residual"] = portfolio_return - total_attributed

    return attributions


def analyze_performance_by_style(
    returns: pd.DataFrame,
    style_exposures: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Analyze performance metrics grouped by style.

    If ``style_exposures`` is not provided, it is derived automatically
    by running :func:`style_analysis`.

    Parameters
    ----------
    returns : pd.DataFrame
        Asset returns (T x N).
    style_exposures : pd.DataFrame, optional
        Style exposures (N x S).  If None, derived from ``style_analysis``.

    Returns
    -------
    pd.DataFrame
        Performance metrics by style (columns: ``{style}_return``).
    """
    if returns.empty:
        return pd.DataFrame()

    if style_exposures is None:
        result = style_analysis(returns)
        style_exposures = result.exposures

    if style_exposures.empty:
        return pd.DataFrame()

    # style_exposures is (N assets x S styles) — static exposures
    # We compute weighted return per style per period
    style_weights: dict[str, pd.Series] = {}
    for style in style_exposures.columns:
        w = style_exposures[style].reindex(returns.columns, fill_value=0.0).astype(float)
        total = float(w.sum())
        if total > 0:
            w = w / total
        style_weights[style] = w

    results = []
    for t in range(len(returns)):
        t_returns = returns.iloc[t]
        row_data: dict[str, int | float] = {"Period": int(t)}

        for style in style_exposures.columns:
            w = style_weights[style]
            total = float(w.sum())
            if total <= 0:
                row_data[f"{style}_return"] = 0.0
            else:
                row_data[f"{style}_return"] = float((t_returns * w).sum())

        results.append(row_data)

    # returns is guaranteed non-empty above, so results is also non-empty here.
    return pd.DataFrame(results).set_index("Period")


def fetch_style_factors(
    tickers: list[str],
    factors: list[str] | None = None,
    library: str = "us",
) -> pd.DataFrame:
    """Fetch style factor data.

    .. note::

       A concrete data provider must be configured before calling this
       function.  Pass pre-fetched factor data directly to
       :func:`style_analysis` or :func:`calculate_style_tilts`.

    Parameters
    ----------
    tickers : list of str
        Asset tickers.
    factors : list of str, default ["size", "value", "momentum"]
        Style factors to fetch.
    library : str, default "us"
        Data source library. Options: 'us', 'chinese'.

    Returns
    -------
    pd.DataFrame
        Factor data with MultiIndex (date, factor).

    Raises
    ------
    NotImplementedError
        Always raised until a data provider is configured.
    """
    import logging

    logger = logging.getLogger(__name__)
    logger.error(
        "fetch_style_factors called without a configured data provider. "
        "Pass pre-fetched factor data directly to style_analysis() or "
        "calculate_style_tilts()."
    )
    raise NotImplementedError(
        "No style factor data provider is configured. "
        "Please pass pre-fetched factor data directly to "
        "style_analysis() or calculate_style_tilts()."
    )
