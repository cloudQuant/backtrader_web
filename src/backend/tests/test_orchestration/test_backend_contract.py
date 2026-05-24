from types import SimpleNamespace
from unittest.mock import patch

from app.services.orchestration.apscheduler_backend import APSchedulerBackend
from app.services.orchestration.base import OrchestratorBackend


class _FakeAkshareScheduler:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.scheduler = SimpleNamespace(running=True, get_jobs=lambda: ["job-1", "job-2"])

    async def start(self) -> None:
        self.calls.append(("start",))

    async def shutdown(self) -> None:
        self.calls.append(("shutdown",))

    async def add_or_update_task(self, task_id: int) -> None:
        self.calls.append(("add_or_update_task", task_id))

    async def remove_task(self, task_id: int) -> None:
        self.calls.append(("remove_task", task_id))

    async def run_task_now(self, task_id: int, operator_id: str | None = None) -> dict[str, object]:
        self.calls.append(("run_task_now", task_id, operator_id))
        return {"task_id": task_id, "operator_id": operator_id, "status": "queued"}

    async def reload_active_tasks(self) -> None:
        self.calls.append(("reload_active_tasks",))


async def test_apscheduler_backend_implements_orchestrator_contract():
    with patch("app.services.akshare_scheduler.AkshareScheduler", _FakeAkshareScheduler):
        backend = APSchedulerBackend()

    assert isinstance(backend, OrchestratorBackend)


async def test_apscheduler_backend_delegates_all_contract_methods():
    with patch("app.services.akshare_scheduler.AkshareScheduler", _FakeAkshareScheduler):
        backend = APSchedulerBackend()

    fake_scheduler = backend._scheduler

    await backend.start()
    await backend.add_or_update_task(11)
    await backend.remove_task(11)
    result = await backend.run_task_now(11, operator_id="user-1")
    await backend.reload_active_tasks()
    status = await backend.get_backend_status()
    await backend.shutdown()

    assert result == {"task_id": 11, "operator_id": "user-1", "status": "queued"}
    assert status == {"type": "apscheduler", "running": True, "job_count": 2}
    assert fake_scheduler.calls == [
        ("start",),
        ("add_or_update_task", 11),
        ("remove_task", 11),
        ("run_task_now", 11, "user-1"),
        ("reload_active_tasks",),
        ("shutdown",),
    ]
