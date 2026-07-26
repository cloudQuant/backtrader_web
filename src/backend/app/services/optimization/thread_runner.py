import json
import logging
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.backtest import TaskStatus

module_logger = logging.getLogger(__name__)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _trial_summary_entry(result: dict[str, Any]) -> dict[str, Any]:
    is_success = bool(result.get("success")) or bool(result.get("metrics"))
    return {
        "trial_index": result.get("trial_index"),
        "success": is_success,
        "status": "success" if is_success else "failed",
        "params": dict(result.get("params", {}) or {}),
        "metrics": dict(result.get("metrics", {}) or {}),
        "error": result.get("error"),
        "exit_code": result.get("exit_code"),
        "artifact_path": result.get("artifact_path"),
    }


def _update_artifact_manifest(
    artifact_root: str | None,
    *,
    task_id: str,
    grid: list[dict[str, Any]],
    runtime_task: dict[str, Any] | None,
    all_trial_results: list[dict[str, Any]],
    successful_results: list[dict[str, Any]],
    final_status: str | None = None,
) -> None:
    if not artifact_root:
        return

    artifact_root_path = Path(artifact_root)
    manifest_path = artifact_root_path / "manifest.json"
    summary_path = artifact_root_path / "summary.json"
    existing_manifest = _read_json(manifest_path)
    completed_count = len(successful_results)
    failed_count = sum(
        1
        for item in all_trial_results
        if not (bool(item.get("success")) or bool(item.get("metrics")))
    )
    status = final_status or str(
        (runtime_task or {}).get("status") or existing_manifest.get("status") or "running"
    )
    updated_at = datetime.now(timezone.utc).isoformat()
    trial_entries = sorted(
        (_trial_summary_entry(item) for item in all_trial_results),
        key=lambda item: int(item.get("trial_index", -1) or -1),
    )
    best_result = successful_results[0] if successful_results else None

    manifest_payload = {
        **existing_manifest,
        "task_id": task_id,
        "artifact_root": str(artifact_root_path),
        "status": status,
        "total_trials": len(grid),
        "completed": completed_count,
        "failed": failed_count,
        "updated_at": updated_at,
        "successful_trials": completed_count,
        "failed_trials": failed_count,
        "trial_artifacts": trial_entries,
    }
    _write_json(manifest_path, manifest_payload)

    summary_payload = {
        "task_id": task_id,
        "artifact_root": str(artifact_root_path),
        "status": status,
        "total_trials": len(grid),
        "completed": completed_count,
        "failed": failed_count,
        "success_rate": round(completed_count / len(grid), 4) if grid else 0.0,
        "best_result": _trial_summary_entry(best_result) if best_result else None,
        "updated_at": updated_at,
    }
    _write_json(summary_path, summary_payload)


def run_optimization_thread(
    task_id: str,
    strategy_dir: str,
    grid: list[dict[str, Any]],
    n_workers: int,
    persist_to_db: bool = True,
    artifact_root: str | None = None,
    *,
    run_single_trial_fn: Callable[[str, dict[str, Any], int, str, str | None], dict[str, Any]],
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
    successful_results: list[dict[str, Any]] = []
    all_trial_results: list[dict[str, Any]] = []

    try:
        with process_pool_executor_cls(max_workers=n_workers) as executor:
            futures = {}
            for i, params in enumerate(grid):
                if is_cancelled_fn(task_id, persist_to_db):
                    break
                fut = executor.submit(
                    run_single_trial_fn,
                    strategy_dir,
                    params,
                    i,
                    tmp_base,
                    artifact_root,
                )
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

                all_trial_results.append(trial_result)
                trial_succeeded = bool(trial_result.get("success")) or bool(
                    trial_result.get("metrics")
                )

                if trial_succeeded:
                    successful_results.append(trial_result)
                    update_task_fn(task_id, completed=len(successful_results))
                else:
                    task = get_task_fn(task_id)
                    if task:
                        update_task_fn(task_id, failed=task["failed"] + 1)

                task = update_task_fn(task_id, results=list(successful_results))
                _update_artifact_manifest(
                    artifact_root,
                    task_id=task_id,
                    grid=grid,
                    runtime_task=task,
                    all_trial_results=all_trial_results,
                    successful_results=successful_results,
                )

                if persist_to_db:
                    persist_runtime_task_fn(task_id)

        task = get_task_fn(task_id)
        final_status = (
            TaskStatus.CANCELLED.value
            if (task and task.get("status") == TaskStatus.CANCELLED.value)
            else TaskStatus.COMPLETED.value
        )
        if task and task.get("status") != TaskStatus.CANCELLED.value:
            update_task_fn(task_id, status=TaskStatus.COMPLETED.value, results=successful_results)
            final_status = TaskStatus.COMPLETED.value

        _update_artifact_manifest(
            artifact_root,
            task_id=task_id,
            grid=grid,
            runtime_task=get_task_fn(task_id),
            all_trial_results=all_trial_results,
            successful_results=successful_results,
            final_status=final_status,
        )

        if persist_to_db and final_status != TaskStatus.CANCELLED.value:
            if not persist_runtime_task_fn(
                task_id,
                completed=len(successful_results),
                failed=task["failed"] if task else 0,
                results=successful_results,
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
            len(successful_results),
            len(grid),
        )

    except Exception as e:
        log.error("Optimization task failed %s: %s", task_id, e)
        update_task_fn(task_id, status=TaskStatus.FAILED.value, error=str(e))
        _update_artifact_manifest(
            artifact_root,
            task_id=task_id,
            grid=grid,
            runtime_task=get_task_fn(task_id),
            all_trial_results=all_trial_results,
            successful_results=successful_results,
            final_status=TaskStatus.FAILED.value,
        )
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
