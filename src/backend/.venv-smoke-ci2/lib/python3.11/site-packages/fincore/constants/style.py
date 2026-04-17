"""Style constants for tearsheet generation and reporting.

This module provides constants for performance attribution formatting,
sector classifications, capitalization buckets, and statistic display.
"""

from __future__ import annotations

from collections import OrderedDict

import numpy as np
import pandas as pd

__all__ = [
    "CAPACITY_CAPITAL_BASE",
    "CAPACITY_SWEEP_MAX_PV",
    "CAPACITY_SWEEP_MIN_PV",
    "CAPACITY_SWEEP_STEP",
    "CAP_BUCKETS",
    "DURATION_STATS",
    "FACTOR_PARTITIONS",
    "FACTOR_STAT_FUNCS",
    "LIQUIDATION_DAILY_VOL_LIMIT",
    "MM_DISPLAY_UNIT",
    "PERF_ATTRIB_TURNOVER_THRESHOLD",
    "PNL_STATS",
    "RETURN_STATS",
    "SECTORS",
    "SIMPLE_STAT_FUNCS",
    "STAT_FUNCS_PCT",
    "STAT_FUNC_NAMES",
    "SUMMARY_STATS",
    "TRADE_DAILY_VOL_LIMIT",
]


PERF_ATTRIB_TURNOVER_THRESHOLD = 0.25
"""Minimum turnover threshold for performance attribution."""

# Capacity tear sheet defaults
LIQUIDATION_DAILY_VOL_LIMIT = 0.2
"""Default max bar consumption for liquidation (20%)."""

TRADE_DAILY_VOL_LIMIT = 0.05
"""Default max bar consumption per trade (5%)."""

CAPACITY_CAPITAL_BASE = 1_000_000
"""Default capital base ($1M) for liquidation analysis."""

CAPACITY_SWEEP_MIN_PV = 100_000
"""Min portfolio value for capacity sweep."""

CAPACITY_SWEEP_MAX_PV = 300_000_000
"""Max portfolio value for capacity sweep."""

CAPACITY_SWEEP_STEP = 1_000_000
"""Step size for capacity sweep."""

SECTORS = OrderedDict(
    [
        (101, "Basic Materials"),
        (102, "Consumer Cyclical"),
        (103, "Financial Services"),
        (104, "Real Estate"),
        (205, "Consumer Defensive"),
        (206, "Healthcare"),
        (207, "Utilities"),
        (308, "Communication Services"),
        (309, "Energy"),
        (310, "Industrials"),
        (311, "Technology"),
    ]
)

CAP_BUCKETS = OrderedDict(
    [
        ("Micro", (50000000, 300000000)),
        ("Small", (300000000, 2000000000)),
        ("Mid", (2000000000, 10000000000)),
        ("Large", (10000000000, 200000000000)),
        ("Mega", (200000000000, np.inf)),
    ]
)

SIMPLE_STAT_FUNCS = [
    "annual_return",
    "cum_returns_final",
    "annual_volatility",
    "sharpe_ratio",
    "calmar_ratio",
    "stability_of_timeseries",
    "max_drawdown",
    "omega_ratio",
    "sortino_ratio",
    "stats.skew",
    "stats.kurtosis",
    "tail_ratio",
    "value_at_risk",
]

FACTOR_STAT_FUNCS = [
    "alpha",
    "beta",
]

STAT_FUNC_NAMES = {
    "annual_return": "Annual return",
    "cum_returns_final": "Cumulative returns",
    "annual_volatility": "Annual volatility",
    "sharpe_ratio": "Sharpe ratio",
    "calmar_ratio": "Calmar ratio",
    "stability_of_timeseries": "Stability",
    "max_drawdown": "Max drawdown",
    "omega_ratio": "Omega ratio",
    "sortino_ratio": "Sortino ratio",
    "skew": "Skew",
    "kurtosis": "Kurtosis",
    "tail_ratio": "Tail ratio",
    "common_sense_ratio": "Common sense ratio",
    "value_at_risk": "Daily value at risk",
    "alpha": "Alpha",
    "beta": "Beta",
}

