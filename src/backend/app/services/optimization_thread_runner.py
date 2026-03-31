import logging
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any

from app.schemas.backtest import TaskStatus

module_logger = logging.getLogger(__name__)


def run_optimization_thread(
    task_id: str,
    strategy_dir: str,
    grid: list[dict[str, Any]],
    n_workers: int,
    persist_to_db: bool = True,
    *,
    run_single_trial_fn: Callable[[str, dict[str, Any], int, str], dict[str, Any]],
    is_cancelled_fn: Callable[[str, bool], bool],
    persist_runtime_task_fn: Callable[..., bool],
    get_task_fn: Callable[[str], dict[str, Any] | None],
    update_task_fn: Callable[..., dict[str, Any] | None],
    process_pool_executor_cls: type[ProcessPoolExecutor] = ProcessPoolExecutor,
    as_completed_fn: Callable[[Any], Any] = as_completed,
    mkdtemp_fn: Callable[..., str],
    rmtree_fn: Callable[..., Any],
    logger: logging.Logger | None = None,
) -> None:
    log = logger or module_logger
    tmp_base = mkdtemp_fn(prefix=f"opt_{task_id[:8]}_")
    all_results: list[dict[str, Any]] = []

    try:
        with process_pool_executor_cls(max_workers=n_workers) as executor:
            futures = {}
            for i, params in enumerate(grid):
                if is_cancelled_fn(task_id, persist_to_db):
                    break
                fut = executor.submit(run_single_trial_fn, strategy_dir, params, i, tmp_base)
                futures[fut] = i

            for fut in as_completed_fn(futures):
                if is_cancelled_fn(task_id, persist_to_db):
                    for pending_fut in futures:
                        pending_fut.cancel()
                    break

                try:
                    trial_result = fut.result(timeout=5)
                except Exception:
                    trial_result = {"success": False, "error": "worker exception"}

                if trial_result["success"]:
                    all_results.append(trial_result)
                    update_task_fn(task_id, completed=len(all_results))
                else:
                    task = get_task_fn(task_id)
                    if task:
                        update_task_fn(task_id, failed=task["failed"] + 1)

                update_task_fn(task_id, results=list(all_results))

                if persist_to_db:
                    persist_runtime_task_fn(task_id)

        task = get_task_fn(task_id)
        final_status = (
            TaskStatus.CANCELLED.value
            if (task and task.get("status") == TaskStatus.CANCELLED.value)
            else TaskStatus.COMPLETED.value
        )
        if task and task.get("status") != TaskStatus.CANCELLED.value:
            update_task_fn(task_id, status=TaskStatus.COMPLETED.value, results=all_results)
            final_status = TaskStatus.COMPLETED.value

        if persist_to_db and final_status != TaskStatus.CANCELLED.value:
            if not persist_runtime_task_fn(
                task_id,
                completed=len(all_results),
                failed=task["failed"] if task else 0,
                results=all_results,
                status=final_status,
            ):
                log.warning("Failed to persist optimization results to DB for task %s", task_id)

        if final_status == TaskStatus.CANCELLED.value:
            if persist_to_db:
                if not persist_runtime_task_fn(task_id, status=TaskStatus.CANCELLED.value):
                    log.debug("Failed to persist cancel to DB for task %s", task_id)

        log.info(
            "Optimization %s %s: %s/%s successful",
            task_id,
            final_status,
            len(all_results),
            len(grid),
        )

    except Exception as e:
        log.error("Optimization task failed %s: %s", task_id, e)
        update_task_fn(task_id, status=TaskStatus.FAILED.value, error=str(e))
        if persist_to_db:
            if not persist_runtime_task_fn(
                task_id,
                completed=0,
                failed=0,
                results=[],
                status=TaskStatus.FAILED.value,
                error_message=str(e),
            ):
                log.warning("Failed to persist error to DB for task %s", task_id)
    finally:
        try:
            rmtree_fn(tmp_base, ignore_errors=True)
        except Exception as e:
            # Cleanup is non-critical; log and continue
            log.debug("Temp dir cleanup failed: %s", e)
