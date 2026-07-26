"""Brinson performance attribution."""

from app.schemas.perf_attribution import BrinsonAttributionResult


class BrinsonAttributionService:
    """Calculate Brinson allocation, selection, and interaction effects."""

    def calculate(
        self,
        *,
        portfolio_weights: dict[str, float],
        benchmark_weights: dict[str, float],
        portfolio_returns: dict[str, float],
        benchmark_returns: dict[str, float],
    ) -> BrinsonAttributionResult:
        """Calculate Brinson attribution effects for shared assets."""
        assets = sorted(
            set(portfolio_weights)
            & set(benchmark_weights)
            & set(portfolio_returns)
            & set(benchmark_returns)
        )
        if not assets:
            return BrinsonAttributionResult(status="degraded", reason="insufficient_assets")

        allocation_effect = 0.0
        selection_effect = 0.0
        interaction_effect = 0.0
        for asset in assets:
            portfolio_weight = float(portfolio_weights[asset])
            benchmark_weight = float(benchmark_weights[asset])
            portfolio_return = float(portfolio_returns[asset])
            benchmark_return = float(benchmark_returns[asset])
            allocation_effect += (portfolio_weight - benchmark_weight) * benchmark_return
            selection_effect += benchmark_weight * (portfolio_return - benchmark_return)
            interaction_effect += (portfolio_weight - benchmark_weight) * (
                portfolio_return - benchmark_return
            )

        total_excess_return = allocation_effect + selection_effect + interaction_effect
        return BrinsonAttributionResult(
            status="ok",
            asset_count=len(assets),
            allocation_effect=round(allocation_effect, 6),
            selection_effect=round(selection_effect, 6),
            interaction_effect=round(interaction_effect, 6),
            total_excess_return=round(total_excess_return, 6),
        )
