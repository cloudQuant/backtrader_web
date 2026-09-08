from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from importlib import import_module

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchEvaluation,
    ResearchEvidencePackage,
    ResearchHoldoutArtifactBinding,
    ResearchHoldoutEvaluationCommand,
    ResearchHoldoutExecution,
)
from app.services.research.canonical import canonical_json, content_hash
from app.services.research.evidence_package import EvidencePackageService
from app.services.research.holdout_claim import (
    HoldoutClaimService,
    HoldoutEvaluatorRuntimeIdentity,
)
from app.services.research.holdout_finalize import HoldoutFinalizeService
from tests import test_ai_research_holdout_request as request_tests
from tests.test_ai_research_holdout_authorization import _dataset_registry
from tests.test_ai_research_holdout_claim import _queued_command
from tests.test_ai_research_holdout_execution_contract import _result_payload
from tests.test_ai_research_holdout_finalize import (
    _trusted_passing_measurements,
    _trusted_rejecting_measurements,
)

_IMAGE = f"sha256:{'5' * 64}"
_EVALUATOR = "ai_research_evaluator"


@pytest.fixture(autouse=True)
def enable_protocol_v2_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)


def _worker_module():
    return import_module("app.services.research.holdout_worker")


async def _queued_context(client, auth_user, suffix: str):
    old_image = request_tests._EVALUATOR_IMAGE
    request_tests._EVALUATOR_IMAGE = _IMAGE
    try:
        context, _headers, command = await _queued_command(client, auth_user, suffix)
    finally:
        request_tests._EVALUATOR_IMAGE = old_image
    runtime = HoldoutEvaluatorRuntimeIdentity(
        worker_identity="holdout-worker-production",
        evaluator_identity=_EVALUATOR,
        evaluator_image_digest=_IMAGE,
    )
    return context, command, runtime


class _Executor:
    def __init__(
        self,
        measurements: dict,
        *,
        fail_after_dispatch: bool = False,
        fail_before_apply: bool = False,
        delay_seconds: float = 0,
    ) -> None:
        self.measurements = json.loads(canonical_json(measurements))
        self.fail_after_dispatch = fail_after_dispatch
        self.fail_before_apply = fail_before_apply
        self.delay_seconds = delay_seconds
        self.execute_calls = 0
        self.inspect_calls = 0
        self.observed_command = None

    async def execute(self, command):
        self.execute_calls += 1
        if self.fail_before_apply:
            raise ValueError("HOLDOUT_HTTP_EXECUTOR_TIMEOUT")
        self.observed_command = command
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.fail_after_dispatch:
            raise ValueError("HOLDOUT_HTTP_EXECUTOR_TIMEOUT")
        return self._result(command)

    async def inspect(self, command):
        self.inspect_calls += 1
        contract = import_module("app.services.research.holdout_execution_contract")
        return contract.HoldoutExecutionInspection.from_mapping(
            {
                "schema_version": "holdout-execution-inspection-v2",
                "operation_id": command.snapshot["operation_id"],
                "command_hash": command.command_hash,
                "evaluator_identity": command.snapshot["evaluator_identity"],
                "evaluator_image_digest": command.snapshot["evaluator_image_digest"],
                "status": "OBSERVED" if self.observed_command is not None else "NOT_EXECUTED",
                "result": (
                    self._result(command).snapshot if self.observed_command is not None else None
                ),
                "error_code": None,
            },
            command=command,
        )

    def _result(self, command):
        contract = import_module("app.services.research.holdout_execution_contract")
        return contract.HoldoutExecutionResult.from_mapping(
            _result_payload(command, measurements=self.measurements),
            command=command,
        )


class _HeartbeatCountingClaimService(HoldoutClaimService):
    def __init__(self, *, dataset_registry) -> None:
        super().__init__(dataset_registry=dataset_registry, lease_seconds=60)
        self.heartbeat_calls = 0

    async def heartbeat(self, **kwargs):
        self.heartbeat_calls += 1
        return await super().heartbeat(**kwargs)


