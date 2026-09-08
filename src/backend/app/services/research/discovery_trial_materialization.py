"""Publish journal-bound discovery evidence into the append-only trial ledger."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchCandidate,
    ResearchDatasetSnapshot,
    ResearchDiscoveryExecution,
    ResearchQuotaReservation,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTrial,
)
from app.services.research.artifact_broker import ArtifactBroker, StageOutputContext
from app.services.research.candidate_registry import verify_candidate_integrity
from app.services.research.canonical import canonical_json, content_hash
from app.services.research.database_clock import DatabaseUtcNow
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.discovery_execution_contract import (
    DiscoveryExecutionCommand,
    DiscoveryExecutionResult,
)
from app.services.research.discovery_execution_journal import (
    _require_candidate_inputs,
    _require_owner_command,
    _require_recorded_dispatch,
)
from app.services.research.discovery_search_budget import lock_search_epoch
from app.services.research.experiment_ledger import ExperimentLedger


@dataclass(frozen=True, slots=True)
class DiscoveryTrialPublication:
    """Evidence identifiers, not a candidate freeze or successful stage."""

    execution_id: str
    trial_id: str
    output_artifact_id: str
    status: str
    error_code: str | None


class DiscoveryTrialMaterializer:
    """Derive one trial and retained returns only from a dispatched journal."""

    def __init__(self, *, dataset_registry: DatasetRegistry) -> None:
        if not isinstance(dataset_registry, DatasetRegistry):
            raise ValueError("DISCOVERY_PUBLICATION_DATASET_REGISTRY_REQUIRED")
        self._datasets = dataset_registry

    async def publish_in_session(
        self,
        session: AsyncSession,
        *,
        context: StageOutputContext,
        execution_id: str,
    ) -> DiscoveryTrialPublication:
        """Stage a trial, artifact, binding and journal link atomically.

        The caller owns commit/rollback and eventual stage completion. No HTTP,
        new execution, candidate freeze, or statistical metric is synthesized.
        Late or cancelled work retains its original journal for reconciliation
        but cannot publish through this live-stage path.
        """
        epoch = await lock_search_epoch(session, user_id=context.user_id, run_id=context.run_id)
        task, run, attempt = await _live_context(session, context, epoch.id)
        journal = await session.scalar(
            select(ResearchDiscoveryExecution)
            .where(
                ResearchDiscoveryExecution.id == execution_id,
                ResearchDiscoveryExecution.user_id == context.user_id,
            )
            .with_for_update()
        )
        if journal is None or (
            journal.status != "OBSERVED"
            or journal.search_epoch_id != epoch.id
            or type(journal.search_ordinal) is not int
            or journal.search_ordinal < 1
            or journal.search_budget_hash != content_hash(epoch.search_budget)
            or journal.run_id != run.id
            or journal.task_id != task.id
            or journal.stage_attempt_id != attempt.id
        ):
            raise ValueError("DISCOVERY_PUBLICATION_EVIDENCE_DENIED")
        command = DiscoveryExecutionCommand.from_mapping(journal.command_json)
        snapshot = command.snapshot
        _require_owner_command(
            journal,
            user_id=context.user_id,
            command=command,
            denied_code="DISCOVERY_PUBLICATION_EVIDENCE_DENIED",
            conflict_code="DISCOVERY_PUBLICATION_EVIDENCE_DENIED",
        )
        if snapshot["lease_token_hash"] != sha256(context.lease_token.encode()).hexdigest() or (
            snapshot["run_request_hash"] != run.request_hash
            or snapshot["profile"]
            != {
                "id": run.capability_profile_id,
                "version": run.capability_profile_version,
                "evidence_hash": run.capability_evidence_hash,
            }
        ):
            raise ValueError("DISCOVERY_PUBLICATION_EVIDENCE_DENIED")
        result = DiscoveryExecutionResult.from_mapping(journal.result_json, command=command)
        await _require_recorded_dispatch(
            session,
            record=journal,
            command=command,
            denied_code="DISCOVERY_PUBLICATION_QUOTA_DENIED",
        )
        quota = await session.get(ResearchQuotaReservation, journal.quota_reservation_id)
        intent = {
            "schema_version": "discovery-execution-intent-v1",
            "inputs": {
                key: value
                for key, value in snapshot.items()
                if key not in {"operation_id", "quota"}
            },
        }
        if (
            quota.status != "SETTLED"
            or quota.task_id != task.id
            or quota.stage_attempt_id != attempt.id
            or quota.fencing_token != snapshot["quota"]["fencing_token"]
            or quota.resource_type != "sandbox_seconds"
            or quota.unit != "seconds"
            or quota.reserved_amount < snapshot["policy"]["wall_timeout_seconds"]
            or quota.request_hash != content_hash(intent)
            or canonical_json(quota.reservation_context) != canonical_json(intent)
            or quota.settled_amount
            != max(1, (result.snapshot["elapsed_milliseconds"] + 999) // 1000)
        ):
            raise ValueError("DISCOVERY_PUBLICATION_QUOTA_DENIED")
        candidate = await session.get(
            ResearchCandidate, journal.candidate_id, populate_existing=True, with_for_update=True
        )
        if candidate is None or (
            candidate.user_id != context.user_id
            or candidate.run_id != run.id
            or candidate.experiment_epoch_id != epoch.id
            or candidate.freeze_status != "MUTABLE"
            or candidate.dataset_snapshot_id != run.dataset_snapshot_id
            or candidate.candidate_hash != snapshot["candidate_hash"]
            or candidate.environment_hash != snapshot["environment_hash"]
            or candidate.cost_model_hash != snapshot["cost_model_hash"]
            or canonical_json(candidate.params) != canonical_json(snapshot["params"])
        ):
            raise ValueError("DISCOVERY_PUBLICATION_CANDIDATE_DENIED")
        await verify_candidate_integrity(session, candidate)
        await _require_candidate_inputs(
            session, candidate=candidate, snapshot=snapshot, user_id=context.user_id
        )
        dataset = await session.get(ResearchDatasetSnapshot, candidate.dataset_snapshot_id)
        await self._datasets.revalidate_snapshot_in_session(session, snapshot=dataset)
        for key in ("code", "dependencies"):
            artifact = snapshot[key]
            blob = await session.get(ResearchArtifactContent, artifact["artifact_id"])
            if (
                blob is None
                or len(blob.content) != artifact["size_bytes"]
                or (sha256(blob.content).hexdigest() != artifact["content_hash"])
            ):
                raise ValueError("DISCOVERY_PUBLICATION_CONTENT_DENIED")
        payload = _evidence_payload(journal.id, command, result)
        artifact = await ArtifactBroker().register_stage_output_in_session(
            session,
            context=context,
            kind="discovery_trial_evidence",
            content=payload,
            media_type="application/json",
            schema_version="discovery-trial-evidence-v1",
            producer_identity=snapshot["runner_identity"],
            container_image_digest=snapshot["policy"]["image_digest"],
        )
        evidence = result.snapshot
        observed = evidence["observed_market_performance"]
        trial = await ExperimentLedger().record_trial_in_session(
            session,
            user_id=context.user_id,
            run_id=run.id,
            candidate_id=candidate.id,
            idempotency_key=f"discovery:{journal.id}",
            stage="VALIDATE_DISCOVERY",
            status=evidence["status"],
            input_hash=command.request_hash,
            metrics={"sample_count": len(evidence["returns"]), "execution_id": journal.id},
            observed_market_performance=observed,
            counts_as_market_trial=observed,
            counting_reason=(
                "OBSERVED_DISCOVERY_EXECUTION" if observed else "NO_MARKET_RESULT_OBSERVED"
            ),
            error_code=evidence["error_code"],
            returns_artifact_id=artifact.id,
        )
        if journal.trial_id is not None and journal.trial_id != trial.id:
            raise ValueError("DISCOVERY_PUBLICATION_TRIAL_CONFLICT")
        # No independent commit: even the final database-clock rejection rolls
        # back the new trial, retained bytes and binding together.
        await _live_context(session, context, epoch.id)
        journal.trial_id = trial.id
        await session.flush()
        return DiscoveryTrialPublication(
            journal.id, trial.id, artifact.id, evidence["status"], evidence["error_code"]
        )


def _evidence_payload(
    execution_id: str, command: DiscoveryExecutionCommand, result: DiscoveryExecutionResult
) -> bytes:
    snapshot = command.snapshot
    return canonical_json(
        {
            "schema_version": "discovery-trial-evidence-v1",
            "execution_id": execution_id,
            "command_hash": command.request_hash,
            "candidate_id": snapshot["candidate_id"],
            "candidate_hash": snapshot["candidate_hash"],
            "dataset": snapshot["dataset"],
            "result": result.snapshot,
        }
    ).encode("utf-8")


async def replay_discovery_publication(
    session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    attempt: ResearchStageAttempt,
    execution_id: str | None = None,
) -> DiscoveryTrialPublication:
    """Read an exact completed receipt; never republish or execute on recovery.

    A new lease may adopt old evidence only through this read-only path. Mutable
    candidate/epoch policy is deliberately not reinterpreted as a fresh execution.
    """
    try:
        return await _replay_discovery_publication(
            session,
            task=task,
            run=run,
            attempt=attempt,
            execution_id=execution_id,
        )
    except ValueError:
        # Recovery is a trust boundary. Do not leak which stored identity was
        # corrupt, and never let a lower-level validation code become a second
        # adoption path for incomplete evidence.
        raise ValueError("DISCOVERY_PUBLICATION_REPLAY_DENIED") from None


async def _replay_discovery_publication(
    session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    attempt: ResearchStageAttempt,
    execution_id: str | None,
) -> DiscoveryTrialPublication:
    """Validate the persisted publication against current authoritative inputs."""

    denied = "DISCOVERY_PUBLICATION_REPLAY_DENIED"
    current_run = await session.get(ResearchRun, run.id, populate_existing=True)
    if current_run is None or current_run.id != run.id:
        raise ValueError(denied)
    run = current_run
    journal = await session.scalar(
        select(ResearchDiscoveryExecution).where(
            ResearchDiscoveryExecution.stage_attempt_id == attempt.id,
            ResearchDiscoveryExecution.user_id == task.user_id,
        ).execution_options(populate_existing=True)
    )
    if journal is None or (
        (execution_id is not None and journal.id != execution_id)
        or journal.status != "OBSERVED"
        or journal.trial_id is None
        or journal.run_id != run.id
        or journal.task_id != task.id
        or journal.search_epoch_id != run.experiment_epoch_id
        or not journal.search_budget_hash
        or not journal.search_ordinal
        or attempt.run_id != run.id
        or attempt.task_id != task.id
        or task.run_id != run.id
        or run.user_id != task.user_id
        or attempt.stage != "VALIDATE_DISCOVERY"
    ):
        raise ValueError(denied)
    command = DiscoveryExecutionCommand.from_mapping(journal.command_json)
    _require_owner_command(
        journal, user_id=task.user_id, command=command, denied_code=denied, conflict_code=denied
    )
    snapshot = command.snapshot
    if (
        not isinstance(attempt.lease_token, str)
        or snapshot["lease_token_hash"] != sha256(attempt.lease_token.encode()).hexdigest()
        or snapshot["run_request_hash"] != run.request_hash
        or snapshot["profile"]
        != {
            "id": run.capability_profile_id,
            "version": run.capability_profile_version,
            "evidence_hash": run.capability_evidence_hash,
        }
    ):
        raise ValueError(denied)
    candidate = await session.get(
        ResearchCandidate,
        journal.candidate_id,
        populate_existing=True,
    )
    if candidate is None or (
        candidate.id != journal.candidate_id
        or snapshot["candidate_id"] != candidate.id
        or snapshot["candidate_hash"] != candidate.candidate_hash
        or candidate.user_id != task.user_id
        or candidate.run_id != run.id
        or candidate.experiment_epoch_id != run.experiment_epoch_id
        or candidate.dataset_snapshot_id != run.dataset_snapshot_id
    ):
        raise ValueError(denied)
    dataset = await session.get(
        ResearchDatasetSnapshot,
        candidate.dataset_snapshot_id,
        populate_existing=True,
    )
    if dataset is None or (
        dataset.user_id != task.user_id
        or snapshot["dataset"]
        != {
            "snapshot_id": dataset.id,
            "snapshot_identity_hash": dataset.snapshot_identity_hash,
            "object_receipt_id": dataset.object_receipt_id,
            "object_digest": dataset.object_digest,
            "object_size_bytes": dataset.object_size_bytes,
            "partition_kind": dataset.partition_kind,
        }
        or canonical_json(snapshot["execution_policy"])
        != canonical_json(dataset.execution_policy)
    ):
        raise ValueError(denied)
    await verify_candidate_integrity(session, candidate)
    # Re-read and compare the current dataset/artifact identities rather than
    # treating the journal command as self-authenticating historical truth.
    await _require_candidate_inputs(
        session,
        candidate=candidate,
        snapshot=snapshot,
        user_id=task.user_id,
    )
    result = DiscoveryExecutionResult.from_mapping(journal.result_json, command=command)
    evidence = result.snapshot
    observed = evidence["observed_market_performance"]
    trial = await session.get(ResearchTrial, journal.trial_id)
    if trial is None or (
        trial.user_id != task.user_id
        or trial.run_id != run.id
        or trial.candidate_id != journal.candidate_id
        or trial.idempotency_key != f"discovery:{journal.id}"
        or trial.stage != "VALIDATE_DISCOVERY"
        or trial.input_hash != command.request_hash
        or trial.status != evidence["status"]
        or trial.error_code != evidence["error_code"]
        or trial.status != attempt.status
        or trial.error_code != attempt.error_code
        or trial.returns_artifact_id != attempt.output_artifact_id
        or trial.observed_market_performance != observed
        or trial.counts_as_market_trial != observed
        or trial.counting_reason
        != ("OBSERVED_DISCOVERY_EXECUTION" if observed else "NO_MARKET_RESULT_OBSERVED")
        or trial.metrics != {"sample_count": len(evidence["returns"]), "execution_id": journal.id}
        or trial.parent_trial_id is not None
    ):
        raise ValueError(denied)
    artifact = await session.get(ResearchArtifact, trial.returns_artifact_id)
    blob = await session.get(ResearchArtifactContent, trial.returns_artifact_id)
    payload = _evidence_payload(journal.id, command, result)
    if (
        artifact is None
        or blob is None
        or (
            bytes(blob.content) != payload
            or artifact.content_hash != sha256(payload).hexdigest()
            or artifact.size_bytes != len(payload)
            or artifact.kind != "discovery_trial_evidence"
            or artifact.schema_version != "discovery-trial-evidence-v1"
        )
    ):
        raise ValueError(denied)
    return DiscoveryTrialPublication(
        journal.id, trial.id, artifact.id, evidence["status"], evidence["error_code"]
    )


async def _live_context(
    session: AsyncSession, context: StageOutputContext, epoch_id: str
) -> tuple[ResearchTask, ResearchRun, ResearchStageAttempt]:
    task = await session.scalar(
        select(ResearchTask)
        .where(
            ResearchTask.id == context.task_id,
            ResearchTask.user_id == context.user_id,
            ResearchTask.run_id == context.run_id,
            ResearchTask.status == "RUNNING",
            ResearchTask.stage_cursor == "VALIDATE_DISCOVERY",
            ResearchTask.lease_token == context.lease_token,
            ResearchTask.lease_expires_at > DatabaseUtcNow(),
            ResearchTask.cancel_requested_at.is_(None),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    run = await session.scalar(
        select(ResearchRun)
        .where(
            ResearchRun.id == context.run_id,
            ResearchRun.user_id == context.user_id,
            ResearchRun.status == "RUNNING",
            ResearchRun.experiment_epoch_id == epoch_id,
            ResearchRun.request_hash == context.request_hash,
            ResearchRun.stage_cursor == "VALIDATE_DISCOVERY",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    attempt = await session.scalar(
        select(ResearchStageAttempt)
        .where(
            ResearchStageAttempt.id == context.stage_attempt_id,
            ResearchStageAttempt.task_id == context.task_id,
            ResearchStageAttempt.run_id == context.run_id,
            ResearchStageAttempt.status == "RUNNING",
            ResearchStageAttempt.stage == "VALIDATE_DISCOVERY",
            ResearchStageAttempt.lease_token == context.lease_token,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is None or task is None or attempt is None or context.stage != "VALIDATE_DISCOVERY":
        raise ValueError("DISCOVERY_PUBLICATION_CONTEXT_DENIED")
    return task, run, attempt
