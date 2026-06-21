"""Stock analysis support API for the AI assistant."""

from __future__ import annotations

import asyncio
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.stock_analysis import StockAnalysisTaskModel
from app.schemas.auth import TokenPayload
from app.schemas.stock_analysis import (
    StockAnalysisParams,
    StockAnalysisExportFormat,
    StockAnalysisSaveToKnowledgeBaseRequest,
    StockAnalysisSaveToKnowledgeBaseResponse,
    StockAnalysisSaveToWorkspaceRequest,
    StockAnalysisSaveToWorkspaceResponse,
)
from app.services.stock_analysis.exporter import StockAnalysisExporter
from app.services.stock_analysis.tasks import (
    StockAnalysisConcurrencyLimitExceeded,
    StockAnalysisTaskService,
)

router = APIRouter()


def _content_disposition(file_name: str) -> str:
    ascii_fallback = StockAnalysisExporter._safe_file_part(file_name, fallback="stock_analysis")
    encoded = quote(file_name)
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


def _task_response(task: StockAnalysisTaskModel) -> dict:
    return {
        "task_id": task.id,
        "status": task.status,
        "symbol": task.symbol,
        "symbol_name": task.symbol_name,
        "market_type": task.market_type,
        "analysis_date": task.analysis_date,
        "research_depth": task.research_depth,
        "selected_modules": task.selected_modules or [],
        "progress": task.progress,
        "current_step": task.current_step,
        "message": task.message,
        "error_message": task.error_message,
        "report_id": task.report_id,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
    }


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
async def create_stock_analysis_task(
    data: StockAnalysisParams,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = StockAnalysisTaskService(db)
    try:
        task = await service.create_pending(
            user_id=current_user.sub,
            params=data,
            request_text=f"分析 {data.symbol}",
        )
    except StockAnalysisConcurrencyLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "reason_code": "stock_analysis_concurrency_limit",
                "active_count": exc.active_count,
                "limit": exc.limit,
            },
        ) from exc
    await db.commit()
    await db.refresh(task)
    asyncio.create_task(
        StockAnalysisTaskService.run_pending_task(task_id=task.id, user_id=current_user.sub)
    )
    return _task_response(task)


@router.get("/tasks/{task_id}")
async def get_stock_analysis_task(
    task_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await StockAnalysisTaskService(db).get_task(user_id=current_user.sub, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task_not_found")
    return _task_response(task)


@router.post("/tasks/{task_id}/cancel")
async def cancel_stock_analysis_task(
    task_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await StockAnalysisTaskService(db).cancel_task(
        user_id=current_user.sub,
        task_id=task_id,
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task_not_found")
    return _task_response(task)


@router.post("/tasks/{task_id}/retry")
async def retry_stock_analysis_task(
    task_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = StockAnalysisTaskService(db)
    try:
        task = await service.retry_task(user_id=current_user.sub, task_id=task_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task_not_found")
    asyncio.create_task(
        StockAnalysisTaskService.run_pending_task(task_id=task.id, user_id=current_user.sub)
    )
    return _task_response(task)


@router.get("/tasks/{task_id}/result")
async def get_stock_analysis_result(
    task_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = StockAnalysisTaskService(db)
    task = await service.get_task(user_id=current_user.sub, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task_not_found")
    report = await service.get_report_by_task(user_id=current_user.sub, task_id=task_id)
    return {
        "task_id": task.id,
        "report_id": report.id if report else None,
        "status": task.status,
        "report": report.report_json if report else None,
    }


@router.get("/reports/{report_id}/export")
async def export_stock_analysis_report(
    report_id: str,
    format: StockAnalysisExportFormat = Query("markdown"),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = StockAnalysisTaskService(db)
    result = await service.export_report(
        user_id=current_user.sub,
        report_id=report_id,
        export_format=format,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report_not_found")
    export, content = result
    return StreamingResponse(
        BytesIO(content),
        media_type=StockAnalysisExporter.CONTENT_TYPES[format],
        headers={"Content-Disposition": _content_disposition(export.file_name)},
    )


@router.post(
    "/reports/{report_id}/save-to-knowledge-base",
    response_model=StockAnalysisSaveToKnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_stock_analysis_report_to_knowledge_base(
    report_id: str,
    data: StockAnalysisSaveToKnowledgeBaseRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = StockAnalysisTaskService(db)
    try:
        document = await service.save_report_to_knowledge_base(
            user_id=current_user.sub,
            report_id=report_id,
            knowledge_base_id=data.knowledge_base_id,
            title=data.title,
            parent_id=data.parent_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report_or_kb_not_found")
    return StockAnalysisSaveToKnowledgeBaseResponse(
        document_id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        report_id=report_id,
        title=document.title,
        content_type=document.content_type,
        status=document.status,
        index_status=document.index_status,
        created_at=document.created_at,
    )


@router.post(
    "/reports/{report_id}/save-to-workspace",
    response_model=StockAnalysisSaveToWorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_stock_analysis_report_to_workspace(
    report_id: str,
    data: StockAnalysisSaveToWorkspaceRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = StockAnalysisTaskService(db)
    try:
        saved = await service.save_report_to_workspace(
            user_id=current_user.sub,
            report_id=report_id,
            workspace_id=data.workspace_id,
            title=data.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if saved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="report_or_workspace_not_found",
        )
    return StockAnalysisSaveToWorkspaceResponse(
        workspace_id=data.workspace_id,
        report_id=saved["report_id"],
        task_id=saved["task_id"],
        title=saved["title"],
        symbol=saved["symbol"],
        decision_label=saved["decision_label"],
        risk_level=saved["risk_level"],
        saved_at=saved["saved_at"],
    )