class _ThresholdInconsistentExecutor(_Executor):
    def _result(self, command):
        contract = import_module("app.services.research.holdout_execution_contract")
        payload = _result_payload(command, measurements=self.measurements)
        terminal = payload["terminal_receipt"]
        assert isinstance(terminal, dict)
        safe_metrics = terminal["safe_metrics"]
        assert isinstance(safe_metrics, dict)
        safe_metrics["max_drawdown"] = 0.99
        return contract.HoldoutExecutionResult.from_mapping(payload, command=command)


class _CrashAfterCheckpointFinalizer:
    def __init__(self) -> None:
        self._delegate = HoldoutFinalizeService()

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    async def checkpoint_execution_receipt(self, **kwargs):
        await self._delegate.checkpoint_execution_receipt(**kwargs)
        raise RuntimeError("simulated-crash-after-checkpoint")


class _CrashAfterFinalizeFinalizer:
    def __init__(self) -> None:
        self._delegate = HoldoutFinalizeService()

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    async def finalize_claimed_evaluation(self, **kwargs):
        await self._delegate.finalize_claimed_evaluation(**kwargs)
        raise RuntimeError("simulated-crash-after-finalize")


class _CrashAfterPackageEvidenceService:
    def __init__(self, *, dataset_registry) -> None:
        self._delegate = EvidencePackageService(dataset_registry=dataset_registry)

    async def build_for_terminal_command(self, **kwargs):
        await self._delegate.build_for_terminal_command(**kwargs)
        raise RuntimeError("simulated-crash-after-package")


def _worker(
    context,
    runtime,
    executor,
    *,
    claim_service=None,
    finalize_service=None,
    evidence_service=None,
):
    module = _worker_module()
    datasets = _dataset_registry(context)
    return module.HoldoutEvaluationWorker(
        executor=executor,
        runtime=runtime,
        claim_service=claim_service
        or HoldoutClaimService(dataset_registry=datasets, lease_seconds=60),
        finalize_service=finalize_service or HoldoutFinalizeService(),
        evidence_service=evidence_service or EvidencePackageService(dataset_registry=datasets),
        heartbeat_interval_seconds=0.01,
    )


@pytest.mark.asyncio
async def test_worker_runs_queued_command_to_passed_unique_evidence_package(
    client,
    auth_user,
) -> None:
    context, command, runtime = await _queued_context(client, auth_user, "worker-pass")
    measurements = await _trusted_passing_measurements(context, runtime=runtime)
    raw_canary = 0.3141592653589793
    measurements["returns"][0] = raw_canary
    executor = _Executor(measurements)
    worker = _worker(context, runtime, executor)

    results = await worker.run_once(limit=1)

    assert [(result.command_id, result.status, result.error_code) for result in results] == [
        (command["id"], "PASSED", None)
    ]
    assert executor.execute_calls == 1
    assert await _count(ResearchEvidencePackage) == 1
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, command["id"])
        evaluation = await session.get(ResearchEvaluation, stored.evaluation_id)
        execution = await session.scalar(
            select(ResearchHoldoutExecution).where(
                ResearchHoldoutExecution.command_id == command["id"]
            )
        )
        binding = await session.scalar(
            select(ResearchHoldoutArtifactBinding).where(
                ResearchHoldoutArtifactBinding.command_id == command["id"]
            )
        )
        artifact = await session.get(ResearchArtifact, binding.artifact_id)
        ordinary_content = await session.get(ResearchArtifactContent, binding.artifact_id)
        package = await session.scalar(
            select(ResearchEvidencePackage).where(
                ResearchEvidencePackage.command_id == command["id"]
            )
        )
    assert stored is not None and stored.status == "SUCCEEDED"
    assert evaluation is not None and evaluation.status == "PASSED"
    assert execution is not None and execution.result_json is not None
    serialized_receipt = json.dumps(execution.result_json, sort_keys=True)
    assert "returns" not in serialized_receipt
    assert "trial_sharpes" not in serialized_receipt
    assert str(raw_canary) not in serialized_receipt
    assert artifact is not None and artifact.kind == "sealed_holdout_artifact_receipt"
    assert ordinary_content is None
    assert package is not None
    policy_hash = evaluation.gate_inputs["promotion_policy_hash"]
    assert package.manifest["material"]["promotion_policy_hash"] == policy_hash
    assert package.approval_binding_hash == content_hash(package.manifest["material"])


