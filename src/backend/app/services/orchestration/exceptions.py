"""
Orchestration-specific exception types.
"""


class AirflowAPIError(Exception):
    """Airflow REST API call failed.

    Attributes:
        status_code: HTTP status code from Airflow.
        detail: Error description.
        endpoint: The API endpoint that failed.
    """

    def __init__(self, status_code: int, detail: str, endpoint: str = "") -> None:
        self.status_code = status_code
        self.detail = detail
        self.endpoint = endpoint
        super().__init__(f"Airflow API error {status_code} on {endpoint}: {detail}")


class AirflowConnectionError(AirflowAPIError):
    """Airflow service connection failed (timeout or unreachable)."""

    def __init__(self, detail: str = "Connection timeout", endpoint: str = "") -> None:
        super().__init__(status_code=0, detail=detail, endpoint=endpoint)


class AirflowDAGNotFoundError(AirflowAPIError):
    """Requested DAG does not exist in Airflow."""

    def __init__(self, dag_id: str) -> None:
        super().__init__(
            status_code=404,
            detail=f"DAG '{dag_id}' not found",
            endpoint=f"/dags/{dag_id}",
        )


class CyclicDependencyError(ValueError):
    """Dependency graph contains a cycle.

    Attributes:
        cycle: List of script_ids forming the cycle.
    """

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        super().__init__(f"Cyclic dependency detected: {' -> '.join(cycle)}")


class DAGGenerationError(Exception):
    """DAG file generation failed.

    Attributes:
        script_id: The script that failed to generate.
        reason: Why generation failed.
    """

    def __init__(self, script_id: str, reason: str) -> None:
        self.script_id = script_id
        self.reason = reason
        super().__init__(f"DAG generation failed for '{script_id}': {reason}")
