"""
Enhanced backtest API routes.

Includes:
- Strict request validation
- Task status/result APIs
- Report export
- WebSocket progress streaming
"""

import asyncio
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_websocket_current_user
from app.schemas.backtest_enhanced import (
    BacktestCancelledEvent,
    BacktestCompletedEvent,
    BacktestFailedEvent,
    BacktestListResponse,
    BacktestProgressEvent,
    BacktestRequest,
    BacktestResponse,
    BacktestResult,
    BacktestStatusResponse,
    BacktestTaskCreatedEvent,
    OptimizationRequest,
    OptimizationResult,
    TaskStatus,
)
from app.services.backtest_service import BacktestService
from app.services.report_service import ReportService
from app.services.strategy_service import STRATEGIES_DIR, get_template_by_id
from app.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()
_OPTIMIZATION_SUCCESSOR_PATH = "/api/v1/optimization/submit/backtest"


@lru_cache
def get_backtest_service():
    return BacktestService()


@lru_cache
def get_report_service():
    return ReportService()


def _build_strategy_report_metadata(strategy_id: str) -> dict[str, str]:
    text = str(strategy_id or "").strip()
    fallback = {
        "name": f"Strategy {text or 'unknown'}",
        "description": "Strategy metadata unavailable",
    }
    if not text:
        return fallback

    template_ids = [text]
    if "/" not in text:
        template_ids.append(f"backtest/{text}")

    for template_id in template_ids:
        template = get_template_by_id(template_id)
        if template is None:
            continue
        return {
            "name": getattr(template, "name", None) or fallback["name"],
            "description": getattr(template, "description", None) or fallback["description"],
        }

    strategy_dirs: list[Path] = []
    if "/" in text:
        strategy_dirs.append(STRATEGIES_DIR / text)
    else:
        strategy_dirs.extend([STRATEGIES_DIR / "backtest" / text, STRATEGIES_DIR / text])

    for strategy_dir in strategy_dirs:
        config_path = strategy_dir / "config.yaml"
        if not config_path.is_file():
            continue
        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            logger.warning("Failed to parse config.yaml for strategy %s", text, exc_info=True)
            continue
        strategy = config.get("strategy")
        if not isinstance(strategy, dict):
            continue
        return {
            "name": str(strategy.get("name") or fallback["name"]),
            "description": str(strategy.get("description") or fallback["description"]),
        }

    return fallback


def _score_legacy_optimization_result(metrics: dict[str, Any], metric: str) -> float:
    value = metrics.get(metric)
    if not isinstance(value, (int, float)):
        return float("-inf")
    if metric == "max_drawdown":
        return -float(value)
    return float(value)


def _build_legacy_optimization_result(
    task_results: dict[str, Any], metric: str
) -> OptimizationResult:
    param_names = list(task_results.get("param_names") or [])
    metric_names = list(task_results.get("metric_names") or [])
    all_results: list[dict[str, Any]] = []

    for row in list(task_results.get("rows") or []):
        params = {name: row[name] for name in param_names if name in row}
        metrics = {
            name: float(row[name])
            for name in metric_names
            if name in row and isinstance(row[name], (int, float))
        }
        all_results.append({"params": params, "metrics": metrics})

    ranked_results = sorted(
        all_results,
        key=lambda item: _score_legacy_optimization_result(item.get("metrics", {}), metric),
        reverse=True,
    )
    best_result = ranked_results[0] if ranked_results else None

    return OptimizationResult(
        best_params=best_result["params"] if best_result else {},
        best_metrics=best_result["metrics"] if best_result else {},
        all_results=all_results,
        n_trials=int(task_results.get("completed", len(all_results)) or 0),
    )


