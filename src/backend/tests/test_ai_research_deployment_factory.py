"""Contract tests for the reviewed protocol-v2 Explorer factory."""

from __future__ import annotations

from app.research_deployments.explorer import create_worker
from app.services.research.worker_process import resolve_worker_factory


def test_deployment_factory_supplies_the_complete_server_owned_core_graph() -> None:
    """An enabled worker image cannot start with a partial placeholder executor map."""

    worker = create_worker()

    assert worker.has_complete_executor_set is True


def test_deployment_bootstrap_can_resolve_the_reviewed_factory_reference() -> None:
    """The exact operator-facing reference resolves inside the restricted namespace."""

    factory = resolve_worker_factory("app.research_deployments.explorer:create_worker")

    assert factory().has_complete_executor_set is True
