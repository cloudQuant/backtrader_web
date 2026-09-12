"""Candidate identity and irreversible freeze transitions for v2 research."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchCandidate,
    ResearchCandidateFreezeReceipt,
    ResearchDatasetSnapshot,
    ResearchDiscoveryExecution,
    ResearchExperimentEpoch,
    ResearchGenerationMaterialization,
    ResearchHypothesisVersion,
    ResearchModelInvocation,
    ResearchQuotaBucket,
    ResearchQuotaReservation,
    ResearchRun,
    ResearchStageArtifactBinding,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTaskEvent,
    ResearchTrial,
)
from app.services.research.canonical import canonical_json, content_hash
from app.services.research.dataset_registry import (
    DatasetRegistry,
    require_verified_snapshot_integrity,
)
from app.services.research.discovery_search_budget import lock_search_epoch


@dataclass(frozen=True, slots=True)
class DiscoveryFreezeEvidence:
    """Server-derived immutable inputs captured by the strict freeze receipt."""

    generation_materialization_hash: str
    ledger_hash: str
    attempt_count_total: int
    market_trial_count: int
    search_budget_hash: str
    dataset_snapshot_hash: str
    dataset_snapshot_identity_hash: str
    code_hash: str
    dependency_hash: str
    hypothesis_hash: str
    environment_hash: str
    cost_model_hash: str


class CandidateRegistry:
    """Own candidate creation/freeze without granting evaluation write access."""

    def __init__(self, *, dataset_registry: DatasetRegistry | None = None) -> None:
        """Use an injected resolver-backed registry when freezing a candidate."""

        self._datasets = dataset_registry or DatasetRegistry()

    async def create_mutable(
        self,
        *,
        user_id: str,
        run_id: str,
        experiment_epoch_id: str,
        dataset_snapshot_id: str,
        code_artifact_id: str,
        dependency_artifact_id: str,
        environment_hash: str,
        cost_model_hash: str,
        params: dict[str, Any],
        source_version_id: str | None = None,
    ) -> ResearchCandidate:
        """Create a content-addressed candidate in an open experiment epoch."""

        async with database.async_session_maker() as session:
            model = await self.create_mutable_in_session(
                session,
                user_id=user_id,
                run_id=run_id,
                experiment_epoch_id=experiment_epoch_id,
                dataset_snapshot_id=dataset_snapshot_id,
                code_artifact_id=code_artifact_id,
                dependency_artifact_id=dependency_artifact_id,
                environment_hash=environment_hash,
                cost_model_hash=cost_model_hash,
                params=params,
                source_version_id=source_version_id,
            )
            await session.commit()
            await session.refresh(model)
            return model

    async def create_mutable_in_session(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        run_id: str,
        experiment_epoch_id: str,
        dataset_snapshot_id: str,
        code_artifact_id: str,
        dependency_artifact_id: str,
        environment_hash: str,
        cost_model_hash: str,
        params: dict[str, Any],
        source_version_id: str | None = None,
    ) -> ResearchCandidate:
        """Add one mutable candidate to an existing transaction without committing it.

        The caller owns the surrounding transaction and must have established any
        stronger stage/lease fence before reaching this aggregate boundary.
        """

        run = await _owner_run(session, user_id, run_id)
        epoch = await _owner_epoch(session, user_id, experiment_epoch_id)
        if run.experiment_epoch_id != epoch.id:
            raise ValueError("CANDIDATE_RUN_EPOCH_MISMATCH")
        if epoch.status != "OPEN" or epoch.selected_candidate_id is not None:
            raise ValueError("EXPERIMENT_EPOCH_CANDIDATE_LOCKED")
        dataset = await _owner_dataset(session, user_id, dataset_snapshot_id)
        code_artifact = await _artifact(session, code_artifact_id)
        dependency_artifact = await _artifact(session, dependency_artifact_id)
        hypothesis = await _owner_hypothesis(session, user_id, run.hypothesis_version_id)
        _validate_create_binding(
            run=run,
            epoch=epoch,
            dataset=dataset,
            hypothesis=hypothesis,
            code_artifact=code_artifact,
            dependency_artifact=dependency_artifact,
            environment_hash=environment_hash,
            cost_model_hash=cost_model_hash,
            params=params,
        )
        candidate_hash = candidate_identity_hash(
            run_id=run.id,
            experiment_epoch_id=epoch.id,
            hypothesis_version_id=hypothesis.id,
            hypothesis_content_hash=hypothesis.content_hash,
            dataset_snapshot_id=dataset.id,
            dataset_content_hash=dataset.content_hash,
            dataset_snapshot_identity_hash=_verified_dataset_identity_hash(dataset),
            code_artifact_id=code_artifact.id,
            code_hash=code_artifact.content_hash,
            dependency_artifact_id=dependency_artifact.id,
            dependency_hash=dependency_artifact.content_hash,
            environment_hash=environment_hash,
            cost_model_hash=cost_model_hash,
            params=params,
            source_version_id=source_version_id,
        )
        model = ResearchCandidate(
            user_id=user_id,
            run_id=run.id,
            experiment_epoch_id=epoch.id,
            source_version_id=source_version_id,
            dataset_snapshot_id=dataset.id,
            code_artifact_id=code_artifact.id,
            dependency_artifact_id=dependency_artifact.id,
            candidate_hash=candidate_hash,
            environment_hash=environment_hash,
            cost_model_hash=cost_model_hash,
            params=params,
            freeze_status="MUTABLE",
        )
        session.add(model)
        await session.flush()
        return model

    async def freeze(
        self,
        user_id: str,
        candidate_id: str,
        *,
        frozen_by: str,
        expected_candidate_hash: str,
    ) -> ResearchCandidate:
        """Freeze one proven candidate and lock its epoch selection exactly once.

        Persisted ``discovery-v1`` runs always use the strict publication gate.
        The earlier generation-only workflow retains its existing evidence
        classification for backwards compatibility; the public v2 endpoint
        calls :meth:`freeze_discovery` and cannot select that compatibility path.
        """

        return await self._freeze(
            user_id,
            candidate_id,
            frozen_by=frozen_by,
            expected_candidate_hash=expected_candidate_hash,
            require_discovery_workflow=False,
        )

    async def freeze_discovery(
        self,
        user_id: str,
        candidate_id: str,
        *,
        frozen_by: str,
        expected_candidate_hash: str,
    ) -> ResearchCandidate:
        """Freeze only a completed, fully published ``discovery-v1`` candidate."""

        return await self._freeze(
            user_id,
            candidate_id,
            frozen_by=frozen_by,
            expected_candidate_hash=expected_candidate_hash,
            require_discovery_workflow=True,
        )

    async def _freeze(
        self,
        user_id: str,
        candidate_id: str,
        *,
        frozen_by: str,
        expected_candidate_hash: str,
        require_discovery_workflow: bool,
    ) -> ResearchCandidate:
        """Apply the irreversible transition after its versioned evidence gate."""

        if not frozen_by.strip():
            raise ValueError("CANDIDATE_FREEZE_ACTOR_INVALID")
        async with database.async_session_maker() as session:
            identity = (
                await session.execute(
                    select(
                        ResearchCandidate.run_id,
                        ResearchCandidate.experiment_epoch_id,
                    ).where(
                        ResearchCandidate.id == candidate_id, ResearchCandidate.user_id == user_id
                    )
                )
            ).one_or_none()
            if identity is None:
                raise ValueError("CANDIDATE_NOT_FOUND")
            run_id, epoch_id = identity
            # Search preparation/publication also takes this real epoch write
            # lock first. The identity lookup only locates the lock target and
            # grants no authority; every binding is checked again afterwards.
            try:
                locked_epoch = await lock_search_epoch(
                    session,
                    user_id=user_id,
                    run_id=run_id,
                    require_open=False,
                )
            except ValueError:
                raise ValueError("CANDIDATE_RUN_BINDING_MISMATCH") from None
            # Keep an explicit row-lock read for databases with FOR UPDATE,
            # while the preceding no-op UPDATE is the effective SQLite lock.
            epoch = await _owner_epoch(session, user_id, locked_epoch.id)
            result = await session.execute(
                select(ResearchCandidate)
                .where(
                    ResearchCandidate.id == candidate_id,
                    ResearchCandidate.user_id == user_id,
                )
                .with_for_update()
            )
            candidate = result.scalar_one_or_none()
            if candidate is None:
                raise ValueError("CANDIDATE_NOT_FOUND")
            if (
                candidate.experiment_epoch_id != epoch.id
                or candidate.experiment_epoch_id != epoch_id
                or candidate.run_id != run_id
            ):
                raise ValueError("CANDIDATE_RUN_BINDING_MISMATCH")
            await verify_candidate_integrity(session, candidate)
            if candidate.candidate_hash != expected_candidate_hash:
                raise ValueError("CANDIDATE_FREEZE_HASH_MISMATCH")

            run = await session.get(ResearchRun, candidate.run_id, populate_existing=True)
            if run is None:
                raise ValueError("CANDIDATE_RUN_BINDING_MISMATCH")
            if require_discovery_workflow and run.workflow_version != "discovery-v1":
                raise ValueError("CANDIDATE_FREEZE_DISCOVERY_WORKFLOW_REQUIRED")
            evidence: DiscoveryFreezeEvidence | None = None
            if candidate.freeze_status == "FROZEN":
                if epoch.selected_candidate_id != candidate.id:
                    raise ValueError("CANDIDATE_FREEZE_EPOCH_INCONSISTENT")
                if run.workflow_version == "discovery-v1":
                    evidence = await _require_discovery_freeze_ready(
                        session,
                        candidate=candidate,
                        run=run,
                        epoch=epoch,
                    )
            elif epoch.status != "OPEN" or epoch.selected_candidate_id is not None:
                raise ValueError("EXPERIMENT_EPOCH_CANDIDATE_LOCKED")
            elif run.workflow_version == "discovery-v1":
                evidence = await _require_discovery_freeze_ready(
                    session,
                    candidate=candidate,
                    run=run,
                    epoch=epoch,
                )

            completed_trials = await session.scalar(
                select(func.count(ResearchTrial.id)).where(
                    ResearchTrial.user_id == candidate.user_id,
                    ResearchTrial.run_id == candidate.run_id,
                    ResearchTrial.candidate_id == candidate.id,
                    ResearchTrial.status == "SUCCEEDED",
                    ResearchTrial.observed_market_performance.is_(True),
                    ResearchTrial.counts_as_market_trial.is_(True),
                )
            )
            if int(completed_trials or 0) < 1 or (
                evidence is not None and evidence.market_trial_count < 1
            ):
                raise ValueError("CANDIDATE_FREEZE_REQUIRES_COMPLETED_TRIAL")

            dataset = await _candidate_dataset(session, candidate)
            try:
                await self._datasets.revalidate_snapshot_in_session(session, snapshot=dataset)
            except ValueError as exc:
                if require_discovery_workflow and str(exc) == "DATASET_OBJECT_RESOLVER_REQUIRED":
                    raise ValueError("CANDIDATE_FREEZE_VERIFICATION_UNAVAILABLE") from None
                raise
            require_verified_snapshot_integrity(dataset)
            if candidate.freeze_status == "FROZEN":
                if evidence is not None:
                    await _require_exact_freeze_receipt(
                        session,
                        candidate=candidate,
                        run=run,
                        epoch=epoch,
                        evidence=evidence,
                    )
                return candidate

            frozen_at = datetime.now(timezone.utc)
            candidate.freeze_status = "FROZEN"
            candidate.frozen_at = frozen_at
            candidate.frozen_by = frozen_by
            epoch.selected_candidate_id = candidate.id
            epoch.status = "SELECTED"
            if evidence is not None:
                session.add(
                    ResearchCandidateFreezeReceipt(
                        user_id=candidate.user_id,
                        run_id=run.id,
                        experiment_epoch_id=epoch.id,
                        candidate_id=candidate.id,
                        candidate_hash=candidate.candidate_hash,
                        workflow_version=run.workflow_version,
                        generation_materialization_hash=(evidence.generation_materialization_hash),
                        ledger_hash=evidence.ledger_hash,
                        attempt_count_total=evidence.attempt_count_total,
                        market_trial_count=evidence.market_trial_count,
                        search_budget_hash=evidence.search_budget_hash,
                        dataset_snapshot_hash=evidence.dataset_snapshot_hash,
                        dataset_snapshot_identity_hash=(evidence.dataset_snapshot_identity_hash),
                        code_hash=evidence.code_hash,
                        dependency_hash=evidence.dependency_hash,
                        hypothesis_hash=evidence.hypothesis_hash,
                        environment_hash=evidence.environment_hash,
                        cost_model_hash=evidence.cost_model_hash,
                        checker_version="candidate-freeze-v1",
                        frozen_by=frozen_by,
                        frozen_at=frozen_at,
                    )
                )
            await session.commit()
            await session.refresh(candidate)
            return candidate


async def _require_discovery_freeze_ready(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    run: ResearchRun,
    epoch: ResearchExperimentEpoch,
) -> DiscoveryFreezeEvidence:
    """Prove the complete discovery-family ledger before selecting a candidate."""

    family_run_ids = tuple(
        (
            await session.scalars(
                select(ResearchRun.id).where(
                    ResearchRun.user_id == candidate.user_id,
                    ResearchRun.experiment_epoch_id == epoch.id,
                )
            )
        ).all()
    )
    if not family_run_ids or run.id not in family_run_ids:
        raise ValueError("CANDIDATE_RUN_BINDING_MISMATCH")

    family_tasks = list(
        (
            await session.scalars(
                select(ResearchTask)
                .where(
                    ResearchTask.user_id == candidate.user_id,
                    ResearchTask.run_id.in_(family_run_ids),
                )
                .order_by(ResearchTask.id.asc())
                .with_for_update()
            )
        ).all()
    )
    if any(task.status in {"QUEUED", "RUNNING"} for task in family_tasks):
        raise ValueError("CANDIDATE_FREEZE_FAMILY_TASK_ACTIVE")
    candidate_tasks = [task for task in family_tasks if task.run_id == run.id]
    if run.status != "SUCCEEDED" or not any(task.status == "SUCCEEDED" for task in candidate_tasks):
        raise ValueError("CANDIDATE_FREEZE_RUN_NOT_SUCCEEDED")

    runs_by_id = {
        item.id: item
        for item in (
            await session.scalars(
                select(ResearchRun)
                .where(
                    ResearchRun.id.in_(family_run_ids),
                    ResearchRun.user_id == candidate.user_id,
                )
                .order_by(ResearchRun.id.asc())
                .with_for_update()
            )
        ).all()
    }
    if any(item.status in {"QUEUED", "RUNNING"} for item in runs_by_id.values()):
        raise ValueError("CANDIDATE_FREEZE_FAMILY_TASK_ACTIVE")
    task_run_ids = {task.run_id for task in family_tasks}
    if set(runs_by_id) != set(family_run_ids) or task_run_ids != set(family_run_ids):
        raise ValueError("CANDIDATE_FREEZE_ATTEMPT_LEDGER_INCOMPLETE")
    attempts = list(
        (
            await session.scalars(
                select(ResearchStageAttempt)
                .where(ResearchStageAttempt.run_id.in_(family_run_ids))
                .order_by(
                    ResearchStageAttempt.run_id.asc(),
                    ResearchStageAttempt.task_id.asc(),
                    ResearchStageAttempt.attempt_no.asc(),
                    ResearchStageAttempt.id.asc(),
                )
                .with_for_update()
            )
        ).all()
    )
    if any(
        attempt.status not in {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"}
        for attempt in attempts
    ):
        raise ValueError("CANDIDATE_FREEZE_ATTEMPT_LEDGER_INCOMPLETE")
    family_tasks_by_id = {task.id: task for task in family_tasks}
    if any(
        attempt.task_id not in family_tasks_by_id
        or family_tasks_by_id[attempt.task_id].run_id != attempt.run_id
        for attempt in attempts
    ):
        raise ValueError("CANDIDATE_FREEZE_ATTEMPT_LEDGER_INCOMPLETE")
    events = list(
        (
            await session.scalars(
                select(ResearchTaskEvent)
                .where(ResearchTaskEvent.task_id.in_(tuple(task.id for task in family_tasks)))
                .order_by(ResearchTaskEvent.task_id.asc(), ResearchTaskEvent.sequence_no.asc())
            )
        ).all()
    )
    if any(
        event.user_id != candidate.user_id
        or event.task_id not in family_tasks_by_id
        or family_tasks_by_id[event.task_id].run_id != event.run_id
        for event in events
    ):
        raise ValueError("CANDIDATE_FREEZE_ATTEMPT_LEDGER_INCOMPLETE")
    terminal_event_tasks = {
        event.task_id
        for event in events
        if event.event_type in {"TASK_FINALIZED", "TASK_CANCEL_REQUESTED", "TASK_LEASE_RECOVERED"}
        and event.status in {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"}
    }
    if any(task.id not in terminal_event_tasks for task in family_tasks):
        raise ValueError("CANDIDATE_FREEZE_ATTEMPT_LEDGER_INCOMPLETE")

    generation = await _require_generation_provenance(session, candidate=candidate, run=run)

    try:
        expected_budget_hash = content_hash(epoch.search_budget)
        trial_limit = epoch.search_budget["max_trials"]
    except (KeyError, TypeError, ValueError):
        raise ValueError("CANDIDATE_FREEZE_SEARCH_BUDGET_INVALID") from None
    if type(trial_limit) is not int or not 1 <= trial_limit <= 2_147_483_647:
        raise ValueError("CANDIDATE_FREEZE_SEARCH_BUDGET_INVALID")
    journals = list(
        (
            await session.scalars(
                select(ResearchDiscoveryExecution)
                .where(
                    ResearchDiscoveryExecution.user_id == candidate.user_id,
                    or_(
                        ResearchDiscoveryExecution.run_id.in_(family_run_ids),
                        ResearchDiscoveryExecution.search_epoch_id == epoch.id,
                    ),
                )
                .order_by(
                    ResearchDiscoveryExecution.search_ordinal.asc(),
                    ResearchDiscoveryExecution.id.asc(),
                )
                .with_for_update()
            )
        ).all()
    )
    if not journals:
        raise ValueError("CANDIDATE_FREEZE_DISCOVERY_PUBLICATION_REQUIRED")
    if any(
        journal.status != "OBSERVED" or journal.result_json is None or journal.trial_id is None
        for journal in journals
    ):
        raise ValueError("CANDIDATE_FREEZE_DISCOVERY_UNRECONCILED")
    if any(
        journal.search_epoch_id != epoch.id
        or journal.search_ordinal is None
        or journal.search_budget_hash != expected_budget_hash
        or journal.run_id not in family_run_ids
        for journal in journals
    ):
        raise ValueError("CANDIDATE_FREEZE_LEDGER_INTEGRITY_DENIED")

    discovery_attempts = {
        attempt.id for attempt in attempts if attempt.stage == "VALIDATE_DISCOVERY"
    }
    journal_attempts = {journal.stage_attempt_id for journal in journals}
    if discovery_attempts != journal_attempts:
        raise ValueError("CANDIDATE_FREEZE_ATTEMPT_LEDGER_INCOMPLETE")
    search_ordinals = [journal.search_ordinal for journal in journals]
    if len(set(search_ordinals)) != len(search_ordinals) or any(
        ordinal is None or not 1 <= ordinal <= trial_limit for ordinal in search_ordinals
    ):
        raise ValueError("CANDIDATE_FREEZE_SEARCH_BUDGET_INVALID")

    trials = list(
        (
            await session.scalars(
                select(ResearchTrial)
                .where(
                    ResearchTrial.user_id == candidate.user_id,
                    ResearchTrial.run_id.in_(family_run_ids),
                )
                .order_by(
                    ResearchTrial.run_id.asc(), ResearchTrial.ordinal.asc(), ResearchTrial.id.asc()
                )
                .with_for_update()
            )
        ).all()
    )
    journal_trial_ids = {journal.trial_id for journal in journals}
    discovery_trial_ids = {trial.id for trial in trials if trial.stage == "VALIDATE_DISCOVERY"}
    if discovery_trial_ids != journal_trial_ids:
        raise ValueError("CANDIDATE_FREEZE_LEDGER_INCOMPLETE")
    if len(journals) + len(trials) - len(discovery_trial_ids) > trial_limit:
        raise ValueError("CANDIDATE_FREEZE_SEARCH_BUDGET_INVALID")

    from app.services.research.discovery_trial_materialization import (
        replay_discovery_publication,
    )

    tasks_by_id = family_tasks_by_id
    candidate_succeeded = False
    candidate_journal_task_ids: set[str] = set()
    quota_ledger: list[dict[str, Any]] = []
    for journal in journals:
        task = tasks_by_id.get(journal.task_id)
        journal_run = runs_by_id.get(journal.run_id)
        attempt = await session.get(ResearchStageAttempt, journal.stage_attempt_id)
        if task is None or journal_run is None or attempt is None:
            raise ValueError("CANDIDATE_FREEZE_LEDGER_INTEGRITY_DENIED")
        try:
            publication = await replay_discovery_publication(
                session,
                task=task,
                run=journal_run,
                attempt=attempt,
                execution_id=journal.id,
            )
        except (TypeError, ValueError):
            raise ValueError("CANDIDATE_FREEZE_LEDGER_INTEGRITY_DENIED") from None
        quota = await session.scalar(
            select(ResearchQuotaReservation)
            .where(ResearchQuotaReservation.id == journal.quota_reservation_id)
            .with_for_update()
        )
        bucket = (
            await session.scalar(
                select(ResearchQuotaBucket)
                .where(ResearchQuotaBucket.id == quota.bucket_id)
                .with_for_update()
            )
            if quota is not None
            else None
        )
        if (
            quota is None
            or bucket is None
            or quota.status != "SETTLED"
            or bucket.status != "ACTIVE"
            or quota.task_id != journal.task_id
            or quota.stage_attempt_id != journal.stage_attempt_id
            or quota.provider_operation_id != journal.operation_id
        ):
            raise ValueError("CANDIDATE_FREEZE_QUOTA_UNRECONCILED")
        quota_ledger.append(
            {
                "reservation_id": quota.id,
                "bucket_id": bucket.id,
                "task_id": quota.task_id,
                "stage_attempt_id": quota.stage_attempt_id,
                "provider_operation_id": quota.provider_operation_id,
                "resource_type": quota.resource_type,
                "reserved_amount": quota.reserved_amount,
                "settled_amount": quota.settled_amount,
                "unit": quota.unit,
                "status": quota.status,
                "policy_version": quota.policy_version,
                "request_hash": quota.request_hash,
                "bucket_status": bucket.status,
                "bucket_policy_version": bucket.policy_version,
                "bucket_resource_type": bucket.resource_type,
            }
        )
        if journal.candidate_id == candidate.id and publication.status == "SUCCEEDED":
            candidate_succeeded = True
            candidate_journal_task_ids.add(journal.task_id)
    if not candidate_succeeded:
        raise ValueError("CANDIDATE_FREEZE_SUCCESSFUL_DISCOVERY_REQUIRED")
    if generation.task_id not in candidate_journal_task_ids:
        raise ValueError("CANDIDATE_FREEZE_GENERATION_PROVENANCE_INVALID")

    retained_artifacts: dict[str, ResearchArtifact] = {}
    for artifact_id in (candidate.code_artifact_id, candidate.dependency_artifact_id):
        artifact = await session.get(ResearchArtifact, artifact_id)
        artifact_content = await session.get(ResearchArtifactContent, artifact_id)
        if (
            artifact is None
            or artifact_content is None
            or len(artifact_content.content) != artifact.size_bytes
            or content_hash_bytes(artifact_content.content) != artifact.content_hash
        ):
            raise ValueError("CANDIDATE_FREEZE_ARTIFACT_CONTENT_INVALID")
        retained_artifacts[artifact_id] = artifact

    dataset = await _candidate_dataset(session, candidate)
    hypothesis = await _owner_hypothesis(session, candidate.user_id, run.hypothesis_version_id)
    market_trial_count = sum(
        1
        for trial in trials
        if trial.candidate_id == candidate.id
        and trial.status == "SUCCEEDED"
        and trial.counts_as_market_trial
    )
    ledger_hash = content_hash(
        {
            "schema_version": "candidate-freeze-ledger-v1",
            "candidate_id": candidate.id,
            "candidate_hash": candidate.candidate_hash,
            "experiment_epoch_id": epoch.id,
            "family_runs": [
                {
                    "id": item.id,
                    "user_id": item.user_id,
                    "status": item.status,
                    "protocol_version": item.protocol_version,
                    "workflow_version": item.workflow_version,
                    "request_hash": item.request_hash,
                    "hypothesis_version_id": item.hypothesis_version_id,
                    "dataset_snapshot_id": item.dataset_snapshot_id,
                    "experiment_epoch_id": item.experiment_epoch_id,
                    "promotion_policy_version": item.promotion_policy_version,
                    "capability_profile_id": item.capability_profile_id,
                    "capability_profile_version": item.capability_profile_version,
                    "capability_evidence_hash": item.capability_evidence_hash,
                }
                for item in runs_by_id.values()
            ],
            "tasks": [
                {
                    "id": task.id,
                    "run_id": task.run_id,
                    "status": task.status,
                    "stage_cursor": task.stage_cursor,
                    "attempt_count": task.attempt_count,
                    "event_sequence": task.event_sequence,
                    "error_code": task.error_code,
                }
                for task in family_tasks
            ],
            "attempts": [
                {
                    "id": attempt.id,
                    "run_id": attempt.run_id,
                    "task_id": attempt.task_id,
                    "stage": attempt.stage,
                    "attempt_no": attempt.attempt_no,
                    "status": attempt.status,
                    "input_hash": attempt.input_hash,
                    "output_artifact_id": attempt.output_artifact_id,
                    "error_code": attempt.error_code,
                }
                for attempt in attempts
            ],
            "events": [
                {
                    "id": event.id,
                    "task_id": event.task_id,
                    "run_id": event.run_id,
                    "sequence_no": event.sequence_no,
                    "event_type": event.event_type,
                    "stage": event.stage,
                    "status": event.status,
                    "error_code": event.error_code,
                    "stage_attempt_id": event.stage_attempt_id,
                }
                for event in events
            ],
            "discovery_executions": [
                {
                    "id": journal.id,
                    "operation_id": journal.operation_id,
                    "run_id": journal.run_id,
                    "task_id": journal.task_id,
                    "stage_attempt_id": journal.stage_attempt_id,
                    "candidate_id": journal.candidate_id,
                    "quota_reservation_id": journal.quota_reservation_id,
                    "command_hash": journal.command_hash,
                    "search_ordinal": journal.search_ordinal,
                    "search_budget_hash": journal.search_budget_hash,
                    "trial_id": journal.trial_id,
                    "result_hash": content_hash(journal.result_json),
                    "status": journal.status,
                    "error_code": journal.error_code,
                }
                for journal in journals
            ],
            "trials": [
                {
                    "id": trial.id,
                    "run_id": trial.run_id,
                    "candidate_id": trial.candidate_id,
                    "parent_trial_id": trial.parent_trial_id,
                    "ordinal": trial.ordinal,
                    "stage": trial.stage,
                    "status": trial.status,
                    "input_hash": trial.input_hash,
                    "returns_artifact_id": trial.returns_artifact_id,
                    "metrics_hash": content_hash(trial.metrics),
                    "observed_market_performance": trial.observed_market_performance,
                    "counts_as_market_trial": trial.counts_as_market_trial,
                    "error_code": trial.error_code,
                }
                for trial in trials
            ],
            "quota": quota_ledger,
            "generation_materialization_hash": generation.materialization_hash,
        }
    )
    return DiscoveryFreezeEvidence(
        generation_materialization_hash=generation.materialization_hash,
        ledger_hash=ledger_hash,
        attempt_count_total=len(attempts),
        market_trial_count=market_trial_count,
        search_budget_hash=expected_budget_hash,
        dataset_snapshot_hash=dataset.content_hash,
        dataset_snapshot_identity_hash=_verified_dataset_identity_hash(dataset),
        code_hash=retained_artifacts[candidate.code_artifact_id].content_hash,
        dependency_hash=retained_artifacts[candidate.dependency_artifact_id].content_hash,
        hypothesis_hash=hypothesis.content_hash,
        environment_hash=candidate.environment_hash,
        cost_model_hash=candidate.cost_model_hash,
    )


async def _require_exact_freeze_receipt(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    run: ResearchRun,
    epoch: ResearchExperimentEpoch,
    evidence: DiscoveryFreezeEvidence,
) -> ResearchCandidateFreezeReceipt:
    """Make a repeated strict freeze prove the original receipt exactly."""

    receipt = await session.scalar(
        select(ResearchCandidateFreezeReceipt)
        .where(ResearchCandidateFreezeReceipt.candidate_id == candidate.id)
        .with_for_update()
    )
    if receipt is None or not _receipt_matches_identity(
        receipt,
        candidate=candidate,
        run=run,
        epoch=epoch,
    ):
        raise ValueError("CANDIDATE_FREEZE_RECEIPT_INVALID")
    expected_evidence = {
        "generation_materialization_hash": evidence.generation_materialization_hash,
        "ledger_hash": evidence.ledger_hash,
        "attempt_count_total": evidence.attempt_count_total,
        "market_trial_count": evidence.market_trial_count,
        "search_budget_hash": evidence.search_budget_hash,
        "dataset_snapshot_hash": evidence.dataset_snapshot_hash,
        "dataset_snapshot_identity_hash": evidence.dataset_snapshot_identity_hash,
        "code_hash": evidence.code_hash,
        "dependency_hash": evidence.dependency_hash,
        "hypothesis_hash": evidence.hypothesis_hash,
        "environment_hash": evidence.environment_hash,
        "cost_model_hash": evidence.cost_model_hash,
    }
    if any(getattr(receipt, key) != value for key, value in expected_evidence.items()):
        raise ValueError("CANDIDATE_FREEZE_RECEIPT_INVALID")
    return receipt


async def require_strict_freeze_receipt(
    session: AsyncSession,
    candidate: ResearchCandidate,
) -> ResearchCandidateFreezeReceipt:
    """Verify the immutable strict-freeze authority before sealed operations."""

    if (
        candidate.freeze_status != "FROZEN"
        or candidate.frozen_at is None
        or candidate.frozen_by is None
    ):
        raise ValueError("CANDIDATE_STRICT_FREEZE_RECEIPT_REQUIRED")
    await verify_candidate_integrity(session, candidate)
    run = await session.get(ResearchRun, candidate.run_id)
    epoch = await session.get(ResearchExperimentEpoch, candidate.experiment_epoch_id)
    if run is None or epoch is None:
        raise ValueError("CANDIDATE_STRICT_FREEZE_RECEIPT_REQUIRED")
    if (
        run.workflow_version != "discovery-v1"
        or epoch.selected_candidate_id != candidate.id
        or epoch.status not in {"SELECTED", "DISCLOSED", "CLOSED"}
    ):
        raise ValueError("CANDIDATE_STRICT_FREEZE_RECEIPT_REQUIRED")
    try:
        evidence = await _require_discovery_freeze_ready(
            session,
            candidate=candidate,
            run=run,
            epoch=epoch,
        )
        return await _require_exact_freeze_receipt(
            session,
            candidate=candidate,
            run=run,
            epoch=epoch,
            evidence=evidence,
        )
    except ValueError:
        raise ValueError("CANDIDATE_STRICT_FREEZE_RECEIPT_REQUIRED") from None


def _receipt_matches_identity(
    receipt: ResearchCandidateFreezeReceipt,
    *,
    candidate: ResearchCandidate,
    run: ResearchRun,
    epoch: ResearchExperimentEpoch,
) -> bool:
    """Compare the receipt to the selected candidate without trusting callers."""

    return (
        receipt.user_id == candidate.user_id
        and receipt.run_id == candidate.run_id == run.id
        and receipt.experiment_epoch_id == candidate.experiment_epoch_id == epoch.id
        and receipt.candidate_id == candidate.id
        and receipt.candidate_hash == candidate.candidate_hash
        and receipt.workflow_version == run.workflow_version == "discovery-v1"
        and receipt.checker_version == "candidate-freeze-v1"
        and receipt.frozen_by == candidate.frozen_by
        and candidate.frozen_at is not None
        and _utc_datetime(receipt.frozen_at) == _utc_datetime(candidate.frozen_at)
    )


def _utc_datetime(value: datetime) -> datetime:
    """Normalize SQLite-naive and timezone-aware persisted instants."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def strict_freeze_receipt_fingerprint(receipt: ResearchCandidateFreezeReceipt) -> str:
    """Canonical safe fingerprint for downstream evidence and stale checks."""

    return content_hash(
        {
            "schema_version": "candidate-freeze-receipt-fingerprint-v1",
            "receipt_id": receipt.id,
            "user_id": receipt.user_id,
            "run_id": receipt.run_id,
            "experiment_epoch_id": receipt.experiment_epoch_id,
            "candidate_id": receipt.candidate_id,
            "candidate_hash": receipt.candidate_hash,
            "workflow_version": receipt.workflow_version,
            "generation_materialization_hash": receipt.generation_materialization_hash,
            "ledger_hash": receipt.ledger_hash,
            "attempt_count_total": receipt.attempt_count_total,
            "market_trial_count": receipt.market_trial_count,
            "search_budget_hash": receipt.search_budget_hash,
            "dataset_snapshot_hash": receipt.dataset_snapshot_hash,
            "dataset_snapshot_identity_hash": receipt.dataset_snapshot_identity_hash,
            "code_hash": receipt.code_hash,
            "dependency_hash": receipt.dependency_hash,
            "hypothesis_hash": receipt.hypothesis_hash,
            "environment_hash": receipt.environment_hash,
            "cost_model_hash": receipt.cost_model_hash,
            "checker_version": receipt.checker_version,
            "frozen_by": receipt.frozen_by,
            "frozen_at": _utc_datetime(receipt.frozen_at).isoformat(),
        }
    )