async def _await_legacy_optimization_task_result(
    task_id: str,
    user_id: str,
    metric: str,
    timeout: int = 600,
) -> OptimizationResult:
    from app.services.param_optimization_service import (
        get_optimization_progress,
        get_optimization_results,
    )

    waited = 0
    while waited < timeout:
        task_results = get_optimization_results(task_id, user_id=user_id)
        if task_results and task_results.get("status") in {
            TaskStatus.COMPLETED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        }:
            return _build_legacy_optimization_result(task_results, metric)

        task_progress = get_optimization_progress(task_id, user_id=user_id)
        if task_progress and task_progress.get("status") in {
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        }:
            return _build_legacy_optimization_result(
                {
                    "status": task_progress.get("status"),
                    "param_names": [],
                    "metric_names": [],
                    "rows": [],
                    "completed": task_progress.get("completed", 0),
                },
                metric,
            )

        await asyncio.sleep(1)
        waited += 1

    raise HTTPException(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        detail="Legacy optimization proxy timed out while waiting for task completion",
    )


def _is_terminal_backtest_status(task_status: TaskStatus | None) -> bool:
    status_value = getattr(task_status, "value", task_status)
    return status_value in {
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    }


def _build_backtest_runtime_snapshot(
    task_id: str,
    task_status: TaskStatus,
    result: BacktestResult | None,
) -> dict[str, Any]:
    status_value = getattr(task_status, "value", task_status)

    if status_value == TaskStatus.PENDING.value:
        return BacktestTaskCreatedEvent(task_id=task_id).model_dump(mode="python")
    if status_value == TaskStatus.RUNNING.value:
        return BacktestProgressEvent(
            task_id=task_id,
            progress=0,
            message="Backtest task is running",
        ).model_dump(mode="python")
    if status_value == TaskStatus.COMPLETED.value:
        return BacktestCompletedEvent(
            task_id=task_id,
            result=result.model_dump(mode="python") if result else None,
        ).model_dump(mode="python")
    if status_value == TaskStatus.FAILED.value:
        error_message = result.error_message if result and result.error_message else "Unknown error"
        return BacktestFailedEvent(
            task_id=task_id,
            message=error_message,
            error=error_message,
        ).model_dump(mode="python")
    return BacktestCancelledEvent(task_id=task_id).model_dump(mode="python")


def _mark_legacy_optimization_proxy(response: Response, method: str = "unknown") -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'<{_OPTIMIZATION_SUCCESSOR_PATH}>; rel="successor-version"'
    response.headers["X-Deprecated-Endpoint"] = _OPTIMIZATION_SUCCESSOR_PATH
    logger.warning(
        "Deprecated optimization endpoint called: method=%s, successor=%s. "
        "This endpoint will be removed in v2.0.0.",
        method,
        _OPTIMIZATION_SUCCESSOR_PATH,
    )


async def _proxy_legacy_optimization_request(
    *,
    request: OptimizationRequest,
    current_user_id: str,
    expected_method: str,
    response: Response,
) -> OptimizationResult:
    if request.method != expected_method:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{expected_method.capitalize()} optimization requires method={expected_method}",
        )

    from app.api.optimization_api import submit_backtest_optimization_task_internal

    _mark_legacy_optimization_proxy(response, expected_method)
    submit_response = await submit_backtest_optimization_task_internal(
        request=request,
        user_id=current_user_id,
    )
    return await _await_legacy_optimization_task_result(
        submit_response.task_id,
        current_user_id,
        getattr(request, "metric", "sharpe_ratio"),
    )


# ==================== Backtest API ====================


@router.post("/run", response_model=BacktestResponse, summary="Run backtest")
async def run_backtest(
    request: BacktestRequest,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Submit a backtest task (enhanced)."""
    result = await service.run_backtest(current_user.sub, request)

    # Notify WebSocket clients (if connected)
    await ws_manager.send_to_task(
        result.task_id,
        BacktestTaskCreatedEvent(task_id=result.task_id).model_dump(mode="python"),
    )

    return result


@router.get("/{task_id}", response_model=BacktestResult, summary="Get backtest result")
async def get_backtest_result(
    task_id: str,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Get backtest result."""
    result = await service.get_result(task_id, user_id=current_user.sub)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found",
        )
    return result


