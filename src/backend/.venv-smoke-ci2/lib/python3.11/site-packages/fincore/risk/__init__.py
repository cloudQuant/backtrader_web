"""Advanced risk models for fincore.

Provides sophisticated risk measurement techniques beyond standard
volatility and VaR:
- EVT (Extreme Value Theory) models for tail risk
- GARCH models for conditional volatility
- Skew-t and other heavy-tailed distributions
"""

from __future__ import annotations

from fincore.risk.evt import (
    evt_cvar,
    evt_var,
    extreme_risk,
    gev_fit,
    gpd_fit,
    hill_estimator,
)
from fincore.risk.garch import (
    EGARCH,
    GARCH,
    GJRGARCH,
    conditional_var,
    forecast_volatility,
)

__all__ = [
    "EGARCH",
    # GARCH classes
    "GARCH",
    "GJRGARCH",
    "conditional_var",
    "evt_cvar",
    "evt_var",
    "extreme_risk",
    "forecast_volatility",
    "gev_fit",
    "gpd_fit",
    # EVT functions
    "hill_estimator",
]
