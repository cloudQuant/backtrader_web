"""
Enhanced backtest API routes.

Includes:
- Strict request validation
- Task status/result APIs
- Report export
- WebSocket progress streaming
"""

from functools import lru_cache

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

from app.api.deps import get_current_user
from app.schemas.backtest_enhanced import (
    BacktestListResponse,
    BacktestRequest,
    BacktestResponse,
    BacktestResult,
    OptimizationRequest,
    OptimizationResult,
    TaskStatus,
)
from app.services.backtest_service import BacktestService
from app.services.optimization_service import OptimizationService
from app.services.report_service import ReportService
from app.websocket_manager import manager as ws_manager

router = APIRouter()


@lru_cache
def get_backtest_service():
    return BacktestService()


@lru_cache
def get_optimization_service():
    return OptimizationService()


@lru_cache
def get_report_service():
    return ReportService()


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
        {
            "type": "task_created",
            "task_id": result.task_id,
            "status": "pending",
        },
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


@router.get("/{task_id}/status", summary="Get backtest task status")
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
    return {"task_id": task_id, "status": task_status.value}


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
    "/optimization/grid", response_model=OptimizationResult, summary="Grid search optimization"
)
async def grid_search_optimization(
    request: OptimizationRequest,
    current_user=Depends(get_current_user),
    service: OptimizationService = Depends(get_optimization_service),
):
    """Grid search optimization.

    Iterates through all parameter combinations to find optimal parameters.
    """
    if request.method != "grid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Grid search requires method=grid",
        )

    result = await service.run_grid_search(current_user.sub, request)
    return result


@router.post(
    "/optimization/bayesian", response_model=OptimizationResult, summary="Bayesian optimization"
)
async def bayesian_optimization(
    request: OptimizationRequest,
    current_user=Depends(get_current_user),
    service: OptimizationService = Depends(get_optimization_service),
):
    """Bayesian optimization (intelligent optimization).

    Uses Optuna for Bayesian optimization to find optimal parameters.
    """
    if request.method != "bayesian":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bayesian optimization requires method=bayesian",
        )

    result = await service.run_bayesian_optimization(current_user.sub, request)
    return result


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

    # Get strategy info
    # TODO: Get from strategy table
    strategy = {
        "name": f"Strategy {result.strategy_id}",
        "description": "Custom strategy",
    }

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
    strategy = {
        "name": f"Strategy {result.strategy_id}",
        "description": "Custom strategy",
    }

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
    strategy = {
        "name": f"Strategy {result.strategy_id}",
        "description": "Custom strategy",
    }

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


@router.websocket("/ws/backtest/{task_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    task_id: str,
):
    """WebSocket endpoint - Real-time backtest progress and log streaming.

    Args:
        websocket: WebSocket connection object.
        task_id: Backtest task ID.

    Usage:
        - Client connection: ws://host/api/v1/backtest/ws/backtest/{task_id}
        - Receive messages: JSON format, containing type, task_id, message, data
        - Message types:
            - connected: Connection successful
            - progress: Progress update (includes progress percentage, current result)
            - log: Log message
            - completed: Backtest complete (includes full result)
            - failed: Backtest failed (includes error information)
    """

    # Generate unique client ID
    client_id = f"client_{id(websocket)}"

    # Establish connection
    await ws_manager.connect(websocket, task_id, client_id)

    try:
        # Poll task status and push updates
        backtest_service = get_backtest_service()
        import asyncio

        while True:
            # Check task status
            task_status = await backtest_service.get_task_status(task_id)
            result = await backtest_service.get_result(task_id)

            # Send progress update
            if task_status == TaskStatus.RUNNING:
                progress = await ws_manager.get_connection_count(task_id)
                await ws_manager.send_to_task(
                    task_id,
                    {
                        "type": "progress",
                        "task_id": task_id,
                        "progress": min(progress * 10, 100),
                        "data": result.model_dump(mode="python") if result else {},
                    },
                )

            # Send completion message
            elif task_status == TaskStatus.COMPLETED and result:
                await ws_manager.send_to_task(
                    task_id,
                    {
                        "type": "completed",
                        "task_id": task_id,
                        "result": result.model_dump(mode="python"),
                    },
                )
                break

            # Send failure message
            elif task_status == TaskStatus.FAILED:
                await ws_manager.send_to_task(
                    task_id,
                    {
                        "type": "failed",
                        "task_id": task_id,
                        "error": result.error_message if result else "Unknown error",
                    },
                )
                break

            # Exit loop if task is completed or failed
            if task_status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                break

            # Wait 1 second before checking again
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        # Normal disconnect
        ws_manager.disconnect(websocket, task_id, client_id)
    except Exception as e:
        # Exception disconnect
        import logging

        logging.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket, task_id, client_id)
