"""Workspace reconciliation routines.

These functions are called once at FastAPI startup (see
:mod:`app.main`) to repair stale runtime state left behind by an
unclean shutdown:

* :func:`reconcile_orphaned_run_statuses` — units whose ``run_status``
  is still ``queued``/``running`` but whose backing
  :class:`app.models.backtest.BacktestTask` is already terminal.
* :func:`reconcile_completed_bar_counts` — units that finished a run
  but did not record their final ``bar_count``.

Extracted from the original ``WorkspaceService`` so the god-class shrinks
without breaking its public surface; the facade in
:mod:`app.services.workspace_service` still exposes
``reconcile_orphaned_run_statuses`` and ``reconcile_completed_bar_counts``
as thin async methods that delegate here.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.backtest import BacktestTask
from app.models.workspace import StrategyUnit, Workspace
from app.schemas.backtest import TaskStatus

if TYPE_CHECKING:
    from app.services.backtest.service import BacktestService

logger = logging.getLogger(__name__)


# Status values that come from BacktestTask.status and map to a
# StrategyUnit.run_status terminal value.
_TASK_STATUS_TO_RUN_STATUS: dict[str, str] = {
    TaskStatus.COMPLETED.value: "completed",
    TaskStatus.CANCELLED.value: "cancelled",
    TaskStatus.FAILED.value: "failed",
}


async def reconcile_orphaned_run_statuses() -> int:
    """Repair StrategyUnit.run_status when the backing task is already terminal.

    Walks every unit whose ``run_status`` is ``queued`` or ``running``,
    looks up its ``last_task_id``, and forces the unit into the matching
    terminal status (``completed``/``cancelled``/``failed``) when the
    task itself has finished. Units missing a ``last_task_id`` are
    parked at ``idle``; units whose task row has disappeared are marked
    ``failed`` (the run is unrecoverable).

    Returns:
        Number of unit rows whose ``run_status`` was rewritten.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(StrategyUnit)
            .join(Workspace, StrategyUnit.workspace_id == Workspace.id)
            .where(StrategyUnit.run_status.in_(["queued", "running"]))
            .where(Workspace.workspace_type != "trading")
        )
        units = list(result.scalars().all())
        if not units:
            return 0

        task_ids = [str(unit.last_task_id) for unit in units if unit.last_task_id]
        task_by_id: dict[str, BacktestTask] = {}
        if task_ids:
            task_result = await session.execute(
                select(BacktestTask).where(BacktestTask.id.in_(task_ids))
            )
            task_by_id = {str(task.id): task for task in task_result.scalars().all()}

        changed = 0
        for unit in units:
            last_task_id = str(unit.last_task_id or "").strip()
            if not last_task_id:
                next_status = "idle"
            else:
                task = task_by_id.get(last_task_id)
                if task is None:
                    next_status = "failed"
                else:
                    task_status = str(task.status)
                    mapped = _TASK_STATUS_TO_RUN_STATUS.get(task_status)
                    if mapped is None:
                        # Task is still pending/running on this side; leave alone.
                        continue
                    next_status = mapped

            if str(unit.run_status or "") != next_status:
                unit.run_status = next_status
                changed += 1

        if changed:
            await session.commit()
        return changed


async def reconcile_completed_bar_counts(
    resolve_bar_count: Callable[[BacktestService, str, str | None], Awaitable[int]],
) -> int:
    """Backfill ``StrategyUnit.bar_count`` for completed runs that lost it.

    Args:
        resolve_bar_count: Callable that resolves the bar count for a
            given task. Injected so the helper does not import the
            workspace service back-edge (the historical resolver lives
            on :class:`app.services.workspace_service.WorkspaceService` as
            ``_resolve_unit_bar_count``).

    Returns:
        Number of unit rows whose ``bar_count`` was updated.
    """
    from app.services.backtest.service import BacktestService

    backtest_service = BacktestService()
    async with async_session_maker() as session:
        result = await session.execute(
            select(StrategyUnit).where(
                StrategyUnit.run_status == "completed",
                StrategyUnit.last_task_id.is_not(None),
            )
        )
        units = list(result.scalars().all())
        changed = 0
        for unit in units:
            unit_obj = cast(Any, unit)
            task_id = str(unit_obj.last_task_id or "").strip()
            if not task_id:
                continue
            resolved_bar_count = await resolve_bar_count(
                backtest_service,
                task_id,
                None,
            )
            if resolved_bar_count > 0 and int(unit_obj.bar_count or 0) != resolved_bar_count:
                unit_obj.bar_count = resolved_bar_count
                changed += 1

        if changed:
            await session.commit()
        return changed
