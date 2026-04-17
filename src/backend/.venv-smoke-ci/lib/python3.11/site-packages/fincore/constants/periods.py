"""Project-wide period constants and annualization factors."""

from __future__ import annotations

import pandas as pd
from packaging import version as _pkg_version

__all__ = [
    "ANNUALIZATION_FACTORS",
    "APPROX_BDAYS_PER_MONTH",
    "APPROX_BDAYS_PER_YEAR",
    "DAILY",
    "MONTHLY",
    "MONTHS_PER_YEAR",
    "QTRS_PER_YEAR",
    "QUARTERLY",
    "WEEKLY",
    "WEEKS_PER_YEAR",
    "YEARLY",
]


APPROX_BDAYS_PER_MONTH = 21
APPROX_BDAYS_PER_YEAR = 252

MONTHS_PER_YEAR = 12
WEEKS_PER_YEAR = 52
QTRS_PER_YEAR = 4

DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"
QUARTERLY = "quarterly"
YEARLY = "yearly"

ANNUALIZATION_FACTORS = {
    DAILY: APPROX_BDAYS_PER_YEAR,
    WEEKLY: WEEKS_PER_YEAR,
    MONTHLY: MONTHS_PER_YEAR,
    QUARTERLY: QTRS_PER_YEAR,
    YEARLY: 1,
}


# Period to frequency mapping (version-aware for pandas 2.2+)
if _pkg_version.parse(pd.__version__) >= _pkg_version.parse("2.2.0"):
    PERIOD_TO_FREQ = {
        DAILY: "D",
        WEEKLY: "W",
        MONTHLY: "ME",
        QUARTERLY: "QE",
        YEARLY: "YE",
    }
else:
    PERIOD_TO_FREQ = {
        DAILY: "D",
        WEEKLY: "W",
        MONTHLY: "M",
        QUARTERLY: "Q",
        YEARLY: "A",
    }
