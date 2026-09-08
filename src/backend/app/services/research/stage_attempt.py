"""Idempotent checkpoints around protocol-v2 external stage side effects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchGenerationMaterialization,
    ResearchRun,
    ResearchStageArtifactBinding,
    ResearchStageAttempt,
    ResearchTask,
)
from app.services.research.canonical import content_hash
from app.services.research.database_clock import DatabaseUtcNow
from app.services.research.discovery_search_budget import lock_search_epoch
from app.services.research.discovery_trial_materialization import (
    DiscoveryTrialMaterializer,
    replay_discovery_publication,
)
from app.services.research.generation_materialization import (
    GenerationMaterializationProposal,
    ResearchGenerationMaterializer,
)
from app.services.research.task_runner import append_research_task_event
from app.services.research.workflow_graph import expected_next_stage

_TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"})


@dataclass(frozen=True, slots=True)
class _GenerationCompletionContext:
    """Internal lease context passed to the server-owned materializer."""

    task_id: str
    run_id: str
    user_id: str
    stage_attempt_id: str
    lease_token: str
    stage: str
    request_hash: str
    trace_id: str | None


class ResearchStageAttemptService:
    """Create and close a persisted stage checkpoint under the task's lease."""

    def __init__(
        self,
        *,
        generation_materializer: ResearchGenerationMaterializer | None = None,
        discovery_materializer: DiscoveryTrialMaterializer | None = None,
    ) -> None:
        """Keep materialization disabled until a deployment injects its policy."""

        self._generation_materializer = generation_materializer
        self._discovery_materializer = discovery_materializer

    async def begin(
        self,
        *,
        task_id: str,
        lease_token: str,
        stage: str,
        idempotency_key: str,
        input_payload: dict[str, Any],
        now: datetime | None = None,
    ) -> ResearchStageAttempt:
        """Create one leased checkpoint or return its identical prior attempt."""

        if not stage.strip() or not idempotency_key.strip():
            raise ValueError("RESEARCH_STAGE_ATTEMPT_IDENTITY_REQUIRED")
        if not lease_token.strip():
            raise ValueError("RESEARCH_STAGE_ATTEMPT_LEASE_REQUIRED")
        input_hash = content_hash(input_payload)
        started_at = _as_utc(now or _now())
        async with database.async_session_maker() as session:
            task = await _leased_task(session, task_id, lease_token)
            existing_result = await session.execute(
                select(ResearchStageAttempt)
                .where(
                    ResearchStageAttempt.task_id == task.id,
                    ResearchStageAttempt.idempotency_key == idempotency_key,
                )
                .with_for_update()
            )
            existing = existing_result.scalar_one_or_none()
            if existing is not None:
                if existing.stage != stage or existing.input_hash != input_hash:
                    raise ValueError("RESEARCH_STAGE_ATTEMPT_IDEMPOTENCY_CONFLICT")
                if existing.status == "RUNNING":
                    await _require_live_task_lease(session, task.id, lease_token)
                return existing
            next_attempt = (
                int(
                    await session.scalar(
                        select(func.coalesce(func.max(ResearchStageAttempt.attempt_no), 0)).where(
                            ResearchStageAttempt.task_id == task.id,
                            ResearchStageAttempt.stage == stage,
                        )
                    )
                    or 0
                )
                + 1
            )
            model = ResearchStageAttempt(
                run_id=task.run_id,
                task_id=task.id,
                stage=stage,
                attempt_no=next_attempt,
                idempotency_key=idempotency_key,
                status="RUNNING",
                lease_token=lease_token,
                input_hash=input_hash,
                started_at=started_at,
            )
            # The first lease check can become stale while we resolve the
            # idempotency key. Authorize the checkpoint write at database time.
            await _require_live_task_lease(session, task.id, lease_token)
            task.stage_cursor = stage
            session.add(model)
            try:
                await session.flush()
                await append_research_task_event(
                    session,
                    task,
                    event_type="STAGE_ATTEMPT_STARTED",
                    stage=model.stage,
                    status=model.status,
                    stage_attempt_id=model.id,
                    created_at=started_at,
                )
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ValueError("RESEARCH_STAGE_ATTEMPT_CONCURRENT_CONFLICT") from None
            await session.refresh(model)
            return model

    async def complete(
        self,
        *,
        task_id: str,
        lease_token: str,
        attempt_id: str,
        status: str,
        output_artifact_id: str | None = None,
        error_code: str | None = None,
        next_stage: str | None = None,
        generation_proposal: GenerationMaterializationProposal | None = None,
        discovery_execution_id: str | None = None,
        now: datetime | None = None,
    ) -> ResearchStageAttempt:
        """Close a checkpoint once; late or differently leased workers are rejected."""

        if status not in _TERMINAL_STATUSES:
            raise ValueError("RESEARCH_STAGE_ATTEMPT_TERMINAL_STATUS_INVALID")
        if next_stage is not None and not next_stage.strip():
            raise ValueError("RESEARCH_STAGE_ATTEMPT_NEXT_STAGE_INVALID")
        if generation_proposal is not None:
            if status != "SUCCEEDED" or output_artifact_id is not None:
                raise ValueError("RESEARCH_GENERATION_PROPOSAL_TRANSITION_INVALID")
            if self._generation_materializer is None:
                raise ValueError("RESEARCH_GENERATION_MATERIALIZER_UNAVAILABLE")
        if discovery_execution_id is not None:
            if (
                not isinstance(discovery_execution_id, str)
                or len(discovery_execution_id) != 64
                or any(c not in "0123456789abcdef" for c in discovery_execution_id)
                or generation_proposal is not None
                or output_artifact_id is not None
                or next_stage is not None
            ):
                raise ValueError("RESEARCH_DISCOVERY_PROPOSAL_TRANSITION_INVALID")
            if self._discovery_materializer is None:
                raise ValueError("RESEARCH_DISCOVERY_MATERIALIZER_UNAVAILABLE")
        completed_at = _as_utc(now or _now())
        typed_publication = generation_proposal is not None or discovery_execution_id is not None
        async with database.async_session_maker() as session:
            if typed_publication:
                # Publication takes epoch -> task -> run -> attempt locks. Do not
                # first hold the task and then wait on an epoch held by a publisher.
                identity = (
                    await session.execute(
                        select(ResearchTask.user_id, ResearchTask.run_id).where(
                            ResearchTask.id == task_id, ResearchTask.lease_token == lease_token
                        )
                    )
                ).one_or_none()
                if identity is None:
                    raise ValueError("RESEARCH_STAGE_ATTEMPT_LEASE_DENIED")
                locked_epoch = await lock_search_epoch(
                    session, user_id=identity.user_id, run_id=identity.run_id, require_open=False
                )
            task = await _task_with_current_lease_token(
                session,
                task_id,
                lease_token,
                allow_cancel_requested=True,
            )
            run = await session.get(
                ResearchRun,
                task.run_id,
                populate_existing=True,
                with_for_update=typed_publication,
            )
            if run is None and (
                generation_proposal is not None or discovery_execution_id is not None
            ):
                raise ValueError("RESEARCH_STAGE_ATTEMPT_RUN_NOT_FOUND")
            if typed_publication and run.experiment_epoch_id != locked_epoch.id:
                raise ValueError("RESEARCH_STAGE_ATTEMPT_RUN_EPOCH_CHANGED")
            result = await session.execute(
                select(ResearchStageAttempt)
                .where(
                    ResearchStageAttempt.id == attempt_id,
                    ResearchStageAttempt.task_id == task.id,
                    ResearchStageAttempt.lease_token == lease_token,
                )
                .with_for_update()
            )
            attempt = result.scalar_one_or_none()
            if attempt is None:
                raise ValueError("RESEARCH_STAGE_ATTEMPT_LEASE_DENIED")
            if generation_proposal is not None and (
                attempt.stage != "GENERATE"
                or next_stage != expected_next_stage("GENERATE", run.workflow_version)
            ):
                raise ValueError("RESEARCH_GENERATION_PROPOSAL_TRANSITION_INVALID")
            if discovery_execution_id is not None and (
                run.workflow_version != "discovery-v1" or attempt.stage != "VALIDATE_DISCOVERY"
            ):
                raise ValueError("RESEARCH_DISCOVERY_PROPOSAL_TRANSITION_INVALID")
            if (
                attempt.stage == "VALIDATE_DISCOVERY"
                and status == "SUCCEEDED"
                and discovery_execution_id is None
            ):
                raise ValueError("RESEARCH_DISCOVERY_CONTRACT_UNAVAILABLE")
            if (
                run is not None
                and run.workflow_version == "discovery-v1"
                and attempt.stage == "GENERATE"
                and status == "SUCCEEDED"
                and generation_proposal is None
            ):
                raise ValueError("RESEARCH_GENERATION_CONTRACT_UNAVAILABLE")
            if attempt.status in _TERMINAL_STATUSES:
                if generation_proposal is not None:
                    output_artifact_id = await _replayed_generation_output_artifact_id(
                        session,
                        attempt=attempt,
                        proposal=generation_proposal,
                    )
                if discovery_execution_id is not None:
                    publication = await replay_discovery_publication(
                        session,
                        task=task,
                        run=run,
                        attempt=attempt,
                        execution_id=discovery_execution_id,
                    )
                    output_artifact_id = publication.output_artifact_id
                if (
                    attempt.status != status
                    or attempt.output_artifact_id != output_artifact_id
                    or attempt.error_code != error_code
                ):
                    raise ValueError("RESEARCH_STAGE_ATTEMPT_TERMINAL_CONFLICT")
                if status == "SUCCEEDED" and (
                    not isinstance(output_artifact_id, str) or not output_artifact_id.strip()
                ):
                    raise ValueError("RESEARCH_STAGE_ATTEMPT_SUCCESS_ARTIFACT_REQUIRED")
                if output_artifact_id is not None:
                    await _require_bound_output_artifact(session, task, attempt, output_artifact_id)
                return attempt
            await _require_live_task_lease(session, task.id, lease_token)
            if task.cancel_requested_at is not None:
                # The external side effect may have returned concurrently with a
                # cancellation request. Preserve a terminal audit receipt but do
                # not make its output eligible for a following stage.
                status = "CANCELLED"
                output_artifact_id = None
                error_code = "TASK_CANCEL_REQUESTED"
                generation_proposal = None
                discovery_execution_id = None
            if generation_proposal is not None:
                run = await session.get(ResearchRun, task.run_id)
                if run is None:
                    raise ValueError("RESEARCH_STAGE_ATTEMPT_RUN_NOT_FOUND")
                materialization = await self._generation_materializer.materialize_in_session(
                    session,
                    task=task,
                    attempt=attempt,
                    context=_GenerationCompletionContext(
                        task_id=task.id,
                        run_id=run.id,
                        user_id=task.user_id,
                        stage_attempt_id=attempt.id,
                        lease_token=lease_token,
                        stage=attempt.stage,
                        request_hash=run.request_hash,
                        trace_id=task.trace_id,
                    ),
                    proposal=generation_proposal,
                )
                output_artifact_id = materialization.output_artifact_id
            if discovery_execution_id is not None:
                publication = await self._discovery_materializer.publish_in_session(
                    session,
                    context=_GenerationCompletionContext(
                        task_id=task.id,
                        run_id=run.id,
                        user_id=task.user_id,
                        stage_attempt_id=attempt.id,
                        lease_token=lease_token,
                        stage=attempt.stage,
                        request_hash=run.request_hash,
                        trace_id=task.trace_id,
                    ),
                    execution_id=discovery_execution_id,
                )
                if publication.status != status or publication.error_code != error_code:
                    raise ValueError("RESEARCH_DISCOVERY_RESULT_TRANSITION_CONFLICT")
                output_artifact_id = publication.output_artifact_id
            if status == "SUCCEEDED" and (
                not isinstance(output_artifact_id, str) or not output_artifact_id.strip()
            ):
                raise ValueError("RESEARCH_STAGE_ATTEMPT_SUCCESS_ARTIFACT_REQUIRED")
            if output_artifact_id is not None:
                await _require_bound_output_artifact(session, task, attempt, output_artifact_id)
            # Artifact validation and generation materialization can take long
            # enough for an old worker's task lease to expire. Recheck before
            # transitioning the durable checkpoint.
            await _require_live_task_lease(session, task.id, lease_token)
            attempt.status = status
            attempt.output_artifact_id = output_artifact_id
            attempt.error_code = error_code
            attempt.completed_at = completed_at
            if status == "SUCCEEDED":
                await _advance_stage_cursor(session, task, next_stage)
            await append_research_task_event(
                session,
                task,
                event_type="STAGE_ATTEMPT_COMPLETED",
                stage=attempt.stage,
                status=attempt.status,
                error_code=attempt.error_code,
                stage_attempt_id=attempt.id,
                created_at=completed_at,
            )
            await session.commit()
            await session.refresh(attempt)
            return attempt

    async def resume_succeeded_checkpoint(
        self,
        *,
        task_id: str,
        lease_token: str,
        stage: str,
        next_stage: str | None,
    ) -> bool:
        """Adopt a prior successful receipt under the current lease without replaying it.

        A recovered task has a new lease token, while its completed checkpoint
        deliberately retains the original token for auditability.  The current
        lease may therefore advance the task cursor only after it has found a
        terminal successful receipt for the same task and stage.
        """

        if not stage.strip():
            raise ValueError("RESEARCH_STAGE_ATTEMPT_IDENTITY_REQUIRED")
        if next_stage is not None and not next_stage.strip():
            raise ValueError("RESEARCH_STAGE_ATTEMPT_NEXT_STAGE_INVALID")
        async with database.async_session_maker() as session:
            task = await _leased_task(session, task_id, lease_token)
            checkpoint = await session.scalar(
                select(ResearchStageAttempt)
                .where(
                    ResearchStageAttempt.task_id == task.id,
                    ResearchStageAttempt.stage == stage,
                    ResearchStageAttempt.status == "SUCCEEDED",
                )
                .order_by(ResearchStageAttempt.attempt_no.desc())
                .limit(1)
                .with_for_update()
            )
            if checkpoint is None:
                return False
            run = await session.get(ResearchRun, task.run_id)
            if run is None:
                raise ValueError("RESEARCH_STAGE_ATTEMPT_RUN_NOT_FOUND")
            if run.workflow_version == "discovery-v1" and next_stage != expected_next_stage(
                stage, run.workflow_version
            ):
                raise ValueError("RESEARCH_STAGE_ATTEMPT_NEXT_STAGE_INVALID")
            if run.workflow_version == "discovery-v1" and stage == "GENERATE":
                relation = await session.scalar(
                    select(ResearchGenerationMaterialization).where(
                        ResearchGenerationMaterialization.stage_attempt_id == checkpoint.id,
                        ResearchGenerationMaterialization.user_id == task.user_id,
                        ResearchGenerationMaterialization.run_id == run.id,
                        ResearchGenerationMaterialization.task_id == task.id,
                        ResearchGenerationMaterialization.manifest_artifact_id
                        == checkpoint.output_artifact_id,
                    )
                )
                if relation is None:
                    raise ValueError("RESEARCH_GENERATION_CONTRACT_UNAVAILABLE")
            if stage == "VALIDATE_DISCOVERY":
                if run.workflow_version != "discovery-v1":
                    raise ValueError("RESEARCH_DISCOVERY_PROPOSAL_TRANSITION_INVALID")
                await replay_discovery_publication(
                    session,
                    task=task,
                    run=run,
                    attempt=checkpoint,
                )
            if not checkpoint.output_artifact_id:
                raise ValueError("RESEARCH_STAGE_ATTEMPT_SUCCESS_ARTIFACT_REQUIRED")
            await _require_bound_output_artifact(
                session,
                task,
                checkpoint,
                checkpoint.output_artifact_id,
            )
            await _require_live_task_lease(session, task.id, lease_token)
            await _advance_stage_cursor(session, task, next_stage)
            await append_research_task_event(
                session,
                task,
                event_type="STAGE_CHECKPOINT_RESUMED",
                stage=checkpoint.stage,
                status=checkpoint.status,
                error_code=checkpoint.error_code,
                stage_attempt_id=checkpoint.id,
            )
            await session.commit()
            return True


