"""
Airflow REST API v1 async adapter.

Uses httpx.AsyncClient with connection pooling for efficient communication
with the Airflow webserver.
"""

from typing import Any

import httpx

from app.services.orchestration.exceptions import (
    AirflowAPIError,
    AirflowDAGNotFoundError,
)


class AirflowAdapter:
    """Async client for Airflow Stable REST API v1.

    Args:
        base_url: Airflow API base URL (e.g. http://localhost:8080/api/v1).
        username: Basic auth username.
        password: Basic auth password.
    """

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            auth=(username, password),
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    def _handle_response(self, response: httpx.Response, endpoint: str) -> dict:
        """Convert HTTP errors to structured exceptions."""
        if response.status_code == 404:
            raise AirflowDAGNotFoundError(endpoint.split("/")[-1] if "/" in endpoint else endpoint)
        if response.status_code >= 400:
            detail = ""
            try:
                body = response.json()
                detail = body.get("detail", body.get("title", str(body)))
            except Exception:
                detail = response.text[:200]
            raise AirflowAPIError(response.status_code, detail, endpoint)
        return response.json()

    async def health_check(self) -> bool:
        """Check if Airflow service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            resp = await self._client.get("/health")
            if resp.status_code == 200:
                data = resp.json()
                meta_status = data.get("metadatabase", {}).get("status")
                return meta_status == "healthy"
            return False
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ConnectTimeout):
            return False
        except Exception:
            return False

    async def list_dags(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List all DAGs."""
        resp = await self._client.get("/dags", params={"limit": limit, "offset": offset})
        return self._handle_response(resp, "/dags")

    async def get_dag(self, dag_id: str) -> dict[str, Any]:
        """Get DAG details."""
        endpoint = f"/dags/{dag_id}"
        resp = await self._client.get(endpoint)
        return self._handle_response(resp, endpoint)

    async def trigger_dag_run(self, dag_id: str, conf: dict | None = None) -> dict[str, Any]:
        """Trigger a new DAG run.

        Args:
            dag_id: DAG identifier.
            conf: Runtime configuration parameters.
        """
        endpoint = f"/dags/{dag_id}/dagRuns"
        payload: dict[str, Any] = {}
        if conf:
            payload["conf"] = conf
        resp = await self._client.post(endpoint, json=payload)
        return self._handle_response(resp, endpoint)

    async def get_dag_run(self, dag_id: str, dag_run_id: str) -> dict[str, Any]:
        """Get DAG run details."""
        endpoint = f"/dags/{dag_id}/dagRuns/{dag_run_id}"
        resp = await self._client.get(endpoint)
        return self._handle_response(resp, endpoint)

    async def list_dag_runs(self, dag_id: str, limit: int = 25, offset: int = 0) -> dict[str, Any]:
        """List DAG runs."""
        endpoint = f"/dags/{dag_id}/dagRuns"
        resp = await self._client.get(
            endpoint, params={"limit": limit, "offset": offset, "order_by": "-start_date"}
        )
        return self._handle_response(resp, endpoint)

    async def get_task_instances(self, dag_id: str, dag_run_id: str) -> dict[str, Any]:
        """Get task instances for a DAG run."""
        endpoint = f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances"
        resp = await self._client.get(endpoint)
        return self._handle_response(resp, endpoint)

    async def get_task_log(
        self, dag_id: str, dag_run_id: str, task_id: str, try_number: int = 1
    ) -> str:
        """Get task instance log content."""
        endpoint = f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}"
        resp = await self._client.get(endpoint, headers={"Accept": "text/plain"})
        if resp.status_code >= 400:
            self._handle_response(resp, endpoint)
        return resp.text

    async def pause_dag(self, dag_id: str) -> dict[str, Any]:
        """Pause a DAG."""
        endpoint = f"/dags/{dag_id}"
        resp = await self._client.patch(endpoint, json={"is_paused": True})
        return self._handle_response(resp, endpoint)

    async def unpause_dag(self, dag_id: str) -> dict[str, Any]:
        """Unpause a DAG."""
        endpoint = f"/dags/{dag_id}"
        resp = await self._client.patch(endpoint, json={"is_paused": False})
        return self._handle_response(resp, endpoint)

    async def close(self) -> None:
        """Close the HTTP client and release connections."""
        await self._client.aclose()
