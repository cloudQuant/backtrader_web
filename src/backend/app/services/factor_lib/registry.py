"""Factor registry and built-in factor calculations."""

import statistics
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

FactorCalculator = Callable[[list[dict[str, Any]], int], list[float | None]]


@dataclass(frozen=True)
class FactorDefinition:
    """Factor metadata and calculator."""

    id: str
    name: str
    category: str
    lookback: int
    description: str
    calculator: FactorCalculator


class FactorRegistry:
    """Registry for built-in and custom factor definitions."""

    def __init__(self) -> None:
        self._factors: dict[str, FactorDefinition] = {}

    @classmethod
    def with_builtin_factors(cls) -> "FactorRegistry":
        """Build a registry populated with MVP built-in factors."""
        registry = cls()
        registry.register(
            FactorDefinition(
                id="momentum_5",
                name="5日动量",
                category="momentum",
                lookback=5,
                description="最近 5 个周期收盘价涨跌幅。",
                calculator=_calculate_momentum,
            )
        )
        registry.register(
            FactorDefinition(
                id="volatility_5",
                name="5日波动率",
                category="risk",
                lookback=5,
                description="最近 5 个周期收益率标准差。",
                calculator=_calculate_volatility,
            )
        )
        registry.register(
            FactorDefinition(
                id="reversal_1",
                name="1日反转",
                category="reversal",
                lookback=1,
                description="上一周期收益率取反。",
                calculator=_calculate_reversal,
            )
        )
        return registry

    def register(self, factor: FactorDefinition) -> None:
        """Register a factor definition."""
        self._factors[factor.id] = factor

    def list_factors(self) -> list[FactorDefinition]:
        """List all registered factors."""
        return list(self._factors.values())

    def get_factor(self, factor_id: str) -> FactorDefinition:
        """Get a factor by id."""
        return self._factors[factor_id]

    def calculate(self, factor_id: str, records: list[dict[str, Any]]) -> list[float | None]:
        """Calculate one factor for OHLCV records."""
        factor = self.get_factor(factor_id)
        return factor.calculator(records, factor.lookback)


def _close_values(records: list[dict[str, Any]]) -> list[float]:
    return [float(record["close"]) for record in records]


def _calculate_momentum(records: list[dict[str, Any]], lookback: int) -> list[float | None]:
    closes = _close_values(records)
    values: list[float | None] = []
    for index, close in enumerate(closes):
        if index < lookback or closes[index - lookback] <= 0:
            values.append(None)
            continue
        values.append(round((close - closes[index - lookback]) / closes[index - lookback], 6))
    return values


def _calculate_volatility(records: list[dict[str, Any]], lookback: int) -> list[float | None]:
    closes = _close_values(records)
    returns: list[float] = []
    values: list[float | None] = []
    for index, close in enumerate(closes):
        if index == 0 or closes[index - 1] <= 0:
            returns.append(0.0)
        else:
            returns.append((close - closes[index - 1]) / closes[index - 1])
        if index < lookback:
            values.append(None)
            continue
        values.append(round(statistics.pstdev(returns[index - lookback + 1 : index + 1]), 6))
    return values


def _calculate_reversal(records: list[dict[str, Any]], lookback: int) -> list[float | None]:
    closes = _close_values(records)
    values: list[float | None] = []
    for index, close in enumerate(closes):
        if index < lookback or closes[index - lookback] <= 0:
            values.append(None)
            continue
        period_return = (close - closes[index - lookback]) / closes[index - lookback]
        values.append(round(-period_return, 6))
    return values
