"""
Airflow DAG management API endpoints.

Provides DAG listing, triggering, status querying, and log viewing
through the AI for Investor interface. Only available when Airflow backend is active.
"""

import typing

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.schemas.auth import TokenPayload
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# Module-level reference to the active orchestration backend
_orchestration_backend = None


def set_orchestration_backend(backend: typing.Any) -> None:
    """Set the active orchestration backend (called during app startup)."""
    global _orchestration_backend
    _orchestration_backend = backend


def _get_airflow_adapter() -> typing.Any:
    """Get the Airflow adapter, raising 503 if not in Airflow mode."""
    from app.services.orchestration.airflow_backend import AirflowBackend

    if _orchestration_backend is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestration backend not initialized",
        )
    if not isinstance(_orchestration_backend, AirflowBackend):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Airflow backend not active. Current mode: apscheduler",
        )
    return _orchestration_backend._adapter


@router.get("/dags")
async def list_dags(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: TokenPayload = Depends(get_current_user),
) -> dict:
    """List all Airflow DAGs."""
    adapter = _get_airflow_adapter()
    return await adapter.list_dags(limit=limit, offset=offset)


@router.get("/dags/{dag_id}")
async def get_dag(
    dag_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> dict:
    """Get DAG details."""
    adapter = _get_airflow_adapter()
    return await adapter.get_dag(dag_id)


@router.post("/dags/{dag_id}/trigger")
async def trigger_dag(
    dag_id: str,
    conf: dict | None = None,
    current_user: TokenPayload = Depends(get_current_user),
) -> dict:
    """Trigger a DAG run with optional configuration."""
    adapter = _get_airflow_adapter()
    result = await adapter.trigger_dag_run(dag_id, conf=conf)
    logger.info(f"DAG triggered: {dag_id} by user {current_user.sub}")
    return result


@router.patch("/dags/{dag_id}/pause")
async def toggle_dag_pause(
    dag_id: str,
    is_paused: bool = True,
    current_user: TokenPayload = Depends(get_current_user),
) -> dict:
    """Pause or unpause a DAG."""
    adapter = _get_airflow_adapter()
    if is_paused:
        return await adapter.pause_dag(dag_id)
    return await adapter.unpause_dag(dag_id)


@router.get("/dags/{dag_id}/runs")
async def list_dag_runs(
    dag_id: str,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: TokenPayload = Depends(get_current_user),
) -> dict:
    """List DAG runs (execution history)."""
    adapter = _get_airflow_adapter()
    return await adapter.list_dag_runs(dag_id, limit=limit, offset=offset)


@router.get("/dags/{dag_id}/runs/{dag_run_id}/tasks")
async def get_task_instances(
    dag_id: str,
    dag_run_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> dict:
    """Get task instances for a specific DAG run."""
    adapter = _get_airflow_adapter()
    return await adapter.get_task_instances(dag_id, dag_run_id)


@router.get("/dags/{dag_id}/runs/{dag_run_id}/tasks/{task_id}/logs")
async def get_task_log(
    dag_id: str,
    dag_run_id: str,
    task_id: str,
    try_number: int = Query(1, ge=1),
    current_user: TokenPayload = Depends(get_current_user),
) -> dict:
    """Get task instance execution log."""
    adapter = _get_airflow_adapter()
    log_content = await adapter.get_task_log(dag_id, dag_run_id, task_id, try_number)
    return {"log": log_content}


@router.get("/orchestration/status")
async def get_orchestration_status(
    current_user: TokenPayload = Depends(get_current_user),
) -> dict:
    """Get current orchestration backend status."""
    if _orchestration_backend is None:
        return {"backend_type": "none", "connected": False}
    return await _orchestration_backend.get_backend_status()
