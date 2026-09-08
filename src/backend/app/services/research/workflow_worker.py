"""External-worker orchestration for durable protocol-v2 research tasks.

This module is deliberately not mounted as a FastAPI background task.  A
deployment-owned worker process must inject the stage executors it is allowed
to run.  Missing executors fail closed rather than turning a queued request
into an invented strategy or local backtest result.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select

from app.db import database
from app.models.ai_research_v2 import ResearchRun, ResearchTask
from app.services.research.generation_materialization import GenerationMaterializationProposal
from app.services.research.stage_attempt import ResearchStageAttemptService
from app.services.research.task_runner import ClaimedResearchTask, DurableResearchTaskRunner
from app.services.research.workflow_graph import expected_next_stage as graph_expected_next_stage
from app.services.research.workflow_graph import workflow_stages
from app.utils.logger import setup_logger

_STAGE_TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED"})
_DEFAULT_WORKFLOW_VERSIONS = ("generation-v1",)

logger = setup_logger(__name__)


@dataclass(frozen=True, slots=True)
class StageExecutionContext:
    """Opaque leased context passed to a deployment-owned stage executor."""

    task_id: str
    run_id: str
    user_id: str
    stage_attempt_id: str
    lease_token: str
    stage: str
    request_hash: str
    trace_id: str | None
    workflow_version: str = "generation-v1"


@dataclass(frozen=True, slots=True)
class StageExecutionOutcome:
    """The only result shape a stage executor may return to the worker."""

    status: str
    next_stage: str | None = None
    output_artifact_id: str | None = None
    error_code: str | None = None
    generation_proposal: GenerationMaterializationProposal | None = None
    discovery_execution_id: str | None = None

    @classmethod
    def succeeded(
        cls,
        *,
        next_stage: str | None = None,
        output_artifact_id: str | None = None,
    ) -> StageExecutionOutcome:
        """Create a completed stage outcome with an optional next stage."""

        return cls(status="SUCCEEDED", next_stage=next_stage, output_artifact_id=output_artifact_id)

    @classmethod
    def failed(
        cls,
        error_code: str,
        *,
        output_artifact_id: str | None = None,
    ) -> StageExecutionOutcome:
        """Create a fail-closed terminal result with an optional diagnostic receipt."""

        return cls(
            status="FAILED",
            error_code=error_code,
            output_artifact_id=output_artifact_id,
        )

    @classmethod
    def generated(
        cls,
        *,
        proposal: GenerationMaterializationProposal,
    ) -> StageExecutionOutcome:
        """Return a typed terminal GENERATE proposal for server-owned persistence.

        An executor may supply the completed, gateway-owned output, but it
        cannot choose a stage artifact or manufacture a candidate.  The stage
        checkpoint service creates both under the current lease transaction.
        """

        return cls(
            status="SUCCEEDED",
            next_stage=None,
            generation_proposal=proposal,
        )

    @classmethod
    def discovered(
        cls,
        execution_id: str,
        *,
        status: str = "SUCCEEDED",
        error_code: str | None = None,
    ) -> StageExecutionOutcome:
        """Return only a typed discovery-journal receipt proposal.

        The journal ID is intentionally the sole externally supplied evidence
        reference.  Stage completion re-reads and verifies that durable journal
        row before it can publish a trial or a terminal task result.
        """

        resolved_error = error_code
        if status != "SUCCEEDED" and resolved_error is None:
            resolved_error = f"RESEARCH_DISCOVERY_EXECUTION_{status}"
        return cls(
            status=status,
            error_code=resolved_error,
            discovery_execution_id=execution_id,
        )

    def validate(self) -> None:
        """Reject ambiguous executor results before they reach persistence."""

        if self.status not in _STAGE_TERMINAL_STATUSES:
            raise ValueError("RESEARCH_STAGE_OUTCOME_STATUS_INVALID")
        if self.status != "SUCCEEDED" and self.next_stage is not None:
            raise ValueError("RESEARCH_STAGE_OUTCOME_NEXT_STAGE_INVALID")
        if self.next_stage is not None and not self.next_stage.strip():
            raise ValueError("RESEARCH_STAGE_OUTCOME_NEXT_STAGE_INVALID")
        if self.status != "SUCCEEDED" and not self.error_code:
            raise ValueError("RESEARCH_STAGE_OUTCOME_ERROR_REQUIRED")
        if self.status == "SUCCEEDED" and self.error_code is not None:
            raise ValueError("RESEARCH_STAGE_OUTCOME_SUCCESS_ERROR_INVALID")
        if self.generation_proposal is not None and self.discovery_execution_id is not None:
            raise ValueError("RESEARCH_STAGE_OUTCOME_PROPOSAL_AMBIGUOUS")
        if self.discovery_execution_id is not None:
            if (
                not isinstance(self.discovery_execution_id, str)
                or not self.discovery_execution_id.strip()
            ):
                raise ValueError("RESEARCH_DISCOVERY_PROPOSAL_ID_INVALID")
            if self.next_stage is not None:
                raise ValueError("RESEARCH_DISCOVERY_PROPOSAL_TRANSITION_INVALID")
            if self.output_artifact_id is not None:
                raise ValueError("RESEARCH_DISCOVERY_PROPOSAL_ARTIFACT_FORBIDDEN")
            return
        if self.generation_proposal is not None:
            if self.status != "SUCCEEDED" or self.next_stage is not None:
                raise ValueError("RESEARCH_GENERATION_PROPOSAL_TRANSITION_INVALID")
            if self.output_artifact_id is not None:
                raise ValueError("RESEARCH_GENERATION_PROPOSAL_ARTIFACT_FORBIDDEN")
            return
        if self.status == "SUCCEEDED" and (
            not isinstance(self.output_artifact_id, str) or not self.output_artifact_id.strip()
        ):
            raise ValueError("RESEARCH_STAGE_OUTCOME_OUTPUT_ARTIFACT_REQUIRED")


class ResearchStageExecutor(Protocol):
    """One stage implementation owned by the deployment worker boundary."""

    async def execute(self, context: StageExecutionContext) -> StageExecutionOutcome:
        """Execute only under the supplied durable task/stage lease."""


@dataclass(frozen=True, slots=True)
class WorkerTaskResult:
    """Terminal task result observed by one worker poll cycle."""

    task_id: str
    status: str
    error_code: str | None


class ResearchProtocolPoller(Protocol):
    """Minimal worker contract owned by the external process lifecycle."""

    async def run_once(self) -> list[WorkerTaskResult]:
        """Perform one bounded recover-and-claim cycle."""


class ResearchProtocolWorker:
    """Claim tasks and sequence only explicitly registered stage executors."""

    def __init__(
        self,
        *,
        task_runner: DurableResearchTaskRunner | None = None,
        stage_attempts: ResearchStageAttemptService | None = None,
        executors: Mapping[str, ResearchStageExecutor] | None = None,
        workflow_versions: tuple[str, ...] = _DEFAULT_WORKFLOW_VERSIONS,
        max_stages_per_task: int = 16,
        heartbeat_interval_seconds: float | None = None,
    ) -> None:
        if max_stages_per_task < 1:
            raise ValueError("RESEARCH_WORKER_MAX_STAGES_INVALID")
        self._workflow_versions = _normalize_workflow_versions(workflow_versions)
        if task_runner is None:
            self._tasks = DurableResearchTaskRunner(workflow_versions=self._workflow_versions)
        else:
            self._tasks = task_runner
            if (
                isinstance(task_runner, DurableResearchTaskRunner)
                and task_runner.workflow_versions != self._workflow_versions
            ):
                raise ValueError("RESEARCH_WORKER_RUNNER_WORKFLOW_MISMATCH")
        self._stage_attempts = stage_attempts or ResearchStageAttemptService()
        self._executors = dict(executors or {})
        self._max_stages_per_task = max_stages_per_task
        resolved_heartbeat_interval = (
            self._tasks.heartbeat_interval_seconds
            if heartbeat_interval_seconds is None
            else heartbeat_interval_seconds
        )
        if (
            resolved_heartbeat_interval <= 0
            or resolved_heartbeat_interval >= self._tasks.lease_seconds
        ):
            raise ValueError("RESEARCH_WORKER_HEARTBEAT_INTERVAL_INVALID")
        self._heartbeat_interval_seconds = resolved_heartbeat_interval

    async def run_once(self) -> list[WorkerTaskResult]:
        """Recover expired leases, then process each newly acquired task once."""

        await self._tasks.recover_expired_leases()
        claims = await self._tasks.claim_due()
        return [await self._execute_claim(claim) for claim in claims]

    @property
    def has_complete_executor_set(self) -> bool:
        """Return whether this sequential core worker can safely claim new tasks."""

        return all(
            self._executors.get(stage) is not None
            for workflow_version in self._workflow_versions
            for stage in workflow_stages(workflow_version)
        )

    async def _execute_claim(self, claim: ClaimedResearchTask) -> WorkerTaskResult:
        task, run = await _leased_task_and_run(
            claim,
            workflow_versions=self._workflow_versions,
        )
        if task is None:
            return WorkerTaskResult(
                task_id=claim.task_id,
                status="TIMED_OUT",
                error_code="RESEARCH_WORKER_LEASE_NOT_CURRENT",
            )
        if run is None:
            # A runner from an incompatible deployment must not finalize an
            # otherwise live task.  Its lease expiry lets a compatible worker
            # recover it under the versioned SQL predicates instead.
            return WorkerTaskResult(
                task_id=claim.task_id,
                status="TIMED_OUT",
                error_code="RESEARCH_WORKER_RUN_BINDING_INVALID",
            )

        heartbeat_stop = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            self._maintain_lease_heartbeat(claim, heartbeat_stop),
            name=f"ai-research-v2-task-heartbeat:{claim.task_id}",
        )
        try:
            return await self._execute_leased_claim(claim, task, run)
        finally:
            heartbeat_stop.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _execute_leased_claim(
        self,
        claim: ClaimedResearchTask,
        task: ResearchTask,
        run: ResearchRun,
    ) -> WorkerTaskResult:
        """Execute one current lease while its lifecycle owns lease renewal."""

        try:
            stage = await self._resume_completed_stage(
                task_id=task.id,
                lease_token=claim.lease_token,
                stage=task.stage_cursor,
                workflow_version=run.workflow_version,
            )
        except ValueError as exc:
            return await self._finalize_error(
                claim,
                error_code=_stage_error_code(str(exc)),
            )
        if stage is None:
            completed = await self._tasks.finalize(
                task.id,
                claim.lease_token,
                status="SUCCEEDED",
            )
            return _result_from_terminal(claim.task_id, completed, fallback_error=None)
        for _ in range(self._max_stages_per_task):
            try:
                expected_next_stage = graph_expected_next_stage(stage, run.workflow_version)
            except ValueError as exc:
                return await self._finalize_error(
                    claim,
                    error_code=_stage_error_code(str(exc)),
                )
            try:
                attempt = await self._stage_attempts.begin(
                    task_id=task.id,
                    lease_token=claim.lease_token,
                    stage=stage,
                    idempotency_key=f"worker:{task.id}:{stage}:{claim.lease_token}",
                    input_payload={
                        "protocol_version": run.protocol_version,
                        "run_id": run.id,
                        "stage": stage,
                        "request_hash": run.request_hash,
                        "workflow_version": run.workflow_version,
                        "expected_next_stage": expected_next_stage,
                    },
                )
            except ValueError as exc:
                return await self._finalize_error(
                    claim,
                    error_code=_stage_error_code(str(exc)),
                )

            executor = self._executors.get(stage)
            if executor is None:
                outcome = StageExecutionOutcome.failed("RESEARCH_STAGE_EXECUTOR_UNAVAILABLE")
            else:
                try:
                    context = StageExecutionContext(
                        task_id=task.id,
                        run_id=run.id,
                        user_id=task.user_id,
                        stage_attempt_id=attempt.id,
                        lease_token=claim.lease_token,
                        stage=stage,
                        request_hash=run.request_hash,
                        trace_id=task.trace_id,
                        workflow_version=run.workflow_version,
                    )
                    outcome = await executor.execute(context)
                    outcome.validate()
                except ValueError as exc:
                    outcome = StageExecutionOutcome.failed(_stage_error_code(str(exc)))
                except Exception:
                    outcome = StageExecutionOutcome.failed("RESEARCH_STAGE_EXECUTOR_FAILED")

            if outcome.generation_proposal is not None:
                if stage != "GENERATE" or outcome.status != "SUCCEEDED":
                    outcome = StageExecutionOutcome.failed(
                        "RESEARCH_GENERATION_PROPOSAL_STAGE_INVALID"
                    )
            elif outcome.discovery_execution_id is not None:
                if stage != "VALIDATE_DISCOVERY" or expected_next_stage is not None:
                    outcome = StageExecutionOutcome.failed(
                        "RESEARCH_DISCOVERY_PROPOSAL_STAGE_INVALID"
                    )
            elif outcome.status == "SUCCEEDED":
                if stage == "GENERATE":
                    # An artifact can diagnose a generic executor response, but
                    # it cannot establish the model invocation/candidate chain.
                    outcome = StageExecutionOutcome.failed(
                        "RESEARCH_GENERATION_CONTRACT_UNAVAILABLE",
                        output_artifact_id=outcome.output_artifact_id,
                    )
                elif stage == "VALIDATE_DISCOVERY":
                    # The final discovery stage is only successful after its
                    # journal receipt is re-read and trial publication validates
                    # it; an arbitrary output artifact cannot substitute.
                    outcome = StageExecutionOutcome.failed(
                        "RESEARCH_DISCOVERY_CONTRACT_UNAVAILABLE",
                        output_artifact_id=outcome.output_artifact_id,
                    )
                elif outcome.next_stage != expected_next_stage:
                    outcome = StageExecutionOutcome.failed("RESEARCH_STAGE_TRANSITION_INVALID")
                elif expected_next_stage is None:
                    # A generic artifact is useful as a diagnostic receipt but
                    # cannot establish candidate or model provenance.
                    outcome = StageExecutionOutcome.failed(
                        "RESEARCH_GENERATION_CONTRACT_UNAVAILABLE",
                        output_artifact_id=outcome.output_artifact_id,
                    )

            try:
                completion_kwargs = {
                    "task_id": task.id,
                    "lease_token": claim.lease_token,
                    "attempt_id": attempt.id,
                    "status": outcome.status,
                    "output_artifact_id": outcome.output_artifact_id,
                    "error_code": outcome.error_code,
                    "next_stage": expected_next_stage if outcome.status == "SUCCEEDED" else None,
                    "generation_proposal": outcome.generation_proposal,
                }
                if outcome.discovery_execution_id is not None:
                    completion_kwargs["discovery_execution_id"] = outcome.discovery_execution_id
                completed_attempt = await self._stage_attempts.complete(
                    **completion_kwargs,
                )
            except ValueError as exc:
                return await self._finalize_error(
                    claim,
                    error_code=_stage_error_code(str(exc)),
                )

            if completed_attempt.status == "CANCELLED":
                return await self._finalize_error(
                    claim,
                    error_code=(
                        completed_attempt.error_code
                        or outcome.error_code
                        or "TASK_CANCEL_REQUESTED"
                    ),
                )
            if outcome.status != "SUCCEEDED":
                return await self._finalize_error(claim, error_code=outcome.error_code)
            if expected_next_stage is None:
                completed = await self._tasks.finalize(
                    task.id,
                    claim.lease_token,
                    status="SUCCEEDED",
                )
                return _result_from_terminal(claim.task_id, completed, fallback_error=None)
            stage = expected_next_stage

        return await self._finalize_error(claim, error_code="RESEARCH_WORKER_STAGE_LIMIT_EXCEEDED")

    async def _maintain_lease_heartbeat(
        self,
        claim: ClaimedResearchTask,
        stop: asyncio.Event,
    ) -> None:
        """Renew the current lease until terminal cleanup starts or ownership is lost."""

        try:
            while True:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self._heartbeat_interval_seconds)
                    return
                except asyncio.TimeoutError:
                    if not await self._tasks.heartbeat(claim.task_id, claim.lease_token):
                        logger.warning(
                            "Trusted AI-research worker lost its task lease while executing: {}",
                            claim.task_id,
                        )
                        return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # If a separate DB renewal cannot complete, lease expiry is still the
            # fail-closed boundary.  A later checkpoint CAS will reject this worker.
            logger.warning("Trusted AI-research task lease heartbeat failed: {}", exc)

    async def _finalize_error(
        self, claim: ClaimedResearchTask, *, error_code: str | None
    ) -> WorkerTaskResult:
        completed = await self._tasks.finalize(
            claim.task_id,
            claim.lease_token,
            status="FAILED",
            error_code=error_code,
        )
        return _result_from_terminal(claim.task_id, completed, fallback_error=error_code)

    async def _resume_completed_stage(
        self,
        *,
        task_id: str,
        lease_token: str,
        stage: str,
        workflow_version: str,
    ) -> str | None:
        """Advance from a durable success receipt without replaying its side effect."""

        expected_next_stage = graph_expected_next_stage(stage, workflow_version)
        resumed = await self._stage_attempts.resume_succeeded_checkpoint(
            task_id=task_id,
            lease_token=lease_token,
            stage=stage,
            next_stage=expected_next_stage,
        )
        if not resumed:
            return stage
        if expected_next_stage is None:
            return None
        return expected_next_stage


async def run_research_protocol_worker(
    worker: ResearchProtocolPoller,
    *,
    stop_event: asyncio.Event,
    poll_interval_seconds: float,
) -> None:
    """Poll a deployment-injected worker until its owning process requests shutdown.

    This deliberately has no FastAPI lifecycle hook or default executor map.
    A separately deployed Explorer process must construct ``worker`` with only
    its approved stage executors and own the stop signal supplied here.
    """

    if poll_interval_seconds <= 0:
        raise ValueError("RESEARCH_WORKER_POLL_INTERVAL_INVALID")
    if isinstance(worker, ResearchProtocolWorker) and not worker.has_complete_executor_set:
        raise ValueError("RESEARCH_WORKER_EXECUTORS_INCOMPLETE")
    while not stop_event.is_set():
        await worker.run_once()
        if stop_event.is_set():
            return
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval_seconds)
        except asyncio.TimeoutError:
            continue


async def _leased_task_and_run(
    claim: ClaimedResearchTask,
    *,
    workflow_versions: tuple[str, ...],
) -> tuple[ResearchTask | None, ResearchRun | None]:
    async with database.async_session_maker() as session:
        task = await session.get(ResearchTask, claim.task_id)
        if task is None or task.status != "RUNNING" or task.lease_token != claim.lease_token:
            return None, None
        run = await session.scalar(
            select(ResearchRun).where(
                ResearchRun.id == task.run_id,
                ResearchRun.protocol_version == "v2",
                ResearchRun.workflow_version.in_(workflow_versions),
            )
        )
        if run is None:
            return task, None
        return task, run


def _result_from_terminal(
    task_id: str,
    completed: ResearchTask | None,
    *,
    fallback_error: str | None,
) -> WorkerTaskResult:
    if completed is None:
        return WorkerTaskResult(
            task_id=task_id,
            status="TIMED_OUT",
            error_code="RESEARCH_WORKER_LEASE_NOT_CURRENT",
        )
    return WorkerTaskResult(
        task_id=task_id,
        status=completed.status,
        error_code=completed.error_code or fallback_error,
    )


def _stage_error_code(error: str) -> str:
    """Persist stable codes only; never copy an exception message into evidence."""

    if error == "RESEARCH_STAGE_ATTEMPT_CANCEL_REQUESTED":
        return "TASK_CANCEL_REQUESTED"
    if error == "RESEARCH_STAGE_ATTEMPT_LEASE_DENIED":
        return "RESEARCH_WORKER_LEASE_NOT_CURRENT"
    if error == "RESEARCH_STAGE_OUTCOME_OUTPUT_ARTIFACT_REQUIRED":
        return "RESEARCH_STAGE_OUTPUT_ARTIFACT_REQUIRED"
    if error in {
        "RESEARCH_WORKFLOW_STAGE_INVALID",
        "RESEARCH_WORKFLOW_VERSION_INVALID",
    }:
        return error
    return "RESEARCH_STAGE_CHECKPOINT_FAILED"


def _normalize_workflow_versions(workflow_versions: tuple[str, ...]) -> tuple[str, ...]:
    """Reject an empty or unknown worker graph set before it can execute work."""

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
