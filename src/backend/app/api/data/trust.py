"""Market data trust API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.schemas.market_data_trust import (
    AssetSpecResponse,
    DataPrecheckRequest,
    DataPrecheckResponse,
    ExecutionModelResponse,
    MarketDataCoverageMatrixResponse,
)
from app.services.asset_spec_service import get_asset_spec_service
from app.services.backtest.execution_model import ExecutionModel
from app.services.market_data_coverage_service import get_market_data_coverage_service
from app.services.market_data_precheck_service import get_market_data_precheck_service

router = APIRouter()


@router.get(
    "/asset-specs/{symbol}",
    response_model=AssetSpecResponse,
    summary="Resolve asset specification",
)
async def get_asset_spec(
    symbol: str,
    asset_type: str | None = Query(None),
    current_user=Depends(get_current_user),
):
    del current_user
    return await get_asset_spec_service().get_or_create(symbol=symbol, asset_type=asset_type)


@router.get(
    "/asset-specs/{symbol}/execution-model",
    response_model=ExecutionModelResponse,
    summary="Resolve backtest execution model",
)
async def get_execution_model(
    symbol: str,
    asset_type: str | None = Query(None),
    current_user=Depends(get_current_user),
):
    del current_user
    spec = await get_asset_spec_service().get_or_create(symbol=symbol, asset_type=asset_type)
    payload = spec.model_dump(mode="python")
    return ExecutionModel.from_asset_spec(payload).to_response()


@router.get(
    "/coverage",
    response_model=MarketDataCoverageMatrixResponse,
    summary="List market data coverage matrix",
)
async def list_market_data_coverage(
    asset_type: str | None = Query(None),
    symbol: str | None = Query(None),
    timeframe: str | None = Query(None),
    provider: str | None = Query(None),
    refresh_if_empty: bool = Query(True),
    limit: int = Query(200, ge=1, le=1000),
    current_user=Depends(get_current_user),
):
    del current_user
    return await get_market_data_coverage_service().list_coverage(
        asset_type=asset_type,
        symbol=symbol,
        timeframe=timeframe,
        provider=provider,
        limit=limit,
        refresh_if_empty=refresh_if_empty,
    )


@router.post(
    "/coverage/refresh-local",
    response_model=MarketDataCoverageMatrixResponse,
    summary="Refresh local CSV coverage matrix",
)
async def refresh_local_coverage(
    asset_type: str | None = Query(None),
    symbol: str | None = Query(None),
    timeframe: str | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    current_user=Depends(get_current_user),
):
    del current_user
    return await get_market_data_coverage_service().refresh_local_csv_coverage(
        asset_type=asset_type,
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )


@router.post(
    "/precheck",
    response_model=DataPrecheckResponse,
    summary="Run market data precheck for a backtest",
)
async def run_data_precheck(
    request: DataPrecheckRequest,
    current_user=Depends(get_current_user),
):
    del current_user
    try:
        return await get_market_data_precheck_service().precheck(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
