"""
Process-local execution runner for backtest tasks.

This runner only manages execution handles owned by the current API process.
Persistent task state remains the responsibility of ``BacktestExecutionManager``.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from collections.abc import Awaitable

logger = logging.getLogger(__name__)


class BacktestExecutionRunner:
    """Manage process-local asyncio tasks and subprocess handles."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._processes: dict[str, subprocess.Popen] = {}

    def schedule(self, task_id: str, execution: Awaitable[None]) -> asyncio.Task:
        """Schedule one local execution coroutine and retain its handle."""

        async def _wrapped_execution() -> None:
            try:
                await execution
            finally:
                current_task = asyncio.current_task()
                if self._tasks.get(task_id) is current_task:
                    self._tasks.pop(task_id, None)

        task = asyncio.create_task(_wrapped_execution())
        self._tasks[task_id] = task
        return task

    def register_process(self, task_id: str, process: subprocess.Popen) -> None:
        """Register one subprocess handle for later cancellation."""
        self._processes[task_id] = process

    def unregister_process(self, task_id: str) -> None:
        """Forget a subprocess handle once execution finishes."""
        self._processes.pop(task_id, None)

    def get_task(self, task_id: str) -> asyncio.Task | None:
        """Return the process-local asyncio task for one backtest."""
        return self._tasks.get(task_id)

    def get_process(self, task_id: str) -> subprocess.Popen | None:
        """Return the process-local subprocess handle for one backtest."""
        return self._processes.get(task_id)

    def cancel_local_execution(self, task_id: str) -> bool:
        """Best-effort cancellation for execution owned by this process only."""
        task = self._tasks.pop(task_id, None)
        process = self._processes.pop(task_id, None)
        had_local_handle = task is not None or process is not None

        if task and not task.done():
            task.cancel()

        if process and process.poll() is None:
            try:
                process.kill()
            except Exception:  # pragma: no cover - defensive logging path
                logger.warning("Failed to kill subprocess for backtest %s", task_id, exc_info=True)

        return had_local_handle
