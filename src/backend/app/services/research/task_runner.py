"""Durable task submission, leasing, cancellation, and terminal transitions."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.db import database
from app.models.ai_research_v2 import (
    ResearchDatasetSnapshot,
    ResearchExperimentEpoch,
    ResearchHypothesisVersion,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTaskEvent,
)
from app.services.research.canonical import content_hash
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.data_precheck import ResearchDataPrecheckService
from app.services.research.database_clock import DatabaseUtcNow, database_utc_now
from app.services.research.discovery_search_budget import lock_experiment_epoch
from app.services.research.workflow_graph import workflow_stages

_TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"})
_NON_SUCCESS_TERMINAL_STATUSES = frozenset({"FAILED", "CANCELLED", "TIMED_OUT"})
_DEFAULT_WORKFLOW_VERSIONS = ("generation-v1",)


@dataclass(frozen=True, slots=True)
class SubmittedResearchTask:
    """The idempotent run/task pair returned by a trusted submission."""

    run: ResearchRun
    task: ResearchTask


@dataclass(frozen=True, slots=True)
class ClaimedResearchTask:
    """A task lease that must accompany every worker state transition."""

    task_id: str
    lease_token: str


class ResearchTaskService:
    """Create v2 runs and tasks with request-hash-bound idempotency."""

    def __init__(
        self,
        *,
        data_prechecks: ResearchDataPrecheckService | None = None,
        workflow_version: str = "generation-v1",
    ) -> None:
        """Bind all newly submitted runs to one server-selected workflow graph."""

        workflow_stages(workflow_version)
        self._submit_lock = asyncio.Lock()
        self._data_prechecks = data_prechecks or ResearchDataPrecheckService()
        self._workflow_version = workflow_version

    async def submit(
        self,
        *,
        user_id: str,
        hypothesis_version_id: str,
        dataset_snapshot_id: str,
        experiment_epoch_id: str,
        profile_id: str,
        profile_version: str,
        promotion_policy_version: str,
        request_json: dict[str, Any],
        precheck_id: str | None,
        idempotency_key: str,
        workspace_id: str | None = None,
        trace_id: str | None = None,
        now: datetime | None = None,
    ) -> SubmittedResearchTask:
        """Atomically submit a fully bound v2 run or return its prior result."""

        if not idempotency_key.strip():
            raise ValueError("RESEARCH_TASK_IDEMPOTENCY_KEY_REQUIRED")
        request_hash = content_hash(request_json)
        async with self._submit_lock:
            return await self._submit_once(
                user_id=user_id,
                hypothesis_version_id=hypothesis_version_id,
                dataset_snapshot_id=dataset_snapshot_id,
                experiment_epoch_id=experiment_epoch_id,
                profile_id=profile_id,
                profile_version=profile_version,
                promotion_policy_version=promotion_policy_version,
                request_json=request_json,
                precheck_id=precheck_id,
                request_hash=request_hash,
                idempotency_key=idempotency_key,
                workspace_id=workspace_id,
                trace_id=trace_id or f"research-{uuid.uuid4().hex}",
                now=now,
            )

    async def _submit_once(self, **kwargs: Any) -> SubmittedResearchTask:
        user_id = str(kwargs["user_id"])
        idempotency_key = str(kwargs["idempotency_key"])
        request_hash = str(kwargs["request_hash"])
        async with database.async_session_maker() as session:
            existing = await _existing_submission(session, user_id, idempotency_key)
            if existing is not None:
                return await _resolve_existing_submission(session, existing, request_hash)

            profile = await CapabilityRegistry().get(
                str(kwargs["profile_id"]),
                str(kwargs["profile_version"]),
            )
            decision = await CapabilityRegistry().evaluate(
                str(kwargs["profile_id"]),
                str(kwargs["profile_version"]),
                required=("protocol_v2",),
            )
            if profile is None or not decision.allowed:
                raise ValueError(f"{decision.code}:{','.join(decision.missing_capabilities)}")

            hypothesis = await _confirmed_hypothesis(
                session, user_id, str(kwargs["hypothesis_version_id"])
            )
            if kwargs["request_json"].get("hypothesis_content_hash") != hypothesis.content_hash:
                raise ValueError("RESEARCH_TASK_CONFIRMATION_STALE")
            dataset = await _explorer_dataset(session, user_id, str(kwargs["dataset_snapshot_id"]))
            epoch = await _open_epoch(session, user_id, str(kwargs["experiment_epoch_id"]))
            if epoch.hypothesis_version_id != hypothesis.id:
                raise ValueError("RESEARCH_TASK_EPOCH_HYPOTHESIS_MISMATCH")
            try:
                precheck = await self._data_prechecks.require_current(
                    session,
                    user_id=user_id,
                    precheck_id=kwargs.get("precheck_id"),
                    hypothesis=hypothesis,
                    dataset=dataset,
                    epoch=epoch,
                    profile=profile,
                    profile_id=str(kwargs["profile_id"]),
                    profile_version=str(kwargs["profile_version"]),
                    promotion_policy_version=str(kwargs["promotion_policy_version"]),
                    request_json=dict(kwargs["request_json"]),
                    workspace_id=kwargs.get("workspace_id"),
                    now=kwargs.get("now"),
                )
            except ValueError:
                # A drifted server-attested object must remain quarantined even
                # though the enclosing submission creates no run/task.  The
                # data precheck revalidates while this transaction is active;
                # persist only its FAILED snapshot state before propagating the
                # fence failure.  Earlier validation failures have no writes
                # and are left to the context manager's rollback.
                if dataset.integrity_status == "FAILED":
                    await session.commit()
                raise

            run = ResearchRun(
                user_id=user_id,
                workspace_id=kwargs.get("workspace_id"),
                hypothesis_version_id=hypothesis.id,
                dataset_snapshot_id=dataset.id,
                data_precheck_id=precheck.id,
                experiment_epoch_id=epoch.id,
                protocol_version="v2",
                workflow_version=self._workflow_version,
                status="QUEUED",
                stage_cursor="CLARIFY",
                promotion_policy_version=str(kwargs["promotion_policy_version"]),
                request_hash=request_hash,
                capability_profile_id=profile.profile_id,
                capability_profile_version=profile.version,
                capability_evidence_hash=profile.evidence_hash,
                trace_id=str(kwargs["trace_id"]),
            )
            session.add(run)
            await session.flush()
            task = ResearchTask(
                user_id=user_id,
                run_id=run.id,
                status="QUEUED",
                stage_cursor="CLARIFY",
                request_json=dict(kwargs["request_json"]),
                idempotency_key=idempotency_key,
                idempotency_request_hash=request_hash,
                trace_id=run.trace_id,
            )
            session.add(task)
            try:
                await session.flush()
                await append_research_task_event(
                    session,
                    task,
                    event_type="TASK_SUBMITTED",
                    created_at=kwargs.get("now"),
                )
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await _existing_submission(session, user_id, idempotency_key)
                if existing is None:
                    raise
                return await _resolve_existing_submission(session, existing, request_hash)
            await session.refresh(run)
            await session.refresh(task)
            return SubmittedResearchTask(run=run, task=task)

    async def list_for_user(
        self,
        *,
        user_id: str,
        cursor: str | None = None,
        limit: int = 20,
        active_only: bool = False,
    ) -> tuple[list[ResearchTask], str | None]:
        """List only one owner's task summaries using a stable opaque boundary."""

        boundary = _decode_task_cursor(cursor) if cursor else None
        async with database.async_session_maker() as session:
            statement = select(ResearchTask).where(ResearchTask.user_id == user_id)
            if active_only:
                statement = statement.where(ResearchTask.status.not_in(_TERMINAL_STATUSES))
            if boundary is not None:
                created_at, task_id = boundary
                statement = statement.where(
                    or_(
                        ResearchTask.created_at < created_at,
                        and_(ResearchTask.created_at == created_at, ResearchTask.id < task_id),
                    )
                )
            rows = list(
                (
                    await session.execute(
                        statement.order_by(
                            ResearchTask.created_at.desc(), ResearchTask.id.desc()
                        ).limit(limit + 1)
                    )
                ).scalars()
            )
        visible = rows[:limit]
        next_cursor = _encode_task_cursor(visible[-1]) if len(rows) > limit and visible else None
        return visible, next_cursor

    async def get_for_user(self, *, user_id: str, task_id: str) -> ResearchTask | None:
        """Return a task only when the authenticated owner can read it."""

        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchTask).where(
                    ResearchTask.id == task_id,
                    ResearchTask.user_id == user_id,
                )
            )
            return result.scalar_one_or_none()

    async def list_events_for_user(
        self,
        *,
        user_id: str,
        task_id: str,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[ResearchTask | None, list[ResearchTaskEvent], str | None, str | None]:
        """Read one owner's event stream without querying legacy event payloads."""

        async with database.async_session_maker() as session:
            task = await session.scalar(
                select(ResearchTask).where(
                    ResearchTask.id == task_id,
                    ResearchTask.user_id == user_id,
                )
            )
            if task is None:
                return None, [], None, None
            boundary = _decode_task_event_cursor(cursor) if cursor else None
            if boundary is not None and boundary[0] != task.id:
                raise ValueError("RESEARCH_TASK_CURSOR_INVALID")
            sequence_boundary = boundary[1] if boundary is not None else 0
            if sequence_boundary > task.event_sequence:
                raise ValueError("RESEARCH_TASK_CURSOR_INVALID")
            rows = list(
                (
                    await session.execute(
                        select(ResearchTaskEvent)
                        .where(
                            ResearchTaskEvent.task_id == task.id,
                            ResearchTaskEvent.sequence_no > sequence_boundary,
                        )
                        .order_by(ResearchTaskEvent.sequence_no.asc())
                        .limit(limit + 1)
                    )
                ).scalars()
            )
            visible = rows[:limit]
            resume_sequence = visible[-1].sequence_no if visible else sequence_boundary
            next_cursor = (
                _encode_task_event_cursor(task.id, visible[-1].sequence_no)
                if len(rows) > limit and visible
                else None
            )
            resume_cursor = _encode_task_event_cursor(task.id, resume_sequence)
            return task, visible, next_cursor, resume_cursor


class DurableResearchTaskRunner:
    """Lease tasks with CAS updates; late workers cannot submit terminal state."""

    def __init__(
        self,
        *,
        lease_seconds: int = 900,
        max_batch: int = 20,
        workflow_versions: tuple[str, ...] = _DEFAULT_WORKFLOW_VERSIONS,
    ) -> None:
        if lease_seconds < 1:
            raise ValueError("RESEARCH_TASK_LEASE_SECONDS_INVALID")
        if max_batch < 1:
            raise ValueError("RESEARCH_TASK_MAX_BATCH_INVALID")
        self._lease_seconds = lease_seconds
        self._max_batch = max_batch
        self._workflow_versions = _normalize_workflow_versions(workflow_versions)

    @property
    def lease_seconds(self) -> int:
        """Return the worker lease duration used to validate heartbeat cadence."""

        return self._lease_seconds

    @property
    def heartbeat_interval_seconds(self) -> float:
        """Return a conservative cadence that renews well before lease expiry."""

        return max(0.1, min(self._lease_seconds / 3, 60.0))

    @property
    def workflow_versions(self) -> tuple[str, ...]:
        """Return the exact persisted workflow versions this runner may lease."""

        return self._workflow_versions

    async def claim_due(self, *, now: datetime | None = None) -> list[ClaimedResearchTask]:
        """Atomically claim queued tasks; only successful CAS updates become leases."""

        injected_claim_time = _as_utc(now) if now is not None else None
        claims: list[ClaimedResearchTask] = []
        async with database.async_session_maker() as session:
            claim_time = injected_claim_time or await database_utc_now(session)
            expires_at = claim_time + timedelta(seconds=self._lease_seconds)
            due_tasks = list(
                (
                    await session.execute(
                        select(ResearchTask.id, ResearchTask.run_id)
                        .join(ResearchRun, ResearchRun.id == ResearchTask.run_id)
                        .where(
                            ResearchTask.status == "QUEUED",
                            ResearchTask.lease_token.is_(None),
                            ResearchRun.protocol_version == "v2",
                            ResearchRun.workflow_version.in_(self._workflow_versions),
                        )
                        .order_by(ResearchTask.created_at, ResearchTask.id)
                        .limit(self._max_batch)
                    )
                ).all()
            )
            for task_id, run_id in due_tasks:
                lease_token = uuid.uuid4().hex
                result = await session.execute(
                    update(ResearchTask)
                    .where(
                        ResearchTask.id == task_id,
                        ResearchTask.status == "QUEUED",
                        ResearchTask.lease_token.is_(None),
                        ResearchTask.run_id.in_(_eligible_run_ids(self._workflow_versions)),
                    )
                    .values(
                        status="RUNNING",
                        lease_token=lease_token,
                        lease_expires_at=expires_at,
                        lease_heartbeat_at=claim_time,
                        started_at=claim_time,
                        attempt_count=ResearchTask.attempt_count + 1,
                    )
                )
                if result.rowcount == 1:
                    run_update = await session.execute(
                        update(ResearchRun)
                        .where(
                            ResearchRun.id == run_id,
                            ResearchRun.protocol_version == "v2",
                            ResearchRun.workflow_version.in_(self._workflow_versions),
                        )
                        .values(status="RUNNING", started_at=claim_time)
                    )
                    if run_update.rowcount != 1:
                        raise RuntimeError("RESEARCH_TASK_RUN_STATE_UPDATE_MISSING")
                    task = await session.get(ResearchTask, task_id)
                    if task is None:
                        raise RuntimeError("RESEARCH_TASK_EVENT_TASK_MISSING")
                    await append_research_task_event(
                        session,
                        task,
                        event_type="TASK_CLAIMED",
                        created_at=claim_time,
                    )
                    claims.append(
                        ClaimedResearchTask(task_id=str(task_id), lease_token=lease_token)
                    )
            await session.commit()
        return claims

    async def heartbeat(
        self,
        task_id: str,
        lease_token: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Extend only the current worker's active lease."""

        injected_heartbeat_time = _as_utc(now) if now is not None else None
        async with database.async_session_maker() as session:
            if injected_heartbeat_time is None:
                heartbeat_time = await database_utc_now(session)
                lease_check_time: datetime | DatabaseUtcNow = DatabaseUtcNow()
            else:
                heartbeat_time = injected_heartbeat_time
                lease_check_time = injected_heartbeat_time
            result = await session.execute(
                update(ResearchTask)
                .where(
                    ResearchTask.id == task_id,
                    ResearchTask.status == "RUNNING",
                    ResearchTask.lease_token == lease_token,
                    ResearchTask.lease_expires_at.is_not(None),
                    ResearchTask.lease_expires_at > lease_check_time,
                )
                .values(
                    lease_heartbeat_at=heartbeat_time,
                    lease_expires_at=heartbeat_time + timedelta(seconds=self._lease_seconds),
                )
            )
            await session.commit()
            return result.rowcount == 1

    async def request_cancel(self, user_id: str, task_id: str) -> bool:
        """Cancel queued work immediately and persist intent for leased work."""

        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchTask)
                .where(
                    ResearchTask.id == task_id,
                    ResearchTask.user_id == user_id,
                    ResearchTask.status.not_in(_TERMINAL_STATUSES),
                )
                .with_for_update()
            )
            task = result.scalar_one_or_none()
            if task is None:
                return False
            cancellation_time = _now()
            task.cancel_requested_at = cancellation_time
            if task.status == "QUEUED":
                task.status = "CANCELLED"
                task.completed_at = cancellation_time
                await _complete_run_if_no_active_tasks(
                    session,
                    task.run_id,
                    status="CANCELLED",
                    completed_at=cancellation_time,
                )
            await append_research_task_event(
                session,
                task,
                event_type="TASK_CANCEL_REQUESTED",
                created_at=cancellation_time,
            )
            await session.commit()
            return True

    async def finalize(
        self,
        task_id: str,
        lease_token: str,
        *,
        status: str,
        error_code: str | None = None,
    ) -> ResearchTask | None:
        """Commit one terminal result, making a persisted cancel intent win."""

        if status not in {"SUCCEEDED", "FAILED", "TIMED_OUT"}:
            raise ValueError("RESEARCH_TASK_TERMINAL_STATUS_INVALID")
        async with database.async_session_maker() as session:
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
                return None
            task.status = "CANCELLED" if task.cancel_requested_at is not None else status
            task.error_code = error_code
            task.completed_at = _now()
            task.lease_token = None
            task.lease_expires_at = None
            task.lease_heartbeat_at = None
            await _complete_run_if_no_active_tasks(
                session,
                task.run_id,
                status=task.status,
                completed_at=task.completed_at,
                stage_cursor=task.stage_cursor,
            )
            await append_research_task_event(
                session,
                task,
                event_type="TASK_FINALIZED",
                created_at=task.completed_at,
            )
            await session.commit()
            await session.refresh(task)
            return task

    async def recover_expired_leases(self, *, now: datetime | None = None) -> int:
        """Recover only safe checkpoints and fail closed for uncertain side effects.

        A task whose worker died before it created an external stage attempt is
        safe to requeue under a new lease.  A task with an in-flight stage
        attempt is *not* retried blindly: its external outcome is unknown, so
        the attempt and task remain terminal evidence rather than permitting a
        duplicate provider, sandbox, or holdout operation.
        """

        injected_recovery_time = _as_utc(now) if now is not None else None
        async with database.async_session_maker() as session:
            recovery_time = injected_recovery_time or await database_utc_now(session)
            expired_tasks = list(
                (
                    await session.execute(
                        _expired_task_selection(
                            workflow_versions=self._workflow_versions,
                            recovery_time=recovery_time,
                        )
                    )
                ).scalars()
            )
            recovered_count = 0
            for task in expired_tasks:
                latest_current_stage_attempt = await session.scalar(
                    select(ResearchStageAttempt)
                    .where(
                        ResearchStageAttempt.task_id == task.id,
                        ResearchStageAttempt.stage == task.stage_cursor,
                    )
                    .order_by(ResearchStageAttempt.attempt_no.desc())
                    .limit(1)
                )
                running_attempt = await session.scalar(
                    select(ResearchStageAttempt)
                    .where(
                        ResearchStageAttempt.task_id == task.id,
                        ResearchStageAttempt.status == "RUNNING",
                        ResearchStageAttempt.lease_token == task.lease_token,
                    )
                    .limit(1)
                )
                if task.cancel_requested_at is not None:
                    task.status = "CANCELLED"
                    task.error_code = "TASK_CANCEL_REQUESTED"
                    task.completed_at = recovery_time
                    _clear_lease(task)
                    await _complete_run_if_no_active_tasks(
                        session,
                        task.run_id,
                        status="CANCELLED",
                        completed_at=recovery_time,
                        stage_cursor=task.stage_cursor,
                    )
                elif (
                    latest_current_stage_attempt is not None
                    and latest_current_stage_attempt.status in _NON_SUCCESS_TERMINAL_STATUSES
                ):
                    # A worker can die after stage completion committed but before
                    # it finalizes the task.  Requeueing here would replay an
                    # already observed external operation; retain that immutable
                    # terminal receipt and finish the task from it instead.
                    task.status = latest_current_stage_attempt.status
                    task.error_code = latest_current_stage_attempt.error_code
                    task.completed_at = recovery_time
                    _clear_lease(task)
                    await _complete_run_if_no_active_tasks(
                        session,
                        task.run_id,
                        status=task.status,
                        completed_at=recovery_time,
                        stage_cursor=task.stage_cursor,
                    )
                elif running_attempt is None:
                    task.status = "QUEUED"
                    task.error_code = "TASK_LEASE_RECOVERED"
                    task.completed_at = None
                    _clear_lease(task)
                    await _mark_run_queued_if_no_leased_peer(session, task.run_id)
                else:
                    running_attempt.status = "TIMED_OUT"
                    running_attempt.error_code = "RESEARCH_STAGE_OUTCOME_UNKNOWN"
                    running_attempt.completed_at = recovery_time
                    await append_research_task_event(
                        session,
                        task,
                        event_type="STAGE_ATTEMPT_TIMED_OUT",
                        stage=running_attempt.stage,
                        status=running_attempt.status,
                        error_code=running_attempt.error_code,
                        stage_attempt_id=running_attempt.id,
                        created_at=recovery_time,
                    )
                    task.status = "TIMED_OUT"
                    task.error_code = "RESEARCH_STAGE_OUTCOME_UNKNOWN"
                    task.completed_at = recovery_time
                    _clear_lease(task)
                    await _complete_run_if_no_active_tasks(
                        session,
                        task.run_id,
                        status="TIMED_OUT",
                        completed_at=recovery_time,
                        stage_cursor=task.stage_cursor,
                    )
                await append_research_task_event(
                    session,
                    task,
                    event_type="TASK_LEASE_RECOVERED",
                    created_at=recovery_time,
                )
                recovered_count += 1
            await session.commit()
            return recovered_count


