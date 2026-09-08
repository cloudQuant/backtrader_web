"""Server-owned versioned workflow graph tests."""

from __future__ import annotations

import pytest

from app.services.research.workflow_graph import expected_next_stage, workflow_stages


def test_each_supported_workflow_has_an_immutable_server_owned_stage_order() -> None:
    """Only the server graph, never an executor, selects the next stage."""

    assert workflow_stages("generation-v1") == ("CLARIFY", "GENERATE")
    assert workflow_stages("discovery-v1") == (
        "CLARIFY",
        "GENERATE",
        "VALIDATE_DISCOVERY",
    )
    assert expected_next_stage("CLARIFY", "generation-v1") == "GENERATE"
    assert expected_next_stage("GENERATE", "generation-v1") is None
    assert expected_next_stage("CLARIFY", "discovery-v1") == "GENERATE"
    assert expected_next_stage("GENERATE", "discovery-v1") == "VALIDATE_DISCOVERY"
    assert expected_next_stage("VALIDATE_DISCOVERY", "discovery-v1") is None


@pytest.mark.parametrize(
    ("stage", "workflow_version"),
    [
        ("VALIDATE_DISCOVERY", "generation-v1"),
        ("SEALED_EVALUATE", "discovery-v1"),
        ("", "generation-v1"),
    ],
)
def test_graph_rejects_a_stage_not_authorized_by_its_version(
    stage: str, workflow_version: str
) -> None:
    with pytest.raises(ValueError, match="RESEARCH_WORKFLOW_STAGE_INVALID"):
        expected_next_stage(stage, workflow_version)


def test_graph_rejects_an_unknown_version_before_a_task_can_be_created() -> None:
    with pytest.raises(ValueError, match="RESEARCH_WORKFLOW_VERSION_INVALID"):
        workflow_stages("caller-selected-v999")
