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

from sqlalchemy import select, update

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

_ACTIVE_UNIT_RUN_STATUSES = ("queued", "materializing", "running", "cancelling")
_UNIT_RUN_LEASE_PREFIX = "lease-"


def _is_unit_run_lease_token(task_id: object) -> bool:
    """Return whether ``last_task_id`` is a no-task runtime lease."""
    return isinstance(task_id, str) and task_id.startswith(_UNIT_RUN_LEASE_PREFIX)


def _task_status_value(task: BacktestTask) -> str:
    """Normalize ORM strings and ``TaskStatus`` values for reconciliation."""
    status = getattr(task, "status", "")
    return str(getattr(status, "value", status))


async def _rewrite_unit_status(
    session: Any,
    unit: StrategyUnit,
    *,
    expected_status: str,
    expected_task_id: str | None,
    next_status: str,
    clear_task_id: bool = False,
) -> bool:
    """CAS one reconciled unit without overwriting a newer run identity.

    Startup may overlap another API process.  A reconciliation snapshot has no
    authority over a lease or task id that changed after it was read, so every
    repair is conditional on both pieces of persisted ownership state.
    """
    conditions = [
        StrategyUnit.id == unit.id,
        StrategyUnit.workspace_id == unit.workspace_id,
        StrategyUnit.run_status == expected_status,
    ]
    if expected_task_id is None:
        conditions.append(StrategyUnit.last_task_id.is_(None))
    else:
        conditions.append(StrategyUnit.last_task_id == expected_task_id)

    values: dict[str, Any] = {"run_status": next_status}
    if clear_task_id:
        values["last_task_id"] = None
    result = await session.execute(update(StrategyUnit).where(*conditions).values(values))
    return int(getattr(result, "rowcount", 0) or 0) == 1


async def reconcile_orphaned_run_statuses() -> int:
    """Repair StrategyUnit.run_status when the backing task is already terminal.

    Walks every unit whose ``run_status`` is active, including the internal
    ``materializing`` and ``cancelling`` runtime-fence states,
    looks up its ``last_task_id``, and forces the unit into the matching
    terminal status (``completed``/``cancelled``/``failed``) when the
    task itself has finished.  A no-task ``lease-...`` identity is an
    interrupted workspace runtime write: it is terminalized with an exact
    compare-and-swap and cleared so a later claim can proceed.  A real
    pending/running task is never released by this repair.

    Returns:
        Number of unit rows whose ``run_status`` was rewritten.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(StrategyUnit)
            .join(Workspace, StrategyUnit.workspace_id == Workspace.id)
            .where(StrategyUnit.run_status.in_(_ACTIVE_UNIT_RUN_STATUSES))
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
            original_status = str(unit.run_status or "").strip().lower()
            last_task_id = str(unit.last_task_id or "").strip()
            task_id = last_task_id or None
            task = task_by_id.get(last_task_id) if last_task_id else None

            if task is None and _is_unit_run_lease_token(last_task_id):
                # The owner process cannot resume a deterministic runtime
                # write after restart.  Release only this exact lease; a
                # concurrent replacement claimant makes the CAS fail closed.
                next_status = "cancelled" if original_status == "cancelling" else "failed"
                if await _rewrite_unit_status(
                    session,
                    unit,
                    expected_status=original_status,
                    expected_task_id=last_task_id,
                    next_status=next_status,
                    clear_task_id=True,
                ):
                    changed += 1
                continue

            if task is None:
                if original_status == "cancelling":
                    next_status = "cancelled"
                elif original_status == "materializing":
                    next_status = "failed"
                elif not task_id:
                    next_status = "idle"
                else:
                    next_status = "failed"
            else:
                mapped = _TASK_STATUS_TO_RUN_STATUS.get(_task_status_value(task))
                if mapped is None:
                    # Task is still pending/running on this side; leave the
                    # exact internal fence and task identity untouched.
                    continue
                # Mirror run_ops finalization: a successful stop has already
                # persisted cancellation intent, which wins over a delayed
                # terminal observation from the task worker.
                next_status = "cancelled" if original_status == "cancelling" else mapped

            if original_status != next_status and await _rewrite_unit_status(
                session,
                unit,
                expected_status=original_status,
                expected_task_id=task_id,
                next_status=next_status,
            ):
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