async def _require_generation_provenance(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    run: ResearchRun,
) -> ResearchGenerationMaterialization:
    """Rebuild the exact generated candidate identity from retained bytes."""

    denied = "CANDIDATE_FREEZE_GENERATION_PROVENANCE_INVALID"
    relation = await session.scalar(
        select(ResearchGenerationMaterialization)
        .where(ResearchGenerationMaterialization.candidate_id == candidate.id)
        .with_for_update()
    )
    if relation is None:
        raise ValueError(denied)
    task = await session.get(ResearchTask, relation.task_id)
    attempt = await session.get(ResearchStageAttempt, relation.stage_attempt_id)
    invocation = await session.get(ResearchModelInvocation, relation.model_invocation_id)
    manifest = await session.get(ResearchArtifact, relation.manifest_artifact_id)
    manifest_content = await session.get(ResearchArtifactContent, relation.manifest_artifact_id)
    binding = await session.scalar(
        select(ResearchStageArtifactBinding).where(
            ResearchStageArtifactBinding.stage_attempt_id == relation.stage_attempt_id,
            ResearchStageArtifactBinding.artifact_id == relation.manifest_artifact_id,
        )
    )
    if (
        task is None
        or attempt is None
        or invocation is None
        or manifest is None
        or manifest_content is None
        or binding is None
        or relation.user_id != candidate.user_id
        or relation.run_id != run.id
        or relation.task_id != task.id
        or task.user_id != candidate.user_id
        or task.run_id != run.id
        or relation.stage_attempt_id != attempt.id
        or attempt.task_id != task.id
        or attempt.run_id != run.id
        or attempt.stage != "GENERATE"
        or attempt.status != "SUCCEEDED"
        or attempt.output_artifact_id != manifest.id
        or invocation.run_id != run.id
        or invocation.output_hash != relation.model_output_hash
        or relation.candidate_id != candidate.id
        or binding.user_id != candidate.user_id
        or binding.run_id != run.id
        or binding.task_id != task.id
        or manifest.kind != "generation_manifest"
        or manifest.schema_version != "research-generation-manifest-v1"
        or len(manifest_content.content) != manifest.size_bytes
        or content_hash_bytes(manifest_content.content) != manifest.content_hash
    ):
        raise ValueError(denied)
    try:
        payload = json.loads(manifest_content.content)
        if canonical_json(payload).encode("utf-8") != manifest_content.content:
            raise ValueError
        policy_version = payload["policy_version"]
    except (KeyError, TypeError, UnicodeDecodeError, ValueError):
        raise ValueError(denied) from None
    expected_payload = {
        "schema_version": "research-generation-manifest-v1",
        "stage": "GENERATE",
        "task_id": task.id,
        "run_id": run.id,
        "stage_attempt_id": attempt.id,
        "request_hash": run.request_hash,
        "trace_id": task.trace_id,
        "origin": "llm",
        "policy_version": policy_version,
        "model_invocation_id": invocation.id,
        "model_output_hash": invocation.output_hash,
        "candidate_id": candidate.id,
        "candidate_hash": candidate.candidate_hash,
        "code_artifact": {
            "id": candidate.code_artifact_id,
            "kind": "strategy_code",
            "content_hash": (
                await session.get(ResearchArtifact, candidate.code_artifact_id)
            ).content_hash,
        },
        "dependency_artifact": {
            "id": candidate.dependency_artifact_id,
            "kind": "dependency_lock",
            "content_hash": (
                await session.get(ResearchArtifact, candidate.dependency_artifact_id)
            ).content_hash,
        },
        "environment_hash": candidate.environment_hash,
        "cost_model_hash": candidate.cost_model_hash,
        "params_hash": content_hash(candidate.params),
        "execution_state": "MATERIALIZED_NOT_EXECUTED",
        "sandbox_receipt_id": None,
        "evaluation_id": None,
        "market_trial_id": None,
    }
    if payload != expected_payload or type(policy_version) is not str or not policy_version.strip():
        raise ValueError(denied)
    expected_relation_hash = content_hash(
        {
            "task_id": task.id,
            "run_id": task.run_id,
            "stage_attempt_id": attempt.id,
            "candidate_id": candidate.id,
            "candidate_hash": candidate.candidate_hash,
            "model_invocation_id": invocation.id,
            "model_output_hash": relation.model_output_hash,
            "manifest_artifact_id": manifest.id,
            "manifest_hash": manifest.content_hash,
            "policy_version": policy_version,
        }
    )
    if relation.materialization_hash != expected_relation_hash:
        raise ValueError(denied)
    return relation


