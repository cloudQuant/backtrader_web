"""
APScheduler implementation of OrchestratorBackend.

Wraps the existing AkshareScheduler class to conform to the
OrchestratorBackend interface. Used as fallback when Airflow is unavailable.
"""

from typing import Any

from app.services.orchestration.base import OrchestratorBackend


class APSchedulerBackend(OrchestratorBackend):
    """APScheduler-based orchestration backend.

    Delegates all operations to the existing AkshareScheduler instance.
    """

    def __init__(self) -> None:
        from app.services.akshare.scheduler import AkshareScheduler

        self._scheduler = AkshareScheduler()

    async def start(self) -> None:
        """Start the APScheduler and load active tasks."""
        await self._scheduler.start()

    async def shutdown(self) -> None:
        """Shut down the APScheduler."""
        await self._scheduler.shutdown()

    async def add_or_update_task(self, task_id: int) -> None:
        """Add or update a task in APScheduler."""
        await self._scheduler.add_or_update_task(task_id)

    async def remove_task(self, task_id: int) -> None:
        """Remove a task from APScheduler."""
        await self._scheduler.remove_task(task_id)

    async def run_task_now(self, task_id: int, operator_id: str | None = None) -> Any:
        """Execute a task immediately via APScheduler."""
        return await self._scheduler.run_task_now(task_id, operator_id=operator_id)

    async def reload_active_tasks(self) -> None:
        """Reload all active tasks into APScheduler."""
        await self._scheduler.reload_active_tasks()

    async def get_backend_status(self) -> dict[str, Any]:
        """Return APScheduler status."""
        scheduler = self._scheduler.scheduler
        running = scheduler is not None and scheduler.running if scheduler else False
        job_count = len(scheduler.get_jobs()) if scheduler and running else 0
        return {
            "type": "apscheduler",
            "running": running,
            "job_count": job_count,
        }
