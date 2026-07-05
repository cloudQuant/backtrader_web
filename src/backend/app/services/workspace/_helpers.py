"""Pure helper functions extracted from WorkspaceService.

These are all ``@staticmethod`` methods that perform no database I/O and no
async operations (some do filesystem checks). They are called from the
remaining methods on :class:`app.services.workspace_service.WorkspaceService`
and from the extracted slice modules.

The original class retains thin ``@staticmethod`` shims that delegate here so
that existing tests calling ``WorkspaceService._task_elapsed_seconds(...)``
etc. keep working unchanged.
"""

from __future__ import annotations

import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from app.models.backtest import BacktestTask
from app.models.optimization import OptimizationTask
from app.models.workspace import StrategyUnit
from app.schemas.backtest import TaskStatus
from app.services.optimization.task_state import estimate_remaining_seconds

# Re-use module-level constants from workspace_service (imported lazily to
# avoid circular imports at module load time).
_ACTIVE_OPTIMIZATION_STATUSES = {"pending", "queued", "running"}
_TERMINAL_OPTIMIZATION_STATUSES = {
    TaskStatus.COMPLETED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
}
_ALLOWED_RUNTIME_FILE_EXTENSIONS = frozenset(
    {".log", ".yaml", ".yml", ".json", ".txt", ".py", ".md", ".csv"}
)


# ---------------------------------------------------------------------------
# Elapsed-time helpers
# ---------------------------------------------------------------------------


def parse_runtime_datetime(value: Any) -> datetime | None:
    """Parse an ISO datetime string, defaulting to UTC if naive."""
    if not value:
        return None
    try:
        resolved = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    return resolved


def _as_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def db_task_elapsed_seconds(task: BacktestTask | OptimizationTask | None) -> float | None:
    """Compute elapsed seconds for a persisted task row."""
    if task is None or task.created_at is None:
        return None
    created_at = _as_utc_datetime(cast(datetime, task.created_at))
    if created_at is None:
        return None
    end_time = _as_utc_datetime(cast("datetime | None", task.updated_at))
    if str(getattr(task, "status", "") or "") in {
        TaskStatus.RUNNING.value,
        "pending",
        "queued",
        "running",
    }:
        end_time = datetime.now(timezone.utc)
    else:
        end_time = _as_utc_datetime(end_time)
    if end_time is None:
        return None
    elapsed = (end_time - created_at).total_seconds()
    if elapsed < 0:
        return None
    return round(elapsed, 2)


def task_elapsed_seconds(task: BacktestTask | None) -> float | None:
    """Alias for :func:`db_task_elapsed_seconds` (backtest tasks only)."""
    return db_task_elapsed_seconds(task)


def runtime_optimization_elapsed_seconds(task: dict[str, Any] | None) -> float | None:
    """Compute elapsed seconds for an in-memory optimization task dict."""
    if not task:
        return None
    created_at = parse_runtime_datetime(task.get("created_at"))
    if created_at is None:
        return None
    status = str(task.get("status") or "")
    if not status or status in _ACTIVE_OPTIMIZATION_STATUSES:
        end_time = datetime.now(timezone.utc)
    else:
        end_time = parse_runtime_datetime(task.get("updated_at")) or created_at
    elapsed = (end_time - created_at).total_seconds()
    if elapsed < 0:
        return None
    return round(elapsed, 2)


# ---------------------------------------------------------------------------
# Optimization progress helpers
# ---------------------------------------------------------------------------


