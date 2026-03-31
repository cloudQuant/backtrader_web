import itertools
from collections.abc import Callable
from pathlib import Path
from typing import Any


def generate_param_grid(
    param_ranges: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
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
    return [dict(zip(keys, combo, strict=False)) for combo in combos]


def submit_optimization(
    strategy_id: str,
    param_ranges: dict[str, dict[str, float]],
    n_workers: int = 4,
    task_id: str | None = None,
    persist_to_db: bool = True,
    *,
    get_strategy_dir: Callable[[str], Path],
    generate_param_grid_fn: Callable[[dict[str, dict[str, float]]], list[dict[str, Any]]] = generate_param_grid,
    set_task_fn: Callable[[str, dict[str, Any]], Any],
    build_initial_runtime_task_fn: Callable[..., dict[str, Any]],
    created_at_fn: Callable[[], str],
    running_status: str,
    thread_cls: Callable[..., Any],
    run_optimization_thread_fn: Callable[[str, str, list[dict[str, Any]], int, bool], Any],
    task_id_factory: Callable[[], str],
) -> str:
    strategy_dir = get_strategy_dir(strategy_id)
    if not (strategy_dir / "run.py").is_file():
        raise ValueError(f"Strategy {strategy_id} not found or missing run.py")

    grid = generate_param_grid_fn(param_ranges)
    if not grid:
        raise ValueError("Parameter grid is empty, please check parameter range settings")

    resolved_task_id = task_id or task_id_factory()
    set_task_fn(
        resolved_task_id,
        build_initial_runtime_task_fn(
            strategy_id=strategy_id,
            param_ranges=param_ranges,
            total=len(grid),
            n_workers=n_workers,
            created_at=created_at_fn(),
            status=running_status,
        ),
    )

    thread = thread_cls(
        target=run_optimization_thread_fn,
        args=(resolved_task_id, str(strategy_dir), grid, n_workers, persist_to_db),
        daemon=True,
    )
    thread.start()

    return resolved_task_id
