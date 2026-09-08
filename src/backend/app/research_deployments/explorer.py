"""Default disabled-by-configuration Explorer worker composition.

This module is intentionally available only through the deployment factory
namespace.  Importing it does not start a worker, enable protocol-v2 writes,
or select it as the default configuration.
"""

from __future__ import annotations

from app.services.research.deterministic_executor import (
    DeterministicClarifyExecutor,
    DeterministicGenerateExecutor,
)
from app.services.research.workflow_worker import ResearchProtocolWorker


def create_worker() -> ResearchProtocolWorker:
    """Create the reviewed core graph used only when operators opt in explicitly."""

    return ResearchProtocolWorker(
        executors={
            "CLARIFY": DeterministicClarifyExecutor(),
            "GENERATE": DeterministicGenerateExecutor(),
        }
    )