@pytest.mark.asyncio
async def test_same_version_policy_drift_rejects_existing_package_at_approval_boundary(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, command, runtime = await _queued_context(
        client,
        auth_user,
        "worker-package-policy-drift",
    )
    executor = _Executor(await _trusted_passing_measurements(context, runtime=runtime))
    service = EvidencePackageService(dataset_registry=_dataset_registry(context))
    worker = _worker(context, runtime, executor, evidence_service=service)
    assert (await worker.run_once(limit=1))[0].status == "PASSED"

    async with database.async_session_maker() as session:
        package = await session.scalar(
            select(ResearchEvidencePackage).where(
                ResearchEvidencePackage.command_id == command["id"]
            )
        )
        assert package is not None
        candidate_id = package.candidate_id
        policy_version = package.promotion_policy_version
        gate_input_hash = package.gate_input_evidence_hash
        manifest_hash = package.manifest_hash

    from app.services.research import promotion

    current = dict(promotion._SERVER_POLICY_CATALOG[policy_version])
    monkeypatch.setitem(
        promotion._SERVER_POLICY_CATALOG,
        policy_version,
        {**current, "max_drawdown": float(current["max_drawdown"]) - 0.01},
    )
    async with database.async_session_maker() as session:
        with pytest.raises(
            ValueError,
            match="^APPROVAL_EVIDENCE_PACKAGE_UNVERIFIABLE$",
        ):
            await service.validate_for_approval_in_session(
                session,
                candidate_id=candidate_id,
                promotion_policy_version=policy_version,
                gate_input_evidence_hash=gate_input_hash,
                evidence_package_hash=manifest_hash,
            )


@pytest.mark.asyncio
async def test_two_workers_converge_on_one_external_dispatch_and_one_package(
    client,
    auth_user,
) -> None:
    context, _command, runtime = await _queued_context(client, auth_user, "worker-race")
    executor = _Executor(await _trusted_passing_measurements(context, runtime=runtime))
    first = _worker(context, runtime, executor)
    second = _worker(context, runtime, executor)

    await asyncio.gather(first.run_once(limit=1), second.run_once(limit=1))

    assert executor.execute_calls == 1
    assert await _count(ResearchEvidencePackage) == 1


@pytest.mark.asyncio
async def test_rejected_holdout_settles_without_approval_package(client, auth_user) -> None:
    context, command, runtime = await _queued_context(client, auth_user, "worker-reject")
    executor = _Executor(await _trusted_rejecting_measurements(context))
    worker = _worker(context, runtime, executor)

    results = await worker.run_once(limit=1)

    assert [(result.command_id, result.status) for result in results] == [
        (command["id"], "REJECTED")
    ]
    assert await _count(ResearchEvidencePackage) == 0


@pytest.mark.asyncio
async def test_worker_rejects_gate_status_inconsistent_with_safe_threshold_metric(
    client,
    auth_user,
) -> None:
    context, command, runtime = await _queued_context(
        client,
        auth_user,
        "worker-threshold-tamper",
    )
    executor = _ThresholdInconsistentExecutor(
        await _trusted_passing_measurements(context, runtime=runtime)
    )

    results = await _worker(context, runtime, executor).run_once(limit=1)

    assert [(item.status, item.error_code) for item in results] == [
        ("FAILED", "PROMOTION_EVALUATOR_RECEIPT_INVALID")
    ]
    assert await _count(ResearchEvidencePackage) == 0
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, command["id"])
    assert stored is not None and stored.status == "RUNNING"


