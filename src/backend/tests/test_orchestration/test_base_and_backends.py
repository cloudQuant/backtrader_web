"""
Acceptance tests for Task 2 & 6: Backend abstraction, APScheduler adapter, detector.

Validates Requirements: 6.1, 6.2, 6.3, 6.4, 6.6
"""

import pytest


class TestOrchestratorBackendInterface:
    """AT-6.6: OrchestratorBackend defines required abstract methods."""

    def test_cannot_instantiate_abstract_class(self):
        from app.services.orchestration.base import OrchestratorBackend

        with pytest.raises(TypeError):
            OrchestratorBackend()

    def test_abstract_methods_defined(self):
        from app.services.orchestration.base import OrchestratorBackend

        abstract_methods = OrchestratorBackend.__abstractmethods__
        expected = {
            "start", "shutdown", "add_or_update_task",
            "remove_task", "run_task_now", "reload_active_tasks",
            "get_backend_status",
        }
        assert expected == abstract_methods


class TestAPSchedulerBackend:
    """AT-2.1: APSchedulerBackend implements OrchestratorBackend."""

    def test_is_orchestrator_backend(self):
        from app.services.orchestration.apscheduler_backend import APSchedulerBackend
        from app.services.orchestration.base import OrchestratorBackend

        backend = APSchedulerBackend()
        assert isinstance(backend, OrchestratorBackend)

    async def test_get_backend_status_format(self):
        from app.services.orchestration.apscheduler_backend import APSchedulerBackend

        backend = APSchedulerBackend()
        status = await backend.get_backend_status()
        assert status["type"] == "apscheduler"
        assert "running" in status
        assert "job_count" in status
        assert isinstance(status["running"], bool)
        assert isinstance(status["job_count"], int)


class TestBackendDetector:
    """AT-6.1 to AT-6.4: Backend auto-detection logic."""

    async def test_auto_detect_no_airflow_url_uses_apscheduler(self, monkeypatch):
        """When AIRFLOW_API_BASE_URL is empty, auto mode selects APScheduler."""
        monkeypatch.setenv("ORCHESTRATION_BACKEND", "auto")
        monkeypatch.setenv("AIRFLOW_API_BASE_URL", "")

        # Reset settings cache
        import app.config
        app.config._settings = None

        from app.services.orchestration.apscheduler_backend import APSchedulerBackend
        from app.services.orchestration.detector import BackendDetector

        detector = BackendDetector()
        backend = await detector.detect()
        assert isinstance(backend, APSchedulerBackend)

        # Cleanup
        app.config._settings = None

    async def test_forced_apscheduler(self, monkeypatch):
        """ORCHESTRATION_BACKEND=apscheduler forces APScheduler."""
        monkeypatch.setenv("ORCHESTRATION_BACKEND", "apscheduler")

        import app.config
        app.config._settings = None

        from app.services.orchestration.apscheduler_backend import APSchedulerBackend
        from app.services.orchestration.detector import BackendDetector

        detector = BackendDetector()
        backend = await detector.detect()
        assert isinstance(backend, APSchedulerBackend)

        app.config._settings = None

    async def test_forced_airflow_no_url_fallback(self, monkeypatch):
        """ORCHESTRATION_BACKEND=airflow but no URL falls back to APScheduler."""
        monkeypatch.setenv("ORCHESTRATION_BACKEND", "airflow")
        monkeypatch.setenv("AIRFLOW_API_BASE_URL", "")

        import app.config
        app.config._settings = None

        from app.services.orchestration.apscheduler_backend import APSchedulerBackend
        from app.services.orchestration.detector import BackendDetector

        detector = BackendDetector()
        backend = await detector.detect()
        assert isinstance(backend, APSchedulerBackend)

        app.config._settings = None

    async def test_auto_detect_airflow_unreachable_fallback(self, monkeypatch):
        """Auto mode with unreachable Airflow URL falls back to APScheduler."""
        monkeypatch.setenv("ORCHESTRATION_BACKEND", "auto")
        monkeypatch.setenv("AIRFLOW_API_BASE_URL", "http://127.0.0.1:19999/api/v1")
        monkeypatch.setenv("AIRFLOW_PASSWORD", "test")

        import app.config
        app.config._settings = None

        from app.services.orchestration.apscheduler_backend import APSchedulerBackend
        from app.services.orchestration.detector import BackendDetector

        detector = BackendDetector()
        backend = await detector.detect()
        assert isinstance(backend, APSchedulerBackend)

        app.config._settings = None
