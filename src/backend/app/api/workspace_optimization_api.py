"""Workspace optimization API routes.

Extracted from workspace_api.py in iteration 174 (C10) to keep the main
workspace router below the 800-line bar.
"""

import io
import typing
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.api.workspace_api import get_workspace_service
from app.schemas.analytics import (
    BacktestDetailResponse,
    KlineWithSignalsResponse,
    MonthlyReturnsResponse,
)
from app.schemas.workspace import (
    ApplyBestParamsRequest,
    OptimizationArtifactResponse,
    UnitOptimizationRequest,
)
from app.services.analytics_service import AnalyticsService
from app.services.workspace_service import WorkspaceService

router = APIRouter()


@router.post("/{workspace_id}/optimize", summary="Submit unit optimization", response_model=None)
async def submit_unit_optimization(
    workspace_id: str,
    data: UnitOptimizationRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> typing.Any:
    """Submit parameter optimization for a strategy unit."""
    result = await service.submit_unit_optimization(workspace_id, current_user.sub, data)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace or unit not found"
        )
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return result


@router.get(
    "/{workspace_id}/optimize/{unit_id}/progress",
    summary="Unit optimization progress",
    response_model=None,
)
async def get_unit_optimization_progress(
    workspace_id: str,
    unit_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> typing.Any:
    """Get optimization progress for a strategy unit."""
    progress = await service.get_unit_optimization_progress(workspace_id, current_user.sub, unit_id)
    if progress is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No optimization task found"
        )
    return progress


@router.get(
    "/{workspace_id}/optimize/{unit_id}/results",
    summary="Unit optimization results",
    response_model=None,
)
async def get_unit_optimization_results(
    workspace_id: str,
    unit_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> typing.Any:
    """Get optimization results for a strategy unit."""
    results = await service.get_unit_optimization_results(workspace_id, current_user.sub, unit_id)
    if results is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No optimization results found"
        )
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
    current_user: typing.Any = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> typing.Any:
    payload = await service.get_unit_optimization_result_payload(
        workspace_id,
        current_user.sub,
        unit_id,
        result_index,
    )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Optimization result detail not found"
        )

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
    current_user: typing.Any = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> typing.Any:
    payload = await service.get_unit_optimization_result_payload(
        workspace_id,
        current_user.sub,
        unit_id,
        result_index,
    )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Optimization result detail not found"
        )

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
    current_user: typing.Any = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> typing.Any:
    payload = await service.get_unit_optimization_result_payload(
        workspace_id,
        current_user.sub,
        unit_id,
        result_index,
    )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Optimization result detail not found"
        )

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
    current_user: typing.Any = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> typing.Any:
    payload = await service.get_unit_optimization_result_artifact_metadata(
        workspace_id,
        current_user.sub,
        unit_id,
        result_index,
    )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Optimization artifact not found"
        )
    return OptimizationArtifactResponse(**payload)


@router.get(
    "/{workspace_id}/optimize/{unit_id}/results/{result_index}/artifact/download",
    summary="Download persisted optimization artifact archive",
    response_model=None,
)
async def download_unit_optimization_result_artifact(
    workspace_id: str,
    unit_id: str,
    result_index: int,
    current_user: typing.Any = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> typing.Any:
    payload = await service.get_unit_optimization_result_artifact_metadata(
        workspace_id,
        current_user.sub,
        unit_id,
        result_index,
    )
    artifact_path = str((payload or {}).get("artifact_path") or "")
    artifact_dir = Path(artifact_path).expanduser() if artifact_path else None
    if payload is None or artifact_dir is None or not artifact_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Optimization artifact not found"
        )

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
                zf.write(
                    file_path,
                    arcname=str(
                        Path(root_dir.name)
                        / artifact_dir.name
                        / file_path.relative_to(artifact_dir)
                    ),
                )
    buffer.seek(0)

    trial_index = payload.get("trial_index")
    suffix = (
        f"trial_{int(trial_index) + 1:04d}"
        if isinstance(trial_index, int)
        else f"result_{result_index}"
    )
    filename = f"optimization_artifact_{payload['optimization_task_id']}_{suffix}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(buffer, media_type="application/zip", headers=headers)


@router.post(
    "/{workspace_id}/optimize/{unit_id}/cancel",
    summary="Cancel unit optimization",
    response_model=None,
)
async def cancel_unit_optimization(
    workspace_id: str,
    unit_id: str,
    current_user: typing.Any = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> typing.Any:
    """Cancel a running optimization task for a strategy unit."""
    result = await service.cancel_unit_optimization(workspace_id, current_user.sub, unit_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return result


@router.post(
    "/{workspace_id}/optimize/apply", summary="Apply best optimization params", response_model=None
)
async def apply_best_params(
    workspace_id: str,
    data: ApplyBestParamsRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> typing.Any:
    """Apply best parameters from optimization to a strategy unit."""
    result = await service.apply_best_params(workspace_id, current_user.sub, data)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace or unit not found"
        )
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
