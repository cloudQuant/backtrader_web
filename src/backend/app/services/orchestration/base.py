"""
Abstract base class for orchestration backends.
"""

from abc import ABC, abstractmethod
from typing import Any


class OrchestratorBackend(ABC):
    """Abstract interface for task orchestration backends.

    Implementations: APSchedulerBackend, AirflowBackend.
    The system selects the active backend at startup based on
    configuration and Airflow availability.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start the orchestration backend."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully shut down the backend."""

    @abstractmethod
    async def add_or_update_task(self, task_id: int) -> None:
        """Add or update a scheduled task."""

    @abstractmethod
    async def remove_task(self, task_id: int) -> None:
        """Remove a scheduled task."""

    @abstractmethod
    async def run_task_now(self, task_id: int, operator_id: str | None = None) -> Any:
        """Execute a task immediately (manual trigger)."""

    @abstractmethod
    async def reload_active_tasks(self) -> None:
        """Reload all active tasks from the database."""

    @abstractmethod
    async def get_backend_status(self) -> dict[str, Any]:
        """Return backend status information.

        Returns:
            Dict with at least 'type' (str) and connection/running state.
        """
