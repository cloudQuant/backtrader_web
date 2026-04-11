import threading
from datetime import datetime, timezone
from typing import Any

METRIC_NAMES = [
    "initial_cash",
    "net_value",
    "net_profit",
    "total_return",
    "annual_return",
    "sharpe_ratio",
    "max_drawdown",
    "max_drawdown_value",
    "max_market_value",
    "max_leverage",
    "adjusted_return_risk",
    "total_trades",
    "win_rate",
    "avg_profit",
    "avg_profit_rate",
    "total_win_amount",
    "total_loss_amount",
    "profit_loss_ratio",
    "profit_factor",
    "profit_rate_factor",
    "profit_loss_rate_ratio",
    "odds",
    "daily_avg_return",
    "daily_max_loss",
    "daily_max_profit",
    "weekly_avg_return",
    "weekly_max_loss",
    "weekly_max_profit",
    "monthly_avg_return",
    "monthly_max_loss",
    "monthly_max_profit",
    "trading_cost",
    "trading_days",
    "final_value",
]

_runtime_tasks: dict[str, dict[str, Any]] = {}
_runtime_tasks_lock = threading.Lock()
_ACTIVE_OPTIMIZATION_STATUSES = {"pending", "queued", "running"}
_ETA_SAMPLE_WINDOW = 5
_ETA_PROGRESS_SNAPSHOT_WINDOW = 16
_ETA_SLOWDOWN_ALPHA = 0.1
_ETA_SPEEDUP_ALPHA = 0.75


def _finished_count(task: dict[str, Any]) -> int:
    return int(task.get("completed", 0) or 0) + int(task.get("failed", 0) or 0)


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
        previous_finished = _finished_count(task)
        updated_at = kwargs.pop("updated_at", datetime.now(timezone.utc).isoformat())
        task["updated_at"] = updated_at
        task.update(kwargs)
        _record_eta_progress(task, previous_finished=previous_finished, updated_at=updated_at)
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
    updated_at: str | None = None,
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
        "updated_at": updated_at or created_at,
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
        updated_at=db_task.updated_at.isoformat() if getattr(db_task, "updated_at", None) else "",
    )


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        resolved = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    return resolved


def _runtime_task_elapsed_seconds(task: dict[str, Any]) -> float | None:
    created_at = _parse_iso_datetime(task.get("created_at"))
    if created_at is None:
        return None
    status = str(task.get("status") or "")
    if status in _ACTIVE_OPTIMIZATION_STATUSES:
        end_at = datetime.now(timezone.utc)
    else:
        end_at = _parse_iso_datetime(task.get("updated_at")) or created_at
    elapsed = (end_at - created_at).total_seconds()
    if elapsed < 0:
        return None
    return round(elapsed, 2)


def _robust_seconds_per_finished(samples: list[float]) -> float | None:
    positive_samples = sorted(sample for sample in samples if sample > 0)
    if not positive_samples:
        return None
    if len(positive_samples) == 1:
        return positive_samples[0]
    if len(positive_samples) == 2:
        return sum(positive_samples) / 2
    if len(positive_samples) == 3:
        return positive_samples[1]
    trimmed_samples = positive_samples[1:-1]
    if not trimmed_samples:
        return None
    return sum(trimmed_samples) / len(trimmed_samples)


def _record_eta_progress(
    task: dict[str, Any],
    *,
    previous_finished: int,
    updated_at: str,
) -> None:
    current_finished = _finished_count(task)
    if current_finished <= previous_finished:
        return

    updated_at_dt = _parse_iso_datetime(updated_at)
    if updated_at_dt is None:
        return

    snapshots = list(task.get("_eta_progress_snapshots") or [])
    snapshots.append({"finished": current_finished, "at": updated_at})
    snapshots = snapshots[-max(_ETA_PROGRESS_SNAPSHOT_WINDOW, 1) :]
    task["_eta_progress_snapshots"] = snapshots

    total = int(task.get("total") or 0)
    effective_workers = max(1, min(total or current_finished or 1, int(task.get("n_workers") or 1)))
    if current_finished < effective_workers:
        task["_eta_last_sample_finished"] = current_finished
        task["_eta_last_sample_at"] = updated_at
        return

    created_at_dt = _parse_iso_datetime(task.get("created_at"))
    baseline_finished = 0
    baseline_at = created_at_dt
    target_finished = max(0, current_finished - effective_workers)
    for snapshot in reversed(snapshots[:-1]):
        snapshot_finished = int(snapshot.get("finished") or 0)
        snapshot_at = _parse_iso_datetime(snapshot.get("at"))
        if snapshot_at is None:
            continue
        if snapshot_finished <= target_finished:
            baseline_finished = snapshot_finished
            baseline_at = snapshot_at
            break

    if baseline_at is not None and current_finished > baseline_finished:
        delta_finished = current_finished - baseline_finished
        delta_seconds = (updated_at_dt - baseline_at).total_seconds()
        if delta_finished > 0 and delta_seconds > 0:
            seconds_per_finished = delta_seconds / delta_finished
            samples = list(task.get("_eta_recent_seconds_per_finished") or [])
            samples.append(round(seconds_per_finished, 4))
            recent_samples = samples[-max(_ETA_SAMPLE_WINDOW, 1) :]
            task["_eta_recent_seconds_per_finished"] = recent_samples
            previous_smoothed = task.get("_eta_smoothed_seconds_per_finished")
            robust_seconds_per_finished = (
                _robust_seconds_per_finished(recent_samples) or seconds_per_finished
            )
            candidate_seconds_per_finished = robust_seconds_per_finished
            if isinstance(previous_smoothed, int | float) and float(previous_smoothed) > 0:
                if seconds_per_finished <= float(previous_smoothed):
                    candidate_seconds_per_finished = seconds_per_finished
            if isinstance(previous_smoothed, int | float) and float(previous_smoothed) > 0:
                alpha = (
                    _ETA_SPEEDUP_ALPHA
                    if candidate_seconds_per_finished <= float(previous_smoothed)
                    else _ETA_SLOWDOWN_ALPHA
                )
                smoothed = (
                    float(previous_smoothed) * (1.0 - alpha)
                    + candidate_seconds_per_finished * alpha
                )
            else:
                smoothed = candidate_seconds_per_finished
            task["_eta_smoothed_seconds_per_finished"] = round(smoothed, 4)

    task["_eta_last_sample_finished"] = current_finished
    task["_eta_last_sample_at"] = updated_at


