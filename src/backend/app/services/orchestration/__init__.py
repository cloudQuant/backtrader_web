"""
Orchestration backend abstraction layer.

Supports APScheduler (built-in) and Apache Airflow (external service).
The system auto-detects Airflow availability and falls back to APScheduler.
"""

from app.services.orchestration.base import OrchestratorBackend
from app.services.orchestration.exceptions import (
    AirflowAPIError,
    AirflowConnectionError,
    AirflowDAGNotFoundError,
    CyclicDependencyError,
    DAGGenerationError,
)

__all__ = [
    "OrchestratorBackend",
    "AirflowAPIError",
    "AirflowConnectionError",
    "AirflowDAGNotFoundError",
    "CyclicDependencyError",
    "DAGGenerationError",
]
