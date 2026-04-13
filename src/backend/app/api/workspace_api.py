"""
Workspace API routes.

Provides CRUD for workspaces and strategy units, plus bulk operations
(batch create, batch delete, reorder, rename).
"""

import io
import zipfile
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.schemas.analytics import (
    BacktestDetailResponse,
    KlineWithSignalsResponse,
    MonthlyReturnsResponse,
)
from app.schemas.trading import (
    AutoTradingConfigPayload,
    AutoTradingScheduleItem,
    PositionManagerResponse,
    TradingDailySummaryResponse,
)
from app.schemas.workspace import (
    ApplyBestParamsRequest,
    BulkDeleteRequest,
    GroupRenameRequest,
    OptimizationArtifactResponse,
    ReportCreateRequest,
    RunUnitsRequest,
    SortRequest,
    StopUnitsRequest,
    StrategyUnitBatchCreate,
    StrategyUnitCreate,
    StrategyUnitListResponse,
    StrategyUnitResponse,
    StrategyUnitUpdate,
    UnitOptimizationRequest,
    UnitRenameRequest,
    UnitStatusResponse,
    WorkspaceCreate,
    WorkspaceListResponse,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.services.analytics_service import AnalyticsService
from app.services.workspace_service import WorkspaceService

router = APIRouter()


@lru_cache
def get_workspace_service() -> WorkspaceService:
    return WorkspaceService()


# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------


@router.post("/", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED, summary="Create workspace")
async def create_workspace(
    data: WorkspaceCreate,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Create a new workspace."""
    return await service.create_workspace(current_user.sub, data)


@router.get("/", response_model=WorkspaceListResponse, summary="List workspaces")
async def list_workspaces(
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    workspace_type: str | None = Query(None),
):
    """List workspaces for the current user."""
    total, items = await service.list_workspaces(
        current_user.sub,
        skip=skip,
        limit=limit,
        workspace_type=workspace_type,
    )
    return WorkspaceListResponse(total=total, items=items)


@router.get("/{workspace_id}", response_model=WorkspaceResponse, summary="Get workspace")
async def get_workspace(
    workspace_id: str,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Get workspace by ID."""
    ws = await service.get_workspace(workspace_id, current_user.sub)
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return ws


@router.put("/{workspace_id}", response_model=WorkspaceResponse, summary="Update workspace")
async def update_workspace(
    workspace_id: str,
    data: WorkspaceUpdate,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Update workspace by ID."""
    ws = await service.update_workspace(workspace_id, current_user.sub, data)
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return ws


@router.delete("/{workspace_id}", summary="Delete workspace")
async def delete_workspace(
    workspace_id: str,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Delete workspace by ID (cascades to units)."""
    success = await service.delete_workspace(workspace_id, current_user.sub)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return {"message": "Workspace deleted"}


# ---------------------------------------------------------------------------
# Strategy Unit CRUD
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/units", response_model=StrategyUnitListResponse, summary="List units")
async def list_units(
    workspace_id: str,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """List all strategy units in a workspace."""
    units = await service.list_units(workspace_id, current_user.sub)
    if units is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return StrategyUnitListResponse(total=len(units), items=units)


@router.post(
    "/{workspace_id}/units",
    response_model=StrategyUnitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create unit",
)
async def create_unit(
    workspace_id: str,
    data: StrategyUnitCreate,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Create a single strategy unit."""
    result = await service.create_unit(workspace_id, current_user.sub, data)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return result


@router.post(
    "/{workspace_id}/units/batch",
    response_model=list[StrategyUnitResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Batch create units",
)
async def batch_create_units(
    workspace_id: str,
    data: StrategyUnitBatchCreate,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Batch create strategy units."""
    result = await service.batch_create_units(workspace_id, current_user.sub, data.units)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return result


@router.get("/{workspace_id}/units/{unit_id}", response_model=StrategyUnitResponse, summary="Get unit")
async def get_unit(
    workspace_id: str,
    unit_id: str,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Get a single strategy unit."""
    result = await service.get_unit(workspace_id, unit_id, current_user.sub)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")
    return result


@router.put("/{workspace_id}/units/{unit_id}", response_model=StrategyUnitResponse, summary="Update unit")
async def update_unit(
    workspace_id: str,
    unit_id: str,
    data: StrategyUnitUpdate,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Update a strategy unit."""
    result = await service.update_unit(workspace_id, unit_id, current_user.sub, data)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")
    return result


@router.delete("/{workspace_id}/units/{unit_id}", summary="Delete unit")
async def delete_unit(
    workspace_id: str,
    unit_id: str,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Delete a strategy unit."""
    success = await service.delete_unit(workspace_id, unit_id, current_user.sub)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")
    return {"message": "Unit deleted"}


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/units/bulk-delete", summary="Bulk delete units")
async def bulk_delete_units(
    workspace_id: str,
    data: BulkDeleteRequest,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Bulk delete strategy units."""
    deleted = await service.bulk_delete_units(workspace_id, current_user.sub, data.ids)
    return {"deleted": deleted}


@router.post("/{workspace_id}/units/reorder", summary="Reorder units")
async def reorder_units(
    workspace_id: str,
    data: SortRequest,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Reorder strategy units by providing ordered list of IDs."""
    success = await service.reorder_units(workspace_id, current_user.sub, data.unit_ids)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return {"message": "Units reordered"}


@router.post("/{workspace_id}/units/rename-group", summary="Rename group")
async def rename_group(
    workspace_id: str,
    data: GroupRenameRequest,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Rename group for selected units."""
    success = await service.rename_group(workspace_id, current_user.sub, data)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return {"message": "Group renamed"}


@router.post("/{workspace_id}/units/rename-unit", summary="Rename unit")
async def rename_unit(
    workspace_id: str,
    data: UnitRenameRequest,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Rename a single unit."""
    success = await service.rename_unit(workspace_id, current_user.sub, data)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")
    return {"message": "Unit renamed"}


# ---------------------------------------------------------------------------
# Run orchestration (Phase 3)
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/run", summary="Run selected units")
async def run_units(
    workspace_id: str,
    data: RunUnitsRequest,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Run backtest for selected strategy units."""
    results = await service.run_units(
        workspace_id, current_user.sub, data.unit_ids, parallel=data.parallel
    )
    if not results:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace or units not found")
    return {"results": results}


@router.post("/{workspace_id}/stop", summary="Stop selected units")
async def stop_units(
    workspace_id: str,
    data: StopUnitsRequest,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Stop running strategy units."""
    results = await service.stop_units(workspace_id, current_user.sub, data.unit_ids)
    return {"results": results}


@router.get(
    "/{workspace_id}/status",
    response_model=list[UnitStatusResponse],
    summary="Poll unit statuses",
)
async def get_units_status(
    workspace_id: str,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Get current run status of all units in workspace (polling endpoint)."""
    statuses = await service.get_units_status(workspace_id, current_user.sub)
    if statuses is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return statuses


@router.get(
    "/{workspace_id}/trading/auto-config",
    response_model=AutoTradingConfigPayload,
    summary="Get trading workspace auto-trading config",
)
async def get_trading_auto_config(
    workspace_id: str,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    config = await service.get_trading_auto_config(workspace_id, current_user.sub)
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trading workspace not found")
    return config


@router.put(
    "/{workspace_id}/trading/auto-config",
    response_model=AutoTradingConfigPayload,
    summary="Update trading workspace auto-trading config",
)
async def update_trading_auto_config(
    workspace_id: str,
    data: AutoTradingConfigPayload,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    config = await service.update_trading_auto_config(
        workspace_id,
        current_user.sub,
        data.model_dump(exclude_unset=True),
    )
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trading workspace not found")
    return config


@router.get(
    "/{workspace_id}/trading/auto-schedule",
    response_model=list[AutoTradingScheduleItem],
    summary="Get trading workspace auto-trading schedule",
)
async def get_trading_auto_schedule(
    workspace_id: str,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    schedule = await service.get_trading_auto_schedule(workspace_id, current_user.sub)
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trading workspace not found")
    return schedule


@router.get(
    "/{workspace_id}/trading/positions",
    response_model=PositionManagerResponse,
    summary="Get trading workspace aggregated positions",
)
async def get_trading_positions(
    workspace_id: str,
    unit_ids: str | None = Query(None),
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    parsed_unit_ids = [value.strip() for value in str(unit_ids or "").split(",") if value.strip()]
    positions = await service.get_trading_positions(
        workspace_id,
        current_user.sub,
        unit_ids=parsed_unit_ids or None,
    )
    if positions is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trading workspace not found")
    return positions


@router.get(
    "/{workspace_id}/trading/daily-summary",
    response_model=TradingDailySummaryResponse,
    summary="Get trading workspace daily summary",
)
async def get_trading_daily_summary(
    workspace_id: str,
    unit_id: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    summary = await service.get_trading_daily_summary(
        workspace_id,
        current_user.sub,
        unit_id=unit_id,
        start_date=start_date,
        end_date=end_date,
    )
    if summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trading workspace not found")
    return summary


# ---------------------------------------------------------------------------
# Optimization (Phase 4)
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/optimize", summary="Submit unit optimization")
async def submit_unit_optimization(
    workspace_id: str,
    data: UnitOptimizationRequest,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Submit parameter optimization for a strategy unit."""
    result = await service.submit_unit_optimization(workspace_id, current_user.sub, data)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace or unit not found")
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return result


@router.get("/{workspace_id}/optimize/{unit_id}/progress", summary="Unit optimization progress")
async def get_unit_optimization_progress(
    workspace_id: str,
    unit_id: str,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Get optimization progress for a strategy unit."""
    progress = await service.get_unit_optimization_progress(workspace_id, current_user.sub, unit_id)
    if progress is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No optimization task found")
    return progress


@router.get("/{workspace_id}/optimize/{unit_id}/results", summary="Unit optimization results")
async def get_unit_optimization_results(
    workspace_id: str,
    unit_id: str,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Get optimization results for a strategy unit."""
    results = await service.get_unit_optimization_results(workspace_id, current_user.sub, unit_id)
    if results is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No optimization results found")
    return results


@router.get(
    "/{workspace_id}/optimize/{unit_id}/results/{result_index}/detail",
    response_model=BacktestDetailResponse,
    summary="Get persisted unit optimization result detail",
)
async def get_unit_optimization_result_detail(
    workspace_id: str,
    unit_id: str,
    result_index: int,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    payload = await service.get_unit_optimization_result_payload(
        workspace_id,
        current_user.sub,
        unit_id,
        result_index,
    )
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Optimization result detail not found")

    analytics_service = AnalyticsService()
    metrics = analytics_service.calculate_metrics(payload)
    return BacktestDetailResponse(
        task_id=payload["task_id"],
        strategy_name=payload["strategy_name"],
        symbol=payload["symbol"],
        start_date=payload["start_date"],
        end_date=payload["end_date"],
        metrics=metrics,
        equity_curve=analytics_service.process_equity_curve(payload["equity_curve"]),
        drawdown_curve=analytics_service.process_drawdown_curve(payload["drawdown_curve"]),
        trades=analytics_service.process_trades(payload["trades"]),
        created_at=payload["created_at"],
        artifact_path=payload.get("artifact_path"),
        artifact_manifest_path=payload.get("artifact_manifest_path"),
        artifact_summary_path=payload.get("artifact_summary_path"),
        artifact_status=payload.get("artifact_status"),
        artifact_error=payload.get("artifact_error"),
    )


@router.get(
    "/{workspace_id}/optimize/{unit_id}/results/{result_index}/kline",
    response_model=KlineWithSignalsResponse,
    summary="Get persisted unit optimization result kline",
)
async def get_unit_optimization_result_kline(
    workspace_id: str,
    unit_id: str,
    result_index: int,
    start_date: str | None = None,
    end_date: str | None = None,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    payload = await service.get_unit_optimization_result_payload(
        workspace_id,
        current_user.sub,
        unit_id,
        result_index,
    )
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Optimization result detail not found")

    analytics_service = AnalyticsService()
    klines = list(payload["klines"])
    signals = list(payload["signals"])
    if start_date:
        klines = [k for k in klines if k["date"] >= start_date]
        signals = [s for s in signals if s["date"] >= start_date]
    if end_date:
        klines = [k for k in klines if k["date"] <= end_date]
        signals = [s for s in signals if s["date"] <= end_date]
    indicators = payload.get("log_indicators") or analytics_service.calculate_indicators(klines)
    return KlineWithSignalsResponse(
        symbol=payload["symbol"],
        klines=klines,
        signals=analytics_service.process_signals(signals),
        indicators=indicators,
    )


@router.get(
    "/{workspace_id}/optimize/{unit_id}/results/{result_index}/monthly-returns",
    response_model=MonthlyReturnsResponse,
    summary="Get persisted unit optimization monthly returns",
)
async def get_unit_optimization_result_monthly_returns(
    workspace_id: str,
    unit_id: str,
    result_index: int,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    payload = await service.get_unit_optimization_result_payload(
        workspace_id,
        current_user.sub,
        unit_id,
        result_index,
    )
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Optimization result detail not found")

    analytics_service = AnalyticsService()
    return analytics_service.process_monthly_returns(payload["monthly_returns"])


@router.get(
    "/{workspace_id}/optimize/{unit_id}/results/{result_index}/artifact",
    response_model=OptimizationArtifactResponse,
    summary="Get persisted optimization artifact metadata",
)
async def get_unit_optimization_result_artifact(
    workspace_id: str,
    unit_id: str,
    result_index: int,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    payload = await service.get_unit_optimization_result_artifact_metadata(
        workspace_id,
        current_user.sub,
        unit_id,
        result_index,
    )
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Optimization artifact not found")
    return OptimizationArtifactResponse(**payload)


@router.get(
    "/{workspace_id}/optimize/{unit_id}/results/{result_index}/artifact/download",
    summary="Download persisted optimization artifact archive",
)
async def download_unit_optimization_result_artifact(
    workspace_id: str,
    unit_id: str,
    result_index: int,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    payload = await service.get_unit_optimization_result_artifact_metadata(
        workspace_id,
        current_user.sub,
        unit_id,
        result_index,
    )
    artifact_path = str((payload or {}).get("artifact_path") or "")
    artifact_dir = Path(artifact_path).expanduser() if artifact_path else None
    if payload is None or artifact_dir is None or not artifact_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Optimization artifact not found")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        root_dir = artifact_dir.parent
        manifest_path = root_dir / "manifest.json"
        summary_path = root_dir / "summary.json"
        for extra_path in (manifest_path, summary_path):
            if extra_path.is_file():
                zf.write(extra_path, arcname=str(Path(root_dir.name) / extra_path.name))
        for file_path in artifact_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, arcname=str(Path(root_dir.name) / artifact_dir.name / file_path.relative_to(artifact_dir)))
    buffer.seek(0)

    trial_index = payload.get("trial_index")
    suffix = f"trial_{int(trial_index) + 1:04d}" if isinstance(trial_index, int) else f"result_{result_index}"
    filename = f"optimization_artifact_{payload['optimization_task_id']}_{suffix}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(buffer, media_type="application/zip", headers=headers)


@router.post("/{workspace_id}/optimize/{unit_id}/cancel", summary="Cancel unit optimization")
async def cancel_unit_optimization(
    workspace_id: str,
    unit_id: str,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Cancel a running optimization task for a strategy unit."""
    result = await service.cancel_unit_optimization(workspace_id, current_user.sub, unit_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return result


@router.post("/{workspace_id}/optimize/apply", summary="Apply best optimization params")
async def apply_best_params(
    workspace_id: str,
    data: ApplyBestParamsRequest,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Apply best parameters from optimization to a strategy unit."""
    result = await service.apply_best_params(workspace_id, current_user.sub, data)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace or unit not found")
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Combined report (Phase 5)
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/report", summary="Get workspace combined report")
async def get_workspace_report(
    workspace_id: str,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Get aggregated report across all units in a workspace (default config)."""
    report = await service.get_workspace_report(workspace_id, current_user.sub)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return report


@router.post("/{workspace_id}/report", summary="Create / recalculate report with config")
async def create_workspace_report(
    workspace_id: str,
    data: ReportCreateRequest,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Generate combined report with custom configuration parameters."""
    report = await service.get_workspace_report(
        workspace_id,
        current_user.sub,
        start_date=data.start_date,
        end_date=data.end_date,
        max_cash=data.max_cash,
        calc_method=data.calc_method,
        annual_days=data.annual_days,
        weight_mode=data.weight_mode,
        weights=data.weights,
    )
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return report


@router.delete("/{workspace_id}/report", summary="Clear workspace report config cache")
async def delete_workspace_report(
    workspace_id: str,
    current_user=Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    """Clear saved report configuration cache from workspace settings.

    This does NOT delete unit metrics snapshots or run results — it only
    resets the persisted ``report_config`` in workspace settings so the
    next GET /report returns a fresh default-config aggregation.
    """
    result = await service.delete_workspace_report(workspace_id, current_user.sub)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return result