FACTOR_PARTITIONS = {
    "style": ["momentum", "size", "value", "reversal_short_term", "volatility"],
    "sector": [
        "basic_materials",
        "consumer_cyclical",
        "financial_services",
        "real_estate",
        "consumer_defensive",
        "health_care",
        "utilities",
        "communication_services",
        "energy",
        "industrials",
        "technology",
    ],
}

STAT_FUNCS_PCT = [
    "Annual return",
    "Cumulative returns",
    "Annual volatility",
    "Max drawdown",
    "Daily value at risk",
    "Daily turnover",
]

PNL_STATS = OrderedDict(
    [
        ("Total profit", lambda x: x.sum()),
        ("Gross profit", lambda x: x[x > 0].sum()),
        ("Gross loss", lambda x: x[x < 0].sum()),
        ("Profit factor", lambda x: x[x > 0].sum() / x[x < 0].abs().sum() if x[x < 0].abs().sum() != 0 else np.nan),
        ("Avg. trade net profit", "mean"),
        ("Avg. winning trade", lambda x: x[x > 0].mean()),
        ("Avg. losing trade", lambda x: x[x < 0].mean()),
        (
            "Ratio Avg. Win:Avg. Loss",
            lambda x: x[x > 0].mean() / x[x < 0].abs().mean() if x[x < 0].abs().mean() != 0 else np.nan,
        ),
        ("Largest winning trade", "max"),
        ("Largest losing trade", "min"),
    ]
)

SUMMARY_STATS = OrderedDict(
    [
        ("Total number of round_trips", "count"),
        ("Percent profitable", lambda x: len(x[x > 0]) / float(len(x))),
        ("Winning round_trips", lambda x: len(x[x > 0])),
        ("Losing round_trips", lambda x: len(x[x < 0])),
        ("Even round_trips", lambda x: len(x[x == 0])),
    ]
)

RETURN_STATS = OrderedDict(
    [
        ("Avg returns all round_trips", lambda x: x.mean()),
        ("Avg returns winning", lambda x: x[x > 0].mean()),
        ("Avg returns losing", lambda x: x[x < 0].mean()),
        ("Median returns all round_trips", lambda x: x.median()),
        ("Median returns winning", lambda x: x[x > 0].median()),
        ("Median returns losing", lambda x: x[x < 0].median()),
        ("Largest winning trade", "max"),
        ("Largest losing trade", "min"),
    ]
)

DURATION_STATS = OrderedDict(
    [
        ("Avg duration", lambda x: x.mean()),
        ("Median duration", lambda x: x.median()),
        ("Longest duration", lambda x: x.max()),
        ("Shortest duration", lambda x: x.min()),
    ]
)

# Stats that require the full group (open_dt, close_dt) to compute calendar span.
# Used by agg_all_long_short when col="duration" via group_aware_stats.
DURATION_STATS_GROUP = OrderedDict(
    [
        (
            "Avg # round_trips per day",
            lambda data, group: (
                float(len(data)) / _duration_span_days(group)
                if len(data) > 0 and _duration_span_days(group) > 0
                else np.nan
            ),
        ),
        (
            "Avg # round_trips per month",
            lambda data, group: (
                float(len(data)) / (_duration_span_days(group) / 21.0)
                if len(data) > 0 and _duration_span_days(group) > 0
                else np.nan
            ),
        ),
    ]
)


def _duration_span_days(group: pd.DataFrame) -> float:
    """Calendar span in days: close_dt.max() - open_dt.min(). Returns 0 if missing cols or NaT."""
    if "open_dt" not in group.columns or "close_dt" not in group.columns:
        return 0.0
    span = group["close_dt"].max() - group["open_dt"].min()
    if pd.isna(span):
        return 0.0
    seconds = float(span.total_seconds())
    return max(seconds / 86400.0, 0.0)


MM_DISPLAY_UNIT = 1000000.0
