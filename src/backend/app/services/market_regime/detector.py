"""Threshold-based market regime detector."""

import math
import statistics

from app.schemas.risk_analytics import MarketRegimeResult


class MarketRegimeDetector:
    """Classify market regime from a price or equity series."""

    def detect(self, prices: list[float], *, min_observations: int = 30) -> MarketRegimeResult:
        """Classify volatility and trend regimes with threshold rules."""
        values = [float(value) for value in prices if math.isfinite(float(value))]
        if len(values) < min_observations:
            return MarketRegimeResult(
                status="degraded",
                observation_count=len(values),
                reason="insufficient_history",
            )

        returns = [
            (current - previous) / previous
            for previous, current in zip(values, values[1:], strict=False)
            if previous > 0
        ]
        annualized_volatility = (
            statistics.pstdev(returns) * math.sqrt(252) if len(returns) >= 2 else 0.0
        )
        trend_return = (values[-1] - values[0]) / values[0] if values[0] > 0 else 0.0
        volatility_regime = self._volatility_regime(annualized_volatility)
        trend_regime = self._trend_regime(trend_return)
        return MarketRegimeResult(
            status="ok",
            observation_count=len(values),
            volatility_regime=volatility_regime,
            trend_regime=trend_regime,
            overall_regime=f"{trend_regime}_{volatility_regime}_vol",
            annualized_volatility=round(annualized_volatility, 6),
            trend_return=round(trend_return, 6),
        )

    @staticmethod
    def _volatility_regime(annualized_volatility: float) -> str:
        if annualized_volatility >= 0.35:
            return "high"
        if annualized_volatility >= 0.15:
            return "medium"
        return "low"

    @staticmethod
    def _trend_regime(trend_return: float) -> str:
        if trend_return >= 0.05:
            return "bull"
        if trend_return <= -0.05:
            return "bear"
        return "sideways"
