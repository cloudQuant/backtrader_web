from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.database import get_db
from app.schemas.portfolio_ledger import (
    PortfolioLedgerBenchmarkMetricsResult,
    PortfolioLedgerBrinsonRequest,
    PortfolioLedgerBrinsonResult,
    PortfolioLedgerFamaFrenchRequest,
    PortfolioLedgerFamaFrenchResult,
    PortfolioLedgerPositionSizingResult,
    PortfolioLedgerVarCvarResult,
)
from app.services.portfolio_ledger import get_portfolio_ledger_service
from app.services.portfolio_ledger_analytics import get_portfolio_ledger_analytics_service

router = APIRouter(prefix="/portfolio-ledger", tags=["Portfolio Ledger"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    payload: dict,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_portfolio_ledger_service(db).create_portfolio(
        current_user.sub,
        str(payload["name"]),
        str(payload.get("base_currency") or "CNY"),
        str(payload.get("source_type") or "manual"),
        benchmark_symbol=str(payload.get("benchmark_symbol") or "").strip() or None,
        tags=list(payload.get("tags") or []),
        notes=str(payload.get("notes") or "").strip() or None,
    )


@router.get("")
async def list_portfolios(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_portfolio_ledger_service(db).list_portfolios(current_user.sub)


@router.get("/{portfolio_id}")
async def get_portfolio(
    portfolio_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await get_portfolio_ledger_service(db).get_portfolio(current_user.sub, portfolio_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio_not_found")
    return result


@router.post("/{portfolio_id}/import")
async def import_transactions(
    portfolio_id: str,
    payload: dict,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await get_portfolio_ledger_service(db).import_transactions(
        current_user.sub,
        portfolio_id,
        idempotency_key=str(payload["idempotency_key"]),
        transactions=list(payload.get("transactions") or []),
        import_format=str(payload.get("format") or "json"),
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio_not_found")
    return result


@router.get("/{portfolio_id}/holdings")
async def get_holdings(
    portfolio_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await get_portfolio_ledger_service(db).holdings(current_user.sub, portfolio_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio_not_found")
    return result


@router.get("/{portfolio_id}/transactions")
async def get_transactions(
    portfolio_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await get_portfolio_ledger_service(db).list_transactions(
        current_user.sub,
        portfolio_id,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio_not_found")
    return result


@router.get("/{portfolio_id}/snapshots")
async def get_snapshots(
    portfolio_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await get_portfolio_ledger_service(db).snapshots(current_user.sub, portfolio_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio_not_found")
    return result


@router.post("/{portfolio_id}/snapshots/backfill")
async def backfill_snapshots(
    portfolio_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await get_portfolio_ledger_service(db).backfill_snapshots(
        current_user.sub,
        portfolio_id,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio_not_found")
    return result


@router.get("/{portfolio_id}/export")
async def export_portfolio(
    portfolio_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await get_portfolio_ledger_service(db).export_portfolio(current_user.sub, portfolio_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio_not_found")
    return result


@router.get(
    "/{portfolio_id}/analytics/var-cvar",
    response_model=PortfolioLedgerVarCvarResult,
)
async def get_portfolio_var_cvar(
    portfolio_id: str,
    method: str = "historical",
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await get_portfolio_ledger_analytics_service(db).get_var_cvar(
        current_user.sub,
        portfolio_id,
        method=method,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio_not_found")
    return result


@router.get(
    "/{portfolio_id}/analytics/position-sizing",
    response_model=PortfolioLedgerPositionSizingResult,
)
async def get_portfolio_position_sizing(
    portfolio_id: str,
    target_volatility: float = 0.15,
    max_position: float = 1.0,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await get_portfolio_ledger_analytics_service(db).get_position_sizing(
        current_user.sub,
        portfolio_id,
        target_volatility=target_volatility,
        max_position=max_position,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio_not_found")
    return result


@router.get(
    "/{portfolio_id}/analytics/benchmark-metrics",
    response_model=PortfolioLedgerBenchmarkMetricsResult,
)
async def get_portfolio_benchmark_metrics(
    portfolio_id: str,
    benchmark_id: str | None = None,
    risk_free_rate: float = 0.0,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await get_portfolio_ledger_analytics_service(db).get_benchmark_metrics(
        current_user.sub,
        portfolio_id,
        benchmark_id=benchmark_id,
        risk_free_rate=risk_free_rate,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio_not_found")
    return result


@router.post(
    "/{portfolio_id}/analytics/brinson",
    response_model=PortfolioLedgerBrinsonResult,
)
async def calculate_portfolio_brinson(
    portfolio_id: str,
    payload: PortfolioLedgerBrinsonRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await get_portfolio_ledger_analytics_service(db).calculate_brinson(
        current_user.sub,
        portfolio_id,
        payload,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio_not_found")
    return result


@router.post(
    "/{portfolio_id}/analytics/fama-french",
    response_model=PortfolioLedgerFamaFrenchResult,
)
async def calculate_portfolio_fama_french(
    portfolio_id: str,
    payload: PortfolioLedgerFamaFrenchRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await get_portfolio_ledger_analytics_service(db).calculate_fama_french(
        current_user.sub,
        portfolio_id,
        payload,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio_not_found")
    return result
