"""
E2E acceptance tests for Airflow integration API endpoints.

Tests the callback endpoint and the orchestration status endpoint.
Validates Requirements: 6.7, 6.8, 7.1, 7.2, 7.3
"""

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


class TestAirflowCallbackAPI:
    """AT-7.1: Callback endpoint creates TaskExecution records."""

    async def test_callback_success_creates_record(self, client: AsyncClient):
        """Valid success callback creates a COMPLETED execution record."""
        payload = {
            "execution_id": "exec_test_001",
            "dag_id": "dag_stock_zh_a_hist",
            "dag_run_id": "run_20240101",
            "task_id": "stock_zh_a_hist",
            "status": "success",
            "start_time": "2024-01-01T08:00:00Z",
            "end_time": "2024-01-01T08:05:00Z",
            "duration": 300.0,
            "rows_before": 1000,
            "rows_after": 1500,
        }
        resp = await client.post("/api/v1/data/airflow/callback", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["execution_id"] == "exec_test_001"
        assert data["status"] == "completed"

    async def test_callback_failure_creates_record(self, client: AsyncClient):
        """Valid failure callback creates a FAILED execution record."""
        payload = {
            "execution_id": "exec_test_002",
            "dag_id": "dag_bond_daily",
            "dag_run_id": "run_20240102",
            "task_id": "bond_daily",
            "status": "failed",
            "start_time": "2024-01-02T08:00:00Z",
            "end_time": "2024-01-02T08:01:00Z",
            "duration": 60.0,
            "error_message": "Connection timeout to akshare",
            "error_trace": "Traceback...",
        }
        resp = await client.post("/api/v1/data/airflow/callback", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"

    async def test_callback_invalid_status_rejected(self, client: AsyncClient):
        """Invalid status value is rejected with 422."""
        payload = {
            "execution_id": "exec_bad",
            "dag_id": "dag_test",
            "dag_run_id": "run_1",
            "task_id": "task_1",
            "status": "invalid_status",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T00:01:00Z",
            "duration": 60.0,
        }
        resp = await client.post("/api/v1/data/airflow/callback", json=payload)
        assert resp.status_code == 422


class TestOrchestrationStatusAPI:
    """AT-6.4, AT-6.5: Orchestration status and 503 behavior."""

    async def test_orchestration_status_endpoint(self, client: AsyncClient):
        """Status endpoint returns backend info (requires auth)."""
        _, headers = await register_and_login(client)
        resp = await client.get("/api/v1/data/airflow/orchestration/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        # In test environment, backend is not initialized → returns "none"
        assert "backend_type" in data or "type" in data

    async def test_orchestration_status_unauthenticated(self, client: AsyncClient):
        """Status endpoint requires authentication."""
        resp = await client.get("/api/v1/data/airflow/orchestration/status")
        assert resp.status_code == 401


class TestAirflowDAGsAPI:
    """AT-6.5: Airflow DAG endpoints return 503 when not in Airflow mode."""

    async def test_list_dags_503_without_airflow(self, client: AsyncClient):
        """DAG list returns 503 when Airflow backend is not active."""
        _, headers = await register_and_login(client)
        resp = await client.get("/api/v1/data/airflow/dags", headers=headers)
        assert resp.status_code == 503

    async def test_trigger_dag_503_without_airflow(self, client: AsyncClient):
        """DAG trigger returns 503 when Airflow backend is not active."""
        _, headers = await register_and_login(client)
        resp = await client.post(
            "/api/v1/data/airflow/dags/test_dag/trigger",
            headers=headers,
            json=None,
        )
        assert resp.status_code == 503

    async def test_dag_runs_503_without_airflow(self, client: AsyncClient):
        """DAG runs returns 503 when Airflow backend is not active."""
        _, headers = await register_and_login(client)
        resp = await client.get("/api/v1/data/airflow/dags/test/runs", headers=headers)
        assert resp.status_code == 503

    async def test_dags_unauthenticated(self, client: AsyncClient):
        """DAG endpoints require authentication."""
        resp = await client.get("/api/v1/data/airflow/dags")
        assert resp.status_code == 401
