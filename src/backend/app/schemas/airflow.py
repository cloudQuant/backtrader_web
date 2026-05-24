"""
Airflow integration schemas for request/response validation.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class AirflowCallbackPayload(BaseModel):
    """Payload received from Airflow task callbacks.

    Attributes:
        execution_id: Unique execution identifier.
        dag_id: Airflow DAG identifier.
        dag_run_id: Airflow DAG Run identifier.
        task_id: Airflow Task identifier within the DAG.
        status: Execution result (success/failed).
        start_time: Task start timestamp.
        end_time: Task end timestamp.
        duration: Execution duration in seconds.
        error_message: Error message if failed.
        error_trace: Full traceback if failed.
        rows_before: Row count before execution.
        rows_after: Row count after execution.
        result: Additional result metadata.
    """

    execution_id: str
    dag_id: str
    dag_run_id: str
    task_id: str
    status: str = Field(..., pattern="^(success|failed)$")
    start_time: datetime
    end_time: datetime
    duration: float = Field(..., ge=0)
    error_message: str | None = None
    error_trace: str | None = None
    rows_before: int | None = None
    rows_after: int | None = None
    result: dict | None = None


class AirflowDAGResponse(BaseModel):
    """DAG information response."""

    dag_id: str
    description: str | None = None
    schedule_interval: str | None = None
    is_paused: bool
    is_active: bool
    last_run_state: str | None = None
    last_run_start: datetime | None = None
    tags: list[str] = []


class AirflowDAGRunResponse(BaseModel):
    """DAG Run information response."""

    dag_run_id: str
    dag_id: str
    state: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    duration: float | None = None
    conf: dict | None = None


class AirflowTaskInstanceResponse(BaseModel):
    """Task Instance information response."""

    task_id: str
    dag_id: str
    dag_run_id: str
    state: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    duration: float | None = None
    try_number: int = 1
    max_tries: int = 0
