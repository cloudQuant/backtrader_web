import threading
from typing import Any

METRIC_NAMES = [
    "total_return",
    "annual_return",
    "sharpe_ratio",
    "max_drawdown",
    "total_trades",
    "win_rate",
    "final_value",
]

_runtime_tasks: dict[str, dict[str, Any]] = {}
_runtime_tasks_lock = threading.Lock()


def get_runtime_task(task_id: str) -> dict[str, Any] | None:
    with _runtime_tasks_lock:
        task = _runtime_tasks.get(task_id)
        return dict(task) if task else None


def set_runtime_task(task_id: str, data: dict[str, Any]) -> None:
    with _runtime_tasks_lock:
        _runtime_tasks[task_id] = dict(data)


def update_runtime_task(task_id: str, **kwargs: Any) -> dict[str, Any] | None:
    with _runtime_tasks_lock:
        task = _runtime_tasks.get(task_id)
        if task is None:
            return None
        task.update(kwargs)
        return dict(task)


def build_runtime_task(
    *,
    status: str,
    strategy_id: str,
    param_ranges: dict[str, dict[str, float]] | None,
    total: int,
    completed: int,
    failed: int,
    results: list[dict[str, Any]] | None,
    n_workers: int,
    created_at: str,
    error: str | None,
) -> dict[str, Any]:
    resolved_param_ranges = param_ranges or {}
    return {
        "status": status,
        "strategy_id": strategy_id,
        "param_names": list(resolved_param_ranges.keys()),
        "param_ranges": resolved_param_ranges,
        "total": total,
        "completed": completed,
        "failed": failed,
        "results": list(results or []),
        "n_workers": n_workers,
        "created_at": created_at,
        "error": error,
    }


def build_initial_runtime_task(
    strategy_id: str,
    param_ranges: dict[str, dict[str, float]],
    total: int,
    n_workers: int,
    created_at: str,
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    return build_runtime_task(
        status=status,
        strategy_id=strategy_id,
        param_ranges=param_ranges,
        total=total,
        completed=0,
        failed=0,
        results=[],
        n_workers=n_workers,
        created_at=created_at,
        error=error,
    )


def build_runtime_task_from_db_task(db_task: Any) -> dict[str, Any]:
    return build_runtime_task(
        status=db_task.status,
        strategy_id=db_task.strategy_id,
        param_ranges=db_task.param_ranges,
        total=db_task.total or 0,
        completed=db_task.completed or 0,
        failed=db_task.failed or 0,
        results=db_task.results,
        n_workers=db_task.n_workers or 4,
        created_at=db_task.created_at.isoformat() if db_task.created_at else "",
        error=db_task.error_message,
    )


def build_progress_response(task_id: str, task: dict[str, Any]) -> dict[str, Any]:
    total = int(task.get("total", 0) or 0)
    completed = int(task.get("completed", 0) or 0)
    failed = int(task.get("failed", 0) or 0)
    done = completed + failed
    return {
        "task_id": task_id,
        "status": task.get("status"),
        "strategy_id": task.get("strategy_id"),
        "total": total,
        "completed": completed,
        "failed": failed,
        "progress": round(done / total * 100, 1) if total > 0 else 0,
        "n_workers": int(task.get("n_workers", 4) or 4),
        "created_at": task.get("created_at", ""),
    }


def build_results_response(task_id: str, task: dict[str, Any]) -> dict[str, Any]:
    results = list(task.get("results", []) or [])
    rows: list[dict[str, Any]] = []
    for result in results:
        row = dict(result.get("params", {}))
        metrics = result.get("metrics")
        if isinstance(metrics, dict):
            row.update(metrics)
        rows.append(row)

    rows.sort(key=lambda row: row.get("annual_return", -999999), reverse=True)
    best = rows[0] if rows else None
    param_names = task.get("param_names") or list((task.get("param_ranges") or {}).keys())

    return {
        "task_id": task_id,
        "status": task.get("status"),
        "strategy_id": task.get("strategy_id"),
        "param_names": param_names,
        "metric_names": METRIC_NAMES,
        "total": int(task.get("total", 0) or 0),
        "completed": int(task.get("completed", 0) or 0),
        "failed": int(task.get("failed", 0) or 0),
        "rows": rows,
        "best": best,
    }
