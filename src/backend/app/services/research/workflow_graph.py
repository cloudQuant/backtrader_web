"""Server-owned protocol-v2 workflow graphs.

Executors may report typed evidence, but they never choose a successor.  A run
persists one of these versions when it is created so later deployments can
continue the exact graph it was authorized to execute.
"""

from __future__ import annotations

from typing import Final

_WORKFLOW_STAGES: Final[dict[str, tuple[str, ...]]] = {
    "generation-v1": ("CLARIFY", "GENERATE"),
    "discovery-v1": ("CLARIFY", "GENERATE", "VALIDATE_DISCOVERY"),
}


def workflow_stages(workflow_version: str = "generation-v1") -> tuple[str, ...]:
    """Return the immutable stage sequence authorized for one persisted version."""

    if not isinstance(workflow_version, str):
        raise ValueError("RESEARCH_WORKFLOW_VERSION_INVALID")
    try:
        return _WORKFLOW_STAGES[workflow_version]
    except KeyError:
        raise ValueError("RESEARCH_WORKFLOW_VERSION_INVALID") from None


def expected_next_stage(
    stage: str,
    workflow_version: str = "generation-v1",
) -> str | None:
    """Return the sole server-approved successor for a versioned stage."""

    if not isinstance(stage, str):
        raise ValueError("RESEARCH_WORKFLOW_STAGE_INVALID")
    stages = workflow_stages(workflow_version)
    try:
        stage_index = stages.index(stage)
    except ValueError:
        raise ValueError("RESEARCH_WORKFLOW_STAGE_INVALID") from None
    successor_index = stage_index + 1
    return stages[successor_index] if successor_index < len(stages) else None
