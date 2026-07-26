import asyncio

import pytest

from app.services.akshare.scheduler import AkshareScheduler


@pytest.mark.asyncio
async def test_scheduler_triggered_jobs_are_serialized(monkeypatch):
    scheduler = AkshareScheduler()

    active_count = 0
    max_active_count = 0

    async def fake_run_task_now(task_id: int, operator_id: str | None = None) -> object:
        nonlocal active_count, max_active_count
        active_count += 1
        max_active_count = max(max_active_count, active_count)
        await asyncio.sleep(0.01)
        active_count -= 1
        return object()

    monkeypatch.setattr(scheduler, "run_task_now", fake_run_task_now)

    await asyncio.gather(*(scheduler._run_task_job(task_id) for task_id in range(5)))

    assert max_active_count == 1