def content_hash_bytes(value: bytes) -> str:
    """Hash retained immutable bytes without changing canonical JSON semantics."""

    from hashlib import sha256

    return sha256(value).hexdigest()


def candidate_identity_hash(
    *,
    run_id: str,
    experiment_epoch_id: str,
    hypothesis_version_id: str,
    hypothesis_content_hash: str,
    dataset_snapshot_id: str,
    dataset_content_hash: str,
    dataset_snapshot_identity_hash: str,
    code_artifact_id: str,
    code_hash: str,
    dependency_artifact_id: str,
    dependency_hash: str,
    environment_hash: str,
    cost_model_hash: str,
    params: dict[str, Any],
    source_version_id: str | None,
) -> str:
    """Canonical immutable identity for a candidate and all its inputs."""

    return content_hash(
        {
            "run_id": run_id,
            "epoch_id": experiment_epoch_id,
            "hypothesis_version_id": hypothesis_version_id,
            "hypothesis_content_hash": hypothesis_content_hash,
            "dataset_snapshot_id": dataset_snapshot_id,
            "dataset_hash": dataset_content_hash,
            "dataset_snapshot_identity_hash": dataset_snapshot_identity_hash,
            "code_artifact_id": code_artifact_id,
            "code_hash": code_hash,
            "dependency_artifact_id": dependency_artifact_id,
            "dependency_hash": dependency_hash,
            "environment_hash": environment_hash,
            "cost_model_hash": cost_model_hash,
            "params": params,
            "source_version_id": source_version_id,
        }
    )


