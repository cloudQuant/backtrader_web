"""
Parameter optimization service (multiprocess grid search).

Design:
- Build a Cartesian product grid from (start, end, step) parameter ranges.
- Evaluate combinations in parallel via concurrent.futures.ProcessPoolExecutor.
- Each worker: write a temporary config.yaml -> run a run.py subprocess -> parse logs -> return metrics.
- The main process aggregates results and exposes progress queries.
"""

import itertools
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# ---- Global State ----

_tasks: Dict[str, Dict[str, Any]] = {}
_tasks_lock = Lock()


def _get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Get a task by ID from the global task registry.

    Args:
        task_id: The task identifier.

    Returns:
        The task dictionary if found, None otherwise.
    """
    with _tasks_lock:
        return _tasks.get(task_id)


def _set_task(task_id: str, data: Dict[str, Any]):
    """Set a task in the global task registry.

    Args:
        task_id: The task identifier.
        data: The task data dictionary to store.
    """
    with _tasks_lock:
        _tasks[task_id] = data


def _update_task(task_id: str, **kwargs):
    """Update specific fields of a task in the global registry.

    Args:
        task_id: The task identifier.
        **kwargs: Field names and values to update.
    """
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id].update(kwargs)


# ---- Worker (runs in subprocess of ProcessPoolExecutor) ----


def _run_single_trial(
    strategy_dir: str,
    params: Dict[str, Any],
    trial_index: int,
    tmp_base: str,
) -> Dict[str, Any]:
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
    strategy_path = Path(strategy_dir)
    trial_dir = Path(tmp_base) / f"trial_{trial_index}"
    result: Dict[str, Any] = {"params": params, "trial_index": trial_index, "success": False}

    try:
        # Copy strategy directory to temporary location
        shutil.copytree(strategy_path, trial_dir, dirs_exist_ok=True)

        # Clear logs subdirectory
        logs_dir = trial_dir / "logs"
        if logs_dir.is_dir():
            shutil.rmtree(logs_dir)

        # Write current parameters to config.yaml
        config_path = trial_dir / "config.yaml"
        config: dict = {}
        if config_path.is_file():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

        if "params" not in config:
            config["params"] = {}
        config["params"].update(params)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        run_py = trial_dir / "run.py"

        # Prepare environment: set data directory so run.py can find data files
        project_root = Path(strategy_dir).parent.parent  # strategies/ -> project root
        env = dict(os.environ)
        env["BACKTRADER_DATA_DIR"] = str(project_root / "datas")
        # Add original strategy directory to PYTHONPATH for local module imports
        extra_paths = [str(strategy_dir), str(trial_dir)]
        env["PYTHONPATH"] = os.pathsep.join(extra_paths + [env.get("PYTHONPATH", "")])

        # Execute run.py
        proc = subprocess.run(
            [sys.executable, "-O", str(run_py)],
            cwd=str(trial_dir),
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )

        if proc.returncode != 0:
            result["error"] = (
                proc.stderr.strip().split("\n")[-1] if proc.stderr else "unknown error"
            )
            return result

        # Parse logs to extract performance metrics
        metrics = _parse_trial_logs(trial_dir)
        if metrics:
            result["metrics"] = metrics
            result["success"] = True
        else:
            result["error"] = "no logs produced"

    except Exception as e:
        result["error"] = str(e)
    finally:
        # Clean up temporary directory
        try:
            if trial_dir.is_dir():
                shutil.rmtree(trial_dir)
        except Exception:
            pass

    return result


def _safe_float(val, default=0.0):
    """Convert a value to float, handling NaN and infinity.

    Args:
        val: Value to convert.
        default: Default value to return if conversion fails or value is invalid.

    Returns:
        Float value or default if conversion fails or value is NaN/inf.
    """
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (ValueError, TypeError):
        return default


def _parse_trial_logs(trial_dir: Path) -> Optional[Dict[str, float]]:
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
    logs_dir = trial_dir / "logs"
    if not logs_dir.is_dir():
        return None

    subdirs = sorted(
        [d for d in logs_dir.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )
    if not subdirs:
        return None

    log_dir = subdirs[0]

    # value.log -> equity curve -> return / drawdown
    # columns: log_time(0) dt(1) value(2) cash(3)
    value_path = log_dir / "value.log"
    equity = []
    if value_path.is_file():
        with open(value_path, "r", encoding="utf-8") as f:
            _header = f.readline()
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    equity.append(_safe_float(parts[2]))

    initial = equity[0] if equity else 100000.0
    final = equity[-1] if equity else initial
    total_return = ((final - initial) / initial * 100) if initial > 0 else 0.0

    n_days = len(equity)
    n_years = n_days / 252.0 if n_days > 0 else 1.0
    annual_return = (
        ((final / initial) ** (1.0 / n_years) - 1) * 100 if n_years > 0 and initial > 0 else 0.0
    )

    # drawdown
    peak = 0.0
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = ((peak - v) / peak * 100) if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # sharpe (daily)
    if len(equity) > 1:
        returns = [
            (equity[i] - equity[i - 1]) / equity[i - 1]
            for i in range(1, len(equity))
            if equity[i - 1] > 0
        ]
        if returns:
            avg_r = sum(returns) / len(returns)
            std_r = (sum((r - avg_r) ** 2 for r in returns) / len(returns)) ** 0.5
            sharpe = (avg_r / std_r * (252**0.5)) if std_r > 0 else 0
        else:
            sharpe = 0
    else:
        sharpe = 0

    # trade.log
    trade_path = log_dir / "trade.log"
    total_trades = 0
    win_trades = 0
    if trade_path.is_file():
        with open(trade_path, "r", encoding="utf-8") as f:
            header_line = f.readline().strip()
            headers = header_line.split("\t")
            isclosed_idx = headers.index("isclosed") if "isclosed" in headers else -1
            pnlcomm_idx = headers.index("pnlcomm") if "pnlcomm" in headers else -1
            for line in f:
                parts = line.strip().split("\t")
                if isclosed_idx >= 0 and isclosed_idx < len(parts):
                    if parts[isclosed_idx] == "1":
                        total_trades += 1
                        if pnlcomm_idx >= 0 and pnlcomm_idx < len(parts):
                            if _safe_float(parts[pnlcomm_idx]) > 0:
                                win_trades += 1

    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0

    return {
        "total_return": round(total_return, 4),
        "annual_return": round(annual_return, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
        "total_trades": total_trades,
        "win_rate": round(win_rate, 2),
        "final_value": round(final, 2),
    }


# ---- Public API ----


def generate_param_grid(
    param_ranges: Dict[str, Dict[str, float]],
) -> List[Dict[str, Any]]:
    """Generate a Cartesian product parameter grid from range specifications.

    Args:
        param_ranges: Dictionary mapping parameter names to range specifications.
            Each spec must contain: start (inclusive), end (inclusive), step.
            Optional: type ("int" or "float", defaults to "float").

    Returns:
        List of parameter dictionaries, one for each combination in the grid.
    """
    keys = []
    value_lists = []
    for name, spec in param_ranges.items():
        start = spec["start"]
        end = spec["end"]
        step = spec["step"]
        ptype = spec.get("type", "float")

        vals = []
        v = start
        while v <= end + 1e-9:
            vals.append(int(v) if ptype == "int" else round(v, 6))
            v += step
        keys.append(name)
        value_lists.append(vals)

    combos = list(itertools.product(*value_lists))
    return [dict(zip(keys, combo)) for combo in combos]


def submit_optimization(
    strategy_id: str,
    param_ranges: Dict[str, Dict[str, float]],
    n_workers: int = 4,
) -> str:
    """Submit an optimization task to run asynchronously.

    Args:
        strategy_id: The strategy identifier to optimize.
        param_ranges: Dictionary mapping parameter names to range specifications.
        n_workers: Number of parallel worker processes to use.

    Returns:
        The task ID for tracking optimization progress.

    Raises:
        ValueError: If strategy does not exist or parameter grid is empty.
    """
    from app.services.strategy_service import STRATEGIES_DIR

    strategy_dir = STRATEGIES_DIR / strategy_id
    if not (strategy_dir / "run.py").is_file():
        raise ValueError(f"Strategy {strategy_id} not found or missing run.py")

    grid = generate_param_grid(param_ranges)
    if not grid:
        raise ValueError("Parameter grid is empty, please check parameter range settings")

    task_id = uuid.uuid4().hex[:8]
    _set_task(
        task_id,
        {
            "status": "running",
            "strategy_id": strategy_id,
            "total": len(grid),
            "completed": 0,
            "failed": 0,
            "results": [],
            "param_names": list(param_ranges.keys()),
            "created_at": datetime.now().isoformat(),
            "n_workers": n_workers,
        },
    )

    import threading

    t = threading.Thread(
        target=_run_optimization_thread,
        args=(task_id, str(strategy_dir), grid, n_workers),
        daemon=True,
    )
    t.start()

    return task_id


def _run_optimization_thread(
    task_id: str,
    strategy_dir: str,
    grid: List[Dict[str, Any]],
    n_workers: int,
):
    """Run multiprocess optimization in a background thread.

    Args:
        task_id: The optimization task identifier.
        strategy_dir: Path to the strategy directory.
        grid: List of parameter combinations to evaluate.
        n_workers: Number of parallel worker processes.
    """
    tmp_base = tempfile.mkdtemp(prefix=f"opt_{task_id}_")
    all_results: List[Dict[str, Any]] = []

    try:
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            futures = {}
            for i, params in enumerate(grid):
                # Check cancellation flag before submitting
                task = _get_task(task_id)
                if task and task["status"] == "cancelled":
                    break
                fut = executor.submit(_run_single_trial, strategy_dir, params, i, tmp_base)
                futures[fut] = i

            for fut in as_completed(futures):
                # Check cancellation flag when collecting results
                task = _get_task(task_id)
                if task and task["status"] == "cancelled":
                    # Try to cancel remaining futures
                    for pending_fut in futures:
                        pending_fut.cancel()
                    break

                try:
                    trial_result = fut.result(timeout=5)
                except Exception:
                    trial_result = {"success": False, "error": "worker exception"}

                if trial_result["success"]:
                    all_results.append(trial_result)
                    _update_task(task_id, completed=len(all_results))
                else:
                    task = _get_task(task_id)
                    if task:
                        _update_task(task_id, failed=task["failed"] + 1)

                _update_task(task_id, results=list(all_results))

        # Only mark completed if not cancelled
        task = _get_task(task_id)
        if task and task["status"] != "cancelled":
            _update_task(task_id, status="completed", results=all_results)
        logger.info(f"Optimization completed {task_id}: {len(all_results)}/{len(grid)} successful")

    except Exception as e:
        logger.error(f"Optimization task failed {task_id}: {e}")
        _update_task(task_id, status="error", error=str(e))
    finally:
        try:
            shutil.rmtree(tmp_base, ignore_errors=True)
        except Exception:
            pass


def get_optimization_progress(task_id: str) -> Optional[Dict[str, Any]]:
    """Get the progress of an optimization task.

    Args:
        task_id: The optimization task identifier.

    Returns:
        Dictionary containing progress information with keys:
        - task_id: The task identifier
        - status: Current status ("running", "completed", "error", "cancelled")
        - strategy_id: The strategy being optimized
        - total: Total number of trials
        - completed: Number of completed trials
        - failed: Number of failed trials
        - progress: Progress percentage (0-100)
        - n_workers: Number of worker processes
        - created_at: ISO format creation timestamp
        Returns None if task not found.
    """
    task = _get_task(task_id)
    if not task:
        return None
    return {
        "task_id": task_id,
        "status": task["status"],
        "strategy_id": task["strategy_id"],
        "total": task["total"],
        "completed": task["completed"],
        "failed": task["failed"],
        "progress": round((task["completed"] + task["failed"]) / task["total"] * 100, 1)
        if task["total"] > 0
        else 0,
        "n_workers": task["n_workers"],
        "created_at": task["created_at"],
    }


def get_optimization_results(task_id: str) -> Optional[Dict[str, Any]]:
    """Get the results of a completed optimization task.

    Args:
        task_id: The optimization task identifier.

    Returns:
        Dictionary containing optimization results with keys:
        - task_id: The task identifier
        - status: Current status
        - strategy_id: The strategy that was optimized
        - param_names: List of parameter names
        - metric_names: List of metric names returned
        - total: Total number of trials
        - completed: Number of completed trials
        - failed: Number of failed trials
        - rows: List of result dictionaries sorted by annual_return (descending)
        - best: Best parameter combination (first row)
        Returns None if task not found.
    """
    task = _get_task(task_id)
    if not task:
        return None

    results = task.get("results", [])

    # Build table-formatted data
    rows = []
    for r in results:
        row = dict(r["params"])
        if r.get("metrics"):
            row.update(r["metrics"])
        rows.append(row)

    # Sort by annual return descending
    rows.sort(key=lambda x: x.get("annual_return", -999999), reverse=True)

    # Find best parameters
    best = rows[0] if rows else None

    return {
        "task_id": task_id,
        "status": task["status"],
        "strategy_id": task["strategy_id"],
        "param_names": task["param_names"],
        "metric_names": [
            "total_return",
            "annual_return",
            "sharpe_ratio",
            "max_drawdown",
            "total_trades",
            "win_rate",
            "final_value",
        ],
        "total": task["total"],
        "completed": task["completed"],
        "failed": task["failed"],
        "rows": rows,
        "best": best,
    }


def cancel_optimization(task_id: str) -> bool:
    """Cancel an optimization task (marks status, does not force-kill subprocesses).

    Args:
        task_id: The optimization task identifier.

    Returns:
        True if task was found and marked for cancellation, False otherwise.
    """
    task = _get_task(task_id)
    if not task:
        return False
    _update_task(task_id, status="cancelled")
    return True
