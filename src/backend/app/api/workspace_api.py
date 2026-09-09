"""
Workspace API routes.

Provides CRUD for workspaces and strategy units, plus bulk operations
(batch create, batch delete, reorder, rename).
"""

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from app.api._dependencies import get_current_user
from app.schemas.auth import TokenPayload
from app.schemas.trading import (
    AutoTradingConfigPayload,
    AutoTradingScheduleItem,
    PositionManagerResponse,
    TradingDailySummaryResponse,
)
from app.schemas.workspace import (
    BulkDeleteRequest,
    GroupRenameRequest,
    ReportCreateRequest,
    RunUnitsRequest,
    SortRequest,
    StopUnitsRequest,
    StrategyUnitBatchCreate,
    StrategyUnitCreate,
    StrategyUnitListResponse,
    StrategyUnitResponse,
    StrategyUnitUpdate,
    UnitRenameRequest,
    UnitRuntimeInfoResponse,
    UnitStatusResponse,
    WorkspaceCreate,
    WorkspaceListResponse,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.services.workspace.units import (
    AIStrategyResearchPaperRuntimeStopError,
    AIStrategyResearchUnitMutationError,
    MarketDataBindingUnitMutationError,
)
from app.services.workspace_service import WorkspaceService

router = APIRouter()

_SERVER_OWNED_AI_RESEARCH_SETTINGS_PREFIX = "ai_research"


def _server_owned_ai_research_settings_path(
    value: Any,
    *,
    path: tuple[str, ...] = (),
) -> str | None:
    """Return a reserved settings path supplied through a public workspace API.

    Research task/run snapshots are server-owned provenance.  They are stored
    under ``settings.ai_research`` for recovery, but an owner must not be able
    to construct or amend them through the generic workspace settings API.
    Scan nested maps and lists as well: a future settings deep-merge must not
    turn a nested client value into trusted research state.
    """
    if isinstance(value, dict):
        for raw_key, nested_value in value.items():
            key = str(raw_key).strip()
            normalized = key.casefold()
            next_path = (*path, key)
            if normalized == _SERVER_OWNED_AI_RESEARCH_SETTINGS_PREFIX or normalized.startswith(
                f"{_SERVER_OWNED_AI_RESEARCH_SETTINGS_PREFIX}_"
            ):
                return ".".join(next_path)
            nested_path = _server_owned_ai_research_settings_path(
                nested_value,
                path=next_path,
            )
            if nested_path is not None:
                return nested_path
    elif isinstance(value, list):
        for index, nested_value in enumerate(value):
            nested_path = _server_owned_ai_research_settings_path(
                nested_value,
                path=(*path, str(index)),
            )
            if nested_path is not None:
                return nested_path
    return None


def _reject_server_owned_ai_research_settings(settings: dict[str, Any] | None) -> None:
    """Reject client attempts to write server-owned AI-research provenance."""
    reserved_path = _server_owned_ai_research_settings_path(settings or {})
    if reserved_path is None:
        return
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "WORKSPACE_SERVER_OWNED_SETTINGS_FORBIDDEN",
            "path": reserved_path,
        },
    )


def _reject_explicit_null_workspace_settings(data: WorkspaceUpdate) -> None:
    """Keep an explicit public ``settings: null`` from erasing server state.

    ``WorkspaceUpdate`` intentionally permits omitted settings for ordinary
    metadata updates.  Pydantic represents both an omitted field and an
    explicit JSON null as ``None``, so use ``model_fields_set`` to reject only
    the latter before lifecycle's generic ``setattr`` branch could replace the
    persisted settings document.
    """
    if "settings" not in data.model_fields_set or data.settings is not None:
        return
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "WORKSPACE_SETTINGS_NULL_FORBIDDEN"},
    )


async def _reject_public_execution_mutation_for_ai_research_paper_workspace(
    workspace_id: str,
    user_id: str,
    data: WorkspaceUpdate,
    service: WorkspaceService,
) -> None:
    """Keep public workspace config writes away from attested paper runtimes."""
    execution_fields = {"settings", "trading_config", "workspace_type"}
    if not (set(data.model_fields_set) & execution_fields):
        return
    units = await service.list_units(workspace_id, user_id)
    if units is None:
        return
    for unit in units:
        if not isinstance(unit, dict):
            continue
        for field in ("data_config", "unit_settings", "params", "gateway_config"):
            if _server_owned_ai_research_settings_path(unit.get(field), path=(field,)) is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "AI_RESEARCH_PAPER_WORKSPACE_EXECUTION_MUTATION_FORBIDDEN"},
                )


@lru_cache
def get_workspace_service() -> WorkspaceService:
    return WorkspaceService()


# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create workspace",
)
async def create_workspace(
    data: WorkspaceCreate,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    """Create a new workspace."""
    _reject_server_owned_ai_research_settings(data.settings)
    return await service.create_workspace(current_user.sub, data)


@router.get("/", response_model=WorkspaceListResponse, summary="List workspaces")
async def list_workspaces(
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    workspace_type: str | None = Query(None),
) -> WorkspaceListResponse:
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
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    """Get workspace by ID."""
    ws = await service.get_workspace(workspace_id, current_user.sub)
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return ws


@router.put("/{workspace_id}", response_model=WorkspaceResponse, summary="Update workspace")
async def update_workspace(
    workspace_id: str,
    data: WorkspaceUpdate,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    """Update workspace by ID."""
    _reject_explicit_null_workspace_settings(data)
    _reject_server_owned_ai_research_settings(data.settings)
    await _reject_public_execution_mutation_for_ai_research_paper_workspace(
        workspace_id,
        current_user.sub,
        data,
        service,
    )
    ws = await service.update_workspace(workspace_id, current_user.sub, data)
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return ws


@router.delete("/{workspace_id}", summary="Delete workspace")
async def delete_workspace(
    workspace_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, str]:
    """Delete workspace by ID (cascades to units)."""
    try:
        success = await service.delete_workspace(workspace_id, current_user.sub)
    except AIStrategyResearchUnitMutationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code},
        ) from exc
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return {"message": "Workspace deleted"}


# ---------------------------------------------------------------------------
# Strategy Unit CRUD
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/units", response_model=StrategyUnitListResponse, summary="List units")
async def list_units(
    workspace_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> StrategyUnitListResponse:
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
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    """Create a single strategy unit."""
    try:
        result = await service.create_unit(workspace_id, current_user.sub, data)
    except AIStrategyResearchUnitMutationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code},
        ) from exc
    except MarketDataBindingUnitMutationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code},
        ) from exc
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
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> list[dict[str, Any]]:
    """Batch create strategy units."""
    try:
        result = await service.batch_create_units(workspace_id, current_user.sub, data.units)
    except AIStrategyResearchUnitMutationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code},
        ) from exc
    except MarketDataBindingUnitMutationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code},
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return result


@router.get(
    "/{workspace_id}/units/{unit_id}", response_model=StrategyUnitResponse, summary="Get unit"
)
async def get_unit(
    workspace_id: str,
    unit_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    """Get a single strategy unit."""
    result = await service.get_unit(workspace_id, unit_id, current_user.sub)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")
    return result


@router.get(
    "/{workspace_id}/units/{unit_id}/runtime",
    response_model=UnitRuntimeInfoResponse,
    summary="Get unit runtime metadata",
)
async def get_unit_runtime_info(
    workspace_id: str,
    unit_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    result = await service.get_unit_runtime_info(workspace_id, unit_id, current_user.sub)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit runtime not found")
    return result


@router.get(
    "/{workspace_id}/units/{unit_id}/runtime/files/{relative_path:path}",
    response_class=PlainTextResponse,
    summary="Read unit runtime file",
)
async def get_unit_runtime_file(
    workspace_id: str,
    unit_id: str,
    relative_path: str,
    tail: int | None = Query(None, ge=1, le=20000),
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> str:
    content = await service.read_unit_runtime_file(
        workspace_id,
        unit_id,
        current_user.sub,
        relative_path,
        tail=tail,
    )
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime file not found")
    return content


@router.post(
    "/{workspace_id}/units/{unit_id}/runtime/open",
    summary="Open unit runtime directory",
)
async def open_unit_runtime_dir(
    workspace_id: str,
    unit_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    result = await service.open_unit_runtime_dir(workspace_id, unit_id, current_user.sub)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit runtime not found")
    return result


@router.put(
    "/{workspace_id}/units/{unit_id}", response_model=StrategyUnitResponse, summary="Update unit"
)
async def update_unit(
    workspace_id: str,
    unit_id: str,
    data: StrategyUnitUpdate,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    """Update a strategy unit."""
    try:
        result = await service.update_unit(workspace_id, unit_id, current_user.sub, data)
    except AIStrategyResearchUnitMutationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code},
        ) from exc
    except MarketDataBindingUnitMutationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code},
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")
    return result


@router.delete("/{workspace_id}/units/{unit_id}", summary="Delete unit")
async def delete_unit(
    workspace_id: str,
    unit_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, str]:
    """Delete a strategy unit."""
    try:
        success = await service.delete_unit(workspace_id, unit_id, current_user.sub)
    except AIStrategyResearchUnitMutationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code},
        ) from exc
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
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, int]:
    """Bulk delete strategy units."""
    try:
        deleted = await service.bulk_delete_units(workspace_id, current_user.sub, data.ids)
    except AIStrategyResearchUnitMutationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code},
        ) from exc
    return {"deleted": deleted}


