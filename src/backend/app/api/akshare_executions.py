"""
API routes for akshare execution records.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data_management_deps import get_current_db_user, require_data_admin_user
from app.db.database import get_db
from app.services.akshare_execution_service import AkshareExecutionService

router = APIRouter()


@router.get("/executions")
async def list_executions(
    task_id: int | None = None,
    script_id: str | None = None,
    status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_db_user),
):
    service = AkshareExecutionService(db)
    items, total = await service.list_executions(
        task_id=task_id,
        script_id=script_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/executions/stats")
async def get_execution_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_db_user),
):
    return await AkshareExecutionService(db).get_stats()


@router.get("/executions/recent")
async def get_recent_executions(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_db_user),
):
    return await AkshareExecutionService(db).get_recent(limit=limit)


@router.get("/executions/running")
async def get_running_executions(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_db_user),
):
    return await AkshareExecutionService(db).get_running()


@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_db_user),
):
    execution = await AkshareExecutionService(db).get_execution(execution_id)
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return execution


@router.post("/executions/{execution_id}/retry")
async def retry_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    try:
        execution = await AkshareExecutionService(db).retry_execution(
            execution_id,
            operator_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"execution_id": execution.execution_id, "status": execution.status.value}
