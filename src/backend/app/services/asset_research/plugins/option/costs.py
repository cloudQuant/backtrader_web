"""Explicit, immutable option-cost inputs used by exact-contract outcomes."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

_RATE_FIELDS = (
    "commission_rate",
    "exchange_fee_rate",
    "entry_slippage_rate",
    "exit_slippage_rate",
    "funding_cost_rate",
    "exercise_settlement_cost_rate",
    "other_cost_rate",
)


@dataclass(frozen=True, slots=True)
class OptionCostSnapshot:
    """All cost rates already normalized to one long-contract premium return.

    Each field is mandatory even when its value is zero.  That distinction
    prevents an incomplete source payload from being mistaken for a zero-cost
    market and keeps future replays tied to the original cost model version.
    """

    cost_model_version: str
    commission_rate: float
    exchange_fee_rate: float
    entry_slippage_rate: float
    exit_slippage_rate: float
    funding_cost_rate: float
    exercise_settlement_cost_rate: float
    other_cost_rate: float

    @property
    def total_cost_rate(self) -> float:
        return sum(getattr(self, field_name) for field_name in _RATE_FIELDS)

    def to_payload(self) -> dict[str, float | str]:
        return {
            "cost_model_version": self.cost_model_version,
            **{field_name: getattr(self, field_name) for field_name in _RATE_FIELDS},
            "total_cost_rate": self.total_cost_rate,
        }


def parse_option_cost_snapshot(
    value: object,
) -> tuple[OptionCostSnapshot | None, str | None]:
    """Require every declared cost rather than quietly filling in zeros."""
    if not isinstance(value, Mapping):
        return None, "OPTION.COST_SNAPSHOT_MISSING"
    version = value.get("cost_model_version")
    if not isinstance(version, str) or not version.strip():
        return None, "OPTION.COST_SNAPSHOT_INCOMPLETE"
    rates: dict[str, float] = {}
    for field_name in _RATE_FIELDS:
        if field_name not in value:
            return None, "OPTION.COST_SNAPSHOT_INCOMPLETE"
        rate = _rate(value[field_name])
        if rate is None:
            return None, "OPTION.COST_SNAPSHOT_INVALID"
        rates[field_name] = rate
    return (
        OptionCostSnapshot(cost_model_version=version.strip(), **rates),
        None,
    )


def _rate(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed
