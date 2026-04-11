"""
Parameter optimization service (multiprocess grid search).

Design:
- Build a Cartesian product grid from (start, end, step) parameter ranges.
- Evaluate combinations in parallel via concurrent.futures.ProcessPoolExecutor.
- Each worker: write a temporary config.yaml -> run a run.py subprocess -> parse logs -> return metrics.
- The main process aggregates results and exposes progress queries.
- Task state is persisted to DB for multi-instance support and restart resilience.
"""

import asyncio
import itertools
import logging
import shutil
import subprocess
import tempfile
import threading
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.backtest import TaskStatus
from app.schemas.backtest_enhanced import OptimizationRequest
from app.services.backtest_service import BacktestService
from app.services.optimization_async_runner import (
    _ensure_async_runner_loop,
    _run_async,
)
from app.services.optimization_execution_manager import (
    get_optimization_execution_manager,
)
from app.services.optimization_submission import (
    generate_param_grid as _submission_generate_param_grid,
)
from app.services.optimization_submission import (
    submit_optimization as _submission_submit_optimization,
)
from app.services.optimization_task_gateway import (
    cancel_optimization_task as _gateway_cancel_optimization_task,
)
from app.services.optimization_task_gateway import (
    is_optimization_cancelled as _gateway_is_optimization_cancelled,
)
from app.services.optimization_task_gateway import (
    load_optimization_task_state as _gateway_load_optimization_task_state,
)
from app.services.optimization_task_gateway import (
    persist_optimization_task as _gateway_persist_optimization_task,
)
from app.services.optimization_task_state import (
    build_initial_runtime_task,
    build_progress_response,
    build_results_response,
    build_runtime_task_from_db_task,
    get_runtime_task,
    set_runtime_task,
    update_runtime_task,
)
from app.services.optimization_thread_runner import (
    run_optimization_thread as _thread_runner_run_optimization_thread,
)
from app.services.optimization_trial_runner import (
    parse_trial_logs as _trial_runner_parse_trial_logs,
)
from app.services.optimization_trial_runner import (
    run_single_trial as _trial_runner_run_single_trial,
)
from app.services.optimization_trial_runner import safe_float as _trial_runner_safe_float

logger = logging.getLogger(__name__)

__all__ = ["_ensure_async_runner_loop", "_run_async"]

# ---- Global State ----


def _get_task(task_id: str) -> dict[str, Any] | None:
    """Get a task by ID from the global task registry.

    Args:
        task_id: The task identifier.

    Returns:
        The task dictionary if found, None otherwise.
    """
    return get_runtime_task(task_id)


def _set_task(task_id: str, data: dict[str, Any]):
    """Set a task in the global task registry.

    Args:
        task_id: The task identifier.
        data: The task data dictionary to store.
    """
    set_runtime_task(task_id, data)


def _update_task(task_id: str, **kwargs):
    """Update specific fields of a task in the global registry.

    Args:
        task_id: The task identifier.
        **kwargs: Field names and values to update.
    """
    return update_runtime_task(task_id, **kwargs)


def _load_task_state(
    task_id: str, user_id: str | None = None, use_db: bool = True
) -> dict[str, Any] | None:
    return _gateway_load_optimization_task_state(
        task_id,
        user_id=user_id,
        use_db=use_db,
        get_manager=get_optimization_execution_manager,
        run_async=_run_async,
        get_task=_get_task,
        build_runtime_task=build_runtime_task_from_db_task,
    )


def _query_task_response(
    task_id: str,
    response_builder,
    user_id: str | None = None,
    use_db: bool = True,
) -> dict[str, Any] | None:
    task = _load_task_state(task_id, user_id=user_id, use_db=use_db)
    if not task:
        return None
    return response_builder(task_id, task)


def _is_optimization_cancelled(task_id: str, persist_to_db: bool) -> bool:
    return _gateway_is_optimization_cancelled(
        task_id,
        persist_to_db,
        get_manager=get_optimization_execution_manager,
        run_async=_run_async,
        get_task=_get_task,
        update_task=_update_task,
    )


def _persist_runtime_task(
    task_id: str,
    completed: int | None = None,
    failed: int | None = None,
    results: list[dict[str, Any]] | None = None,
    status: str | None = None,
    error_message: str | None = None,
) -> bool:
    return _gateway_persist_optimization_task(
        task_id,
        completed=completed,
        failed=failed,
        results=results,
        status=status,
        error_message=error_message,
        get_manager=get_optimization_execution_manager,
        run_async=_run_async,
        get_task=_get_task,
    )


# ---- Worker (runs in subprocess of ProcessPoolExecutor) ----


def _run_single_trial(
    strategy_dir: str,
    params: dict[str, Any],
    trial_index: int,
    tmp_base: str,
    artifact_root: str | None = None,
) -> dict[str, Any]:
    """Run a single backtest trial in an isolated process.

    To avoid conflicts from multiple processes writing to the same logs/
    directory, the entire strategy directory is copied to a temporary
    location for execution.

    Args:
        strategy_dir: Path to the strategy directory containing run.py.
        params: Dictionary of parameters to use for this trial.
        trial_index: Index of this trial in the optimization grid.
        tmp_base: Base temporary directory for trial execution.

    Returns:
        Dictionary containing trial results with keys:
        - params: The parameters used for this trial
        - trial_index: Index of this trial
        - success: Boolean indicating if trial succeeded
        - metrics: Performance metrics (if success=True)
        - error: Error message (if success=False)
    """
    return _trial_runner_run_single_trial(
        strategy_dir,
        params,
        trial_index,
        tmp_base,
        artifact_root,
        parse_trial_logs_fn=_parse_trial_logs,
        subprocess_module=subprocess,
    )


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Convert a value to float, handling NaN and infinity.

    Args:
        val: Value to convert.
        default: Default value to return if conversion fails or value is invalid.

    Returns:
        Float value or default if conversion fails or value is NaN/inf.
    """
    return _trial_runner_safe_float(val, default)


def _parse_trial_logs(trial_dir: Path) -> dict[str, float] | None:
    """Extract core performance metrics from a trial's logs directory.

    Args:
        trial_dir: Path to the trial directory containing logs.

    Returns:
        Dictionary containing performance metrics:
        - total_return: Total return percentage
        - annual_return: Annualized return percentage
        - sharpe_ratio: Sharpe ratio
        - max_drawdown: Maximum drawdown percentage
        - total_trades: Total number of trades
        - win_rate: Win rate percentage
        - final_value: Final portfolio value
        Returns None if logs are not available.
    """
    return _trial_runner_parse_trial_logs(trial_dir, safe_float_fn=_safe_float)


# ---- Public API ----


def generate_param_grid(
    param_ranges: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    """Generate a Cartesian product parameter grid from range specifications.

    Args:
        param_ranges: Dictionary mapping parameter names to range specifications.
            Each spec must contain: start (inclusive), end (inclusive), step.
            Optional: type ("int" or "float", defaults to "float").

    Returns:
        List of parameter dictionaries, one for each combination in the grid.
    """
    return _submission_generate_param_grid(param_ranges)


def submit_optimization(
    strategy_id: str,
    param_ranges: dict[str, dict[str, float]],
    n_workers: int = 4,
    task_id: str | None = None,
    persist_to_db: bool = True,
    strategy_dir: str | None = None,
    artifact_root: str | None = None,
) -> str:
    """Submit an optimization task to run asynchronously.

    Args:
        strategy_id: The strategy identifier to optimize.
        param_ranges: Dictionary mapping parameter names to range specifications.
        n_workers: Number of parallel worker processes to use.
        task_id: Optional task ID (e.g. from DB). If not provided, generates one.
        persist_to_db: If True and task_id is from DB, persist results to DB on completion.
        strategy_dir: Pre-resolved strategy directory (e.g. unit runtime dir).
            If provided, skips get_strategy_dir lookup.

    Returns:
        The task ID for tracking optimization progress.

    Raises:
        ValueError: If strategy does not exist or parameter grid is empty.
    """
    from app.services.strategy_service import get_strategy_dir

    return _submission_submit_optimization(
        strategy_id,
        param_ranges,
        n_workers=n_workers,
        task_id=task_id,
        persist_to_db=persist_to_db,
        artifact_root=artifact_root,
        get_strategy_dir=get_strategy_dir,
        generate_param_grid_fn=generate_param_grid,
        set_task_fn=_set_task,
        build_initial_runtime_task_fn=build_initial_runtime_task,
        created_at_fn=lambda: datetime.now(timezone.utc).isoformat(),
        running_status=TaskStatus.RUNNING.value,
        thread_cls=threading.Thread,
        run_optimization_thread_fn=_run_optimization_thread,
        task_id_factory=lambda: uuid.uuid4().hex[:8],
        strategy_dir_override=strategy_dir,
    )


def _run_optimization_thread(
    task_id: str,
    strategy_dir: str,
    grid: list[dict[str, Any]],
    n_workers: int,
    persist_to_db: bool = True,
    artifact_root: str | None = None,
):
    """Run multiprocess optimization in a background thread.

    Args:
        task_id: The optimization task identifier.
        strategy_dir: Path to the strategy directory.
        grid: List of parameter combinations to evaluate.
        n_workers: Number of parallel worker processes.
        persist_to_db: If True, persist final state to DB on completion.
    """
    _thread_runner_run_optimization_thread(
        task_id,
        strategy_dir,
        grid,
        n_workers,
        persist_to_db=persist_to_db,
        artifact_root=artifact_root,
        run_single_trial_fn=_run_single_trial,
        is_cancelled_fn=_is_optimization_cancelled,
        persist_runtime_task_fn=_persist_runtime_task,
        get_task_fn=_get_task,
        update_task_fn=_update_task,
        process_pool_executor_cls=ProcessPoolExecutor,
        as_completed_fn=as_completed,
        mkdtemp_fn=tempfile.mkdtemp,
        rmtree_fn=shutil.rmtree,
        logger=logger,
    )


def get_optimization_progress(
    task_id: str, user_id: str | None = None, use_db: bool = True
) -> dict[str, Any] | None:
    """Get the progress of an optimization task. Checks DB first, then in-memory.

    Args:
        task_id: The optimization task identifier.

    Returns:
        Dictionary containing progress information with keys:
        - task_id: The task identifier
        - status: Current status ("pending", "running", "completed", "failed", "cancelled")
        - strategy_id: The strategy being optimized
        - total: Total number of trials
        - completed: Number of completed trials
        - failed: Number of failed trials
        - progress: Progress percentage (0-100)
        - n_workers: Number of worker processes
        - created_at: ISO format creation timestamp
        Returns None if task not found.
    """
    return _query_task_response(
        task_id,
        build_progress_response,
        user_id=user_id,
        use_db=use_db,
    )


def get_optimization_results(
    task_id: str, user_id: str | None = None, use_db: bool = True
) -> dict[str, Any] | None:
    """Get the results of a completed optimization task. Checks DB first, then in-memory.

    Args:
        task_id: The optimization task identifier.

    Returns:
        Dictionary containing optimization results, or None if task not found.
    """
    return _query_task_response(
        task_id,
        build_results_response,
        user_id=user_id,
        use_db=use_db,
    )


def cancel_optimization(task_id: str, user_id: str | None = None, use_db: bool = True) -> bool:
    """Cancel an optimization task (marks status in-memory and optionally DB).

    Args:
        task_id: The optimization task identifier.
        user_id: Optional user ID for ownership check when updating DB.
        use_db: If True, attempt DB update (via _run_async). Set False when
            caller (e.g. API) will handle DB update with await to avoid
            nested event loop issues.

    Returns:
        True if task was found and marked for cancellation, False otherwise.
    """
    return _gateway_cancel_optimization_task(
        task_id,
        user_id=user_id,
        use_db=use_db,
        get_manager=get_optimization_execution_manager,
        run_async=_run_async,
        get_task=_get_task,
        update_task=_update_task,
    )


def _build_backtest_optimization_runtime_task(
    request: OptimizationRequest,
    total: int,
) -> dict[str, Any]:
    param_spec = request.param_grid if request.method == "grid" else request.param_bounds
    return {
        "status": TaskStatus.RUNNING.value,
        "strategy_id": request.strategy_id,
        "param_names": list((param_spec or {}).keys()),
        "param_ranges": param_spec or {},
        "total": total,
        "completed": 0,
        "failed": 0,
        "results": [],
        "n_workers": 1 if request.method == "bayesian" else 4,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }


def _generate_backtest_param_combinations(param_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))
    return [dict(zip(keys, combo, strict=False)) for combo in combinations]


def estimate_backtest_optimization_total(request: OptimizationRequest) -> int:
    if request.method == "grid":
        return len(_generate_backtest_param_combinations(request.param_grid or {}))
    return request.n_trials


def _extract_backtest_metrics(result: Any) -> dict[str, float]:
    return {
        "sharpe_ratio": float(getattr(result, "sharpe_ratio", 0.0) or 0.0),
        "total_return": float(getattr(result, "total_return", 0.0) or 0.0),
        "max_drawdown": float(getattr(result, "max_drawdown", 0.0) or 0.0),
        "annual_return": float(getattr(result, "annual_return", 0.0) or 0.0),
        "win_rate": float(getattr(result, "win_rate", 0.0) or 0.0),
    }


def _score_optimization_metrics(metrics: dict[str, float], metric: str) -> float:
    if metric == "max_drawdown":
        return -float(metrics.get("max_drawdown", float("inf")))
    if metric == "total_return":
        return float(metrics.get("total_return", float("-inf")))
    return float(metrics.get("sharpe_ratio", float("-inf")))


def _objective_value_from_metrics(metrics: dict[str, float], metric: str) -> float:
    if metric == "max_drawdown":
        return float(metrics.get("max_drawdown", float("inf")))
    if metric == "total_return":
        return -float(metrics.get("total_return", float("-inf")))
    return -float(metrics.get("sharpe_ratio", float("-inf")))


def _failure_objective_value(metric: str) -> float:
    if metric == "max_drawdown":
        return float("inf")
    return float("inf")


def _finalize_backtest_optimization_task(task_id: str, persist_to_db: bool) -> None:
    task = _get_task(task_id)
    final_status = (
        TaskStatus.CANCELLED.value
        if (task and task.get("status") == TaskStatus.CANCELLED.value)
        else TaskStatus.COMPLETED.value
    )
    if task and task.get("status") != TaskStatus.CANCELLED.value:
        _update_task(task_id, status=TaskStatus.COMPLETED.value)
        final_status = TaskStatus.COMPLETED.value

    if persist_to_db:
        _persist_runtime_task(
            task_id,
            completed=task.get("completed", 0) if task else 0,
            failed=task.get("failed", 0) if task else 0,
            results=task.get("results", []) if task else [],
            status=final_status,
        )


async def _wait_for_backtest_completion(
    backtest_service: BacktestService,
    task_id: str,
    timeout: int = 600,
) -> Any:
    status = await backtest_service.get_task_status(task_id)

    if status != TaskStatus.PENDING and status != TaskStatus.RUNNING:
        return await backtest_service.get_result(task_id)

    waited = 0
    while waited < timeout:
        await asyncio.sleep(1)
        waited += 1

        status = await backtest_service.get_task_status(task_id)

        if status == TaskStatus.COMPLETED:
            return await backtest_service.get_result(task_id)
        if status == TaskStatus.FAILED:
            result = await backtest_service.get_result(task_id)
            raise RuntimeError(f"Backtest failed: {result.error_message}")
        if status == TaskStatus.CANCELLED:
            raise RuntimeError("Backtest task cancelled")

    raise RuntimeError(f"Backtest task timeout ({timeout} seconds)")


async def _run_backtest_request(
    user_id: str,
    backtest_request: Any,
    backtest_service: BacktestService | None = None,
) -> Any:
    service = backtest_service or BacktestService()
    backtest_response = await service.run_backtest(user_id, backtest_request)
    return await _wait_for_backtest_completion(service, backtest_response.task_id)


def _run_backtest_grid_optimization(
    task_id: str,
    user_id: str,
    request: OptimizationRequest,
    persist_to_db: bool,
) -> None:
    backtest_service = BacktestService()
    results: list[dict[str, Any]] = []

    for params in _generate_backtest_param_combinations(request.param_grid or {}):
        if _is_optimization_cancelled(task_id, persist_to_db):
            break

        backtest_request = request.backtest_config.model_copy()
        backtest_request.params = params

        try:
            result = _run_async(
                _run_backtest_request(
                    user_id,
                    backtest_request,
                    backtest_service=backtest_service,
                )
            )
            if getattr(result, "status", None) == TaskStatus.COMPLETED:
                results.append({"params": params, "metrics": _extract_backtest_metrics(result)})
                _update_task(task_id, completed=len(results), results=list(results))
            else:
                task = _get_task(task_id)
                _update_task(task_id, failed=(task.get("failed", 0) if task else 0) + 1)
        except Exception as e:
            logger.error("Backtest grid optimization trial failed: %s", e)
            task = _get_task(task_id)
            _update_task(task_id, failed=(task.get("failed", 0) if task else 0) + 1)

        if persist_to_db:
            _persist_runtime_task(task_id)


def _run_backtest_bayesian_optimization(
    task_id: str,
    user_id: str,
    request: OptimizationRequest,
    persist_to_db: bool,
) -> None:
    try:
        import optuna
    except ImportError as e:
        raise RuntimeError("Please install Optuna: pip install optuna") from e

    backtest_service = BacktestService()
    results: list[dict[str, Any]] = []
    study = optuna.create_study(direction="minimize")

    def objective(trial: Any) -> float:
        params: dict[str, Any] = {}
        for key, bounds in (request.param_bounds or {}).items():
            bound_type = bounds.get("type")
            if bound_type == "int":
                params[key] = trial.suggest_int(key, bounds["min"], bounds["max"])
            elif bound_type == "float":
                params[key] = trial.suggest_float(key, bounds["min"], bounds["max"])
            elif bound_type == "categorical":
                params[key] = trial.suggest_categorical(key, bounds["choices"])

        backtest_request = request.backtest_config.model_copy()
        backtest_request.params = params

        try:
            result = _run_async(
                _run_backtest_request(
                    user_id,
                    backtest_request,
                    backtest_service=backtest_service,
                )
            )
            if getattr(result, "status", None) == TaskStatus.COMPLETED:
                metrics = _extract_backtest_metrics(result)
                results.append({"params": params, "metrics": metrics})
                _update_task(task_id, completed=len(results), results=list(results))
                return _objective_value_from_metrics(metrics, request.metric)

            task = _get_task(task_id)
            _update_task(task_id, failed=(task.get("failed", 0) if task else 0) + 1)
            return _failure_objective_value(request.metric)
        except Exception as e:
            logger.error("Backtest bayesian optimization trial failed: %s", e)
            task = _get_task(task_id)
            _update_task(task_id, failed=(task.get("failed", 0) if task else 0) + 1)
            return _failure_objective_value(request.metric)

    for _ in range(request.n_trials):
        if _is_optimization_cancelled(task_id, persist_to_db):
            break
        study.optimize(objective, n_trials=1)
        if persist_to_db:
            _persist_runtime_task(task_id)


def _run_backtest_optimization_thread(
    task_id: str,
    user_id: str,
    request: OptimizationRequest,
    persist_to_db: bool,
) -> None:
    try:
        if request.method == "grid":
            _run_backtest_grid_optimization(task_id, user_id, request, persist_to_db)
        else:
            _run_backtest_bayesian_optimization(task_id, user_id, request, persist_to_db)
        _finalize_backtest_optimization_task(task_id, persist_to_db)
    except Exception as e:
        logger.error("Backtest optimization task failed %s: %s", task_id, e)
        _update_task(task_id, status=TaskStatus.FAILED.value, error=str(e))
        if persist_to_db:
            _persist_runtime_task(
                task_id,
                completed=0,
                failed=0,
                results=[],
                status=TaskStatus.FAILED.value,
                error_message=str(e),
            )


def submit_backtest_optimization(
    user_id: str,
    request: OptimizationRequest,
    task_id: str | None = None,
    persist_to_db: bool = True,
) -> str:
    resolved_task_id = task_id or uuid.uuid4().hex[:8]
    total = estimate_backtest_optimization_total(request)
    _set_task(resolved_task_id, _build_backtest_optimization_runtime_task(request, total))

    thread = threading.Thread(
        target=_run_backtest_optimization_thread,
        kwargs={
            "task_id": resolved_task_id,
            "user_id": user_id,
            "request": request,
            "persist_to_db": persist_to_db,
        },
        daemon=True,
    )
    thread.start()
    return resolved_task_id
