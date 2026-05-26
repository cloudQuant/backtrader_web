"""VaR and CVaR calculation service."""

import math
import random
import statistics
from typing import Literal

from app.schemas.risk_analytics import VarCvarResult

VarCvarMethod = Literal["historical", "parametric", "monte_carlo"]


class VarCvarService:
    """Calculate VaR and CVaR from strategy return series."""

    def calculate_from_equity_curve(
        self,
        equity_curve: list[float],
        *,
        method: VarCvarMethod = "historical",
        min_observations: int = 30,
    ) -> VarCvarResult:
        """Calculate VaR/CVaR from an equity curve."""
        returns = self._returns_from_equity_curve(equity_curve)
        return self.calculate_from_returns(
            returns,
            method=method,
            min_observations=min_observations,
        )

    def calculate_from_returns(
        self,
        returns: list[float],
        *,
        method: VarCvarMethod = "historical",
        min_observations: int = 30,
    ) -> VarCvarResult:
        """Calculate VaR/CVaR from periodic returns."""
        clean_returns = [float(value) for value in returns if math.isfinite(float(value))]
        if len(clean_returns) < min_observations:
            return VarCvarResult(
                status="degraded",
                method=method,
                observation_count=len(clean_returns),
                reason="insufficient_history",
            )

        if method == "historical":
            var_95, cvar_95 = self._historical_tail(clean_returns, 0.05)
            var_99, cvar_99 = self._historical_tail(clean_returns, 0.01)
        elif method == "parametric":
            var_95, cvar_95 = self._parametric_tail(clean_returns, 0.05)
            var_99, cvar_99 = self._parametric_tail(clean_returns, 0.01)
        elif method == "monte_carlo":
            simulated_returns = self._monte_carlo_returns(clean_returns)
            var_95, cvar_95 = self._historical_tail(simulated_returns, 0.05)
            var_99, cvar_99 = self._historical_tail(simulated_returns, 0.01)
        else:
            raise ValueError(f"Unsupported VaR/CVaR method: {method}")

        return VarCvarResult(
            status="ok",
            method=method,
            observation_count=len(clean_returns),
            var_95=round(var_95, 6),
            var_99=round(var_99, 6),
            cvar_95=round(cvar_95, 6),
            cvar_99=round(cvar_99, 6),
        )

    @staticmethod
    def _returns_from_equity_curve(equity_curve: list[float]) -> list[float]:
        returns: list[float] = []
        values = [float(value) for value in equity_curve if math.isfinite(float(value))]
        for previous, current in zip(values, values[1:], strict=False):
            if previous > 0:
                returns.append((current - previous) / previous)
        return returns

    @staticmethod
    def _historical_tail(returns: list[float], alpha: float) -> tuple[float, float]:
        sorted_returns = sorted(returns)
        tail_count = max(1, math.ceil(len(sorted_returns) * alpha))
        tail = sorted_returns[:tail_count]
        return tail[-1], statistics.fmean(tail)

    @staticmethod
    def _parametric_tail(returns: list[float], alpha: float) -> tuple[float, float]:
        mean = statistics.fmean(returns)
        std = statistics.pstdev(returns)
        if std == 0:
            return mean, mean
        z_score = statistics.NormalDist().inv_cdf(alpha)
        var_value = mean + z_score * std
        cvar_value = mean - std * statistics.NormalDist().pdf(z_score) / alpha
        return var_value, cvar_value

    @staticmethod
    def _monte_carlo_returns(returns: list[float], *, iterations: int = 5000) -> list[float]:
        rng = random.Random(42)
        mean = statistics.fmean(returns)
        std = statistics.pstdev(returns)
        if std == 0:
            return [mean]
        return [rng.gauss(mean, std) for _ in range(iterations)]
