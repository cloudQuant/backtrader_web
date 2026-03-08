"""
Backtest execution runner tests.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.services.backtest_runner import BacktestExecutionRunner


@pytest.mark.asyncio
async def test_schedule_stores_and_cleans_up_task():
    runner = BacktestExecutionRunner()
    started = asyncio.Event()

    async def execution():
        started.set()

    task = runner.schedule("task123", execution())
    await started.wait()
    await task

    assert runner.get_task("task123") is None


def test_cancel_local_execution_cancels_task_and_process():
    runner = BacktestExecutionRunner()
    task = MagicMock()
    task.done.return_value = False
    process = MagicMock()
    process.poll.return_value = None

    runner._tasks["task123"] = task
    runner._processes["task123"] = process

    cancelled = runner.cancel_local_execution("task123")

    assert cancelled is True
    task.cancel.assert_called_once()
    process.kill.assert_called_once()
    assert runner.get_task("task123") is None
    assert runner.get_process("task123") is None


def test_cancel_local_execution_returns_false_without_local_handles():
    runner = BacktestExecutionRunner()
    assert runner.cancel_local_execution("missing") is False
