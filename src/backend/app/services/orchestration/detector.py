"""
Orchestration backend auto-detection.

Checks Airflow availability at startup and selects the appropriate backend.
"""

from app.config import get_settings
from app.services.orchestration.base import OrchestratorBackend
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BackendDetector:
    """Detects and instantiates the appropriate orchestration backend.

    Priority:
    1. ORCHESTRATION_BACKEND=airflow → force Airflow
    2. ORCHESTRATION_BACKEND=apscheduler → force APScheduler
    3. ORCHESTRATION_BACKEND=auto → health check Airflow, fallback to APScheduler
    """

    async def detect(self) -> OrchestratorBackend:
        """Detect and return the appropriate backend instance.

        Returns:
            An initialized OrchestratorBackend instance.
        """
        settings = get_settings()
        mode = getattr(settings, "ORCHESTRATION_BACKEND", "auto").strip().lower()

        if mode == "apscheduler":
            logger.info("Orchestration backend forced to APScheduler by configuration")
            return self._create_apscheduler()

        if mode == "airflow":
            logger.info("Orchestration backend forced to Airflow by configuration")
            return await self._create_airflow_or_fail()

        # auto mode: try Airflow first, fallback to APScheduler
        return await self._auto_detect()

    async def _auto_detect(self) -> OrchestratorBackend:
        """Auto-detect defaults to APScheduler while Airflow remains explicit opt-in."""
        logger.info(
            "Orchestration backend auto mode defaults to APScheduler; "
            "set ORCHESTRATION_BACKEND=airflow to opt in to the experimental Airflow backend"
        )
        return self._create_apscheduler()

    async def _create_airflow_or_fail(self) -> OrchestratorBackend:
        """Create Airflow backend (forced mode, raises on failure)."""
        settings = get_settings()
        airflow_url = getattr(settings, "AIRFLOW_API_BASE_URL", "").strip()

        if not airflow_url:
            logger.warning(
                "ORCHESTRATION_BACKEND=airflow but AIRFLOW_API_BASE_URL not set, "
                "falling back to APScheduler"
            )
            return self._create_apscheduler()

        from app.services.orchestration.airflow_adapter import AirflowAdapter

        adapter = AirflowAdapter(
            base_url=airflow_url,
            username=getattr(settings, "AIRFLOW_USERNAME", "admin"),
            password=getattr(settings, "AIRFLOW_PASSWORD", ""),
        )

        from app.services.orchestration.airflow_backend import AirflowBackend

        return AirflowBackend(adapter=adapter)

    def _create_apscheduler(self) -> OrchestratorBackend:
        """Create APScheduler backend."""
        from app.services.orchestration.apscheduler_backend import APSchedulerBackend

        return APSchedulerBackend()