async def verify_candidate_integrity(
    session: AsyncSession,
    candidate: ResearchCandidate,
) -> None:
    """Reject a candidate whose linked immutable inputs no longer match its hash."""

    run = await session.get(ResearchRun, candidate.run_id)
    epoch = await session.get(ResearchExperimentEpoch, candidate.experiment_epoch_id)
    dataset = await session.get(ResearchDatasetSnapshot, candidate.dataset_snapshot_id)
    code_artifact = await session.get(ResearchArtifact, candidate.code_artifact_id)
    dependency_artifact = await session.get(ResearchArtifact, candidate.dependency_artifact_id)
    if (
        run is None
        or epoch is None
        or dataset is None
        or code_artifact is None
        or dependency_artifact is None
    ):
        raise ValueError("CANDIDATE_BINDING_NOT_FOUND")
    require_verified_snapshot_integrity(dataset)
    hypothesis = await _owner_hypothesis(session, candidate.user_id, run.hypothesis_version_id)
    _validate_create_binding(
        run=run,
        epoch=epoch,
        dataset=dataset,
        hypothesis=hypothesis,
        code_artifact=code_artifact,
        dependency_artifact=dependency_artifact,
        environment_hash=candidate.environment_hash,
        cost_model_hash=candidate.cost_model_hash,
        params=candidate.params,
    )
    expected_hash = candidate_identity_hash(
        run_id=run.id,
        experiment_epoch_id=epoch.id,
        hypothesis_version_id=hypothesis.id,
        hypothesis_content_hash=hypothesis.content_hash,
        dataset_snapshot_id=dataset.id,
        dataset_content_hash=dataset.content_hash,
        dataset_snapshot_identity_hash=_verified_dataset_identity_hash(dataset),
        code_artifact_id=code_artifact.id,
        code_hash=code_artifact.content_hash,
        dependency_artifact_id=dependency_artifact.id,
        dependency_hash=dependency_artifact.content_hash,
        environment_hash=candidate.environment_hash,
        cost_model_hash=candidate.cost_model_hash,
        params=candidate.params,
        source_version_id=candidate.source_version_id,
    )
    if candidate.candidate_hash != expected_hash:
        raise ValueError("CANDIDATE_CONTENT_HASH_MISMATCH")


