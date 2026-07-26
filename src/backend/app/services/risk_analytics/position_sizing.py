"""Position sizing helpers for volatility targeting and risk parity."""

import math
import statistics

from app.schemas.risk_analytics import PositionSizingResult


class PositionSizingService:
    """Calculate position sizing recommendations from return volatility."""

    def calculate_for_equity_curve(
        self,
        equity_curve: list[float],
        *,
        target_volatility: float = 0.15,
        max_position: float = 1.0,
        min_observations: int = 30,
    ) -> PositionSizingResult:
        """Calculate volatility-targeted position fraction from an equity curve."""
        returns = self._returns_from_equity_curve(equity_curve)
        if len(returns) < min_observations:
            return PositionSizingResult(
                status="degraded",
                method="volatility_target",
                observation_count=len(returns),
                target_volatility=target_volatility,
                max_position=max_position,
                reason="insufficient_history",
            )

        annualized_volatility = statistics.pstdev(returns) * math.sqrt(252)
        if annualized_volatility <= 0:
            return PositionSizingResult(
                status="degraded",
                method="volatility_target",
                observation_count=len(returns),
                target_volatility=target_volatility,
                max_position=max_position,
                reason="zero_volatility",
            )

        position = min(max_position, target_volatility / annualized_volatility)
        return PositionSizingResult(
            status="ok",
            method="volatility_target",
            observation_count=len(returns),
            annualized_volatility=round(annualized_volatility, 6),
            target_volatility=round(target_volatility, 6),
            recommended_position=round(max(0.0, position), 6),
            max_position=round(max_position, 6),
        )

    @staticmethod
    def calculate_risk_parity_weights(volatilities: dict[str, float]) -> dict[str, float]:
        """Calculate inverse-volatility risk parity weights."""
        inverse_vols = {
            asset: 1.0 / float(volatility)
            for asset, volatility in volatilities.items()
            if float(volatility) > 0
        }
        total = sum(inverse_vols.values())
        if total <= 0:
            return {}
        return {asset: weight / total for asset, weight in inverse_vols.items()}

    @staticmethod
    def _returns_from_equity_curve(equity_curve: list[float]) -> list[float]:
        returns: list[float] = []
        values = [float(value) for value in equity_curve if math.isfinite(float(value))]
        for previous, current in zip(values, values[1:], strict=False):
            if previous > 0:
                returns.append((current - previous) / previous)
        return returns
