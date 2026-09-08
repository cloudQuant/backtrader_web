"""Bootstrap tests for the dedicated holdout worker process."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import ModuleType

import pytest

from app.services.research.holdout_claim import HoldoutEvaluatorRuntimeIdentity
from app.services.research.holdout_worker import HoldoutEvaluationWorker


class _Settings:
    def __init__(
        self,
        *,
        protocol_enabled: bool = True,
        worker_enabled: bool = True,
        factory: str = "app.research_deployments.holdout:create_worker",
        poll_seconds: float = 0.1,
    ) -> None:
        self.AI_RESEARCH_PROTOCOL_V2_ENABLED = protocol_enabled
        self.AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_ENABLED = worker_enabled
        self.AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_FACTORY = factory
        self.AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_POLL_SECONDS = poll_seconds


class _Executor:
    async def execute(self, command):
        raise AssertionError("not expected")

    async def inspect(self, command):
        raise AssertionError("not expected")


def _worker() -> HoldoutEvaluationWorker:
    return HoldoutEvaluationWorker(
        executor=_Executor(),
        runtime=HoldoutEvaluatorRuntimeIdentity(
            worker_identity="holdout-worker",
            evaluator_identity="holdout-evaluator",
            evaluator_image_digest="sha256:" + "5" * 64,
        ),
        claim_service=object(),
        finalize_service=object(),
        evidence_service=object(),
    )


def test_holdout_cli_import_is_checkout_local() -> None:
    from scripts import run_ai_research_v2_holdout_worker as worker_cli

    backend_root = Path(__file__).resolve().parents[1]
    assert Path(worker_cli.__file__).resolve() == (
        backend_root / "scripts" / "run_ai_research_v2_holdout_worker.py"
    )


def test_holdout_factory_reference_is_restricted_to_deployment_namespace() -> None:
    from app.services.research.holdout_worker_process import resolve_holdout_worker_factory

    with pytest.raises(ValueError, match="HOLDOUT_WORKER_FACTORY_NAMESPACE_DENIED"):
        resolve_holdout_worker_factory(
            "app.services.research.holdout_worker:HoldoutEvaluationWorker",
            importer=lambda _name: pytest.fail("importer must not run"),
        )


def test_holdout_factory_reference_resolves_reviewed_callable() -> None:
    from app.services.research.holdout_worker_process import resolve_holdout_worker_factory

    module = ModuleType("app.research_deployments.holdout")

    def factory() -> object:
        return object()

    module.create_worker = factory
    resolved = resolve_holdout_worker_factory(
        "app.research_deployments.holdout:create_worker",
        importer=lambda name: module if name == module.__name__ else pytest.fail(name),
    )
    assert resolved is factory


@pytest.mark.asyncio
async def test_disabled_holdout_process_does_not_resolve_factory_or_claim() -> None:
    from app.services.research.holdout_worker_process import run_deployment_holdout_worker

    calls: list[str] = []
    started = await run_deployment_holdout_worker(
        settings=_Settings(worker_enabled=False),
        stop_event=asyncio.Event(),
        factory_resolver=lambda reference: calls.append(reference),
    )
    assert started is False
    assert calls == []


@pytest.mark.asyncio
async def test_invalid_factory_return_fails_before_run_once() -> None:
    from app.services.research.holdout_worker_process import run_deployment_holdout_worker

    with pytest.raises(ValueError, match="HOLDOUT_WORKER_FACTORY_RETURN_INVALID"):
        await run_deployment_holdout_worker(
            settings=_Settings(),
            stop_event=asyncio.Event(),
            factory_resolver=lambda _reference: lambda: object(),
        )


@pytest.mark.asyncio
async def test_dedicated_process_runs_bounded_polls_until_stopped() -> None:
    from app.services.research.holdout_worker_process import run_deployment_holdout_worker

    stop = asyncio.Event()
    worker = _worker()
    calls: list[int] = []

    async def run_once(limit: int = 10):
        calls.append(limit)
        stop.set()
        return []

    worker.run_once = run_once
    started = await run_deployment_holdout_worker(
        settings=_Settings(),
        stop_event=stop,
        factory_resolver=lambda _reference: lambda: worker,
    )
    assert started is True
    assert calls == [10]


def test_holdout_cli_returns_nonzero_without_leaking_bootstrap_details(monkeypatch) -> None:
    from scripts import run_ai_research_v2_holdout_worker as worker_cli

    async def invalid() -> bool:
        raise ValueError("HOLDOUT_WORKER_FACTORY_FAILED")

    monkeypatch.setattr(worker_cli, "run_deployment_holdout_worker", invalid)
    assert worker_cli.run() == 2
