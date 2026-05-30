"""
Acceptance tests for Task 3: AirflowAdapter.

Validates Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
"""

import httpx
import pytest

from app.services.orchestration.airflow_adapter import AirflowAdapter
from app.services.orchestration.exceptions import (
    AirflowAPIError,
    AirflowDAGNotFoundError,
)


class TestAirflowAdapterHealthCheck:
    """AT-2.1, AT-2.2: Health check behavior."""

    async def test_health_check_success(self):
        """Healthy Airflow returns True."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={"metadatabase": {"status": "healthy"}, "scheduler": {"status": "healthy"}},
            )
        )
        adapter = AirflowAdapter.__new__(AirflowAdapter)
        adapter._base_url = "http://test/api/v1"
        adapter._client = httpx.AsyncClient(transport=transport, base_url="http://test/api/v1")

        result = await adapter.health_check()
        assert result is True
        await adapter.close()

    async def test_health_check_unhealthy(self):
        """Unhealthy metadatabase returns False."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={"metadatabase": {"status": "unhealthy"}, "scheduler": {"status": "healthy"}},
            )
        )
        adapter = AirflowAdapter.__new__(AirflowAdapter)
        adapter._base_url = "http://test/api/v1"
        adapter._client = httpx.AsyncClient(transport=transport, base_url="http://test/api/v1")

        result = await adapter.health_check()
        assert result is False
        await adapter.close()

    async def test_health_check_connection_error(self):
        """Connection error returns False (no exception raised)."""
        def raise_connect_error(req):
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(raise_connect_error)
        adapter = AirflowAdapter.__new__(AirflowAdapter)
        adapter._base_url = "http://test/api/v1"
        adapter._client = httpx.AsyncClient(transport=transport, base_url="http://test/api/v1")

        result = await adapter.health_check()
        assert result is False
        await adapter.close()


class TestAirflowAdapterErrorHandling:
    """AT-2.3: HTTP errors converted to structured exceptions."""

    async def test_404_raises_dag_not_found(self):
        """404 response raises AirflowDAGNotFoundError."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(404, json={"detail": "DAG not found"})
        )
        adapter = AirflowAdapter.__new__(AirflowAdapter)
        adapter._base_url = "http://test/api/v1"
        adapter._client = httpx.AsyncClient(transport=transport, base_url="http://test/api/v1")

        with pytest.raises(AirflowDAGNotFoundError) as exc_info:
            await adapter.get_dag("nonexistent")
        assert exc_info.value.status_code == 404
        await adapter.close()

    async def test_500_raises_api_error(self):
        """500 response raises AirflowAPIError with status code."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(500, json={"detail": "Internal Server Error"})
        )
        adapter = AirflowAdapter.__new__(AirflowAdapter)
        adapter._base_url = "http://test/api/v1"
        adapter._client = httpx.AsyncClient(transport=transport, base_url="http://test/api/v1")

        with pytest.raises(AirflowAPIError) as exc_info:
            await adapter.list_dags()
        assert exc_info.value.status_code == 500
        assert "Internal Server Error" in exc_info.value.detail
        await adapter.close()

    async def test_403_raises_api_error(self):
        """403 response raises AirflowAPIError."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(403, json={"detail": "Forbidden"})
        )
        adapter = AirflowAdapter.__new__(AirflowAdapter)
        adapter._base_url = "http://test/api/v1"
        adapter._client = httpx.AsyncClient(transport=transport, base_url="http://test/api/v1")

        with pytest.raises(AirflowAPIError) as exc_info:
            await adapter.list_dags()
        assert exc_info.value.status_code == 403
        await adapter.close()


class TestAirflowAdapterTrigger:
    """AT-2.4, AT-2.6: Trigger DAG run with conf parameters."""

    async def test_trigger_dag_with_conf(self):
        """Conf parameters are passed through to the API request."""
        received_body = {}

        def handler(req: httpx.Request):
            import json
            received_body.update(json.loads(req.content))
            return httpx.Response(200, json={
                "dag_run_id": "manual__2024-01-01",
                "dag_id": "test_dag",
                "state": "queued",
                "conf": received_body.get("conf", {}),
            })

        transport = httpx.MockTransport(handler)
        adapter = AirflowAdapter.__new__(AirflowAdapter)
        adapter._base_url = "http://test/api/v1"
        adapter._client = httpx.AsyncClient(transport=transport, base_url="http://test/api/v1")

        conf = {"symbol": "000001", "start_date": "2024-01-01"}
        result = await adapter.trigger_dag_run("test_dag", conf=conf)

        assert result["dag_run_id"] == "manual__2024-01-01"
        assert received_body["conf"] == conf
        await adapter.close()

    async def test_trigger_dag_without_conf(self):
        """Trigger without conf sends empty body."""
        received_body = {}

        def handler(req: httpx.Request):
            import json
            received_body.update(json.loads(req.content))
            return httpx.Response(200, json={
                "dag_run_id": "manual__2024-01-01",
                "dag_id": "test_dag",
                "state": "queued",
            })

        transport = httpx.MockTransport(handler)
        adapter = AirflowAdapter.__new__(AirflowAdapter)
        adapter._base_url = "http://test/api/v1"
        adapter._client = httpx.AsyncClient(transport=transport, base_url="http://test/api/v1")

        await adapter.trigger_dag_run("test_dag")
        assert "conf" not in received_body
        await adapter.close()


class TestAirflowAdapterDAGOperations:
    """AT-2.5: DAG CRUD operations."""

    async def test_list_dags(self):
        """List DAGs returns parsed response."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={
                "dags": [{"dag_id": "dag_1"}, {"dag_id": "dag_2"}],
                "total_entries": 2,
            })
        )
        adapter = AirflowAdapter.__new__(AirflowAdapter)
        adapter._base_url = "http://test/api/v1"
        adapter._client = httpx.AsyncClient(transport=transport, base_url="http://test/api/v1")

        result = await adapter.list_dags()
        assert len(result["dags"]) == 2
        await adapter.close()

    async def test_pause_dag(self):
        """Pause DAG sends is_paused=True."""
        received_body = {}

        def handler(req: httpx.Request):
            import json
            received_body.update(json.loads(req.content))
            return httpx.Response(200, json={"dag_id": "test", "is_paused": True})

        transport = httpx.MockTransport(handler)
        adapter = AirflowAdapter.__new__(AirflowAdapter)
        adapter._base_url = "http://test/api/v1"
        adapter._client = httpx.AsyncClient(transport=transport, base_url="http://test/api/v1")

        await adapter.pause_dag("test")
        assert received_body["is_paused"] is True
        await adapter.close()

    async def test_unpause_dag(self):
        """Unpause DAG sends is_paused=False."""
        received_body = {}

        def handler(req: httpx.Request):
            import json
            received_body.update(json.loads(req.content))
            return httpx.Response(200, json={"dag_id": "test", "is_paused": False})

        transport = httpx.MockTransport(handler)
        adapter = AirflowAdapter.__new__(AirflowAdapter)
        adapter._base_url = "http://test/api/v1"
        adapter._client = httpx.AsyncClient(transport=transport, base_url="http://test/api/v1")

        await adapter.unpause_dag("test")
        assert received_body["is_paused"] is False
        await adapter.close()