def _normalize_workflow_versions(workflow_versions: tuple[str, ...]) -> tuple[str, ...]:
    """Reject an empty or unknown worker graph set before it can claim work."""

    if isinstance(workflow_versions, str):
        raise ValueError("RESEARCH_WORKFLOW_VERSION_INVALID")
    try:
        supplied = tuple(workflow_versions)
    except TypeError as exc:
        raise ValueError("RESEARCH_WORKFLOW_VERSION_INVALID") from exc
    if not supplied:
        raise ValueError("RESEARCH_WORKFLOW_VERSION_INVALID")
    normalized: list[str] = []
    for workflow_version in supplied:
        workflow_stages(workflow_version)
        if workflow_version not in normalized:
            normalized.append(workflow_version)
    return tuple(normalized)


def _eligible_run_ids(workflow_versions: tuple[str, ...]):
    """Return a SQL subquery used by selection and claim CAS predicates alike."""

    return select(ResearchRun.id).where(
        ResearchRun.protocol_version == "v2",
        ResearchRun.workflow_version.in_(workflow_versions),
    )


def _expired_task_selection(*, workflow_versions: tuple[str, ...], recovery_time: datetime):
    """Select expired tasks while locking only the first task row in the lock order."""

    return (
        select(ResearchTask)
        .join(ResearchRun, ResearchRun.id == ResearchTask.run_id)
        .where(
            ResearchTask.status == "RUNNING",
            ResearchTask.lease_expires_at.is_not(None),
            ResearchTask.lease_expires_at <= recovery_time,
            ResearchRun.protocol_version == "v2",
            ResearchRun.workflow_version.in_(workflow_versions),
        )
        .with_for_update(of=ResearchTask)
    )