def _resolved_seconds_per_finished(
    *,
    task: dict[str, Any] | None,
    total: int,
    finished: int,
    n_workers: int,
    elapsed_time: float | None,
) -> tuple[float | None, datetime | None]:
    effective_workers = max(
        1,
        min(
            int((task or {}).get("total") or total or finished or 1),
            int((task or {}).get("n_workers") or n_workers or 1),
        ),
    )
    if finished < effective_workers:
        return None, None
    if task:
        smoothed = task.get("_eta_smoothed_seconds_per_finished")
        if isinstance(smoothed, int | float) and float(smoothed) > 0:
            return (
                float(smoothed),
                _parse_iso_datetime(task.get("_eta_last_sample_at"))
                or _parse_iso_datetime(task.get("updated_at")),
            )
        samples = [
            float(sample)
            for sample in (task.get("_eta_recent_seconds_per_finished") or [])
            if isinstance(sample, int | float) and float(sample) > 0
        ]
        if samples:
            recent_samples = samples[-max(_ETA_SAMPLE_WINDOW, 1) :]
            return (
                sum(recent_samples) / len(recent_samples),
                _parse_iso_datetime(task.get("_eta_last_sample_at"))
                or _parse_iso_datetime(task.get("updated_at")),
            )
    if finished >= effective_workers and elapsed_time is not None and elapsed_time > 0:
        return elapsed_time / finished, None
    return None, None


def estimate_remaining_seconds(
    *,
    total: int,
    finished: int,
    n_workers: int,
    elapsed_time: float | None,
    status: str | None = None,
    task: dict[str, Any] | None = None,
) -> float:
    if status and status not in _ACTIVE_OPTIMIZATION_STATUSES:
        return 0.0
    if total <= 0 or finished >= total:
        return 0.0
    if elapsed_time is None or elapsed_time <= 0:
        return 0.0
    seconds_per_finished, reference_at = _resolved_seconds_per_finished(
        task=task,
        total=total,
        finished=finished,
        n_workers=n_workers,
        elapsed_time=elapsed_time,
    )
    if seconds_per_finished is None or seconds_per_finished <= 0:
        return 0.0
    remaining_seconds = seconds_per_finished * (total - finished)
    if reference_at is not None:
        remaining_seconds = max(
            0.0,
            remaining_seconds - (datetime.now(timezone.utc) - reference_at).total_seconds(),
        )
    return round(max(0.0, remaining_seconds), 2)


def build_progress_response(task_id: str, task: dict[str, Any]) -> dict[str, Any]:
    total = int(task.get("total", 0) or 0)
    completed = int(task.get("completed", 0) or 0)
    failed = int(task.get("failed", 0) or 0)
    done = completed + failed
    n_workers = int(task.get("n_workers", 4) or 4)
    elapsed_time = _runtime_task_elapsed_seconds(task)
    return {
        "task_id": task_id,
        "status": task.get("status"),
        "strategy_id": task.get("strategy_id"),
        "total": total,
        "completed": completed,
        "failed": failed,
        "progress": round(done / total * 100, 1) if total > 0 else 0,
        "n_workers": n_workers,
        "created_at": task.get("created_at", ""),
        "elapsed_time": elapsed_time if elapsed_time is not None else 0.0,
        "remaining_time": estimate_remaining_seconds(
            total=total,
            finished=done,
            n_workers=n_workers,
            elapsed_time=elapsed_time,
            status=str(task.get("status") or ""),
            task=task,
        ),
    }


def build_results_response(task_id: str, task: dict[str, Any]) -> dict[str, Any]:
    results = list(task.get("results", []) or [])
    rows: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        params = dict(result.get("params", {}) or {})
        row = dict(params)
        metrics = result.get("metrics")
        if isinstance(metrics, dict):
            row.update(metrics)
        row["params"] = params
        row["result_index"] = index
        if "artifact_path" in result:
            row["artifact_path"] = result.get("artifact_path")
        if "trial_index" in result:
            row["trial_index"] = result.get("trial_index")
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