def _validate_create_binding(
    *,
    run: ResearchRun,
    epoch: ResearchExperimentEpoch,
    dataset: ResearchDatasetSnapshot,
    hypothesis: ResearchHypothesisVersion,
    code_artifact: ResearchArtifact,
    dependency_artifact: ResearchArtifact,
    environment_hash: str,
    cost_model_hash: str,
    params: dict[str, Any],
) -> None:
    """Validate that every candidate input belongs to the same immutable run."""

    if (
        run.user_id != epoch.user_id
        or run.user_id != dataset.user_id
        or run.user_id != hypothesis.user_id
        or run.experiment_epoch_id != epoch.id
        or run.dataset_snapshot_id != dataset.id
        or run.hypothesis_version_id != hypothesis.id
        or epoch.hypothesis_version_id != hypothesis.id
    ):
        raise ValueError("CANDIDATE_RUN_BINDING_MISMATCH")
    if dataset.partition_kind == "SEALED_HOLDOUT":
        raise ValueError("CANDIDATE_CANNOT_BIND_SEALED_DATASET")
    if code_artifact.kind != "strategy_code" or dependency_artifact.kind != "dependency_lock":
        raise ValueError("CANDIDATE_ARTIFACT_KIND_MISMATCH")
    if not isinstance(params, dict):
        raise ValueError("CANDIDATE_PARAMS_INVALID")
    if not _is_sha256(environment_hash) or not _is_sha256(cost_model_hash):
        raise ValueError("CANDIDATE_INPUT_HASH_INVALID")


