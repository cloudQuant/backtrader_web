"""Scheduler safety contracts for the research-only nightly signal process."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.stock_signal.scheduler import StockSignalScheduler


@pytest.mark.asyncio
async def test_scheduler_is_disabled_without_explicit_operator_enablement() -> None:
    scheduler = StockSignalScheduler()
    scheduler.settings = SimpleNamespace(STOCK_SIGNAL_SCHEDULE_ENABLED=False)

    assert await scheduler.start() is False


@pytest.mark.asyncio
async def test_scheduler_job_only_collects_and_scores_without_order_submission() -> None:
    scheduler = StockSignalScheduler()
    calls: list[str] = []

    class _Runner:
        async def run(self) -> None:
            calls.append("run")

        async def score_pending(self) -> None:
            calls.append("score_pending")

    scheduler.runner = _Runner()

    await scheduler._run_job()

    assert calls == ["run", "score_pending"]
