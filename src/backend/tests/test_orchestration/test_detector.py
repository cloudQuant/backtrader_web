from types import SimpleNamespace
from unittest.mock import patch

from app.services.orchestration.detector import BackendDetector


async def test_auto_detect_defaults_to_apscheduler_even_when_airflow_is_configured():
    detector = BackendDetector()
    apscheduler_backend = object()

    with (
        patch(
            "app.services.orchestration.detector.get_settings",
            return_value=SimpleNamespace(
                ORCHESTRATION_BACKEND="auto",
                AIRFLOW_API_BASE_URL="http://airflow.local/api/v1",
                AIRFLOW_USERNAME="admin",
                AIRFLOW_PASSWORD="secret",
            ),
        ),
        patch.object(detector, "_create_apscheduler", return_value=apscheduler_backend),
    ):
        backend = await detector.detect()

    assert backend is apscheduler_backend


async def test_forced_airflow_mode_still_uses_airflow_backend_factory():
    detector = BackendDetector()
    airflow_backend = object()

    with (
        patch(
            "app.services.orchestration.detector.get_settings",
            return_value=SimpleNamespace(
                ORCHESTRATION_BACKEND="airflow",
                AIRFLOW_API_BASE_URL="http://airflow.local/api/v1",
                AIRFLOW_USERNAME="admin",
                AIRFLOW_PASSWORD="secret",
            ),
        ),
        patch.object(detector, "_create_airflow_or_fail", return_value=airflow_backend),
    ):
        backend = await detector.detect()

    assert backend is airflow_backend