@pytest.mark.asyncio
async def test_dispatch_ack_unknown_is_inspected_and_never_dispatched_twice(
    client,
    auth_user,
) -> None:
    context, command, runtime = await _queued_context(client, auth_user, "worker-unknown")
    executor = _Executor(
        await _trusted_passing_measurements(context, runtime=runtime),
        fail_after_dispatch=True,
    )
    worker = _worker(context, runtime, executor)

    first = await worker.run_once(limit=1)
    assert [(item.status, item.error_code) for item in first] == [
        ("UNKNOWN", "HOLDOUT_HTTP_EXECUTOR_TIMEOUT")
    ]
    async with database.async_session_maker() as session:
        fenced = await session.get(ResearchHoldoutEvaluationCommand, command["id"])
    assert fenced is not None and fenced.status == "RECONCILING"
    assert fenced.error_code == "HOLDOUT_EXECUTION_OUTCOME_UNKNOWN"
    assert fenced.lease_owner is None

    executor.fail_after_dispatch = False
    second = await worker.run_once(limit=1)

    assert [(item.command_id, item.status) for item in second] == [(command["id"], "PASSED")]
    assert executor.execute_calls == 1
    assert executor.inspect_calls == 1
    assert await _count(ResearchEvidencePackage) == 1


@pytest.mark.asyncio
async def test_dispatch_ack_unapplied_reuses_same_operation_only_after_not_executed(
    client,
    auth_user,
) -> None:
    context, command, runtime = await _queued_context(client, auth_user, "worker-unapplied")
    executor = _Executor(
        await _trusted_passing_measurements(context, runtime=runtime),
        fail_before_apply=True,
    )
    worker = _worker(context, runtime, executor)

    first = await worker.run_once(limit=1)
    assert [(item.status, item.error_code) for item in first] == [
        ("UNKNOWN", "HOLDOUT_HTTP_EXECUTOR_TIMEOUT")
    ]
    repeated_unknown = await worker.run_once(limit=1)
    assert [(item.status, item.error_code) for item in repeated_unknown] == [
        ("UNKNOWN", "HOLDOUT_HTTP_EXECUTOR_TIMEOUT")
    ]
    executor.fail_before_apply = False
    completed = await worker.run_once(limit=1)

    assert [(item.command_id, item.status) for item in completed] == [(command["id"], "PASSED")]
    assert executor.execute_calls == 3
    assert executor.inspect_calls == 2
    assert (
        executor.observed_command.snapshot["operation_id"]
        == hashlib.sha256(f"holdout-operation:{command['id']}".encode()).hexdigest()
    )


@pytest.mark.asyncio
async def test_cross_worker_crash_after_prepare_waits_for_expiry_and_proves_not_executed(
    client,
    auth_user,
) -> None:
    context, command_model, runtime = await _queued_context(
        client,
        auth_user,
        "worker-prepared-crash",
    )
    executor = _Executor(await _trusted_passing_measurements(context, runtime=runtime))
    original = _worker(
        context,
        runtime,
        executor,
        claim_service=HoldoutClaimService(
            dataset_registry=_dataset_registry(context),
            lease_seconds=1,
        ),
    )
    claimed = await original._claims.claim(command_id=command_model["id"], runtime=runtime)
    command = await original._execution_command(claimed.command_id)
    await original._journal.prepare(
        user_id=context["candidate"].user_id,
        lease_owner=runtime.worker_identity,
        command=command,
    )

    recovery_runtime = replace(runtime, worker_identity="holdout-prepared-recovery-worker")
    recovery = _worker(context, recovery_runtime, executor)
    waiting = await recovery.run_once(limit=1)
    assert [(item.status, item.error_code) for item in waiting] == [
        ("WAITING", "HOLDOUT_WORKER_FOREIGN_ACTIVE_LEASE")
    ]
    assert executor.execute_calls == 0
    await asyncio.sleep(1.1)

    completed = await recovery.run_once(limit=1)

    assert [(item.status, item.error_code) for item in completed] == [("PASSED", None)]
    assert executor.inspect_calls == 1
    assert executor.execute_calls == 1
    assert executor.observed_command.snapshot["operation_id"] == command.snapshot["operation_id"]


