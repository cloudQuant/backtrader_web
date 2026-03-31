import logging
from collections.abc import Callable
from typing import Any

from app.schemas.backtest import TaskStatus
from app.services.optimization_async_runner import _run_async
from app.services.optimization_execution_manager import (
    get_optimization_execution_manager,
)
from app.services.optimization_task_state import (
    build_runtime_task_from_db_task,
    get_runtime_task,
    update_runtime_task,
)

logger = logging.getLogger(__name__)


def load_optimization_task_state(
    task_id: str,
    user_id: str | None = None,
    use_db: bool = True,
    *,
    get_manager: Callable[[], Any] = get_optimization_execution_manager,
    run_async: Callable[[Any], Any] = _run_async,
    get_task: Callable[[str], dict[str, Any] | None] = get_runtime_task,
    build_runtime_task: Callable[[Any], dict[str, Any]] = build_runtime_task_from_db_task,
) -> dict[str, Any] | None:
    if use_db:
        try:
            mgr = get_manager()
            db_task = run_async(mgr.get_task(task_id, user_id=user_id))
            if db_task:
                return build_runtime_task(db_task)
            if user_id is not None:
                return None
        except Exception as e:
            logger.debug("DB task lookup failed: %s", e)

    return get_task(task_id)


def is_optimization_cancelled(
    task_id: str,
    persist_to_db: bool,
    *,
    get_manager: Callable[[], Any] = get_optimization_execution_manager,
    run_async: Callable[[Any], Any] = _run_async,
    get_task: Callable[[str], dict[str, Any] | None] = get_runtime_task,
    update_task: Callable[..., dict[str, Any] | None] = update_runtime_task,
) -> bool:
    task = get_task(task_id)
    if task and task.get("status") == TaskStatus.CANCELLED.value:
        return True
    if persist_to_db:
        try:
            mgr = get_manager()
            if run_async(mgr.is_cancelled(task_id)):
                update_task(task_id, status=TaskStatus.CANCELLED.value)
                return True
        except Exception as e:
            logger.debug("DB cancel check failed: %s", e)
    return False


def cancel_optimization_task(
    task_id: str,
    user_id: str | None = None,
    use_db: bool = True,
    *,
    get_manager: Callable[[], Any] = get_optimization_execution_manager,
    run_async: Callable[[Any], Any] = _run_async,
    get_task: Callable[[str], dict[str, Any] | None] = get_runtime_task,
    update_task: Callable[..., dict[str, Any] | None] = update_runtime_task,
) -> bool:
    if use_db:
        try:
            mgr = get_manager()
            db_cancelled = run_async(mgr.set_cancelled(task_id, user_id))
            if db_cancelled:
                update_task(task_id, status=TaskStatus.CANCELLED.value)
                return True
            if user_id is not None:
                return False
        except Exception as e:
            logger.debug("DB cancel failed: %s", e)

    task = get_task(task_id)
    if not task:
        return False
    update_task(task_id, status=TaskStatus.CANCELLED.value)
    return True


def persist_optimization_task(
    task_id: str,
    completed: int | None = None,
    failed: int | None = None,
    results: list[dict[str, Any]] | None = None,
    status: str | None = None,
    error_message: str | None = None,
    *,
    get_manager: Callable[[], Any] = get_optimization_execution_manager,
    run_async: Callable[[Any], Any] = _run_async,
    get_task: Callable[[str], dict[str, Any] | None] = get_runtime_task,
) -> bool:
    task = get_task(task_id)
    if task is None and (completed is None or failed is None or results is None):
        return False

    try:
        mgr = get_manager()
        return run_async(
            mgr.update_progress(
                task_id,
                completed=task.get("completed", 0) if completed is None else completed,
                failed=task.get("failed", 0) if failed is None else failed,
                results=task.get("results", []) if results is None else results,
                status=status,
                error_message=error_message,
            )
        )
    except Exception as e:
        logger.debug("DB progress persist failed: %s", e)
        return False
