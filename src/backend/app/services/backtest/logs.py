"""Backtest log-directory resolution shared by services and API routes."""

from __future__ import annotations

import logging
from pathlib import Path

from app.db.sql_repository import SQLRepository
from app.models.backtest import BacktestTask
from app.services.log_parser_service import find_latest_log_dir
from app.services.strategy.runtime_support import has_log_artifacts, latest_meaningful_log_subdir
from app.services.strategy_service import get_strategy_dir

logger = logging.getLogger(__name__)


async def resolve_log_dir(task_id: str, strategy_id: str) -> Path | None:
    """Resolve a task log directory, falling back to the strategy's latest log."""
    try:
        task_repo = SQLRepository(BacktestTask)
        task = await task_repo.get_by_id(task_id)
        if task and getattr(task, "log_dir", None):
            path = Path(task.log_dir)
            if path.is_dir() and has_log_artifacts(path):
                return path
            logs_root = path.parent if path.parent.is_dir() else None
            latest_sibling = latest_meaningful_log_subdir(logs_root) if logs_root else None
            if latest_sibling is not None:
                return latest_sibling
            if path.is_dir() and path.parent.is_dir() and has_log_artifacts(path.parent):
                return path.parent
    except Exception as exc:
        logger.debug("Task log dir lookup failed: %s", exc)
    try:
        strategy_dir = get_strategy_dir(strategy_id)
    except ValueError:
        return None
    return find_latest_log_dir(strategy_dir)
