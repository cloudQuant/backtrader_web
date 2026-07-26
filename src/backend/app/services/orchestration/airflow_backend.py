"""
Airflow implementation of OrchestratorBackend.

Communicates with Airflow via REST API to manage DAGs and trigger runs.
"""

from typing import Any

from app.services.orchestration.airflow_adapter import AirflowAdapter
from app.services.orchestration.base import OrchestratorBackend
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AirflowBackend(OrchestratorBackend):
    """Airflow-based orchestration backend.

    Uses AirflowAdapter to communicate with Airflow REST API.
    """

    def __init__(self, adapter: AirflowAdapter) -> None:
        self._adapter = adapter

    async def start(self) -> None:
        """Verify Airflow connection on start."""
        healthy = await self._adapter.health_check()
        if healthy:
            logger.info("AirflowBackend started, connection verified")
        else:
            logger.warning("AirflowBackend started but Airflow health check failed")

    async def shutdown(self) -> None:
        """Close the Airflow adapter connection."""
        await self._adapter.close()
        logger.info("AirflowBackend shut down")

    async def add_or_update_task(self, task_id: int) -> None:
        """Generate/update DAG file and unpause in Airflow.

        TODO: Integrate DAGGenerator when implemented.
        """
        logger.info(f"AirflowBackend: add_or_update_task({task_id}) - DAG generation pending")

    async def remove_task(self, task_id: int) -> None:
        """Pause DAG and remove DAG file.

        TODO: Integrate DAGGenerator when implemented.
        """
        logger.info(f"AirflowBackend: remove_task({task_id}) - DAG removal pending")

    async def run_task_now(self, task_id: int, operator_id: str | None = None) -> Any:
        """Trigger a DAG run in Airflow.

        TODO: Map task_id to dag_id and trigger with conf.
        """
        dag_id = f"dag_task_{task_id}"
        conf = {"task_id": task_id, "operator_id": operator_id}
        try:
            result = await self._adapter.trigger_dag_run(dag_id, conf=conf)
            logger.info(f"Triggered DAG run: {dag_id}, run_id={result.get('dag_run_id')}")
            return result
        except Exception as exc:
            logger.error(f"Failed to trigger DAG {dag_id}: {exc}")
            raise

    async def reload_active_tasks(self) -> None:
        """Reload active tasks — in Airflow mode, DAGs are loaded from files."""
        logger.info("AirflowBackend: reload_active_tasks (DAGs loaded from filesystem)")

    async def get_backend_status(self) -> dict[str, Any]:
        """Return Airflow backend status."""
        healthy = await self._adapter.health_check()
        return {
            "type": "airflow",
            "connected": healthy,
            "api_url": self._adapter._base_url,
        }