@router.post("/{workspace_id}/units/reorder", summary="Reorder units")
async def reorder_units(
    workspace_id: str,
    data: SortRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, str]:
    """Reorder strategy units by providing ordered list of IDs."""
    success = await service.reorder_units(workspace_id, current_user.sub, data.unit_ids)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return {"message": "Units reordered"}


@router.post("/{workspace_id}/units/rename-group", summary="Rename group")
async def rename_group(
    workspace_id: str,
    data: GroupRenameRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, str]:
    """Rename group for selected units."""
    success = await service.rename_group(workspace_id, current_user.sub, data)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return {"message": "Group renamed"}


@router.post("/{workspace_id}/units/rename-unit", summary="Rename unit")
async def rename_unit(
    workspace_id: str,
    data: UnitRenameRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, str]:
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
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    """Run backtest for selected strategy units."""
    try:
        results = await service.run_units(
            workspace_id, current_user.sub, data.unit_ids, parallel=data.parallel
        )
    except ValueError as exc:
        code = str(exc).strip()
        if code.startswith("AI_RESEARCH_LIVE_HANDOFF_"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": code},
            ) from exc
        raise
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace or units not found"
        )
    return {"results": results}


@router.post("/{workspace_id}/stop", summary="Stop selected units")
async def stop_units(
    workspace_id: str,
    data: StopUnitsRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    """Stop running strategy units."""
    try:
        results = await service.stop_units(workspace_id, current_user.sub, data.unit_ids)
    except AIStrategyResearchPaperRuntimeStopError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code},
        ) from exc
    return {"results": results}


@router.get(
    "/{workspace_id}/status",
    response_model=list[UnitStatusResponse],
    summary="Poll unit statuses",
)
async def get_units_status(
    workspace_id: str,
    unit_ids: str | None = Query(None),
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> list[Any]:
    """Get current run status of all units in workspace (polling endpoint)."""
    parsed_unit_ids = [value.strip() for value in str(unit_ids or "").split(",") if value.strip()]
    statuses = await service.get_units_status(
        workspace_id,
        current_user.sub,
        unit_ids=parsed_unit_ids or None,
    )
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
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    config = await service.get_trading_auto_config(workspace_id, current_user.sub)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trading workspace not found"
        )
    return config


@router.put(
    "/{workspace_id}/trading/auto-config",
    response_model=AutoTradingConfigPayload,
    summary="Update trading workspace auto-trading config",
)
async def update_trading_auto_config(
    workspace_id: str,
    data: AutoTradingConfigPayload,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    config = await service.update_trading_auto_config(
        workspace_id,
        current_user.sub,
        data.model_dump(exclude_unset=True),
    )
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trading workspace not found"
        )
    return config


@router.get(
    "/{workspace_id}/trading/auto-schedule",
    response_model=list[AutoTradingScheduleItem],
    summary="Get trading workspace auto-trading schedule",
)
async def get_trading_auto_schedule(
    workspace_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> list[dict[str, Any]]:
    schedule = await service.get_trading_auto_schedule(workspace_id, current_user.sub)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trading workspace not found"
        )
    return schedule


@router.get(
    "/{workspace_id}/trading/positions",
    response_model=PositionManagerResponse,
    summary="Get trading workspace aggregated positions",
)
async def get_trading_positions(
    workspace_id: str,
    unit_ids: str | None = Query(None),
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    parsed_unit_ids = [value.strip() for value in str(unit_ids or "").split(",") if value.strip()]
    positions = await service.get_trading_positions(
        workspace_id,
        current_user.sub,
        unit_ids=parsed_unit_ids or None,
    )
    if positions is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trading workspace not found"
        )
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
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    summary = await service.get_trading_daily_summary(
        workspace_id,
        current_user.sub,
        unit_id=unit_id,
        start_date=start_date,
        end_date=end_date,
    )
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trading workspace not found"
        )
    return summary


# ---------------------------------------------------------------------------
# Optimization (Phase 4)
# ---------------------------------------------------------------------------

# Combined report (Phase 5)
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/report", summary="Get workspace combined report")
async def get_workspace_report(
    workspace_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    """Get aggregated report across all units in a workspace (default config)."""
    report = await service.get_workspace_report(workspace_id, current_user.sub)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return report


@router.post("/{workspace_id}/report", summary="Create / recalculate report with config")
async def create_workspace_report(
    workspace_id: str,
    data: ReportCreateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
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
    current_user: TokenPayload = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    """Clear saved report configuration cache from workspace settings.

    This does NOT delete unit metrics snapshots or run results — it only
    resets the persisted ``report_config`` in workspace settings so the
    next GET /report returns a fresh default-config aggregation.
    """
    result = await service.delete_workspace_report(workspace_id, current_user.sub)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return result
