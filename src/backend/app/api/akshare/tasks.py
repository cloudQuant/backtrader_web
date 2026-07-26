"""
API routes for akshare scheduled tasks.
"""

import typing

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data.deps import get_current_db_user, require_data_admin_user
from app.db.database import get_db
from app.schemas.akshare_mgmt import ScheduledTaskCreate, ScheduledTaskUpdate
from app.services.akshare.scheduler_service import get_akshare_scheduler_service

router = APIRouter()


@router.get("/tasks/schedule/templates", response_model=None)
async def get_schedule_templates(
    current_user: typing.Any = Depends(get_current_db_user),
) -> typing.Any:
    return {"templates": get_akshare_scheduler_service().get_schedule_templates()}


@router.get("/tasks", response_model=None)
async def list_tasks(
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: typing.Any = Depends(get_current_db_user),
) -> typing.Any:
    service = get_akshare_scheduler_service()
    items, total = await service.list_tasks(db, is_active=is_active, page=page, page_size=page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/tasks", status_code=status.HTTP_201_CREATED, response_model=None)
async def create_task(
    payload: ScheduledTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: typing.Any = Depends(require_data_admin_user),
) -> typing.Any:
    try:
        return await get_akshare_scheduler_service().create_task(
            db,
            payload.model_dump(),
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/tasks/{task_id}", response_model=None)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: typing.Any = Depends(get_current_db_user),
) -> typing.Any:
    task = await get_akshare_scheduler_service().get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.put("/tasks/{task_id}", response_model=None)
async def update_task(
    task_id: int,
    payload: ScheduledTaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: typing.Any = Depends(require_data_admin_user),
) -> typing.Any:
    task = await get_akshare_scheduler_service().update_task(
        db,
        task_id,
        payload.model_dump(exclude_none=True),
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: typing.Any = Depends(require_data_admin_user),
) -> typing.Any:
    deleted = await get_akshare_scheduler_service().delete_task(db, task_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")


@router.patch("/tasks/{task_id}/toggle", response_model=None)
async def toggle_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: typing.Any = Depends(require_data_admin_user),
) -> typing.Any:
    task = await get_akshare_scheduler_service().toggle_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.post("/tasks/{task_id}/run", response_model=None)
async def run_task(
    task_id: int,
    current_user: typing.Any = Depends(require_data_admin_user),
) -> typing.Any:
    execution = await get_akshare_scheduler_service().run_task_now(
        task_id,
        operator_id=current_user.id,
    )
    return {"execution_id": execution.execution_id, "status": execution.status.value}


@router.get("/tasks/{task_id}/executions", response_model=None)
async def get_task_executions(
    task_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: typing.Any = Depends(get_current_db_user),
) -> typing.Any:
    items, total = await get_akshare_scheduler_service().list_task_executions(
        db,
        task_id,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}