def _verified_dataset_identity_hash(dataset: ResearchDatasetSnapshot) -> str:
    """Return the complete attested object identity required by a candidate."""

    value = dataset.snapshot_identity_hash
    if not _is_sha256(value):
        raise ValueError("CANDIDATE_DATASET_IDENTITY_INVALID")
    return value


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


async def _owner_run(session: Any, user_id: str, run_id: str) -> ResearchRun:
    result = await session.execute(
        select(ResearchRun).where(ResearchRun.id == run_id, ResearchRun.user_id == user_id)
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise ValueError("RESEARCH_RUN_NOT_FOUND")
    return model


async def _owner_epoch(session: Any, user_id: str, epoch_id: str) -> ResearchExperimentEpoch:
    result = await session.execute(
        select(ResearchExperimentEpoch)
        .where(ResearchExperimentEpoch.id == epoch_id, ResearchExperimentEpoch.user_id == user_id)
        .with_for_update()
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise ValueError("EXPERIMENT_EPOCH_NOT_FOUND")
    return model


async def _owner_hypothesis(
    session: Any,
    user_id: str,
    hypothesis_id: str,
) -> ResearchHypothesisVersion:
    result = await session.execute(
        select(ResearchHypothesisVersion).where(
            ResearchHypothesisVersion.id == hypothesis_id,
            ResearchHypothesisVersion.user_id == user_id,
        )
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise ValueError("HYPOTHESIS_NOT_FOUND")
    return model


async def _owner_dataset(session: Any, user_id: str, snapshot_id: str) -> ResearchDatasetSnapshot:
    result = await session.execute(
        select(ResearchDatasetSnapshot).where(
            ResearchDatasetSnapshot.id == snapshot_id,
            ResearchDatasetSnapshot.user_id == user_id,
        )
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise ValueError("DATASET_SNAPSHOT_NOT_FOUND")
    if model.partition_kind == "SEALED_HOLDOUT":
        raise ValueError("CANDIDATE_CANNOT_BIND_SEALED_DATASET")
    require_verified_snapshot_integrity(model)
    return model


async def _candidate_dataset(
    session: Any,
    candidate: ResearchCandidate,
) -> ResearchDatasetSnapshot:
    """Load the candidate's immutable dataset before its irreversible freeze."""

    dataset = await session.get(ResearchDatasetSnapshot, candidate.dataset_snapshot_id)
    if dataset is None or dataset.user_id != candidate.user_id:
        raise ValueError("CANDIDATE_BINDING_NOT_FOUND")
    return dataset


async def _artifact(session: Any, artifact_id: str) -> ResearchArtifact:
    model = await session.get(ResearchArtifact, artifact_id)
    if model is None:
        raise ValueError("RESEARCH_ARTIFACT_NOT_FOUND")
    return model
