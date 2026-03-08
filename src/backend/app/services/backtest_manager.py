"""
Persistent state manager for backtest tasks.

This module stores task metadata and results in the database. Actual backtest
execution is still launched by the API process.
"""

import logging
from typing import Any, List, Optional

from sqlalchemy import delete, select

from app.db.database import async_session_maker
from app.models.backtest import BacktestResultModel, BacktestTask
from app.schemas.backtest import BacktestRequest, TaskStatus

logger = logging.getLogger(__name__)


class BacktestExecutionManager:
    """Manage persisted backtest task state and result records."""

    MAX_GLOBAL_TASKS = 10
    MAX_USER_TASKS = 3

    async def get_user_task_count(self, user_id: str) -> int:
        """Return the current active task count for one user."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(BacktestTask).where(
                    BacktestTask.user_id == user_id,
                    BacktestTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
                )
            )
            return len(result.scalars().all())

    async def get_global_task_count(self) -> int:
        """Return the total active task count across all users."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(BacktestTask).where(
                    BacktestTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])
                )
            )
            return len(result.scalars().all())

    async def can_user_start_task(self, user_id: str) -> bool:
        """Return whether a user is within configured concurrency limits."""
        user_count = await self.get_user_task_count(user_id)
        if user_count >= self.MAX_USER_TASKS:
            logger.warning(
                "User %s has %s active tasks and reached the limit of %s",
                user_id,
                user_count,
                self.MAX_USER_TASKS,
            )
            return False

        global_count = await self.get_global_task_count()
        if global_count >= self.MAX_GLOBAL_TASKS:
            logger.warning(
                "Global active tasks reached the limit of %s",
                self.MAX_GLOBAL_TASKS,
            )
            return False

        return True

    async def create_task(self, user_id: str, request: BacktestRequest) -> BacktestTask:
        """Create a new persisted backtest task."""
        if not await self.can_user_start_task(user_id):
            raise ValueError(
                f"Cannot create task: user {user_id} has reached the concurrent task limit"
            )

        task = BacktestTask(
            user_id=user_id,
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            request_data=request.model_dump(mode="json"),
            status=TaskStatus.PENDING,
        )

        async with async_session_maker() as session:
            session.add(task)
            await session.commit()
            await session.refresh(task)

        logger.info("Created backtest task %s for user %s", task.id, user_id)
        return task

    async def get_task(self, task_id: str, user_id: Optional[str] = None) -> Optional[BacktestTask]:
        """Return one task, optionally enforcing ownership."""
        async with async_session_maker() as session:
            task = await session.get(BacktestTask, task_id)
            if task and user_id and task.user_id != user_id:
                return None
            return task

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error_message: Optional[str] = None,
        log_dir: Optional[str] = None,
    ) -> Optional[BacktestTask]:
        """Update task status and optional error or log path."""
        async with async_session_maker() as session:
            task = await session.get(BacktestTask, task_id)
            if not task:
                return None

            task.status = status
            if error_message:
                task.error_message = error_message
            if log_dir:
                task.log_dir = log_dir

            await session.commit()
            await session.refresh(task)
            return task

    async def create_result(
        self,
        task_id: str,
        metrics: dict[str, Any],
        equity_curve: List[float],
        equity_dates: List[str],
        drawdown_curve: List[float],
        trades: List[dict[str, Any]],
        metrics_source: str = "manual",
    ) -> BacktestResultModel:
        """Create and persist one backtest result."""
        result = BacktestResultModel(
            task_id=task_id,
            total_return=metrics.get("total_return", 0),
            annual_return=metrics.get("annual_return", 0),
            sharpe_ratio=metrics.get("sharpe_ratio", 0),
            max_drawdown=metrics.get("max_drawdown", 0),
            win_rate=metrics.get("win_rate", 0),
            metrics_source=metrics_source,
            total_trades=metrics.get("total_trades", 0),
            profitable_trades=metrics.get("profitable_trades", 0),
            losing_trades=metrics.get("losing_trades", 0),
            equity_curve=equity_curve,
            equity_dates=equity_dates,
            drawdown_curve=drawdown_curve,
            trades=trades,
        )

        async with async_session_maker() as session:
            session.add(result)
            await session.commit()
            await session.refresh(result)

        logger.info("Created backtest result for task %s", task_id)
        return result

    async def get_result(self, task_id: str) -> Optional[BacktestResultModel]:
        """Return the stored result for one task."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(BacktestResultModel).where(BacktestResultModel.task_id == task_id)
            )
            return result.scalars().first()

    async def delete_task_and_result(self, task_id: str, user_id: str) -> bool:
        """Delete a task and its result when the user owns the task."""
        async with async_session_maker() as session:
            task = await session.get(BacktestTask, task_id)
            if not task or task.user_id != user_id:
                return False

            await session.execute(
                delete(BacktestResultModel).where(BacktestResultModel.task_id == task_id)
            )
            await session.delete(task)
            await session.commit()

        logger.info("Deleted backtest task %s and its result", task_id)
        return True

    async def list_user_tasks(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> tuple[List[BacktestTask], int]:
        """List persisted tasks for one user."""
        async with async_session_maker() as session:
            query = select(BacktestTask).where(BacktestTask.user_id == user_id)
            total_result = await session.execute(
                select(BacktestTask).where(BacktestTask.user_id == user_id)
            )
            total = len(total_result.scalars().all())

            order_column = getattr(BacktestTask, order_by, BacktestTask.created_at)
            query = query.order_by(order_column.desc() if order_desc else order_column.asc())
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)

            result = await session.execute(query)
            return list(result.scalars().all()), total
