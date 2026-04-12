"""
Service layer for akshare scheduled tasks.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.akshare_mgmt import DataScript, ScheduledTask
from app.services.akshare_execution_service import AkshareExecutionService
from app.services.akshare_scheduler import AkshareScheduler

SCHEDULE_TEMPLATES = [
    {"value": "every_hour", "label": "每小时", "description": "每小时执行一次", "cron_expression": "0 * * * *"},
    {"value": "every_day_at_8", "label": "每天8点", "description": "每天早上8点执行", "cron_expression": "0 8 * * *"},
    {"value": "every_day_at_18", "label": "每天18点", "description": "每天下午18点执行", "cron_expression": "0 18 * * *"},
    {"value": "workdays_at_8", "label": "工作日8点", "description": "工作日早上8点执行", "cron_expression": "0 8 * * 1-5"},
    {"value": "workdays_at_18", "label": "工作日18点", "description": "工作日下午18点执行", "cron_expression": "0 18 * * 1-5"},
    {"value": "every_10_minutes", "label": "每10分钟", "description": "每10分钟执行一次", "cron_expression": "*/10 * * * *"},
]


@lru_cache
def get_akshare_scheduler_service() -> AkshareSchedulerService:
    return AkshareSchedulerService()


class AkshareSchedulerService:
    """CRUD and scheduler-sync service for scheduled tasks."""

    def __init__(self) -> None:
        self.scheduler = AkshareScheduler()

    async def start(self) -> None:
        await self.scheduler.start()

    async def shutdown(self) -> None:
        await self.scheduler.shutdown()

    async def list_tasks(
        self,
        db: AsyncSession,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ScheduledTask], int]:
        stmt = select(ScheduledTask)
        count_stmt = select(func.count(ScheduledTask.id))
        if is_active is not None:
            stmt = stmt.where(ScheduledTask.is_active == is_active)
            count_stmt = count_stmt.where(ScheduledTask.is_active == is_active)
        total = int((await db.execute(count_stmt)).scalar() or 0)
        stmt = stmt.order_by(ScheduledTask.created_at.desc()).offset((page - 1) * page_size).limit(
            page_size
        )
        result = await db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_task(self, db: AsyncSession, task_id: int) -> ScheduledTask | None:
        return await db.get(ScheduledTask, task_id)

    async def create_task(self, db: AsyncSession, payload: dict[str, Any], user_id: str) -> ScheduledTask:
        script = await db.scalar(select(DataScript).where(DataScript.script_id == payload["script_id"]))
        if script is None:
            raise ValueError("Script not found")
        if not script.is_active:
            raise ValueError("Script is not active")
        task = ScheduledTask(**payload, user_id=user_id)
        db.add(task)
        await db.commit()
        await db.refresh(task)
        await self.scheduler.add_or_update_task(task.id)
        return task

    async def update_task(
        self,
        db: AsyncSession,
        task_id: int,
        payload: dict[str, Any],
    ) -> ScheduledTask | None:
        task = await self.get_task(db, task_id)
        if task is None:
            return None
        for key, value in payload.items():
            if value is not None and hasattr(task, key):
                setattr(task, key, value)
        await db.commit()
        await db.refresh(task)
        await self.scheduler.add_or_update_task(task.id)
        return task

    async def delete_task(self, db: AsyncSession, task_id: int) -> bool:
        task = await self.get_task(db, task_id)
        if task is None:
            return False
        await db.delete(task)
        await db.commit()
        await self.scheduler.remove_task(task_id)
        return True

    async def toggle_task(self, db: AsyncSession, task_id: int) -> ScheduledTask | None:
        task = await self.get_task(db, task_id)
        if task is None:
            return None
        task.is_active = not task.is_active
        await db.commit()
        await db.refresh(task)
        await self.scheduler.add_or_update_task(task.id)
        return task

    async def run_task_now(
        self,
        task_id: int,
        operator_id: str | None = None,
    ):
        return await self.scheduler.run_task_now(task_id, operator_id=operator_id)

    async def list_task_executions(
        self,
        db: AsyncSession,
        task_id: int,
        page: int = 1,
        page_size: int = 20,
    ):
        service = AkshareExecutionService(db)
        return await service.list_executions(task_id=task_id, page=page, page_size=page_size)

    def get_schedule_templates(self) -> list[dict[str, str]]:
        return SCHEDULE_TEMPLATES
