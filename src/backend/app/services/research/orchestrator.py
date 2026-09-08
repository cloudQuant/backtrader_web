"""Thin protocol-v2 orchestration facade over independently owned aggregates."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.db import database
from app.models.ai_research_v2 import (
    ResearchApprovalRequest,
    ResearchCandidate,
    ResearchEvaluation,
    ResearchEvidencePackage,
    ResearchGateDecision,
    ResearchGovernanceDecision,
    ResearchHoldoutEvaluationCommand,
    ResearchHumanDecision,
    ResearchHypothesisVersion,
    ResearchModelInvocation,
    ResearchRun,
    ResearchTask,
    ResearchTrial,
)
from app.services.research.approval import (
    approval_decision_record_intent_hash,
    safe_approval_human_text,
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.holdout_execution_contract import REQUIRED_HOLDOUT_GATE_CODES
from app.services.research.redaction import redact_sensitive_payload
from app.services.research.task_runner import DurableResearchTaskRunner, ResearchTaskService


class ResearchOrchestrator:
    """Route v2 submit/read/cancel without making legacy state authoritative."""

    def __init__(
        self,
        *,
        task_service: ResearchTaskService | None = None,
        task_runner: DurableResearchTaskRunner | None = None,
    ) -> None:
        self._tasks = task_service or ResearchTaskService()
        self._runner = task_runner or DurableResearchTaskRunner()

    async def submit(self, **kwargs: Any) -> dict[str, Any]:
        """Submit a fully bound protocol-v2 run through the durable task aggregate."""

        submitted = await self._tasks.submit(**kwargs)
        return {"run": _run_payload(submitted.run), "task": _task_payload(submitted.task)}

    async def list_tasks(
        self,
        *,
        user_id: str,
        cursor: str | None = None,
        limit: int = 20,
        active_only: bool = False,
    ) -> dict[str, Any]:
        """Return only safe task summaries for the authenticated owner."""

        tasks, next_cursor = await self._tasks.list_for_user(
            user_id=user_id,
            cursor=cursor,
            limit=limit,
            active_only=active_only,
        )
        return {"items": [_task_payload(task) for task in tasks], "next_cursor": next_cursor}

    async def get_task(self, *, user_id: str, task_id: str) -> dict[str, Any] | None:
        """Read one task while hiding both absent and foreign resources."""

        task = await self._tasks.get_for_user(user_id=user_id, task_id=task_id)
        return _task_payload(task) if task is not None else None

    async def list_task_events(
        self,
        *,
        user_id: str,
        task_id: str,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any] | None:
        """Return one owner-scoped stream of display-safe task transition summaries."""

        task, events, next_cursor, resume_cursor = await self._tasks.list_events_for_user(
            user_id=user_id,
            task_id=task_id,
            cursor=cursor,
            limit=limit,
        )
        if task is None:
            return None
        if resume_cursor is None:
            raise RuntimeError("RESEARCH_TASK_EVENT_RESUME_CURSOR_MISSING")
        return {
            "items": [_task_event_payload(event) for event in events],
            "next_cursor": next_cursor,
            "resume_cursor": resume_cursor,
        }

    async def get_workbench(self, user_id: str, run_id: str) -> dict[str, Any] | None:
        """Return an owner-scoped, redacted v2 evidence workbench projection."""

        async with database.async_session_maker() as session:
            run_result = await session.execute(
                select(ResearchRun).where(ResearchRun.id == run_id, ResearchRun.user_id == user_id)
            )
            run = run_result.scalar_one_or_none()
            if run is None:
                return None
            hypothesis = await session.get(ResearchHypothesisVersion, run.hypothesis_version_id)
            task_result = await session.execute(
                select(ResearchTask)
                .where(ResearchTask.run_id == run.id, ResearchTask.user_id == user_id)
                .order_by(ResearchTask.created_at.desc())
            )
            task = task_result.scalars().first()
            candidates_result = await session.execute(
                select(ResearchCandidate)
                .where(ResearchCandidate.run_id == run.id, ResearchCandidate.user_id == user_id)
                .order_by(ResearchCandidate.created_at.asc())
            )
            candidates = list(candidates_result.scalars())
            holdout_commands_result = await session.execute(
                select(ResearchHoldoutEvaluationCommand)
                .where(
                    ResearchHoldoutEvaluationCommand.run_id == run.id,
                    ResearchHoldoutEvaluationCommand.user_id == user_id,
                )
                .order_by(
                    ResearchHoldoutEvaluationCommand.created_at.asc(),
                    ResearchHoldoutEvaluationCommand.id.asc(),
                )
            )
            holdout_commands = list(holdout_commands_result.scalars())
            trials_result = await session.execute(
                select(ResearchTrial)
                .where(ResearchTrial.run_id == run.id, ResearchTrial.user_id == user_id)
                .order_by(ResearchTrial.ordinal.asc())
            )
            trials = list(trials_result.scalars())
            invocations_result = await session.execute(
                select(ResearchModelInvocation)
                .where(ResearchModelInvocation.run_id == run.id)
                .order_by(
                    ResearchModelInvocation.created_at.asc(), ResearchModelInvocation.id.asc()
                )
            )
            model_invocations = list(invocations_result.scalars())
            packages_result = await session.execute(
                select(ResearchEvidencePackage)
                .where(
                    ResearchEvidencePackage.run_id == run.id,
                    ResearchEvidencePackage.user_id == user_id,
                )
                .order_by(
                    ResearchEvidencePackage.created_at.asc(), ResearchEvidencePackage.id.asc()
                )
            )
            evidence_packages = list(packages_result.scalars())
            candidate_ids = tuple(candidate.id for candidate in candidates)
            evaluations: list[ResearchEvaluation] = []
            gates: list[ResearchGateDecision] = []
            approval_requests: list[ResearchApprovalRequest] = []
            decisions: list[ResearchHumanDecision] = []
            governance_result = await session.execute(
                select(ResearchGovernanceDecision)
                .where(ResearchGovernanceDecision.actor_id == user_id)
                .order_by(
                    ResearchGovernanceDecision.effective_at.asc(),
                    ResearchGovernanceDecision.id.asc(),
                )
            )
            governance_decisions = [
                decision
                for decision in governance_result.scalars()
                if _governance_scope_matches(
                    decision.scope,
                    run_id=run.id,
                    candidate_ids=frozenset(candidate_ids),
                )
            ]
            if candidate_ids:
                evaluations_result = await session.execute(
                    select(ResearchEvaluation)
                    .where(ResearchEvaluation.candidate_id.in_(candidate_ids))
                    .order_by(ResearchEvaluation.completed_at.asc(), ResearchEvaluation.id.asc())
                )
                evaluations = list(evaluations_result.scalars())
                gates_result = await session.execute(
                    select(ResearchGateDecision)
                    .where(ResearchGateDecision.candidate_id.in_(candidate_ids))
                    .order_by(
                        ResearchGateDecision.evaluated_at.asc(), ResearchGateDecision.id.asc()
                    )
                )
                gates = list(gates_result.scalars())
                approval_requests_result = await session.execute(
                    select(ResearchApprovalRequest)
                    .where(
                        ResearchApprovalRequest.run_id == run.id,
                        ResearchApprovalRequest.candidate_id.in_(candidate_ids),
                        ResearchApprovalRequest.request_material_hash.is_not(None),
                    )
                    .order_by(
                        ResearchApprovalRequest.requested_at.asc(),
                        ResearchApprovalRequest.id.asc(),
                    )
                )
                approval_requests = list(approval_requests_result.scalars())
                decisions_result = await session.execute(
                    select(ResearchHumanDecision)
                    .where(ResearchHumanDecision.candidate_id.in_(candidate_ids))
                    .order_by(
                        ResearchHumanDecision.decided_at.asc(), ResearchHumanDecision.id.asc()
                    )
                )
                decisions = list(decisions_result.scalars())

        dataset = None
        if run.dataset_snapshot_id is not None:
            try:
                visible = await DatasetRegistry().get_for_explorer(user_id, run.dataset_snapshot_id)
            except ValueError:
                visible = None
            if visible is not None:
                dataset = {
                    "id": visible.id,
                    "dataset_policy_version": visible.dataset_policy_version,
                    "partition_kind": visible.partition_kind,
                    "instrument_manifest": redact_sensitive_payload(visible.instrument_manifest),
                    "split_manifest": redact_sensitive_payload(visible.split_manifest),
                    "source_manifest": redact_sensitive_payload(visible.source_manifest),
                    "execution_policy": redact_sensitive_payload(visible.execution_policy),
                    "point_in_time_cutoff": visible.point_in_time_cutoff,
                    "content_hash": visible.content_hash,
                }
        return {
            "run": _run_payload(run),
            "task": _task_payload(task) if task is not None else None,
            "hypothesis": _hypothesis_payload(hypothesis) if hypothesis is not None else None,
            "dataset": dataset,
            "candidates": [_candidate_payload(candidate) for candidate in candidates],
            "holdout_commands": [_holdout_command_payload(command) for command in holdout_commands],
            "ledger": [_trial_payload(trial) for trial in trials],
            "model_invocations": [_model_invocation_payload(item) for item in model_invocations],
            "evaluations": [_evaluation_payload(evaluation) for evaluation in evaluations],
            "gates": [_gate_payload(gate) for gate in gates],
            "approval_requests": [
                _approval_request_payload(request) for request in approval_requests
            ],
            "decisions": [_decision_payload(decision) for decision in decisions],
            "governance_decisions": [
                _governance_decision_payload(decision) for decision in governance_decisions
            ],
            "evidence_packages": [_evidence_package_payload(item) for item in evidence_packages],
            "evidence_class": _evidence_class(
                candidates=candidates,
                trials=trials,
                evaluations=evaluations,
                gates=gates,
                decisions=decisions,
            ),
        }

    async def request_cancel(self, user_id: str, task_id: str) -> dict[str, Any] | None:
        """Persist cancellation intent for an owner-scoped v2 task."""

        changed = await self._runner.request_cancel(user_id, task_id)
        if not changed:
            return None
        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchTask).where(
                    ResearchTask.id == task_id, ResearchTask.user_id == user_id
                )
            )
            task = result.scalar_one_or_none()
        return _task_payload(task) if task is not None else None


def _run_payload(model: ResearchRun) -> dict[str, Any]:
    return {
        "id": model.id,
        "hypothesis_version_id": model.hypothesis_version_id,
        "dataset_snapshot_id": model.dataset_snapshot_id,
        "data_precheck_id": model.data_precheck_id,
        "experiment_epoch_id": model.experiment_epoch_id,
        "protocol_version": model.protocol_version,
        "workflow_version": model.workflow_version,
        "status": model.status,
        "stage_cursor": model.stage_cursor,
        "promotion_policy_version": model.promotion_policy_version,
        "request_hash": model.request_hash,
        "capability_profile_id": model.capability_profile_id,
        "capability_profile_version": model.capability_profile_version,
        "capability_evidence_hash": model.capability_evidence_hash,
        "trace_id": model.trace_id,
        "created_at": model.created_at,
        "started_at": model.started_at,
        "completed_at": model.completed_at,
    }


def _task_payload(model: ResearchTask) -> dict[str, Any]:
    return {
        "id": model.id,
        "run_id": model.run_id,
        "status": model.status,
        "stage_cursor": model.stage_cursor,
        "error_code": model.error_code,
        "trace_id": model.trace_id,
        "cancel_requested_at": model.cancel_requested_at,
        "attempt_count": model.attempt_count,
        "created_at": model.created_at,
        "started_at": model.started_at,
        "completed_at": model.completed_at,
    }


def _task_event_payload(model: Any) -> dict[str, Any]:
    """Expose only the explicitly approved task-event summary fields."""

    return {
        "id": model.id,
        "task_id": model.task_id,
        "run_id": model.run_id,
        "sequence_no": model.sequence_no,
        "event_type": model.event_type,
        "stage": model.stage,
        "status": model.status,
        "error_code": model.error_code,
        "stage_attempt_id": model.stage_attempt_id,
        "trace_id": model.trace_id,
        "created_at": model.created_at,
    }


def _hypothesis_payload(model: ResearchHypothesisVersion) -> dict[str, Any]:
    return {
        "id": model.id,
        "hypothesis_id": model.hypothesis_id,
        "version_no": model.version_no,
        "status": model.status,
        "canonical_payload": redact_sensitive_payload(model.canonical_payload),
        "content_hash": model.content_hash,
        "confirmed_at": model.confirmed_at,
    }


def _holdout_command_payload(model: ResearchHoldoutEvaluationCommand) -> dict[str, Any]:
    """Expose lifecycle state without bearer, lease, or sealed-object material."""

    return {
        "id": model.id,
        "run_id": model.run_id,
        "status": model.status,
        "stage": model.stage,
        "candidate_id": model.candidate_id,
        "candidate_hash": model.candidate_hash,
        "experiment_epoch_id": model.experiment_epoch_id,
        "dataset_snapshot_id": model.dataset_snapshot_id,
        "policy_version": model.policy_version,
        "evaluator_identity": model.evaluator_identity,
        "capability_profile_id": model.capability_profile_id,
        "capability_profile_version": model.capability_profile_version,
        "capability_evidence_hash": model.capability_evidence_hash,
        "evaluation_id": model.evaluation_id,
        "error_code": model.error_code,
        "request_hash": model.request_hash,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }


def _candidate_payload(model: ResearchCandidate) -> dict[str, Any]:
    return {
        "id": model.id,
        "run_id": model.run_id,
        "experiment_epoch_id": model.experiment_epoch_id,
        "source_version_id": model.source_version_id,
        "code_artifact_id": model.code_artifact_id,
        "dependency_artifact_id": model.dependency_artifact_id,
        "candidate_hash": model.candidate_hash,
        "dataset_snapshot_id": model.dataset_snapshot_id,
        "environment_hash": model.environment_hash,
        "cost_model_hash": model.cost_model_hash,
        "params": redact_sensitive_payload(model.params),
        "freeze_status": model.freeze_status,
        "frozen_at": model.frozen_at,
    }


def _trial_payload(model: ResearchTrial) -> dict[str, Any]:
    return {
        "id": model.id,
        "candidate_id": model.candidate_id,
        "ordinal": model.ordinal,
        "stage": model.stage,
        "status": model.status,
        "input_hash": model.input_hash,
        "metrics": redact_sensitive_payload(model.metrics),
        "observed_market_performance": model.observed_market_performance,
        "counts_as_market_trial": model.counts_as_market_trial,
        "counting_reason": model.counting_reason,
        "error_code": model.error_code,
        "completed_at": model.completed_at,
    }


def _evaluation_payload(model: ResearchEvaluation) -> dict[str, Any]:
    """Expose evaluation identity and outcome without measurements or gate inputs."""

    return {
        "id": model.id,
        "experiment_epoch_id": model.experiment_epoch_id,
        "candidate_id": model.candidate_id,
        "dataset_snapshot_id": model.dataset_snapshot_id,
        "evaluation_type": model.evaluation_type,
        "evaluator_identity": model.evaluator_identity,
        "evaluator_version": model.evaluator_version,
        "policy_version": model.policy_version,
        "status": model.status,
        "completed_at": model.completed_at,
    }


def _model_invocation_payload(model: ResearchModelInvocation) -> dict[str, Any]:
    """Expose model lineage without prompt content, output content, or credentials."""

    return {
        "id": model.id,
        "provider": model.provider,
        "requested_model": model.requested_model,
        "resolved_model": model.resolved_model,
        "prompt_template_version": model.prompt_template_version,
        "token_usage": redact_sensitive_payload(model.token_usage),
        "cost": redact_sensitive_payload(model.cost),
        "error_code": model.error_code,
        "created_at": model.created_at,
    }


def _evidence_package_payload(model: ResearchEvidencePackage) -> dict[str, Any]:
    """Return a manifest identity only; raw evidence stays server-controlled."""

    return {
        "id": model.id,
        "candidate_id": model.candidate_id,
        "command_id": model.command_id,
        "evaluation_id": model.evaluation_id,
        "promotion_policy_version": model.promotion_policy_version,
        "gate_input_evidence_hash": model.gate_input_evidence_hash,
        "manifest_hash": model.manifest_hash,
        "approval_binding_hash": model.approval_binding_hash,
        "status": model.status,
        "created_at": model.created_at,
    }


def _gate_payload(model: ResearchGateDecision) -> dict[str, Any]:
    expected_reason = (
        f"HOLDOUT_{model.gate_code}_PASSED"
        if model.gate_code in REQUIRED_HOLDOUT_GATE_CODES and model.status == "PASS"
        else None
    )
    return {
        "id": model.id,
        "candidate_id": model.candidate_id,
        "evaluation_id": model.evaluation_id,
        "gate_code": model.gate_code,
        "policy_version": model.policy_version,
        "input_evidence_hash": model.input_evidence_hash,
        "status": model.status,
        "reason": (
            model.reason
            if expected_reason is not None and model.reason == expected_reason
            else "RESEARCH_GATE_REASON_REDACTED"
        ),
        "evaluated_at": model.evaluated_at,
    }


def _decision_payload(model: ResearchHumanDecision) -> dict[str, Any]:
    return {
        "authority_version": ("v2" if model.decision_material_hash is not None else "legacy"),
        "id": model.id,
        "run_id": model.run_id,
        "candidate_id": model.candidate_id,
        "approval_request_id": model.approval_request_id,
        "decision": model.decision,
        "policy_version": model.policy_version,
        "policy_material_hash": model.policy_material_hash,
        "approval_mode": model.approval_mode,
        "gate_input_evidence_hash": model.gate_input_evidence_hash,
        "risk_acknowledgement": model.risk_acknowledgement,
        "evidence_package_hash": model.evidence_package_hash,
        "decision_material_hash": model.decision_material_hash,
        "decision_intent_hash": (
            approval_decision_record_intent_hash(model)
            if model.decision_material_hash is not None
            else None
        ),
        "challenge_keys": [
            item["key"]
            for item in list(model.challenge_records or [])
            if isinstance(item, dict) and isinstance(item.get("key"), str)
        ],
        "reason": safe_approval_human_text(model.comment or ""),
        "decided_at": model.decided_at,
        "expires_at": model.expires_at,
    }


def _approval_request_payload(model: ResearchApprovalRequest) -> dict[str, Any]:
    """Expose request recovery state without requester or capability internals."""

    return {
        "id": model.id,
        "run_id": model.run_id,
        "candidate_id": model.candidate_id,
        "evidence_package_id": model.evidence_package_id,
        "policy_version": model.policy_version,
        "policy_material_hash": model.policy_material_hash,
        "approval_mode": model.approval_mode,
        "gate_input_evidence_hash": model.gate_input_evidence_hash,
        "evidence_package_hash": model.evidence_package_hash,
        "request_material_hash": model.request_material_hash,
        "status": model.status,
        "requested_at": model.requested_at,
        "eligible_at": model.eligible_at,
        "expires_at": model.expires_at,
        "decided_at": model.decided_at,
    }


def _governance_decision_payload(model: ResearchGovernanceDecision) -> dict[str, Any]:
    """Expose a deviation as a limitation without returning its actor or raw scope."""

    return {
        "id": model.id,
        "target_requirement_or_gate": model.target_requirement_or_gate,
        "original_status": model.original_status,
        "reason": redact_sensitive_payload(model.reason),
        "risk": redact_sensitive_payload(model.risk),
        "compensating_controls": redact_sensitive_payload(model.compensating_controls),
        "effective_at": model.effective_at,
        "expires_at": model.expires_at,
        "revoked_at": model.revoked_at,
    }


def _governance_scope_matches(
    scope: Any,
    *,
    run_id: str,
    candidate_ids: frozenset[str],
) -> bool:
    """Only include deviations bound to this owner-scoped workbench."""

    if not isinstance(scope, dict):
        return False
    return scope.get("run_id") == run_id or scope.get("candidate_id") in candidate_ids


def _evidence_class(
    *,
    candidates: list[ResearchCandidate],
    trials: list[ResearchTrial],
    evaluations: list[ResearchEvaluation],
    gates: list[ResearchGateDecision],
    decisions: list[ResearchHumanDecision],
) -> str:
    """Return the strongest recorded evidence layer without implying a pass."""

    if decisions:
        return "PROTOCOL_V2_HUMAN_DECISION_RECORDED"
    if gates:
        return "PROTOCOL_V2_GATE_DECISIONS_RECORDED"
    if evaluations:
        return "PROTOCOL_V2_EVALUATION_RECORDED"
    if trials:
        return "PROTOCOL_V2_TRIALS_RECORDED"
    if candidates:
        return "PROTOCOL_V2_CANDIDATE_RECORDED"
    return "PROTOCOL_V2_PENDING"
