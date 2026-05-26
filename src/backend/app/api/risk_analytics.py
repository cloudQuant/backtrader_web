"""Risk analytics API routes."""

from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.schemas.risk_analytics import (
    BenchmarkMetricsResult,
    BenchmarkReturnsResult,
    KellyResult,
    MarketRegimeResult,
    PositionSizingResult,
    StressTestRequest,
    StressTestResult,
    VarCvarResult,
)
from app.services.backtest_service import BacktestService
from app.services.market_regime import MarketRegimeDetector
from app.services.risk_analytics import (
    BenchmarkMetricsService,
    BenchmarkService,
    KellyService,
    PositionSizingService,
    StressTestService,
    VarCvarService,
)

router = APIRouter(prefix="/risk-analytics", tags=["Risk Analytics"])


@lru_cache
def get_backtest_service() -> BacktestService:
    """Return cached backtest service dependency."""
    return BacktestService()


@lru_cache
def get_var_cvar_service() -> VarCvarService:
    """Return cached VaR/CVaR service dependency."""
    return VarCvarService()


@lru_cache
def get_stress_test_service() -> StressTestService:
    """Return cached stress test service dependency."""
    return StressTestService()


@lru_cache
def get_kelly_service() -> KellyService:
    """Return cached Kelly service dependency."""
    return KellyService()


@lru_cache
def get_position_sizing_service() -> PositionSizingService:
    """Return cached position sizing service dependency."""
    return PositionSizingService()


@lru_cache
def get_benchmark_service() -> BenchmarkService:
    """Return cached benchmark service dependency."""
    return BenchmarkService()


@lru_cache
def get_benchmark_metrics_service() -> BenchmarkMetricsService:
    """Return cached benchmark metrics service dependency."""
    return BenchmarkMetricsService()


@lru_cache
def get_market_regime_detector() -> MarketRegimeDetector:
    """Return cached market regime detector dependency."""
    return MarketRegimeDetector()


@router.get(
    "/var-cvar/{backtest_id}",
    response_model=VarCvarResult,
    summary="Calculate VaR/CVaR for a backtest",
)
async def get_var_cvar(
    backtest_id: str,
    method: Literal["historical", "parametric", "monte_carlo"] = "historical",
    current_user=Depends(get_current_user),
    backtest_service: BacktestService = Depends(get_backtest_service),
    var_cvar_service: VarCvarService = Depends(get_var_cvar_service),
) -> VarCvarResult:
    """Calculate VaR/CVaR from a completed backtest equity curve."""
    result = await backtest_service.get_result(backtest_id, user_id=current_user.sub)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found",
        )

    calculation = var_cvar_service.calculate_from_equity_curve(result.equity_curve, method=method)
    calculation.backtest_id = backtest_id
    return calculation


@router.post(
    "/stress-test/{backtest_id}",
    response_model=StressTestResult,
    summary="Run stress scenarios for a backtest",
)
async def run_stress_test(
    backtest_id: str,
    request: StressTestRequest,
    current_user=Depends(get_current_user),
    backtest_service: BacktestService = Depends(get_backtest_service),
    stress_test_service: StressTestService = Depends(get_stress_test_service),
) -> StressTestResult:
    """Run stress scenarios against a completed backtest equity curve."""
    result = await backtest_service.get_result(backtest_id, user_id=current_user.sub)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found",
        )

    calculation = stress_test_service.run_scenarios(
        equity_curve=result.equity_curve,
        equity_dates=result.equity_dates,
        scenarios=request.scenarios,
    )
    calculation.backtest_id = backtest_id
    return calculation


@router.get(
    "/kelly/{backtest_id}",
    response_model=KellyResult,
    summary="Calculate Kelly position sizing for a backtest",
)
async def get_kelly(
    backtest_id: str,
    current_user=Depends(get_current_user),
    backtest_service: BacktestService = Depends(get_backtest_service),
    kelly_service: KellyService = Depends(get_kelly_service),
) -> KellyResult:
    """Calculate Kelly position sizing recommendations from backtest trades."""
    result = await backtest_service.get_result(backtest_id, user_id=current_user.sub)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found",
        )

    calculation = kelly_service.calculate(result.trades)
    calculation.backtest_id = backtest_id
    return calculation


