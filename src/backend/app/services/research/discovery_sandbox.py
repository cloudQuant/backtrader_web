"""Fenced non-sealed execution of a server-materialized mutable candidate.

The separately deployed runner must resolve the opaque, content-addressed
inputs under its own storage credentials. This service never executes code,
starts host subprocesses, mounts a Docker socket, or grants holdout access.
"""

from __future__ import annotations

import asyncio
from asyncio import wait_for as _wait_for
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchCandidate,
    ResearchDatasetSnapshot,
    ResearchExperimentEpoch,
    ResearchGenerationMaterialization,
    ResearchQuotaBucket,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
)
from app.services.research.candidate_registry import verify_candidate_integrity
from app.services.research.canonical import content_hash
from app.services.research.capabilities import evaluate_capabilities
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.database_clock import database_utc_now
from app.services.research.dataset_registry import (
    DatasetRegistry,
    require_verified_snapshot_integrity,
)
from app.services.research.discovery_execution_contract import (
    DiscoveryExecutionCommand,
    DiscoveryExecutionResult,
)
from app.services.research.discovery_execution_journal import DiscoveryExecutionJournal
from app.services.research.quota import (
    QuotaDispatchRequirement,
    QuotaReservationRequest,
    QuotaService,
    QuotaSettlementRequest,
)
from app.services.research.sandbox_runner import SandboxPolicy
from app.services.research.stage_attempt import _require_bound_output_artifact
from app.services.research.workflow_worker import StageExecutionContext

_STAGE = "VALIDATE_DISCOVERY"


class DiscoveryRemoteExecutor(Protocol):
    """The remote execution boundary; no local or generated fallback is allowed."""

    async def run(self, command: DiscoveryExecutionCommand) -> DiscoveryExecutionResult:
        """Return one command-bound, observed remote result."""


@dataclass(frozen=True, slots=True)
class DiscoveryDispatchResult:
    """Persisted execution evidence; not a stage, trial, freeze, or gate decision."""

    command: DiscoveryExecutionCommand
    result: DiscoveryExecutionResult
    journal_id: str


