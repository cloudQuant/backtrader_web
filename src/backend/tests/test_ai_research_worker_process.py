"""Deployment bootstrap tests for the protocol-v2 Explorer worker."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import ModuleType

import pytest

from app.services.research.worker_process import (
    resolve_worker_factory,
    run_deployment_worker,
)
from app.services.research.workflow_worker import (
    ResearchProtocolWorker,
    StageExecutionContext,
    StageExecutionOutcome,
)
from scripts import run_ai_research_v2_worker as worker_cli


def test_worker_cli_import_is_checkout_local() -> None:
    """An installed package named scripts must never shadow our deployment CLI."""

    backend_root = Path(__file__).resolve().parents[1]
    assert Path(worker_cli.__file__).resolve() == (
        backend_root / "scripts" / "run_ai_research_v2_worker.py"
    )


class _Settings:
    """Minimal settings double so bootstrap tests never use process configuration."""

    def __init__(
        self,
        *,
        protocol_enabled: bool = True,
        worker_enabled: bool = True,
        factory: str = "app.research_deployments.explorer:create_worker",
        poll_seconds: float = 0.01,
    ) -> None:
        self.AI_RESEARCH_PROTOCOL_V2_ENABLED = protocol_enabled
        self.AI_RESEARCH_PROTOCOL_V2_WORKER_ENABLED = worker_enabled
        self.AI_RESEARCH_PROTOCOL_V2_WORKER_FACTORY = factory
        self.AI_RESEARCH_PROTOCOL_V2_WORKER_POLL_SECONDS = poll_seconds


def test_factory_reference_allows_only_the_deployment_namespace() -> None:
    """Environment configuration cannot make the worker import arbitrary app modules."""

    with pytest.raises(ValueError, match="RESEARCH_WORKER_FACTORY_NAMESPACE_DENIED"):
        resolve_worker_factory(
            "app.services.research.workflow_worker:ResearchProtocolWorker",
            importer=lambda _module_name: pytest.fail("importer must not be called"),
        )


def test_factory_reference_rejects_non_ascii_module_identifiers() -> None:
    """Visually confusable module paths cannot become a deployment factory target."""

    with pytest.raises(ValueError, match="RESEARCH_WORKER_FACTORY_REFERENCE_INVALID"):
        resolve_worker_factory(
            "app.research_deployments.ｅxplorer:create_worker",
            importer=lambda _module_name: pytest.fail("importer must not be called"),
        )


def test_factory_reference_resolves_an_explicit_deployment_callable() -> None:
    """A reviewed factory shipped in the worker image can be resolved deterministically."""

    module = ModuleType("app.research_deployments.explorer")

    def create_worker() -> object:
        return object()

    module.create_worker = create_worker
    factory = resolve_worker_factory(
        "app.research_deployments.explorer:create_worker",
        importer=lambda module_name: _assert_module_name(module_name, module),
    )

    assert factory is create_worker


@pytest.mark.asyncio
async def test_disabled_runtime_does_not_load_or_claim_tasks() -> None:
    """Both protocol and worker flags must be on before any deployment factory is loaded."""

    resolver_calls: list[str] = []
    result = await run_deployment_worker(
        settings=_Settings(worker_enabled=False),
        stop_event=asyncio.Event(),
        factory_resolver=lambda reference: resolver_calls.append(reference),
    )

    assert result is False
    assert resolver_calls == []


@pytest.mark.asyncio
async def test_runtime_rejects_incomplete_worker_before_claiming_tasks() -> None:
    """A bad deployment cannot turn queued user work into placeholder failures."""

    task_runner = _ClaimTrapTaskRunner()
    worker = ResearchProtocolWorker(
        task_runner=task_runner,
        executors={"CLARIFY": _Executor(next_stage="GENERATE")},
    )

    with pytest.raises(ValueError, match="RESEARCH_WORKER_EXECUTORS_INCOMPLETE"):
        await run_deployment_worker(
            settings=_Settings(),
            stop_event=asyncio.Event(),
            factory_resolver=lambda _reference: lambda: worker,
        )

    assert task_runner.calls == []


@pytest.mark.asyncio
async def test_runtime_runs_only_a_complete_deployment_worker_until_stop() -> None:
    """A complete injected worker owns its own loop and exits on the supplied stop signal."""

    stop_event = asyncio.Event()
    task_runner = _StopAfterFirstPollTaskRunner(stop_event)
    worker = ResearchProtocolWorker(
        task_runner=task_runner,
        executors={
            "CLARIFY": _Executor(next_stage="GENERATE"),
            "GENERATE": _Executor(next_stage=None),
        },
    )

    result = await run_deployment_worker(
        settings=_Settings(),
        stop_event=stop_event,
        factory_resolver=lambda _reference: lambda: worker,
    )

    assert result is True
    assert task_runner.calls == ["recover", "claim"]


@pytest.mark.asyncio
async def test_runtime_rejects_a_factory_that_does_not_return_the_worker_type() -> None:
    """Only the audited worker implementation may enter the deployment poll loop."""

    with pytest.raises(ValueError, match="RESEARCH_WORKER_FACTORY_RETURN_INVALID"):
        await run_deployment_worker(
            settings=_Settings(),
            stop_event=asyncio.Event(),
            factory_resolver=lambda _reference: lambda: object(),
        )


def test_worker_cli_returns_success_when_protocol_is_intentionally_disabled(monkeypatch) -> None:
    """The disabled no-op is a normal rollout state, not a crash-loop condition."""

    async def disabled() -> bool:
        return False

    monkeypatch.setattr(worker_cli, "run_deployment_worker", disabled)

    assert worker_cli.run() == 0


def test_worker_cli_returns_nonzero_for_a_fail_closed_bootstrap_error(monkeypatch) -> None:
    """A malformed deployment must be visible to orchestration health checks."""

    async def invalid() -> bool:
        raise ValueError("RESEARCH_WORKER_EXECUTORS_INCOMPLETE")

    monkeypatch.setattr(worker_cli, "run_deployment_worker", invalid)

    assert worker_cli.run() == 2


def _assert_module_name(module_name: str, module: ModuleType) -> ModuleType:
    assert module_name == "app.research_deployments.explorer"
    return module


class _ClaimTrapTaskRunner:
    lease_seconds = 60
    heartbeat_interval_seconds = 20.0

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def recover_expired_leases(self) -> int:
        self.calls.append("recover")
        return 0

    async def claim_due(self) -> list[object]:
        self.calls.append("claim")
        return []


class _StopAfterFirstPollTaskRunner(_ClaimTrapTaskRunner):
    def __init__(self, stop_event: asyncio.Event) -> None:
        super().__init__()
        self._stop_event = stop_event

    async def claim_due(self) -> list[object]:
        self.calls.append("claim")
        self._stop_event.set()
        return []


class _Executor:
    def __init__(self, *, next_stage: str | None) -> None:
        self._next_stage = next_stage

    async def execute(self, context: StageExecutionContext) -> StageExecutionOutcome:
        del context
        return StageExecutionOutcome.succeeded(next_stage=self._next_stage)