@router.get(
    "/position-sizing/{backtest_id}",
    response_model=PositionSizingResult,
    summary="Calculate volatility-targeted position sizing for a backtest",
)
async def get_position_sizing(
    backtest_id: str,
    target_volatility: float = 0.15,
    max_position: float = 1.0,
    min_observations: int = 5,
    current_user=Depends(get_current_user),
    backtest_service: BacktestService = Depends(get_backtest_service),
    position_sizing_service: PositionSizingService = Depends(get_position_sizing_service),
) -> PositionSizingResult:
    """Calculate volatility target position sizing from backtest equity curve."""
    result = await backtest_service.get_result(backtest_id, user_id=current_user.sub)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found",
        )

    calculation = position_sizing_service.calculate_for_equity_curve(
        result.equity_curve,
        target_volatility=target_volatility,
        max_position=max_position,
        min_observations=min_observations,
    )
    calculation.backtest_id = backtest_id
    return calculation


@router.get(
    "/benchmark/{benchmark_id}",
    response_model=BenchmarkReturnsResult,
    summary="Get benchmark return series",
)
async def get_benchmark_returns(
    benchmark_id: str,
    start_date: str,
    end_date: str,
    current_user=Depends(get_current_user),
    benchmark_service: BenchmarkService = Depends(get_benchmark_service),
) -> BenchmarkReturnsResult:
    """Fetch benchmark prices and derive return series."""
    return await benchmark_service.get_benchmark_returns(benchmark_id, start_date, end_date)


@router.get(
    "/benchmark-metrics/{backtest_id}",
    response_model=BenchmarkMetricsResult,
    summary="Calculate strategy metrics relative to benchmark",
)
async def get_benchmark_metrics(
    backtest_id: str,
    benchmark_id: str = "hs300",
    risk_free_rate: float = 0.0,
    current_user=Depends(get_current_user),
    backtest_service: BacktestService = Depends(get_backtest_service),
    benchmark_service: BenchmarkService = Depends(get_benchmark_service),
    benchmark_metrics_service: BenchmarkMetricsService = Depends(get_benchmark_metrics_service),
) -> BenchmarkMetricsResult:
    """Calculate alpha, beta, tracking error, and information ratio."""
    result = await backtest_service.get_result(backtest_id, user_id=current_user.sub)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found",
        )

    benchmark = await benchmark_service.get_benchmark_returns(
        benchmark_id,
        result.equity_dates[0] if result.equity_dates else result.start_date.date().isoformat(),
        result.equity_dates[-1] if result.equity_dates else result.end_date.date().isoformat(),
    )
    metrics = benchmark_metrics_service.calculate(
        strategy_returns=benchmark_metrics_service.returns_from_equity_curve(result.equity_curve),
        benchmark_returns=benchmark.returns,
        benchmark_id=benchmark_id,
        risk_free_rate=risk_free_rate,
    )
    metrics.backtest_id = backtest_id
    return metrics


@router.get(
    "/market-regime/{backtest_id}",
    response_model=MarketRegimeResult,
    summary="Classify market regime for a backtest",
)
async def get_market_regime(
    backtest_id: str,
    current_user=Depends(get_current_user),
    backtest_service: BacktestService = Depends(get_backtest_service),
    detector: MarketRegimeDetector = Depends(get_market_regime_detector),
) -> MarketRegimeResult:
    """Classify volatility and trend regime from backtest equity curve."""
    result = await backtest_service.get_result(backtest_id, user_id=current_user.sub)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found",
        )
    regime = detector.detect(result.equity_curve)
    regime.backtest_id = backtest_id
    return regime
