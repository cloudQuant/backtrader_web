"""
Strategy version comparison and diff utilities.

Extracted from strategy_version_service.py to keep file sizes manageable.
Contains code diff generation, parameter diff generation, and performance
diff generation for comparing strategy versions.
"""

import difflib
import logging
from typing import Any

from sqlalchemy import desc, select

from app.db import database as db
from app.models.backtest import BacktestResultModel, BacktestTask

logger = logging.getLogger(__name__)


def generate_code_diff(
    code1: str,
    code2: str,
    name1: str,
    name2: str,
) -> str:
    """Generate a code difference in unified diff format.

    Args:
        code1: Source code content.
        code2: Target code content.
        name1: Source name for diff header.
        name2: Target name for diff header.

    Returns:
        String containing the unified diff.
    """
    lines1 = code1.splitlines(keepends=True)
    lines2 = code2.splitlines(keepends=True)

    diff = difflib.unified_diff(lines1, lines2, fromfile=name1, tofile=name2, lineterm="")
    return "".join(diff)


def generate_params_diff(
    params1: dict[str, Any],
    params2: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Generate a parameter difference between two parameter sets.

    Args:
        params1: Source parameters dictionary.
        params2: Target parameters dictionary.

    Returns:
        Dictionary with keys 'added', 'removed', 'modified', and 'unchanged'
        containing the respective parameter differences.
    """
    all_keys = set(params1.keys()) | set(params2.keys())

    diff = {
        "added": {},
        "removed": {},
        "modified": {},
        "unchanged": {},
    }

    for key in all_keys:
        if key not in params1:
            diff["added"][key] = params2[key]
        elif key not in params2:
            diff["removed"][key] = params1[key]
        elif params1[key] != params2[key]:
            diff["modified"][key] = {
                "from": params1[key],
                "to": params2[key],
            }
        else:
            diff["unchanged"][key] = params1[key]

    return diff


async def generate_performance_diff(
    from_version_id: str,
    to_version_id: str,
) -> dict[str, Any]:
    """Generate a performance difference between two versions.

    Compares backtest results from both versions.

    Args:
        from_version_id: Source version identifier.
        to_version_id: Target version identifier.

    Returns:
        Dictionary containing performance metrics differences with keys:
        - available: Whether performance data exists for both versions
        - from: Source version metrics
        - to: Target version metrics
        - diff: Metric differences (to - from)
    """

    async def _latest(version_id: str) -> dict[str, Any] | None:
        async with db.async_session_maker() as session:
            stmt = (
                select(BacktestTask, BacktestResultModel)
                .join(BacktestResultModel, BacktestResultModel.task_id == BacktestTask.id)
                .where(BacktestTask.strategy_version_id == version_id)
                .where(BacktestTask.status == "completed")
                .order_by(desc(BacktestTask.created_at))
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.first()
            if not row:
                return None
            task, res = row
            return {
                "task_id": task.id,
                "created_at": task.created_at.isoformat()
                if getattr(task, "created_at", None)
                else None,
                "metrics": {
                    "total_return": float(getattr(res, "total_return", 0.0)),
                    "annual_return": float(getattr(res, "annual_return", 0.0)),
                    "sharpe_ratio": float(getattr(res, "sharpe_ratio", 0.0)),
                    "max_drawdown": float(getattr(res, "max_drawdown", 0.0)),
                    "win_rate": float(getattr(res, "win_rate", 0.0)),
                    "total_trades": int(getattr(res, "total_trades", 0)),
                    "profitable_trades": int(getattr(res, "profitable_trades", 0)),
                    "losing_trades": int(getattr(res, "losing_trades", 0)),
                },
            }

    from_res = await _latest(from_version_id)
    to_res = await _latest(to_version_id)
    if not from_res or not to_res:
        return {"available": False, "from": from_res, "to": to_res}

    diff: dict[str, Any] = {}
    for k, v in to_res["metrics"].items():
        if (
            k in from_res["metrics"]
            and isinstance(v, (int, float))
            and isinstance(from_res["metrics"][k], (int, float))
        ):
            diff[k] = v - from_res["metrics"][k]

    return {"available": True, "from": from_res, "to": to_res, "diff": diff}
