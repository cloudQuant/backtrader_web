"""
Single-instance APScheduler wrapper for akshare tasks.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.config import get_settings
from app.db.database import async_session_maker
from app.models.akshare_mgmt import ScheduledTask, ScheduleType, TriggeredBy
from app.services.akshare_script_service import AkshareScriptService

settings = get_settings()


class AkshareScheduler:
    """In-memory scheduler for akshare tasks."""

    def __init__(self) -> None:
        self.scheduler = None

    def _ensure_scheduler(self):
        if self.scheduler is not None:
            return self.scheduler
        try:
            from apscheduler.executors.asyncio import AsyncIOExecutor
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
        except ImportError as exc:
            raise RuntimeError("APScheduler is not installed") from exc

        self.scheduler = AsyncIOScheduler(
            executors={"default": AsyncIOExecutor()},
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
            timezone=settings.AKSHARE_SCHEDULER_TIMEZONE,
        )
        return self.scheduler

    async def start(self) -> None:
        scheduler = self._ensure_scheduler()
        if not scheduler.running:
            scheduler.start()
            await self.reload_active_tasks()

    async def shutdown(self) -> None:
        if self.scheduler is not None and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None

    def _build_trigger(self, task: ScheduledTask):
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.date import DateTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        if task.schedule_type == ScheduleType.CRON:
            return CronTrigger.from_crontab(
                task.schedule_expression, timezone=settings.AKSHARE_SCHEDULER_TIMEZONE
            )
        if task.schedule_type == ScheduleType.DAILY and ":" in task.schedule_expression:
            hour, minute = task.schedule_expression.split(":")
            return CronTrigger(
                hour=int(hour),
                minute=int(minute),
                timezone=settings.AKSHARE_SCHEDULER_TIMEZONE,
            )
        if task.schedule_type in {ScheduleType.DAILY, ScheduleType.WEEKLY, ScheduleType.MONTHLY}:
            return CronTrigger.from_crontab(
                task.schedule_expression, timezone=settings.AKSHARE_SCHEDULER_TIMEZONE
            )
        if task.schedule_type == ScheduleType.INTERVAL:
            expression = task.schedule_expression.strip().lower()
            if expression.endswith("m"):
                return IntervalTrigger(minutes=int(expression[:-1]))
            if expression.endswith("h"):
                return IntervalTrigger(hours=int(expression[:-1]))
            if expression.endswith("d"):
                return IntervalTrigger(days=int(expression[:-1]))
            return IntervalTrigger(minutes=int(expression))
        return DateTrigger(run_date=datetime.now())

    async def _run_task_job(self, task_id: int) -> None:
        await self.run_task_now(task_id)

    async def add_or_update_task(self, task_id: int) -> None:
        scheduler = self._ensure_scheduler()
        async with async_session_maker() as session:
            task = await session.get(ScheduledTask, task_id)
            if task is None:
                return
            job_id = f"ak_task_{task.id}"
            if not task.is_active:
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
                task.next_execution_at = None
                await session.commit()
                return
            job = scheduler.add_job(
                self._run_task_job,
                trigger=self._build_trigger(task),
                id=job_id,
                replace_existing=True,
                kwargs={"task_id": task.id},
                name=task.name,
            )
            task.next_execution_at = getattr(job, "next_run_time", None)
            await session.commit()

    async def remove_task(self, task_id: int) -> None:
        scheduler = self._ensure_scheduler()
        job_id = f"ak_task_{task_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

    async def reload_active_tasks(self) -> None:
        async with async_session_maker() as session:
            result = await session.execute(
                select(ScheduledTask.id).where(ScheduledTask.is_active.is_(True))
            )
            task_ids = [row[0] for row in result.all()]
        for task_id in task_ids:
            await self.add_or_update_task(task_id)

    async def run_task_now(self, task_id: int, operator_id: str | None = None):
        async with async_session_maker() as session:
            task = await session.get(ScheduledTask, task_id)
            if task is None:
                raise ValueError("Task not found")
            service = AkshareScriptService(session)
            execution = await service.run_script(
                task.script_id,
                parameters=task.parameters,
                operator_id=operator_id,
                task_id=task.id,
                triggered_by=TriggeredBy.MANUAL if operator_id else TriggeredBy.SCHEDULER,
            )
            scheduler = self._ensure_scheduler()
            job = scheduler.get_job(f"ak_task_{task.id}")
            task.last_execution_at = datetime.now()
            task.next_execution_at = getattr(job, "next_run_time", None) if job else None
            await session.commit()
            return execution