@pytest.mark.asyncio
async def test_cross_worker_crash_after_checkpoint_recovers_without_redispatch(
    client,
    auth_user,
) -> None:
    context, command, runtime = await _queued_context(client, auth_user, "worker-checkpoint-crash")
    executor = _Executor(await _trusted_passing_measurements(context, runtime=runtime))
    crashed = _worker(
        context,
        runtime,
        executor,
        claim_service=HoldoutClaimService(
            dataset_registry=_dataset_registry(context),
            lease_seconds=1,
        ),
        finalize_service=_CrashAfterCheckpointFinalizer(),
    )

    assert (await crashed.run_once(limit=1))[0].status == "FAILED"
    assert await _count(ResearchHoldoutArtifactBinding) == 1
    await asyncio.sleep(1.1)
    recovery = _worker(
        context,
        replace(runtime, worker_identity="checkpoint-recovery-worker"),
        executor,
    )

    completed = await recovery.run_once(limit=1)

    assert [(item.status, item.error_code) for item in completed] == [("PASSED", None)]
    assert executor.execute_calls == 1
    assert await _count(ResearchEvidencePackage) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("crash_point", ("finalize", "package"))
async def test_terminal_crash_rebuilds_or_reuses_unique_package_and_settles(
    client,
    auth_user,
    crash_point: str,
) -> None:
    context, command, runtime = await _queued_context(
        client,
        auth_user,
        f"worker-{crash_point}-crash",
    )
    executor = _Executor(await _trusted_passing_measurements(context, runtime=runtime))
    datasets = _dataset_registry(context)
    crashed = _worker(
        context,
        runtime,
        executor,
        finalize_service=(_CrashAfterFinalizeFinalizer() if crash_point == "finalize" else None),
        evidence_service=(
            _CrashAfterPackageEvidenceService(dataset_registry=datasets)
            if crash_point == "package"
            else None
        ),
    )

    assert (await crashed.run_once(limit=1))[0].status == "FAILED"
    recovery = _worker(context, runtime, executor)
    completed = await recovery.run_once(limit=1)

    assert [(item.status, item.error_code) for item in completed] == [("PASSED", None)]
    assert executor.execute_calls == 1
    assert await _count(ResearchEvidencePackage) == 1


@pytest.mark.asyncio
async def test_cross_worker_observed_recovery_from_unknown_never_redispatches(
    client,
    auth_user,
) -> None:
    context, command, runtime = await _queued_context(client, auth_user, "worker-recovery")
    executor = _Executor(
        await _trusted_passing_measurements(context, runtime=runtime),
        fail_after_dispatch=True,
    )
    original = _worker(context, runtime, executor)
    assert (await original.run_once(limit=1))[0].status == "UNKNOWN"

    executor.fail_after_dispatch = False
    recovery_runtime = replace(runtime, worker_identity="holdout-recovery-worker-2")
    recovery = _worker(context, recovery_runtime, executor)
    completed = await recovery.run_once(limit=1)
    assert [(item.status, item.error_code) for item in completed] == [("PASSED", None)]
    assert executor.execute_calls == 1
    assert executor.inspect_calls == 1
    assert await _count(ResearchEvidencePackage) == 1


@pytest.mark.asyncio
async def test_worker_heartbeats_while_remote_evaluator_is_running(client, auth_user) -> None:
    context, _command, runtime = await _queued_context(client, auth_user, "worker-heartbeat")
    executor = _Executor(
        await _trusted_rejecting_measurements(context),
        delay_seconds=0.05,
    )
    claims = _HeartbeatCountingClaimService(dataset_registry=_dataset_registry(context))
    worker = _worker(context, runtime, executor, claim_service=claims)

    await worker.run_once(limit=1)

    assert claims.heartbeat_calls >= 1


async def _count(model) -> int:
    async with database.async_session_maker() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)
