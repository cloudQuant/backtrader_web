"""Benchmark comparison metric calculations."""

import math
import statistics

from app.schemas.risk_analytics import BenchmarkMetricsResult


class BenchmarkMetricsService:
    """Calculate strategy performance metrics relative to a benchmark."""

    def calculate(
        self,
        *,
        strategy_returns: list[float],
        benchmark_returns: list[float],
        benchmark_id: str,
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252,
    ) -> BenchmarkMetricsResult:
        """Calculate alpha, beta, tracking error, and information ratio."""
        count = min(len(strategy_returns), len(benchmark_returns))
        if count < 2:
            return BenchmarkMetricsResult(
                status="degraded",
                benchmark_id=benchmark_id,
                observation_count=count,
                risk_free_rate=risk_free_rate,
                reason="insufficient_overlap",
            )

        strategy = [float(value) for value in strategy_returns[:count]]
        benchmark = [float(value) for value in benchmark_returns[:count]]
        benchmark_variance = statistics.pvariance(benchmark)
        if benchmark_variance <= 0:
            return BenchmarkMetricsResult(
                status="degraded",
                benchmark_id=benchmark_id,
                observation_count=count,
                risk_free_rate=risk_free_rate,
                reason="zero_benchmark_variance",
            )

        strategy_mean = statistics.fmean(strategy)
        benchmark_mean = statistics.fmean(benchmark)
        covariance = statistics.fmean(
            (strategy_value - strategy_mean) * (benchmark_value - benchmark_mean)
            for strategy_value, benchmark_value in zip(strategy, benchmark, strict=False)
        )
        beta = covariance / benchmark_variance
        period_risk_free = risk_free_rate / periods_per_year
        alpha = (
            strategy_mean - period_risk_free - beta * (benchmark_mean - period_risk_free)
        ) * periods_per_year
        active_returns = [
            strategy_value - benchmark_value
            for strategy_value, benchmark_value in zip(strategy, benchmark, strict=False)
        ]
        active_std = statistics.pstdev(active_returns)
        tracking_error = active_std * math.sqrt(periods_per_year)
        information_ratio = (
            statistics.fmean(active_returns) / active_std * math.sqrt(periods_per_year)
            if active_std > 0
            else None
        )
        return BenchmarkMetricsResult(
            status="ok",
            benchmark_id=benchmark_id,
            observation_count=count,
            alpha=round(alpha, 6),
            beta=round(beta, 6),
            tracking_error=round(tracking_error, 6),
            information_ratio=round(information_ratio, 6)
            if information_ratio is not None
            else None,
            risk_free_rate=round(risk_free_rate, 6),
        )

    @staticmethod
    def returns_from_equity_curve(equity_curve: list[float]) -> list[float]:
        """Calculate close-to-close returns from an equity curve."""
        returns: list[float] = []
        values = [float(value) for value in equity_curve if math.isfinite(float(value))]
        for previous, current in zip(values, values[1:], strict=False):
            if previous > 0:
                returns.append((current - previous) / previous)
        return returns
