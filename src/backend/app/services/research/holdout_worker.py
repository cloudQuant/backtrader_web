"""Production-reachable orchestration for the independent holdout evaluator."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.db import database
from app.models.ai_research_v2 import (
    ResearchEvaluation,
    ResearchHoldoutArtifactBinding,
    ResearchHoldoutEvaluationCommand,
    ResearchHoldoutExecution,
)
from app.services.research.database_clock import DatabaseUtcNow
from app.services.research.evidence_package import EvidencePackageService
from app.services.research.holdout_claim import (
    ClaimedHoldoutEvaluation,
    HoldoutClaimService,
    HoldoutEvaluatorRuntimeIdentity,
)
from app.services.research.holdout_execution_contract import (
    HoldoutExecutionCommand,
    HoldoutExecutionResult,
    SealedHoldoutExecutor,
)
from app.services.research.holdout_execution_journal import HoldoutExecutionJournal
from app.services.research.holdout_finalize import HoldoutFinalizeService
from app.services.research.promotion import (
    promotion_policy_material_hash,
    resolve_server_policy,
)


@dataclass(frozen=True, slots=True)
class HoldoutWorkerResult:
    """Safe result of one bounded command poll."""

    command_id: str
    status: str
    error_code: str | None
    evidence_package_id: str | None = None


class HoldoutEvaluationWorker:
    """Claim, dispatch, checkpoint, finalize, and package holdout commands."""

    def __init__(
        self,
        *,
        executor: SealedHoldoutExecutor,
        runtime: HoldoutEvaluatorRuntimeIdentity,
        claim_service: HoldoutClaimService,
        finalize_service: HoldoutFinalizeService,
        evidence_service: EvidencePackageService,
        journal: HoldoutExecutionJournal | None = None,
        heartbeat_interval_seconds: float = 30.0,
    ) -> None:
        if (
            not hasattr(executor, "execute")
            or not hasattr(executor, "inspect")
            or not isinstance(runtime, HoldoutEvaluatorRuntimeIdentity)
            or type(heartbeat_interval_seconds) not in {int, float}
            or heartbeat_interval_seconds <= 0
        ):
            raise ValueError("HOLDOUT_WORKER_CONFIGURATION_INVALID")
        self._executor = executor
        self._runtime = runtime
        self._claims = claim_service
        self._finalize = finalize_service
        self._evidence = evidence_service
        self._journal = journal or HoldoutExecutionJournal()
        self._heartbeat_interval = float(heartbeat_interval_seconds)
        # Raw lease tokens are deliberately ephemeral.  They are retained only
        # by the process that received the claim receipt and never persisted or
        # reconstructed after a crash.
        self._active_lease_tokens: dict[tuple[str, int], str] = {}

    async def run_once(self, limit: int = 10) -> list[HoldoutWorkerResult]:
        """Process a bounded, server-discovered command set once."""

        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("HOLDOUT_WORKER_LIMIT_INVALID")
        commands = await self._due_commands(limit)
        results: list[HoldoutWorkerResult] = []
        for command in commands:
            try:
                result = await self._process(command)
            except ValueError as exc:
                code = _safe_code(exc)
                if code in {"HOLDOUT_CLAIM_ALREADY_STARTED", "HOLDOUT_CLAIM_NOT_RUNNING"}:
                    continue
                result = HoldoutWorkerResult(
                    command_id=command.id,
                    status="FAILED",
                    error_code=code,
                )
            except Exception:
                result = HoldoutWorkerResult(
                    command_id=command.id,
                    status="FAILED",
                    error_code="HOLDOUT_WORKER_FAILED",
                )
            results.append(result)
        return results

    async def _due_commands(self, limit: int) -> list[ResearchHoldoutEvaluationCommand]:
        async with database.async_session_maker() as session:
            return list(
                (
                    await session.scalars(
                        select(ResearchHoldoutEvaluationCommand)
                        .where(
                            ResearchHoldoutEvaluationCommand.status.in_(
                                ("QUEUED", "RUNNING", "RECONCILING", "SUCCEEDED")
                            )
                        )
                        .order_by(
                            ResearchHoldoutEvaluationCommand.created_at.asc(),
                            ResearchHoldoutEvaluationCommand.id.asc(),
                        )
                        .limit(limit)
                    )
                ).all()
            )

    async def _process(
        self,
        seed: ResearchHoldoutEvaluationCommand,
    ) -> HoldoutWorkerResult:
        if seed.status == "SUCCEEDED":
            return await self._complete_terminal(seed.id)
        if seed.status == "RECONCILING" and await self._has_checkpoint(seed.id):
            return await self._reconcile(seed.id)

        claimed: ClaimedHoldoutEvaluation | None = None
        if seed.status == "QUEUED":
            claimed = await self._claims.claim(command_id=seed.id, runtime=self._runtime)
            self._active_lease_tokens[(claimed.command_id, claimed.lease_generation)] = (
                claimed.lease_token
            )
        command = await self._execution_command(seed.id)
        if claimed is not None and (
            claimed.evaluation_id != command.snapshot["evaluation_id"]
            or claimed.lease_generation != command.snapshot["lease_generation"]
        ):
            raise ValueError("HOLDOUT_WORKER_CLAIM_INCONSISTENT")

        user_id = await self._command_user_id(seed.id)
        try:
            record = await self._journal.read(command=command, user_id=user_id)
        except ValueError as exc:
            if str(exc) != "HOLDOUT_EXECUTION_NOT_FOUND":
                raise
            lease_owner = await self._command_lease_owner(seed.id)
            if claimed is None and lease_owner != self._runtime.worker_identity:
                return HoldoutWorkerResult(
                    command_id=seed.id,
                    status="WAITING",
                    error_code="HOLDOUT_WORKER_FOREIGN_ACTIVE_LEASE",
                )
            record = await self._journal.prepare(
                user_id=user_id,
                lease_owner=lease_owner,
                command=command,
            )

        result: HoldoutExecutionResult | None = None
        lease_token = None if seed.status == "RECONCILING" else self._lease_token(command)
        inspect_prepared = record.state == "PREPARED" and lease_token is None
        if inspect_prepared and await self._lease_is_active(command):
            return HoldoutWorkerResult(
                command_id=seed.id,
                status="WAITING",
                error_code="HOLDOUT_WORKER_FOREIGN_ACTIVE_LEASE",
            )
        if record.state in {"IN_FLIGHT", "UNKNOWN"} or inspect_prepared:
            inspection = await self._executor.inspect(command)
            if inspection.status == "UNKNOWN":
                if record.state != "UNKNOWN":
                    record = await self._journal.record_unknown(
                        user_id=user_id,
                        command=command,
                        error_code=inspection.error_code or "HOLDOUT_REMOTE_OUTCOME_UNKNOWN",
                    )
                return HoldoutWorkerResult(
                    command_id=seed.id,
                    status="UNKNOWN",
                    error_code=record.error_code or "HOLDOUT_REMOTE_OUTCOME_UNKNOWN",
                )
            if inspection.status == "NOT_EXECUTED":
                record = await self._journal.record_not_executed(
                    user_id=user_id,
                    command=command,
                    inspection=inspection,
                )
            else:
                assert inspection.result is not None
                record = await self._journal.record_result(
                    user_id=user_id,
                    command=command,
                    result=inspection.result,
                )
                result = inspection.result

        if record.state == "PREPARED":
            won = await self._journal.begin_dispatch(
                user_id=user_id,
                lease_owner=record.lease_owner,
                command=command,
                actor_identity=self._runtime.worker_identity,
            )
            if not won:
                return HoldoutWorkerResult(seed.id, "IN_FLIGHT", None)
            try:
                result = await self._execute_with_heartbeat(
                    command,
                    lease_token=self._lease_token(command),
                )
            except ValueError as exc:
                code = _safe_code(exc)
                await self._journal.record_unknown(
                    user_id=user_id,
                    command=command,
                    error_code=code,
                )
                return HoldoutWorkerResult(seed.id, "UNKNOWN", code)
            record = await self._journal.record_result(
                user_id=user_id,
                command=command,
                result=result,
            )

        if result is None and record.result_json is not None:
            result = HoldoutExecutionResult.from_mapping(record.result_json, command=command)
        if result is None:
            return HoldoutWorkerResult(seed.id, record.state, record.error_code)
        if result.snapshot["status"] != "SUCCEEDED":
            return HoldoutWorkerResult(seed.id, "FAILED", result.snapshot["error_code"])
        if lease_token is None:
            if await self._has_checkpoint(seed.id):
                if await self._lease_is_active(command):
                    return HoldoutWorkerResult(
                        seed.id,
                        "OBSERVED",
                        "HOLDOUT_WORKER_LEASE_ACTIVE",
                    )
                await self._claims.recover_expired(
                    command_id=seed.id,
                    runtime=self._runtime,
                )
                finalized = await self._finalize.reconcile_checkpointed_evaluation(
                    command_id=seed.id,
                    runtime=self._runtime,
                )
                return await self._package_and_settle(
                    command=command,
                    user_id=user_id,
                    finalized=finalized,
                )
            try:
                await self._finalize.checkpoint_observed_execution(
                    command_id=seed.id,
                    operation_id=str(command.snapshot["operation_id"]),
                    runtime=self._runtime,
                )
            except ValueError as exc:
                if str(exc) == "HOLDOUT_FINALIZE_EXECUTION_LEASE_ACTIVE":
                    return HoldoutWorkerResult(
                        seed.id,
                        "OBSERVED",
                        "HOLDOUT_WORKER_LEASE_ACTIVE",
                    )
                raise
            finalized = await self._finalize.reconcile_checkpointed_evaluation(
                command_id=seed.id,
                runtime=self._runtime,
            )
            return await self._package_and_settle(
                command=command,
                user_id=user_id,
                finalized=finalized,
            )
        return await self._checkpoint_finalize_package(
            command=command,
            user_id=user_id,
            result=result,
            lease_token=lease_token,
        )

    async def _execute_with_heartbeat(
        self,
        command: HoldoutExecutionCommand,
        *,
        lease_token: str | None,
    ) -> HoldoutExecutionResult:
        if lease_token is None:
            return await self._executor.execute(command)
        stop = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._heartbeat(command, lease_token, stop),
            name=f"holdout-heartbeat:{command.snapshot['command_id']}",
        )
        try:
            return await self._executor.execute(command)
        finally:
            stop.set()
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

    async def _heartbeat(
        self,
        command: HoldoutExecutionCommand,
        lease_token: str,
        stop: asyncio.Event,
    ) -> None:
        snapshot = command.snapshot
        while not stop.is_set():
            await asyncio.sleep(self._heartbeat_interval)
            if stop.is_set():
                return
            await self._claims.heartbeat(
                command_id=str(snapshot["command_id"]),
                runtime=self._runtime,
                lease_token=lease_token,
                lease_generation=int(snapshot["lease_generation"]),
            )

    async def _checkpoint_finalize_package(
        self,
        *,
        command: HoldoutExecutionCommand,
        user_id: str,
        result: HoldoutExecutionResult,
        lease_token: str,
    ) -> HoldoutWorkerResult:
        snapshot = command.snapshot
        try:
            await self._finalize.checkpoint_execution_receipt(
                command_id=str(snapshot["command_id"]),
                operation_id=str(snapshot["operation_id"]),
                runtime=self._runtime,
                lease_token=lease_token,
                lease_generation=int(snapshot["lease_generation"]),
            )
            finalized = await self._finalize.finalize_claimed_evaluation(
                command_id=str(snapshot["command_id"]),
                runtime=self._runtime,
                lease_token=lease_token,
                lease_generation=int(snapshot["lease_generation"]),
            )
        except ValueError as exc:
            code = str(exc)
            if code not in {
                "HOLDOUT_FINALIZE_LEASE_EXPIRED",
                "HOLDOUT_FINALIZE_LEASE_STALE",
            }:
                raise
            if await self._has_checkpoint(str(snapshot["command_id"])):
                await self._claims.recover_expired(
                    command_id=str(snapshot["command_id"]),
                    runtime=self._runtime,
                )
            else:
                await self._finalize.checkpoint_observed_execution(
                    command_id=str(snapshot["command_id"]),
                    operation_id=str(snapshot["operation_id"]),
                    runtime=self._runtime,
                )
            finalized = await self._finalize.reconcile_checkpointed_evaluation(
                command_id=str(snapshot["command_id"]),
                runtime=self._runtime,
            )
        return await self._package_and_settle(
            command=command,
            user_id=user_id,
            finalized=finalized,
        )

    async def _package_and_settle(
        self,
        *,
        command: HoldoutExecutionCommand,
        user_id: str,
        finalized: Any,
    ) -> HoldoutWorkerResult:
        package_id: str | None = None
        if finalized.evaluation_status == "PASSED":
            package = await self._evidence.build_for_terminal_command(
                user_id=user_id,
                command_id=finalized.command_id,
            )
            package_id = package.id
        await self._journal.settle(user_id=user_id, command=command)
        snapshot = command.snapshot
        self._active_lease_tokens.pop(
            (str(snapshot["command_id"]), int(snapshot["lease_generation"])),
            None,
        )
        return HoldoutWorkerResult(
            command_id=finalized.command_id,
            status=finalized.evaluation_status,
            error_code=None,
            evidence_package_id=package_id,
        )

    async def _reconcile(self, command_id: str) -> HoldoutWorkerResult:
        if not await self._has_checkpoint(command_id):
            return HoldoutWorkerResult(
                command_id=command_id,
                status="UNKNOWN",
                error_code="HOLDOUT_WORKER_UNCHECKPOINTED_RECONCILIATION",
            )
        finalized = await self._finalize.reconcile_checkpointed_evaluation(
            command_id=command_id,
            runtime=self._runtime,
        )
        return await self._complete_terminal(finalized.command_id)

    async def _complete_terminal(self, command_id: str) -> HoldoutWorkerResult:
        async with database.async_session_maker() as session:
            command = await session.get(ResearchHoldoutEvaluationCommand, command_id)
            evaluation = (
                await session.get(ResearchEvaluation, command.evaluation_id)
                if command is not None and command.evaluation_id is not None
                else None
            )
        if command is None or command.status != "SUCCEEDED" or evaluation is None:
            raise ValueError("HOLDOUT_WORKER_TERMINAL_INVALID")
        package_id: str | None = None
        if evaluation.status == "PASSED":
            package = await self._evidence.build_for_terminal_command(
                user_id=command.user_id,
                command_id=command.id,
            )
            package_id = package.id
        execution_command = await self._execution_command_from_journal(command.id)
        if execution_command is not None:
            record = await self._journal.read(command=execution_command, user_id=command.user_id)
            if record.state == "OBSERVED":
                await self._journal.settle(user_id=command.user_id, command=execution_command)
        return HoldoutWorkerResult(
            command_id=command.id,
            status=evaluation.status,
            error_code=None,
            evidence_package_id=package_id,
        )

    async def _execution_command(self, command_id: str) -> HoldoutExecutionCommand:
        async with database.async_session_maker() as session:
            model = await session.get(ResearchHoldoutEvaluationCommand, command_id)
        if model is None:
            raise ValueError("HOLDOUT_WORKER_COMMAND_NOT_FOUND")
        if model.evaluation_id is None:
            raise ValueError("HOLDOUT_WORKER_COMMAND_NOT_CLAIMED")
        operation_id = hashlib.sha256(f"holdout-operation:{model.id}".encode()).hexdigest()
        return HoldoutExecutionCommand.from_mapping(
            {
                "schema_version": "holdout-execution-command-v2",
                "operation_id": operation_id,
                "command_id": model.id,
                "evaluation_id": model.evaluation_id,
                "authorization_id": model.authorization_id,
                "experiment_epoch_id": model.experiment_epoch_id,
                "request_hash": model.request_hash,
                "candidate_id": model.candidate_id,
                "candidate_hash": model.candidate_hash,
                "dataset_snapshot_id": model.dataset_snapshot_id,
                "sealed_dataset_hash": model.sealed_dataset_hash,
                "sealed_dataset_identity_hash": model.sealed_dataset_identity_hash,
                "freeze_receipt_fingerprint": model.freeze_receipt_fingerprint,
                "capability_evidence_hash": model.capability_evidence_hash,
                "policy_version": model.policy_version,
                "promotion_policy_hash": promotion_policy_material_hash(
                    resolve_server_policy(model.policy_version)
                ),
                "evaluator_identity": model.evaluator_identity,
                "evaluator_image_digest": model.evaluator_version,
                "lease_generation": model.lease_generation,
            }
        )

    async def _execution_command_from_journal(
        self,
        command_id: str,
    ) -> HoldoutExecutionCommand | None:
        async with database.async_session_maker() as session:
            record = await session.scalar(
                select(ResearchHoldoutExecution).where(
                    ResearchHoldoutExecution.command_id == command_id
                )
            )
        if record is None:
            return None
        return HoldoutExecutionCommand.from_mapping(dict(record.command_json))

    async def _command_user_id(self, command_id: str) -> str:
        async with database.async_session_maker() as session:
            command = await session.get(ResearchHoldoutEvaluationCommand, command_id)
        if command is None:
            raise ValueError("HOLDOUT_WORKER_COMMAND_NOT_FOUND")
        return command.user_id

    async def _command_lease_owner(self, command_id: str) -> str:
        async with database.async_session_maker() as session:
            command = await session.get(ResearchHoldoutEvaluationCommand, command_id)
        if command is None or not command.lease_owner:
            raise ValueError("HOLDOUT_WORKER_COMMAND_NOT_RUNNING")
        return command.lease_owner

    def _lease_token(self, command: HoldoutExecutionCommand) -> str | None:
        snapshot = command.snapshot
        return self._active_lease_tokens.get(
            (str(snapshot["command_id"]), int(snapshot["lease_generation"]))
        )

    async def _has_checkpoint(self, command_id: str) -> bool:
        async with database.async_session_maker() as session:
            binding_id = await session.scalar(
                select(ResearchHoldoutArtifactBinding.id).where(
                    ResearchHoldoutArtifactBinding.command_id == command_id
                )
            )
        return binding_id is not None

    async def _lease_is_active(self, command: HoldoutExecutionCommand) -> bool:
        snapshot = command.snapshot
        async with database.async_session_maker() as session:
            active_id = await session.scalar(
                select(ResearchHoldoutEvaluationCommand.id).where(
                    ResearchHoldoutEvaluationCommand.id == str(snapshot["command_id"]),
                    ResearchHoldoutEvaluationCommand.status == "RUNNING",
                    ResearchHoldoutEvaluationCommand.stage == "HOLDOUT_PENDING",
                    ResearchHoldoutEvaluationCommand.error_code.is_(None),
                    ResearchHoldoutEvaluationCommand.lease_owner.is_not(None),
                    ResearchHoldoutEvaluationCommand.lease_token_hash.is_not(None),
                    ResearchHoldoutEvaluationCommand.lease_generation
                    == int(snapshot["lease_generation"]),
                    ResearchHoldoutEvaluationCommand.lease_expires_at.is_not(None),
                    ResearchHoldoutEvaluationCommand.lease_expires_at > DatabaseUtcNow(),
                )
            )
        return active_id is not None


def _safe_code(exc: ValueError) -> str:
    value = str(exc)
    if value.startswith(("HOLDOUT_", "EVIDENCE_", "PROMOTION_")) and len(value) <= 128:
        return value
    return "HOLDOUT_WORKER_FAILED"
