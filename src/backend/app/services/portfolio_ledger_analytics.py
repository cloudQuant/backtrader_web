from __future__ import annotations

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.portfolio_ledger import (
    PortfolioLedgerBenchmarkMetricsResult,
    PortfolioLedgerBrinsonRequest,
    PortfolioLedgerBrinsonResult,
    PortfolioLedgerFamaFrenchRequest,
    PortfolioLedgerFamaFrenchResult,
    PortfolioLedgerPositionSizingResult,
    PortfolioLedgerVarCvarResult,
)
from app.services.perf_attribution import BrinsonAttributionService, FamaFrenchAttributionService
from app.services.portfolio_ledger import PortfolioLedgerService, get_portfolio_ledger_service
from app.services.risk_analytics import (
    BenchmarkMetricsService,
    BenchmarkService,
    PositionSizingService,
    VarCvarService,
)
from app.services.risk_analytics.benchmark import BENCHMARK_SYMBOLS

VarCvarMethod = Literal["historical", "parametric", "monte_carlo"]


class PortfolioLedgerAnalyticsService:
    def __init__(
        self,
        ledger_service: PortfolioLedgerService,
        *,
        benchmark_service: BenchmarkService | None = None,
        benchmark_metrics_service: BenchmarkMetricsService | None = None,
        var_cvar_service: VarCvarService | None = None,
        position_sizing_service: PositionSizingService | None = None,
        brinson_service: BrinsonAttributionService | None = None,
        fama_french_service: FamaFrenchAttributionService | None = None,
    ) -> None:
        self.ledger_service = ledger_service
        self.benchmark_service = benchmark_service or BenchmarkService()
        self.benchmark_metrics_service = benchmark_metrics_service or BenchmarkMetricsService()
        self.var_cvar_service = var_cvar_service or VarCvarService()
        self.position_sizing_service = position_sizing_service or PositionSizingService()
        self.brinson_service = brinson_service or BrinsonAttributionService()
        self.fama_french_service = fama_french_service or FamaFrenchAttributionService()

    async def get_var_cvar(
        self,
        user_id: str,
        portfolio_id: str,
        *,
        method: VarCvarMethod = "historical",
    ) -> PortfolioLedgerVarCvarResult | None:
        context = await self.ledger_service.analytics_context(user_id, portfolio_id)
        if context is None:
            return None
        result = self.var_cvar_service.calculate_from_equity_curve(
            list(context["equity_curve"]),
            method=method,
        )
        return PortfolioLedgerVarCvarResult(
            portfolio_id=portfolio_id,
            status=result.status,
            method=result.method,
            observation_count=result.observation_count,
            var_95=result.var_95,
            var_99=result.var_99,
            cvar_95=result.cvar_95,
            cvar_99=result.cvar_99,
            reason=result.reason,
        )

    async def get_position_sizing(
        self,
        user_id: str,
        portfolio_id: str,
        *,
        target_volatility: float = 0.15,
        max_position: float = 1.0,
    ) -> PortfolioLedgerPositionSizingResult | None:
        context = await self.ledger_service.analytics_context(user_id, portfolio_id)
        if context is None:
            return None
        result = self.position_sizing_service.calculate_for_equity_curve(
            list(context["equity_curve"]),
            target_volatility=target_volatility,
            max_position=max_position,
        )
        return PortfolioLedgerPositionSizingResult(
            portfolio_id=portfolio_id,
            status=result.status,
            method=result.method,
            observation_count=result.observation_count,
            annualized_volatility=result.annualized_volatility,
            target_volatility=result.target_volatility,
            recommended_position=result.recommended_position,
            max_position=result.max_position,
            reason=result.reason,
        )

    async def get_benchmark_metrics(
        self,
        user_id: str,
        portfolio_id: str,
        *,
        benchmark_id: str | None = None,
        risk_free_rate: float = 0.0,
    ) -> PortfolioLedgerBenchmarkMetricsResult | None:
        context = await self.ledger_service.analytics_context(user_id, portfolio_id)
        if context is None:
            return None
        equity_dates = [str(item) for item in context["equity_dates"]]
        if len(equity_dates) < 2:
            return PortfolioLedgerBenchmarkMetricsResult(
                portfolio_id=portfolio_id,
                status="degraded",
                benchmark_id=self._resolve_benchmark_id(
                    benchmark_id,
                    context["portfolio"].get("benchmark_symbol"),
                ),
                observation_count=max(len(equity_dates) - 1, 0),
                risk_free_rate=risk_free_rate,
                reason="insufficient_history",
            )
        resolved_benchmark_id = self._resolve_benchmark_id(
            benchmark_id,
            context["portfolio"].get("benchmark_symbol"),
        )
        benchmark = await self.benchmark_service.get_benchmark_returns(
            resolved_benchmark_id,
            equity_dates[0],
            equity_dates[-1],
        )
        if benchmark.status != "ok":
            return PortfolioLedgerBenchmarkMetricsResult(
                portfolio_id=portfolio_id,
                status="degraded",
                benchmark_id=resolved_benchmark_id,
                observation_count=max(len(equity_dates) - 1, 0),
                risk_free_rate=risk_free_rate,
                reason=benchmark.reason,
            )
        result = self.benchmark_metrics_service.calculate(
            strategy_returns=self.benchmark_metrics_service.returns_from_equity_curve(
                list(context["equity_curve"])
            ),
            benchmark_returns=list(benchmark.returns),
            benchmark_id=resolved_benchmark_id,
            risk_free_rate=risk_free_rate,
        )
        return PortfolioLedgerBenchmarkMetricsResult(
            portfolio_id=portfolio_id,
            status=result.status,
            benchmark_id=result.benchmark_id,
            observation_count=result.observation_count,
            alpha=result.alpha,
            beta=result.beta,
            tracking_error=result.tracking_error,
            information_ratio=result.information_ratio,
            risk_free_rate=result.risk_free_rate,
            reason=result.reason,
        )

    async def calculate_brinson(
        self,
        user_id: str,
        portfolio_id: str,
        request: PortfolioLedgerBrinsonRequest,
    ) -> PortfolioLedgerBrinsonResult | None:
        context = await self.ledger_service.analytics_context(user_id, portfolio_id)
        if context is None:
            return None
        position_stats = dict(context["position_stats"])
        result = self.brinson_service.calculate(
            portfolio_weights=self._portfolio_weights(position_stats),
            benchmark_weights=dict(request.benchmark_weights),
            portfolio_returns=self._portfolio_returns(position_stats),
            benchmark_returns=dict(request.benchmark_returns),
        )
        return PortfolioLedgerBrinsonResult(
            portfolio_id=portfolio_id,
            status=result.status,
            asset_count=result.asset_count,
            allocation_effect=result.allocation_effect,
            selection_effect=result.selection_effect,
            interaction_effect=result.interaction_effect,
            total_excess_return=result.total_excess_return,
            reason=result.reason,
        )

    async def calculate_fama_french(
        self,
        user_id: str,
        portfolio_id: str,
        request: PortfolioLedgerFamaFrenchRequest,
    ) -> PortfolioLedgerFamaFrenchResult | None:
        context = await self.ledger_service.analytics_context(user_id, portfolio_id)
        if context is None:
            return None
        strategy_returns = self.benchmark_metrics_service.returns_from_equity_curve(
            list(context["equity_curve"])
        )
        benchmark_id = self._resolve_benchmark_id(
            request.benchmark_id,
            context["portfolio"].get("benchmark_symbol"),
        )
        market_returns = list(request.market_returns or [])
        if not market_returns:
            equity_dates = [str(item) for item in context["equity_dates"]]
            if len(equity_dates) < 2:
                return PortfolioLedgerFamaFrenchResult(
                    portfolio_id=portfolio_id,
                    benchmark_id=benchmark_id,
                    status="degraded",
                    observation_count=max(len(strategy_returns), 0),
                    reason="insufficient_history",
                )
            benchmark = await self.benchmark_service.get_benchmark_returns(
                benchmark_id,
                equity_dates[0],
                equity_dates[-1],
            )
            if benchmark.status != "ok":
                return PortfolioLedgerFamaFrenchResult(
                    portfolio_id=portfolio_id,
                    benchmark_id=benchmark_id,
                    status="degraded",
                    observation_count=max(len(strategy_returns), 0),
                    reason=benchmark.reason,
                )
            market_returns = list(benchmark.returns)
        result = self.fama_french_service.calculate(
            strategy_returns=strategy_returns,
            market_returns=market_returns,
            smb_returns=list(request.smb_returns),
            hml_returns=list(request.hml_returns),
        )
        return PortfolioLedgerFamaFrenchResult(
            portfolio_id=portfolio_id,
            benchmark_id=benchmark_id,
            status=result.status,
            observation_count=result.observation_count,
            alpha=result.alpha,
            market_beta=result.market_beta,
            smb_beta=result.smb_beta,
            hml_beta=result.hml_beta,
            r_squared=result.r_squared,
            reason=result.reason,
        )

    def _resolve_benchmark_id(
        self,
        explicit_benchmark_id: str | None,
        portfolio_benchmark_symbol: str | None,
    ) -> str:
        raw = str(explicit_benchmark_id or portfolio_benchmark_symbol or "hs300").strip()
        normalized = raw.lower()
        if normalized in BENCHMARK_SYMBOLS:
            return normalized
        for benchmark_id, symbol in BENCHMARK_SYMBOLS.items():
            if raw.upper() == symbol.upper():
                return benchmark_id
        return normalized or "hs300"

    def _portfolio_weights(self, position_stats: dict[str, dict[str, float]]) -> dict[str, float]:
        values = {
            symbol: abs(float(item.get("market_value") or 0.0))
            for symbol, item in position_stats.items()
            if abs(float(item.get("quantity") or 0.0)) > 0
        }
        total = sum(values.values())
        if total <= 0:
            return {}
        return {symbol: round(value / total, 6) for symbol, value in values.items()}

    def _portfolio_returns(self, position_stats: dict[str, dict[str, float]]) -> dict[str, float]:
        return {
            symbol: round(float(item.get("return_ratio") or 0.0), 6)
            for symbol, item in position_stats.items()
            if abs(float(item.get("quantity") or 0.0)) > 0
        }


def get_portfolio_ledger_analytics_service(db: AsyncSession) -> PortfolioLedgerAnalyticsService:
    return PortfolioLedgerAnalyticsService(get_portfolio_ledger_service(db))
