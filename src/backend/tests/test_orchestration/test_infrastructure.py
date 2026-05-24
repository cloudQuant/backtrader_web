"""
Acceptance tests for Task 1: Infrastructure (config, exceptions, base class, schemas).

Validates Requirements: 1.7, 2.3, 6.1, 6.4, 6.6, 7.2, 7.3, 7.6, 9.1
"""

import pytest


class TestConfigSettings:
    """AT-1.1: Airflow configuration fields exist with correct defaults."""

    def test_airflow_config_fields_exist(self):
        from app.config import Settings

        settings = Settings(DEBUG=True)
        assert hasattr(settings, "AIRFLOW_API_BASE_URL")
        assert hasattr(settings, "AIRFLOW_USERNAME")
        assert hasattr(settings, "AIRFLOW_PASSWORD")
        assert hasattr(settings, "ORCHESTRATION_BACKEND")
        assert hasattr(settings, "AIRFLOW_DAG_OUTPUT_DIR")
        assert hasattr(settings, "AIRFLOW_CALLBACK_BASE_URL")

    def test_orchestration_backend_default_auto(self):
        from app.config import Settings

        settings = Settings(DEBUG=True)
        assert settings.ORCHESTRATION_BACKEND == "auto"

    def test_airflow_api_base_url_default_empty(self):
        from app.config import Settings

        settings = Settings(DEBUG=True)
        assert settings.AIRFLOW_API_BASE_URL == ""

    def test_airflow_dag_output_dir_default(self):
        from app.config import Settings

        settings = Settings(DEBUG=True)
        assert settings.AIRFLOW_DAG_OUTPUT_DIR == "./dags"

    def test_airflow_callback_base_url_default(self):
        from app.config import Settings

        settings = Settings(DEBUG=True)
        assert settings.AIRFLOW_CALLBACK_BASE_URL == "http://localhost:8000"


class TestExceptions:
    """AT-1.2: Exception classes are properly defined."""

    def test_airflow_api_error(self):
        from app.services.orchestration.exceptions import AirflowAPIError

        exc = AirflowAPIError(500, "Internal error", "/dags")
        assert exc.status_code == 500
        assert exc.detail == "Internal error"
        assert exc.endpoint == "/dags"
        assert "500" in str(exc)

    def test_airflow_connection_error(self):
        from app.services.orchestration.exceptions import AirflowConnectionError

        exc = AirflowConnectionError("Connection timeout")
        assert exc.status_code == 0
        assert "timeout" in exc.detail.lower()

    def test_airflow_dag_not_found_error(self):
        from app.services.orchestration.exceptions import AirflowDAGNotFoundError

        exc = AirflowDAGNotFoundError("my_dag")
        assert exc.status_code == 404
        assert "my_dag" in exc.detail

    def test_cyclic_dependency_error(self):
        from app.services.orchestration.exceptions import CyclicDependencyError

        exc = CyclicDependencyError(["a", "b", "c", "a"])
        assert exc.cycle == ["a", "b", "c", "a"]
        assert "a -> b -> c -> a" in str(exc)

    def test_dag_generation_error(self):
        from app.services.orchestration.exceptions import DAGGenerationError

        exc = DAGGenerationError("stock_hist", "template not found")
        assert exc.script_id == "stock_hist"
        assert "template not found" in exc.reason