async def _leased_task(
    session: Any,
    task_id: str,
    lease_token: str,
    *,
    allow_cancel_requested: bool = False,
) -> ResearchTask:
    task = await _task_with_current_lease_token(
        session,
        task_id,
        lease_token,
        allow_cancel_requested=allow_cancel_requested,
    )
    await _require_live_task_lease(session, task.id, lease_token)
    return task


async def _task_with_current_lease_token(
    session: Any,
    task_id: str,
    lease_token: str,
    *,
    allow_cancel_requested: bool = False,
) -> ResearchTask:
    """Read a token-matching task, allowing terminal receipt replay below."""

    result = await session.execute(
        select(ResearchTask)
        .where(
            ResearchTask.id == task_id,
            ResearchTask.status == "RUNNING",
            ResearchTask.lease_token == lease_token,
        )
        .with_for_update()
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise ValueError("RESEARCH_STAGE_ATTEMPT_LEASE_DENIED")
    if task.cancel_requested_at is not None and not allow_cancel_requested:
        raise ValueError("RESEARCH_STAGE_ATTEMPT_CANCEL_REQUESTED")
    return task


async def _require_live_task_lease(session: Any, task_id: str, lease_token: str) -> None:
    """Fence a new checkpoint write at the database's current UTC time."""

    live_task_id = await session.scalar(
        select(ResearchTask.id)
        .where(
            ResearchTask.id == task_id,
            ResearchTask.status == "RUNNING",
            ResearchTask.lease_token == lease_token,
            ResearchTask.lease_expires_at.is_not(None),
            ResearchTask.lease_expires_at > DatabaseUtcNow(),
        )
        .with_for_update()
    )
    if live_task_id is None:
        raise ValueError("RESEARCH_STAGE_ATTEMPT_LEASE_DENIED")


async def _advance_stage_cursor(
    session: Any,
    task: ResearchTask,
    next_stage: str | None,
) -> None:
    """Advance task and run together only after a durable successful receipt."""

    if next_stage is None:
        return
    task.stage_cursor = next_stage
    run = await session.get(ResearchRun, task.run_id)
    if run is None:
        raise ValueError("RESEARCH_STAGE_ATTEMPT_RUN_NOT_FOUND")
    run.stage_cursor = next_stage


async def _require_bound_output_artifact(
    session: Any,
    task: ResearchTask,
    attempt: ResearchStageAttempt,
    output_artifact_id: str,
) -> None:
    """Require a local artifact content record bound to this exact receipt."""

    if await session.get(ResearchArtifact, output_artifact_id) is None:
        raise ValueError("RESEARCH_STAGE_ATTEMPT_ARTIFACT_NOT_FOUND")
    binding = await session.scalar(
        select(ResearchStageArtifactBinding)
        .where(
            ResearchStageArtifactBinding.user_id == task.user_id,
            ResearchStageArtifactBinding.run_id == task.run_id,
            ResearchStageArtifactBinding.task_id == task.id,
            ResearchStageArtifactBinding.stage_attempt_id == attempt.id,
            ResearchStageArtifactBinding.artifact_id == output_artifact_id,
        )
        .with_for_update()
    )
    if binding is None or attempt.run_id != task.run_id:
        raise ValueError("RESEARCH_STAGE_ATTEMPT_ARTIFACT_BINDING_REQUIRED")
    content = await session.get(ResearchArtifactContent, output_artifact_id)
    if content is None:
        raise ValueError("RESEARCH_STAGE_ATTEMPT_ARTIFACT_CONTENT_REQUIRED")
    artifact = await session.get(ResearchArtifact, output_artifact_id)
    if artifact is None:
        raise ValueError("RESEARCH_STAGE_ATTEMPT_ARTIFACT_NOT_FOUND")
    payload = bytes(content.content)
    if sha256(payload).hexdigest() != artifact.content_hash or len(payload) != artifact.size_bytes:
        raise ValueError("RESEARCH_STAGE_ATTEMPT_ARTIFACT_CONTENT_INTEGRITY_INVALID")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("RESEARCH_STAGE_ATTEMPT_TIMESTAMP_TIMEZONE_REQUIRED")
    return value.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _replayed_generation_output_artifact_id(
    session: Any,
    *,
    attempt: ResearchStageAttempt,
    proposal: GenerationMaterializationProposal,
) -> str:
    """Resolve only the exact persisted terminal GENERATE receipt on replay."""

    relation = await session.scalar(
        select(ResearchGenerationMaterialization)
        .where(ResearchGenerationMaterialization.stage_attempt_id == attempt.id)
        .with_for_update()
    )
    if relation is None:
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_NOT_FOUND")
    if (
        relation.model_invocation_id != proposal.model_invocation_id
        or relation.model_output_hash != content_hash({"output": proposal.model_output})
    ):
        raise ValueError("RESEARCH_GENERATION_MATERIALIZATION_CONFLICT")
    return relation.manifest_artifact_id