async def _existing_submission(session, user_id: str, idempotency_key: str) -> ResearchTask | None:
    result = await session.execute(
        select(ResearchTask).where(
            ResearchTask.user_id == user_id,
            ResearchTask.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def _resolve_existing_submission(
    session, task: ResearchTask, request_hash: str
) -> SubmittedResearchTask:
    if task.idempotency_request_hash != request_hash:
        raise ValueError("RESEARCH_TASK_IDEMPOTENCY_CONFLICT")
    run = await session.get(ResearchRun, task.run_id)
    if run is None:
        raise RuntimeError("RESEARCH_TASK_EXISTING_RUN_MISSING")
    return SubmittedResearchTask(run=run, task=task)


async def _confirmed_hypothesis(
    session, user_id: str, version_id: str
) -> ResearchHypothesisVersion:
    result = await session.execute(
        select(ResearchHypothesisVersion).where(
            ResearchHypothesisVersion.id == version_id,
            ResearchHypothesisVersion.user_id == user_id,
            ResearchHypothesisVersion.status == "CONFIRMED",
        )
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise ValueError("RESEARCH_TASK_HYPOTHESIS_NOT_CONFIRMED")
    return model


async def _explorer_dataset(session, user_id: str, snapshot_id: str) -> ResearchDatasetSnapshot:
    result = await session.execute(
        select(ResearchDatasetSnapshot).where(
            ResearchDatasetSnapshot.id == snapshot_id,
            ResearchDatasetSnapshot.user_id == user_id,
        )
    )
    model = result.scalar_one_or_none()
    if model is None or model.partition_kind == "SEALED_HOLDOUT":
        raise ValueError("RESEARCH_TASK_DATASET_NOT_ELIGIBLE")
    return model


async def _open_epoch(session, user_id: str, epoch_id: str) -> ResearchExperimentEpoch:
    return await lock_experiment_epoch(
        session,
        user_id=user_id,
        epoch_id=epoch_id,
        require_open=True,
        denied_code="RESEARCH_TASK_EPOCH_NOT_OPEN",
    )


def _clear_lease(task: ResearchTask) -> None:
    """Clear an expired ownership fence before another worker can claim it."""

    task.lease_token = None
    task.lease_expires_at = None
    task.lease_heartbeat_at = None


async def append_research_task_event(
    session: Any,
    task: ResearchTask,
    *,
    event_type: str,
    stage: str | None = None,
    status: str | None = None,
    error_code: str | None = None,
    stage_attempt_id: str | None = None,
    created_at: datetime | None = None,
) -> ResearchTaskEvent:
    """Append one safe transition summary inside the caller's existing transaction."""

    if not event_type.strip():
        raise ValueError("RESEARCH_TASK_EVENT_TYPE_REQUIRED")
    sequence_no = await _allocate_research_task_event_sequence(session, task.id)
    event = ResearchTaskEvent(
        user_id=task.user_id,
        task_id=task.id,
        run_id=task.run_id,
        sequence_no=sequence_no,
        event_type=event_type,
        stage=stage or task.stage_cursor,
        status=status or task.status,
        error_code=error_code if error_code is not None else task.error_code,
        stage_attempt_id=stage_attempt_id,
        trace_id=task.trace_id,
        created_at=_as_utc(created_at or _now()),
    )
    session.add(event)
    await session.flush()
    return event


def _supports_update_returning(session: Any) -> bool:
    """Return whether this session's dialect can atomically return an UPDATE value."""

    return bool(session.get_bind().dialect.update_returning)


async def _allocate_research_task_event_sequence(session: Any, task_id: str) -> int:
    """Allocate the next event sequence without trusting a stale ORM snapshot."""

    # ``task`` can have been loaded before a concurrent heartbeat/cancellation
    # transaction.  Allocating from that ORM snapshot can duplicate a sequence
    # number even though the event stream itself is append-only.  Make the task
    # row the atomic allocator instead.  Do not assign the returned value back
    # to the potentially stale ORM instance: a later flush of unrelated task
    # fields must never overwrite a newer allocation made by another session.
    if _supports_update_returning(session):
        sequence_result = await session.execute(
            update(ResearchTask)
            .where(ResearchTask.id == task_id)
            .values(event_sequence=ResearchTask.event_sequence + 1)
            .returning(ResearchTask.event_sequence)
            .execution_options(synchronize_session=False)
        )
        try:
            sequence_no = sequence_result.scalar_one_or_none()
        finally:
            # SQLite keeps a RETURNING cursor active until it is closed.
            sequence_result.close()
        if sequence_no is None:
            raise RuntimeError("RESEARCH_TASK_EVENT_TASK_MISSING")
        return int(sequence_no)

    # MySQL lacks UPDATE ... RETURNING.  Flush the caller's transition first,
    # then lock and refresh the canonical row before allocating.  This keeps a
    # concurrent transaction from observing or reusing the same sequence.
    await session.flush()
    task_result = await session.execute(
        select(ResearchTask)
        .where(ResearchTask.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    current_task = task_result.scalar_one_or_none()
    if current_task is None:
        raise RuntimeError("RESEARCH_TASK_EVENT_TASK_MISSING")
    current_task.event_sequence = int(current_task.event_sequence or 0) + 1
    await session.flush()
    return int(current_task.event_sequence)


async def _mark_run_queued_if_no_leased_peer(session: Any, run_id: str) -> None:
    """Expose a resumed task as queued unless another task still owns the run."""

    leased_peer = await session.scalar(
        select(ResearchTask.id)
        .where(
            ResearchTask.run_id == run_id,
            ResearchTask.status == "RUNNING",
        )
        .limit(1)
    )
    if leased_peer is not None:
        return
    run = await session.get(ResearchRun, run_id)
    if run is None or run.status in _TERMINAL_STATUSES:
        return
    run.status = "QUEUED"
    run.completed_at = None


async def _complete_run_if_no_active_tasks(
    session: Any,
    run_id: str,
    *,
    status: str,
    completed_at: datetime | None,
    stage_cursor: str | None = None,
) -> None:
    """Set a run terminal only after every task attached to it is terminal.

    Retry/recovery tasks may share a run.  A terminal result for one task must
    therefore not hide another queued or leased task from the workbench.
    """

    await session.flush()
    active_task = await session.scalar(
        select(ResearchTask.id)
        .where(
            ResearchTask.run_id == run_id,
            ResearchTask.status.not_in(_TERMINAL_STATUSES),
        )
        .limit(1)
    )
    if active_task is not None:
        return
    run = await session.get(ResearchRun, run_id)
    if run is None or run.status in _TERMINAL_STATUSES:
        return
    run.status = status
    run.completed_at = completed_at
    if stage_cursor is not None:
        run.stage_cursor = stage_cursor


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("RESEARCH_TASK_TIMESTAMP_TIMEZONE_REQUIRED")
    return value.astimezone(timezone.utc)


def _encode_task_cursor(task: ResearchTask) -> str:
    """Encode a task-list boundary without exposing SQL syntax or request payloads."""

    created_at = task.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    payload = json.dumps(
        {
            "v": 1,
            "created_at": created_at.astimezone(timezone.utc).isoformat(),
            "id": task.id,
        },
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_task_cursor(cursor: str) -> tuple[datetime, str]:
    """Decode a strict task-list boundary before it is used in a SQL predicate."""

    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding).decode())
        if set(payload) != {"v", "created_at", "id"} or payload["v"] != 1:
            raise ValueError("shape")
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        task_id = str(payload["id"])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("RESEARCH_TASK_CURSOR_INVALID") from exc
    if not task_id:
        raise ValueError("RESEARCH_TASK_CURSOR_INVALID")
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(timezone.utc), task_id


def _encode_task_event_cursor(task_id: str, sequence_no: int) -> str:
    """Encode one task-local append-only event boundary."""

    payload = json.dumps(
        {"v": 1, "task_id": task_id, "sequence_no": sequence_no}, separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_task_event_cursor(cursor: str) -> tuple[str, int]:
    """Decode a strict task-local event boundary before querying it."""

    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding).decode())
        if set(payload) != {"v", "task_id", "sequence_no"} or payload["v"] != 1:
            raise ValueError("shape")
        task_id = str(payload["task_id"])
        sequence_no = int(payload["sequence_no"])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("RESEARCH_TASK_CURSOR_INVALID") from exc
    if not task_id or sequence_no < 0:
        raise ValueError("RESEARCH_TASK_CURSOR_INVALID")
    return task_id, sequence_no
