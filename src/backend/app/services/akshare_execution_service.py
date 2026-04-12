"""
Execution service for akshare task runs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.akshare_mgmt import ScheduledTask, TaskExecution, TaskStatus, TriggeredBy


class AkshareExecutionService:
    """Service for creating and querying akshare execution records."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_execution(
        self,
        script_id: str,
        task_id: int | None = None,
        params: dict | None = None,
        triggered_by: TriggeredBy = TriggeredBy.SCHEDULER,
        operator_id: str | None = None,
    ) -> TaskExecution:
        execution = TaskExecution(
            execution_id=f"ak_exec_{uuid.uuid4().hex[:12]}",
            task_id=task_id,
            script_id=script_id,
            params=params,
            status=TaskStatus.PENDING,
            triggered_by=triggered_by,
            operator_id=operator_id,
        )
        self.db.add(execution)
        await self.db.commit()
        await self.db.refresh(execution)
        return execution

    async def mark_running(self, execution: TaskExecution) -> TaskExecution:
        execution.status = TaskStatus.RUNNING
        execution.start_time = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(execution)
        return execution

    async def mark_completed(
        self,
        execution: TaskExecution,
        result: dict | None = None,
        rows_before: int | None = None,
        rows_after: int | None = None,
    ) -> TaskExecution:
        end_time = datetime.now(timezone.utc)
        execution.status = TaskStatus.COMPLETED
        execution.end_time = end_time
        execution.duration = (
            (end_time - execution.start_time).total_seconds() if execution.start_time else None
        )
        execution.result = result
        execution.rows_before = rows_before
        execution.rows_after = rows_after
        await self.db.commit()
        await self.db.refresh(execution)
        if execution.task_id:
            task = await self.db.get(ScheduledTask, execution.task_id)
            if task is not None:
                task.last_execution_at = end_time
                await self.db.commit()
        return execution

    async def mark_failed(
        self,
        execution: TaskExecution,
        error_message: str,
        error_trace: str | None = None,
    ) -> TaskExecution:
        end_time = datetime.now(timezone.utc)
        execution.status = TaskStatus.FAILED
        execution.end_time = end_time
        execution.duration = (
            (end_time - execution.start_time).total_seconds() if execution.start_time else None
        )
        execution.error_message = error_message
        execution.error_trace = error_trace
        await self.db.commit()
        await self.db.refresh(execution)
        return execution

    async def get_execution(self, execution_id: str) -> TaskExecution | None:
        result = await self.db.execute(
            select(TaskExecution).where(TaskExecution.execution_id == execution_id)
        )
        return result.scalar_one_or_none()

    async def list_executions(
        self,
        task_id: int | None = None,
        script_id: str | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[TaskExecution], int]:
        filters = []
        if task_id is not None:
            filters.append(TaskExecution.task_id == task_id)
        if script_id:
            filters.append(TaskExecution.script_id == script_id)
        if status:
            filters.append(TaskExecution.status == TaskStatus(status))
        if start_date:
            filters.append(TaskExecution.start_time >= start_date)
        if end_date:
            filters.append(TaskExecution.start_time <= end_date)

        stmt = select(TaskExecution)
        count_stmt = select(func.count()).select_from(TaskExecution)
        if filters:
            stmt = stmt.where(and_(*filters))
            count_stmt = count_stmt.where(and_(*filters))

        total = int((await self.db.execute(count_stmt)).scalar() or 0)
        stmt = stmt.order_by(TaskExecution.created_at.desc()).offset((page - 1) * page_size).limit(
            page_size
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_stats(self) -> dict[str, float | int]:
        total = int((await self.db.execute(select(func.count(TaskExecution.id)))).scalar() or 0)
        success = int(
            (
                await self.db.execute(
                    select(func.count(TaskExecution.id)).where(
                        TaskExecution.status == TaskStatus.COMPLETED
                    )
                )
            ).scalar()
            or 0
        )
        failed = int(
            (
                await self.db.execute(
                    select(func.count(TaskExecution.id)).where(TaskExecution.status == TaskStatus.FAILED)
                )
            ).scalar()
            or 0
        )
        running = int(
            (
                await self.db.execute(
                    select(func.count(TaskExecution.id)).where(TaskExecution.status == TaskStatus.RUNNING)
                )
            ).scalar()
            or 0
        )
        avg_duration = float(
            (
                await self.db.execute(
                    select(func.avg(TaskExecution.duration)).where(
                        TaskExecution.status == TaskStatus.COMPLETED
                    )
                )
            ).scalar()
            or 0
        )
        return {
            "total_count": total,
            "success_count": success,
            "failed_count": failed,
            "running_count": running,
            "success_rate": (success / total * 100) if total else 0,
            "avg_duration": avg_duration,
        }

    async def get_recent(self, limit: int = 20) -> list[TaskExecution]:
        result = await self.db.execute(
            select(TaskExecution).order_by(TaskExecution.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_running(self) -> list[TaskExecution]:
        result = await self.db.execute(
            select(TaskExecution)
            .where(TaskExecution.status == TaskStatus.RUNNING)
            .order_by(TaskExecution.created_at.desc())
        )
        return list(result.scalars().all())

    async def retry_execution(
        self,
        execution_id: str,
        operator_id: str | None = None,
    ) -> TaskExecution:
        execution = await self.get_execution(execution_id)
        if execution is None:
            raise ValueError("Execution not found")
        if execution.task_id is None:
            raise ValueError("Only task-linked executions can be retried")

        from app.services.akshare_scheduler_service import get_akshare_scheduler_service

        service = get_akshare_scheduler_service()
        new_execution = await service.run_task_now(execution.task_id, operator_id=operator_id)
        return new_execution