@router.get(
    "/{task_id}/status",
    response_model=BacktestStatusResponse,
    summary="Get backtest task status",
)
async def get_backtest_status(
    task_id: str,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Get backtest task status."""
    task_status = await service.get_task_status(task_id, user_id=current_user.sub)
    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return BacktestStatusResponse(task_id=task_id, status=task_status)


@router.get("/", response_model=BacktestListResponse, summary="List backtest history")
async def list_backtests(
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset"),
    sort_by: str = Query(
        "created_at", description="Sort field: created_at/sharpe_ratio/total_return"
    ),
    sort_order: str = Query("desc", description="Sort direction: asc/desc"),
):
    """List user's backtest history (enhanced, supports sorting)."""
    sort_desc = str(sort_order).lower() != "asc"
    results = await service.list_results(
        current_user.sub,
        limit,
        offset,
        sort_by,
        sort_desc,
    )
    return results


@router.post("/{task_id}/cancel", summary="Cancel backtest task")
async def cancel_backtest(
    task_id: str,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Cancel a running backtest task."""
    success = await service.cancel_task(task_id, current_user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Task not found, unauthorized, already completed, or running on another "
                "instance (cancellation only works when the task runs in this API process)"
            ),
        )
    return {"message": "Task cancelled", "task_id": task_id}


@router.delete("/{task_id}", summary="Delete backtest result")
async def delete_backtest(
    task_id: str,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Delete backtest result."""
    success = await service.delete_result(task_id, current_user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found or no permission to delete",
        )
    return {"message": "Deleted successfully"}


# ==================== Parameter Optimization API ====================


@router.post(
    "/optimization/grid",
    response_model=OptimizationResult,
    summary="Grid search optimization",
    deprecated=True,
)
async def grid_search_optimization(
    request: OptimizationRequest,
    response: Response,
    current_user=Depends(get_current_user),
):
    """Grid search optimization.

    Iterates through all parameter combinations to find optimal parameters.
    """
    return await _proxy_legacy_optimization_request(
        request=request,
        current_user_id=current_user.sub,
        expected_method="grid",
        response=response,
    )


@router.post(
    "/optimization/bayesian",
    response_model=OptimizationResult,
    summary="Bayesian optimization",
    deprecated=True,
)
async def bayesian_optimization(
    request: OptimizationRequest,
    response: Response,
    current_user=Depends(get_current_user),
):
    """Bayesian optimization (intelligent optimization).

    Uses Optuna for Bayesian optimization to find optimal parameters.
    """
    return await _proxy_legacy_optimization_request(
        request=request,
        current_user_id=current_user.sub,
        expected_method="bayesian",
        response=response,
    )


# ==================== Backtest Trades Pagination ====================


class TradeListResponse(BaseModel):
    """Paginated trade list response."""

    trades: list[dict[str, Any]] = Field(default_factory=list, description="Trade records")
    total: int = Field(..., description="Total number of trades")
    offset: int = Field(..., description="Current offset")
    limit: int = Field(..., description="Items per page")


@router.get("/{task_id}/trades", response_model=TradeListResponse, summary="Get paginated trades")
async def get_paginated_trades(
    task_id: str,
    limit: int = Query(50, ge=1, le=500, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset"),
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Get paginated trade records for a backtest task.

    This endpoint supports pagination for large trade datasets.
    Use `offset` and `limit` parameters to navigate through results.

    Args:
        task_id: Backtest task ID.
        limit: Number of items per page (max 500).
        offset: Number of items to skip.

    Returns:
        Paginated list of trades with metadata.
    """
    result = await service.get_result(task_id, user_id=current_user.sub)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found",
        )

    all_trades = result.trades or []
    total = len(all_trades)

    # Get page slice
    trades_page = all_trades[offset : offset + limit]

    return TradeListResponse(
        trades=trades_page,
        total=total,
        offset=offset,
        limit=limit,
    )


# ==================== Backtest Report Export API ====================


@router.get("/{task_id}/report/html", summary="Export HTML report")
async def get_html_report(
    task_id: str,
    current_user=Depends(get_current_user),
    backtest_service: BacktestService = Depends(get_backtest_service),
    report_service: ReportService = Depends(get_report_service),
):
    """Export backtest report in HTML format."""
    result = await backtest_service.get_result(task_id, user_id=current_user.sub)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found",
        )

    strategy = _build_strategy_report_metadata(result.strategy_id)

    # Generate HTML report
    try:
        html_content = await report_service.generate_html_report(
            result.model_dump(mode="python"), strategy
        )
    except ImportError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"HTML generation not enabled, need to install jinja2: {e}",
        ) from e

    return Response(
        content=html_content,
        media_type="text/html",
        headers={"Content-Disposition": "attachment; filename=backtest.html"},
    )


@router.get("/{task_id}/report/pdf", summary="Export PDF report")
async def get_pdf_report(
    task_id: str,
    current_user=Depends(get_current_user),
    backtest_service: BacktestService = Depends(get_backtest_service),
    report_service: ReportService = Depends(get_report_service),
):
    """Export backtest report in PDF format."""
    result = await backtest_service.get_result(task_id, user_id=current_user.sub)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found",
        )

    # Get strategy info
    strategy = _build_strategy_report_metadata(result.strategy_id)

    # Generate PDF report
    try:
        pdf_bytes = await report_service.generate_pdf_report(
            result.model_dump(mode="python"), strategy
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=backtest.pdf"},
        )
    except ImportError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation not enabled, need to install weasyprint: {e}",
        )


@router.get("/{task_id}/report/excel", summary="Export Excel report")
async def get_excel_report(
    task_id: str,
    current_user=Depends(get_current_user),
    backtest_service: BacktestService = Depends(get_backtest_service),
    report_service: ReportService = Depends(get_report_service),
):
    """Export backtest report in Excel format."""
    result = await backtest_service.get_result(task_id, user_id=current_user.sub)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found",
        )

    # Get strategy info
    strategy = _build_strategy_report_metadata(result.strategy_id)

    # Generate Excel report
    try:
        excel_bytes = await report_service.generate_excel_report(
            result.model_dump(mode="python"), strategy
        )

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=backtest.xlsx"},
        )
    except ImportError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Excel export not enabled, need to install pandas and openpyxl: {e}",
        )


# ==================== WebSocket Endpoint ====================


async def websocket_endpoint(
    websocket: WebSocket,
    task_id: str,
):
    """WebSocket endpoint for authenticated backtest runtime updates.

    Args:
        websocket: WebSocket connection object.
        task_id: Backtest task ID.

    Usage:
        - Client connection: ws://host/ws/backtest/{task_id}
        - Auth handshake: Sec-WebSocket-Protocol = access-token,<jwt>
        - Runtime events are emitted by the service layer; this endpoint only
          handles connection validation, initial snapshot, heartbeat, and
          terminal-state catch-up for late subscribers.
    """

    current_user, accepted_subprotocol = get_websocket_current_user(websocket)
    if current_user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    backtest_service = get_backtest_service()
    task_status = await backtest_service.get_task_status(task_id, user_id=current_user.sub)
    if task_status is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Generate unique client ID
    client_id = f"client_{id(websocket)}"

    # Establish connection
    await ws_manager.connect(websocket, task_id, client_id, accepted_subprotocol)

    try:
        initial_result = await backtest_service.get_result(task_id, user_id=current_user.sub)
        initial_snapshot = _build_backtest_runtime_snapshot(task_id, task_status, initial_result)
        await ws_manager.send_to_task(task_id, initial_snapshot)

        if _is_terminal_backtest_status(task_status):
            return

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                data = None

            if data == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            task_status = await backtest_service.get_task_status(task_id, user_id=current_user.sub)
            if task_status is None:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                break

            if not _is_terminal_backtest_status(task_status):
                continue

            result = await backtest_service.get_result(task_id, user_id=current_user.sub)
            terminal_snapshot = _build_backtest_runtime_snapshot(task_id, task_status, result)
            await ws_manager.send_to_task(task_id, terminal_snapshot)
            break

    except WebSocketDisconnect:
        logging.debug(f"WebSocket disconnected for backtest task {task_id}")
    except Exception:
        logging.exception("WebSocket error for backtest task %s", task_id)
    finally:
        ws_manager.disconnect(websocket, task_id, client_id)