class DiscoverySandboxService:
    """Own discovery input selection, quota, once-only dispatch, and evidence retention."""

    def __init__(
        self,
        *,
        executor: DiscoveryRemoteExecutor,
        dataset_registry: DatasetRegistry,
        policy: SandboxPolicy,
        runner_identity: str,
        quota_policy_version: str,
        quota_lease_seconds: int,
    ) -> None:
        if (
            not callable(getattr(executor, "run", None))
            or not isinstance(dataset_registry, DatasetRegistry)
            or type(policy) is not SandboxPolicy
            or type(quota_lease_seconds) is not int
            or type(policy.wall_timeout_seconds) is not int
            or quota_lease_seconds < policy.wall_timeout_seconds + 120
            or not isinstance(runner_identity, str)
            or not runner_identity.strip()
            or not isinstance(quota_policy_version, str)
            or not quota_policy_version.strip()
        ):
            raise ValueError("DISCOVERY_DEPLOYMENT_POLICY_INVALID")
        self._executor = executor
        self._datasets = dataset_registry
        self._policy = policy
        self._runner_identity = runner_identity
        self._quota_policy_version = quota_policy_version
        self._quota_lease_seconds = quota_lease_seconds
        self._quota = QuotaService()
        self._journal = DiscoveryExecutionJournal()

    async def execute(self, context: StageExecutionContext) -> DiscoveryDispatchResult:
        """Execute a mutable candidate only on its original non-sealed dataset.

        Known remote results are retained before checking whether the task is
        still permitted to consume them. Unknown outcomes keep the reservation
        in flight; no retry or automatic release is attempted here.
        """

        inputs = await self._inputs(context)
        # Validate all content before reserving anything. Dynamic quota fields
        # are deliberately excluded from the intent hash to avoid a cycle.
        DiscoveryExecutionCommand.from_mapping(
            {
                **inputs,
                "operation_id": "preflight",
                "quota": {"reservation_id": "pending", "fencing_token": 1},
            }
        )
        intent = {"schema_version": "discovery-execution-intent-v1", "inputs": inputs}
        intent_hash = content_hash(intent)
        bucket_id = await self._bucket(context.user_id)
        receipts = await self._quota.reserve(
            task_id=context.task_id,
            stage_attempt_id=context.stage_attempt_id,
            policy_version=self._quota_policy_version,
            idempotency_key=f"discovery:{context.stage_attempt_id}",
            request_hash=intent_hash,
            reservation_context=intent,
            requests=(
                QuotaReservationRequest(
                    bucket_id=bucket_id,
                    resource_type="sandbox_seconds",
                    unit="seconds",
                    amount=self._policy.wall_timeout_seconds,
                ),
            ),
            lease_seconds=self._quota_lease_seconds,
            trace_id=context.trace_id,
        )
        if len(receipts) != 1:
            raise ValueError("DISCOVERY_QUOTA_RECEIPT_INVALID")
        receipt = receipts[0]
        operation_id = f"discovery:{receipt.reservation_id}:{receipt.fencing_token}"
        command = DiscoveryExecutionCommand.from_mapping(
            {
                **inputs,
                "operation_id": operation_id,
                "quota": {
                    "reservation_id": receipt.reservation_id,
                    "fencing_token": receipt.fencing_token,
                },
            }
        )
        journal = await self._journal.prepare(user_id=context.user_id, command=command)
        if await self._inputs(context) != inputs:
            raise ValueError("DISCOVERY_INPUT_DRIFT")
        if not await self._quota.claim_external_dispatch_bundle(
            (
                QuotaDispatchRequirement(
                    reservation_id=receipt.reservation_id,
                    fencing_token=receipt.fencing_token,
                    resource_type="sandbox_seconds",
                    unit="seconds",
                    reserved_amount=self._policy.wall_timeout_seconds,
                    request_hash=intent_hash,
                    require_reservation_context=True,
                    reservation_context_schema="discovery-execution-intent-v1",
                    minimum_remaining_seconds=self._policy.wall_timeout_seconds + 90,
                ),
            ),
            provider_operation_id=operation_id,
            task_id=context.task_id,
            run_id=context.run_id,
            stage_attempt_id=context.stage_attempt_id,
            lease_token=context.lease_token,
            stage=_STAGE,
        ):
            raise ValueError("DISCOVERY_DISPATCH_ALREADY_CLAIMED")
        # Claim can wait on another transaction. A changed policy, candidate,
        # dataset or capability must still deny the actual outbound operation.
        # Bound this final check within the wall+90 quota cushion; the remote
        # deadline is wall+60, leaving time for journaling. No retry on timeout.
        try:
            final_inputs = await asyncio.wait_for(self._inputs(context), timeout=10)
        except TimeoutError:
            raise ValueError("DISCOVERY_PREDISPATCH_REVALIDATION_TIMEOUT") from None
        if final_inputs != inputs:
            raise ValueError("DISCOVERY_INPUT_DRIFT")
        try:
            observed = await _wait_for(
                self._executor.run(command), timeout=self._policy.wall_timeout_seconds + 60
            )
            if type(observed) is not DiscoveryExecutionResult:
                raise ValueError("DISCOVERY_EXECUTION_RESULT_INVALID")
            result = DiscoveryExecutionResult.from_mapping(observed.snapshot, command=command)
        except asyncio.CancelledError:
            await asyncio.shield(
                self._journal.record_unknown(
                    user_id=context.user_id,
                    command=command,
                    error_code="DISCOVERY_CALL_CANCELLED",
                )
            )
            raise
        except Exception:
            await self._journal.record_unknown(
                user_id=context.user_id,
                command=command,
                error_code="DISCOVERY_REMOTE_OUTCOME_UNKNOWN",
            )
            raise ValueError("DISCOVERY_REMOTE_OUTCOME_UNKNOWN") from None
        await self._journal.record_result(user_id=context.user_id, command=command, result=result)
        if await self._inputs(context) != inputs:
            raise ValueError("DISCOVERY_INPUT_DRIFT")
        # Round wall usage upward, preserving a minimum unit for a dispatched
        # request. This is sandbox-seconds accounting, never a market result.
        used_seconds = max(1, (result.snapshot["elapsed_milliseconds"] + 999) // 1000)
        if not await self._quota.settle_bundle(
            (
                QuotaSettlementRequest(
                    reservation_id=receipt.reservation_id,
                    fencing_token=receipt.fencing_token,
                    settled_amount=used_seconds,
                ),
            ),
            provider_operation_id=operation_id,
        ):
            raise ValueError("DISCOVERY_QUOTA_SETTLEMENT_FAILED")
        return DiscoveryDispatchResult(command=command, result=result, journal_id=journal.id)

    async def _inputs(self, context: StageExecutionContext) -> dict[str, Any]:
        if type(context) is not StageExecutionContext or context.stage != _STAGE:
            raise ValueError("DISCOVERY_STAGE_CONTEXT_INVALID")
        async with database.async_session_maker() as session:
            task, run = await _load_live_context(session, context)
            relations = list(
                (
                    await session.scalars(
                        select(ResearchGenerationMaterialization)
                        .where(ResearchGenerationMaterialization.task_id == task.id)
                        .limit(2)
                    )
                ).all()
            )
            if not relations:
                raise ValueError("DISCOVERY_GENERATION_MATERIALIZATION_REQUIRED")
            if len(relations) != 1:
                raise ValueError("DISCOVERY_GENERATION_MATERIALIZATION_AMBIGUOUS")
            relation = relations[0]
            if relation.user_id != context.user_id or relation.run_id != run.id:
                raise ValueError("DISCOVERY_CANDIDATE_BINDING_DENIED")
            generated = await session.get(ResearchStageAttempt, relation.stage_attempt_id)
            candidate = await session.get(ResearchCandidate, relation.candidate_id)
            if (
                generated is None
                or generated.status != "SUCCEEDED"
                or generated.stage != "GENERATE"
                or generated.task_id != task.id
                or generated.run_id != run.id
                or generated.output_artifact_id != relation.manifest_artifact_id
                or candidate is None
                or candidate.user_id != context.user_id
                or candidate.run_id != run.id
                or candidate.freeze_status != "MUTABLE"
            ):
                raise ValueError("DISCOVERY_CANDIDATE_BINDING_DENIED")
            await _require_bound_output_artifact(
                session, task, generated, relation.manifest_artifact_id
            )
            await verify_candidate_integrity(session, candidate)
            epoch = await session.get(ResearchExperimentEpoch, candidate.experiment_epoch_id)
            dataset = await session.get(ResearchDatasetSnapshot, candidate.dataset_snapshot_id)
            if (
                epoch is None
                or epoch.status != "OPEN"
                or epoch.selected_candidate_id is not None
                or dataset is None
                or dataset.partition_kind not in {"DISCOVERY", "ITERATION_VALIDATION"}
            ):
                raise ValueError("DISCOVERY_PARTITION_OR_EPOCH_DENIED")
            try:
                await self._datasets.revalidate_snapshot_in_session(session, snapshot=dataset)
            except ValueError:
                if dataset.integrity_status == "FAILED":
                    await session.commit()
                else:
                    await session.rollback()
                raise
            await session.commit()
            require_verified_snapshot_integrity(dataset)
            artifacts = {}
            for name, artifact_id in (
                ("code", candidate.code_artifact_id),
                ("dependencies", candidate.dependency_artifact_id),
            ):
                artifact = await session.get(ResearchArtifact, artifact_id)
                blob = await session.get(ResearchArtifactContent, artifact_id)
                if (
                    artifact is None
                    or blob is None
                    or type(blob.content) is not bytes
                    or len(blob.content) != artifact.size_bytes
                    or sha256(blob.content).hexdigest() != artifact.content_hash
                ):
                    raise ValueError("DISCOVERY_ARTIFACT_CONTENT_INVALID")
                artifacts[name] = {
                    "artifact_id": artifact.id,
                    "content_hash": artifact.content_hash,
                    "size_bytes": artifact.size_bytes,
                }
            profile = await CapabilityRegistry().get(
                run.capability_profile_id, run.capability_profile_version
            )
            # Resolver/profile I/O may have outlived a lease or cancellation.
            # Re-read durable state instead of trusting the earlier ORM cache.
            task, run = await _load_live_context(session, context)
            now = await database_utc_now(session)
            if (
                profile is None
                or profile.profile_id != run.capability_profile_id
                or profile.version != run.capability_profile_version
                or profile.evidence_hash != run.capability_evidence_hash
                or profile.service_identities.get("runner") != self._runner_identity
                or not profile.service_identities.get("explorer")
                or profile.service_identities.get("explorer") == self._runner_identity
                or not profile.queue_isolation
                or not profile.storage_isolation
                or not profile.network_isolation
                or not evaluate_capabilities(profile, required=("sandbox",), now=now).allowed
            ):
                raise ValueError("DISCOVERY_RUNNER_CAPABILITY_DENIED")
            return {
                "schema_version": "discovery-execution-command-v1",
                "stage": _STAGE,
                "task_id": task.id,
                "run_id": run.id,
                "stage_attempt_id": context.stage_attempt_id,
                "candidate_id": candidate.id,
                "candidate_hash": candidate.candidate_hash,
                "run_request_hash": run.request_hash,
                "lease_token_hash": sha256(context.lease_token.encode("utf-8")).hexdigest(),
                "environment_hash": candidate.environment_hash,
                "cost_model_hash": candidate.cost_model_hash,
                "runner_identity": self._runner_identity,
                "profile": {
                    "id": profile.profile_id,
                    "version": profile.version,
                    "evidence_hash": profile.evidence_hash,
                },
                **artifacts,
                "dataset": {
                    "snapshot_id": dataset.id,
                    "snapshot_identity_hash": dataset.snapshot_identity_hash,
                    "object_receipt_id": dataset.object_receipt_id,
                    "object_digest": dataset.object_digest,
                    "object_size_bytes": dataset.object_size_bytes,
                    "partition_kind": dataset.partition_kind,
                },
                "params": dict(candidate.params),
                "execution_policy": dict(dataset.execution_policy),
                "policy": asdict(self._policy),
            }

    async def _bucket(self, user_id: str) -> str:
        async with database.async_session_maker() as session:
            now = await database_utc_now(session)
            buckets = list(
                (
                    await session.scalars(
                        select(ResearchQuotaBucket).where(
                            ResearchQuotaBucket.scope_type == "user",
                            ResearchQuotaBucket.scope_id == user_id,
                            ResearchQuotaBucket.policy_version == self._quota_policy_version,
                            ResearchQuotaBucket.resource_type == "sandbox_seconds",
                            ResearchQuotaBucket.status == "ACTIVE",
                            ResearchQuotaBucket.window_start <= now,
                            ResearchQuotaBucket.window_end > now,
                        )
                    )
                ).all()
            )
            if len(buckets) != 1:
                raise ValueError("DISCOVERY_QUOTA_BUCKET_UNAVAILABLE")
            return buckets[0].id


async def _load_live_context(
    session: AsyncSession, context: StageExecutionContext
) -> tuple[ResearchTask, ResearchRun]:
    task = await session.get(ResearchTask, context.task_id, populate_existing=True)
    run = await session.get(ResearchRun, context.run_id, populate_existing=True)
    attempt = await session.get(
        ResearchStageAttempt, context.stage_attempt_id, populate_existing=True
    )
    now = await database_utc_now(session)
    if (
        task is None
        or run is None
        or attempt is None
        or task.user_id != context.user_id
        or run.user_id != context.user_id
        or task.run_id != run.id
        or run.request_hash != context.request_hash
        or task.status != "RUNNING"
        or run.status != "RUNNING"
        or task.stage_cursor != _STAGE
        or run.stage_cursor != _STAGE
        or task.lease_token != context.lease_token
        or task.cancel_requested_at is not None
        or task.lease_expires_at is None
        or _stored_utc(task.lease_expires_at) <= now
        or attempt.task_id != task.id
        or attempt.run_id != run.id
        or attempt.stage != _STAGE
        or attempt.status != "RUNNING"
        or attempt.lease_token != context.lease_token
    ):
        raise ValueError("DISCOVERY_CONTEXT_DENIED")
    return task, run


def _stored_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo from UTC database columns; never use local timezone."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
