"""
Persistent state manager for parameter optimization tasks.

Stores task metadata and results in the database for multi-instance support
and restart resilience.
"""

import logging
from functools import lru_cache
from typing import Any

from sqlalchemy import select, update

from app.db.database import async_session_maker
from app.models.optimization import OptimizationTask

logger = logging.getLogger(__name__)


class OptimizationExecutionManager:
    """Manage persisted optimization task state and results."""

    async def create_task(
        self,
        user_id: str,
        strategy_id: str,
        total: int,
        param_ranges: dict[str, Any],
        n_workers: int,
    ) -> OptimizationTask:
        """Create a new persisted optimization task."""
        task = OptimizationTask(
            user_id=user_id,
            strategy_id=strategy_id,
            status="running",
            total=total,
            completed=0,
            failed=0,
            results=[],
            param_ranges=param_ranges,
            n_workers=n_workers,
        )

        async with async_session_maker() as session:
            session.add(task)
            await session.commit()
            await session.refresh(task)

        logger.info("Created optimization task %s for user %s", task.id, user_id)
        return task

    async def get_task(self, task_id: str, user_id: str | None = None) -> OptimizationTask | None:
        """Return one task, optionally enforcing ownership."""
        async with async_session_maker() as session:
            task = await session.get(OptimizationTask, task_id)
            if task and user_id and task.user_id != user_id:
                return None
            return task

    async def update_progress(
        self,
        task_id: str,
        completed: int,
        failed: int,
        results: list[dict[str, Any]],
        status: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Update task progress and optionally status."""
        values: dict[str, Any] = {
            "completed": completed,
            "failed": failed,
            "results": results,
        }
        if status:
            values["status"] = status
        if error_message:
            values["error_message"] = error_message

        async with async_session_maker() as session:
            result = await session.execute(
                update(OptimizationTask).where(OptimizationTask.id == task_id).values(**values)
            )
            await session.commit()
            return result.rowcount > 0

    async def set_cancelled(self, task_id: str, user_id: str | None = None) -> bool:
        """Mark task as cancelled. Returns False if not found or ownership mismatch."""
        task = await self.get_task(task_id, user_id)
        if not task:
            return False

        async with async_session_maker() as session:
            await session.execute(
                update(OptimizationTask)
                .where(OptimizationTask.id == task_id)
                .values(status="cancelled")
            )
            await session.commit()
        return True

    async def is_cancelled(self, task_id: str) -> bool:
        """Check if task is marked cancelled in DB (for cross-instance cancel check)."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(OptimizationTask.status).where(OptimizationTask.id == task_id)
            )
            row = result.scalar_one_or_none()
            return row == "cancelled" if row else False


@lru_cache
def get_optimization_execution_manager() -> OptimizationExecutionManager:
    """Return singleton OptimizationExecutionManager."""
    return OptimizationExecutionManager()