def build_runtime_optimization_progress(task: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build progress dict from an in-memory optimization task."""
    if not task:
        return None
    total_c = int(task.get("total") or 0)
    completed_c = int(task.get("completed") or 0) + int(task.get("failed") or 0)
    pct = round(completed_c / total_c * 100, 1) if total_c > 0 else 0
    elapsed_seconds = runtime_optimization_elapsed_seconds(task)
    status = str(task.get("status") or "")
    return {
        "opt_status": task.get("status"),
        "opt_total": total_c,
        "opt_completed": completed_c,
        "opt_progress": pct,
        "opt_elapsed_time": elapsed_seconds if elapsed_seconds is not None else 0.0,
        "opt_remaining_time": estimate_remaining_seconds(
            total=total_c,
            finished=completed_c,
            n_workers=int(task.get("n_workers") or 1),
            elapsed_time=elapsed_seconds,
            status=status,
            task=task,
        ),
    }


def build_db_optimization_progress(task: OptimizationTask | None) -> dict[str, Any] | None:
    """Build progress dict from a persisted optimization task row."""
    if task is None:
        return None
    total_c = int(task.total or 0)
    completed_c = int(task.completed or 0) + int(task.failed or 0)
    pct = round(completed_c / total_c * 100, 1) if total_c > 0 else 0
    elapsed_seconds = db_task_elapsed_seconds(task)
    status = str(task.status or "")
    return {
        "opt_status": task.status,
        "opt_total": total_c,
        "opt_completed": completed_c,
        "opt_progress": pct,
        "opt_elapsed_time": elapsed_seconds if elapsed_seconds is not None else 0.0,
        "opt_remaining_time": estimate_remaining_seconds(
            total=total_c,
            finished=completed_c,
            n_workers=int(task.n_workers or 1),
            elapsed_time=elapsed_seconds,
            status=status,
        ),
    }


def resolve_optimization_progress(
    runtime_task: dict[str, Any] | None,
    db_task: OptimizationTask | None,
) -> dict[str, Any] | None:
    """Pick the best progress source (runtime vs DB)."""
    runtime_progress = build_runtime_optimization_progress(runtime_task)
    db_progress = build_db_optimization_progress(db_task)

    db_status = str((db_progress or {}).get("opt_status") or "")
    if db_progress and db_status in _TERMINAL_OPTIMIZATION_STATUSES:
        return db_progress

    runtime_status = str((runtime_progress or {}).get("opt_status") or "")
    if runtime_progress and runtime_status in _TERMINAL_OPTIMIZATION_STATUSES:
        return runtime_progress

    return runtime_progress or db_progress


def optimization_progress_response_to_opt_info(
    progress: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Convert a progress response dict to the opt_info shape."""
    if not progress:
        return None
    completed = int(progress.get("completed") or 0) + int(progress.get("failed") or 0)
    return {
        "opt_status": progress.get("status"),
        "opt_total": int(progress.get("total") or 0),
        "opt_completed": completed,
        "opt_progress": float(progress.get("progress") or 0.0),
        "opt_elapsed_time": float(progress.get("elapsed_time") or 0.0),
        "opt_remaining_time": float(progress.get("remaining_time") or 0.0),
    }


# ---------------------------------------------------------------------------
# Bar count / data config
# ---------------------------------------------------------------------------


def requested_bar_count(unit: StrategyUnit) -> int | None:
    """Extract the requested bar count from a unit's data_config."""
    from app.services.workspace_service import _normalize_unit_data_config

    data_cfg = _normalize_unit_data_config(cast("dict[str, Any] | None", unit.data_config))
    value = data_cfg.get("bar_count")
    try:
        bar_count = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return None
    return bar_count if bar_count > 0 else None


# ---------------------------------------------------------------------------
# Optimization artifact helpers
# ---------------------------------------------------------------------------


def resolve_optimization_artifact_log_dir(result_entry: dict[str, Any]) -> Path | None:
    """Resolve the log directory for an optimization artifact."""
    artifact_path = Path(str(result_entry.get("artifact_path") or "")).expanduser()
    if not artifact_path.is_dir():
        return None
    logs_dir = artifact_path / "logs"
    if logs_dir.is_dir():
        return logs_dir
    return artifact_path


def build_optimization_artifact_metadata(
    task_id: str,
    result_index: int,
    result_entry: dict[str, Any],
) -> dict[str, Any]:
    """Build metadata dict for an optimization artifact."""
    artifact_path = str(result_entry.get("artifact_path") or "")
    artifact_dir = Path(artifact_path).expanduser() if artifact_path else None
    manifest_path = artifact_dir.parent / "manifest.json" if artifact_dir else None
    summary_path = artifact_dir.parent / "summary.json" if artifact_dir else None
    is_success = bool(result_entry.get("success")) or bool(result_entry.get("metrics"))
    return {
        "artifact_path": artifact_path or None,
        "artifact_manifest_path": str(manifest_path)
        if manifest_path and manifest_path.is_file()
        else None,
        "artifact_summary_path": str(summary_path)
        if summary_path and summary_path.is_file()
        else None,
        "artifact_status": "success" if is_success else "failed",
        "artifact_error": result_entry.get("error"),
        "optimization_task_id": task_id,
        "optimization_result_index": result_index,
        "trial_index": result_entry.get("trial_index"),
    }


# ---------------------------------------------------------------------------
# Runtime file helpers
# ---------------------------------------------------------------------------


def collect_runtime_files(runtime_dir: Path) -> list[Path]:
    """Collect relevant runtime files from a unit's runtime directory."""
    files: list[Path] = []
    preferred_top_level = ["config.yaml", "run.py"]
    for name in preferred_top_level:
        path = runtime_dir / name
        if path.is_file():
            files.append(Path(name))

    for candidate in sorted(runtime_dir.glob("strategy_*.py")):
        if candidate.is_file():
            files.append(candidate.relative_to(runtime_dir))

    log_dir = runtime_dir / "logs"
    if log_dir.is_dir():
        for candidate in sorted(log_dir.iterdir()):
            if candidate.is_file():
                files.append(candidate.relative_to(runtime_dir))

    return files


def runtime_file_kind(relative_path: Path) -> str:
    """Classify a runtime file by its relative path."""
    if relative_path.parts and relative_path.parts[0] == "logs":
        return "log"
    if relative_path.name == "config.yaml":
        return "config"
    if relative_path.name == "run.py":
        return "runner"
    if relative_path.name.startswith("strategy_") and relative_path.suffix == ".py":
        return "strategy"
    return "file"


def resolve_runtime_file(runtime_dir: Path, relative_path: str) -> Path | None:
    """Resolve and validate a runtime file path (path-traversal safe)."""
    candidate = (runtime_dir / str(relative_path or "")).resolve()
    runtime_root = runtime_dir.resolve()
    if not candidate.is_relative_to(runtime_root):
        return None
    if candidate.suffix.lower() not in _ALLOWED_RUNTIME_FILE_EXTENSIONS:
        return None
    return candidate


def open_path_in_file_manager(path: Path) -> None:
    """Open a path in the system file manager."""
    system = platform.system().lower()
    if system == "darwin":
        command = ["open", str(path)]
    elif system == "windows":
        command = ["explorer", str(path)]
    else:
        command = ["xdg-open", str(path)]
    subprocess.Popen(command)


def unit_to_dict(unit: StrategyUnit, opt_info: dict[str, Any] | None = None) -> dict[str, Any]:
    from app.services.trading_workspace_service import TradingWorkspaceService
    from app.services.workspace_service import _normalize_unit_data_config

    opt_info = opt_info or {}
    return {
        "id": unit.id,
        "workspace_id": unit.workspace_id,
        "group_name": unit.group_name or "",
        "strategy_id": unit.strategy_id,
        "strategy_name": unit.strategy_name or "",
        "symbol": unit.symbol or "",
        "symbol_name": unit.symbol_name or "",
        "timeframe": unit.timeframe or "1d",
        "timeframe_n": unit.timeframe_n or 1,
        "category": unit.category or "",
        "sort_order": unit.sort_order or 0,
        "data_config": _normalize_unit_data_config(cast("dict[str, Any] | None", unit.data_config)),
        "unit_settings": unit.unit_settings or {},
        "params": unit.params or {},
        "optimization_config": unit.optimization_config or {},
        "trading_mode": TradingWorkspaceService.normalize_trading_mode(unit.trading_mode),
        "gateway_config": TradingWorkspaceService.normalize_gateway_config(
            cast("dict[str, Any] | None", unit.gateway_config) or {}
        ),
        "lock_trading": bool(unit.lock_trading),
        "lock_running": bool(unit.lock_running),
        "trading_instance_id": unit.trading_instance_id,
        "trading_snapshot": unit.trading_snapshot or {},
        "run_status": unit.run_status or "idle",
        "run_count": unit.run_count or 0,
        "last_run_time": unit.last_run_time,
        "last_task_id": unit.last_task_id,
        "last_optimization_task_id": unit.last_optimization_task_id,
        "bar_count": unit.bar_count,
        "metrics_snapshot": unit.metrics_snapshot or {},
        "opt_status": opt_info.get("opt_status"),
        "opt_total": opt_info.get("opt_total"),
        "opt_completed": opt_info.get("opt_completed"),
        "opt_progress": opt_info.get("opt_progress"),
        "opt_elapsed_time": opt_info.get("opt_elapsed_time"),
        "opt_remaining_time": opt_info.get("opt_remaining_time"),
        "created_at": unit.created_at,
        "updated_at": unit.updated_at,
    }


# ---------------------------------------------------------------------------
# Rename helper
# ---------------------------------------------------------------------------


def compute_rename(
    unit: StrategyUnit,
    mode: str,
    value: str,
    search: str,
    replace: str,
) -> str:
    """Compute the new name for a unit based on rename mode."""
    if mode == "custom":
        return value
    elif mode == "strategy":
        return str(unit.strategy_name or "")
    elif mode == "symbol":
        return str(unit.symbol or "")
    elif mode == "symbol_name":
        return str(unit.symbol_name or "")
    elif mode == "category":
        return str(unit.category or "")
    elif mode == "replace":
        current = str(unit.group_name or "")
        return current.replace(search, replace) if search else current
    return value
