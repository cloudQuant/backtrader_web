"""Server-owned, redacted evidence manifests for protocol-v2 approval."""

from __future__ import annotations

import asyncio
import hashlib
import json
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchCandidate,
    ResearchCapabilityProfile,
    ResearchDatasetSnapshot,
    ResearchEvaluation,
    ResearchEvidencePackage,
    ResearchExperimentEpoch,
    ResearchGateDecision,
    ResearchGovernanceDecision,
    ResearchHoldoutAccessAudit,
    ResearchHoldoutArtifactBinding,
    ResearchHoldoutAuthorization,
    ResearchHoldoutEvaluationCommand,
    ResearchHoldoutExecution,
    ResearchHypothesisVersion,
    ResearchModelInvocation,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTrial,
)
from app.services.research.canonical import canonical_json, content_hash
from app.services.research.dataset_registry import (
    DatasetRegistry,
    require_verified_snapshot_integrity,
)
from app.services.research.holdout_claim import (
    HoldoutEvaluatorRuntimeIdentity,
    _load_started_authority,
    _validate_static_locked_authority,
)
from app.services.research.holdout_execution_contract import (
    HoldoutExecutionCommand,
    HoldoutExecutionResult,
)
from app.services.research.holdout_finalize import HoldoutFinalizeService, _load_binding
from app.services.research.promotion import (
    promotion_policy_material_hash,
    resolve_server_policy,
)
from app.services.research.redaction import redact_sensitive_payload

_LEGACY_MANIFEST_VERSION = "ai_research_evidence_manifest/v1"
_MANIFEST_VERSION = "ai_research_evidence_manifest/v2"
_TERMINAL_ACTIONS = frozenset({"FINALIZE_COMPLETED", "RECONCILE_COMPLETED"})
_TRANSITION_ACTIONS = frozenset(
    {
        "LEASE_EXPIRED_RECONCILING",
        "EXECUTION_OBSERVED_RECONCILING",
        "CHECKPOINT_UNKNOWN",
        "FINALIZE_UNKNOWN",
    }
)
_EVIDENCE_AUDIT_ACTIONS = frozenset(
    {"CLAIM_STARTED", "CHECKPOINT_RECORDED", *_TERMINAL_ACTIONS, *_TRANSITION_ACTIONS}
)
_SECURITY_SCAN_KIND = "security_scan_evidence"
_SECURITY_SCAN_SCHEMA = "security-scan-evidence-v1"
_SEALED_RECEIPT_KIND = "sealed_holdout_artifact_receipt"
_SEALED_RECEIPT_SCHEMA = "sealed-holdout-artifact-receipt-v1"
_SEALED_RECEIPT_MEDIA_TYPE = "application/vnd.ai-research.sealed-holdout-receipt+json"
_BUILD_LOCK_SHARD_COUNT = 64
_BUILD_LOCK_SHARDS_BY_LOOP: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    tuple[asyncio.Lock, ...],
] = weakref.WeakKeyDictionary()
_REQUIRED_GATE_CODES = frozenset(
    {
        "CANDIDATE_FROZEN",
        "SEALED_HOLDOUT",
        "EVIDENCE_BINDING",
        "DEFLATED_SHARPE",
        "MAX_DRAWDOWN",
        "ROBUSTNESS",
        "COST",
        "SLIPPAGE",
        "TURNOVER",
        "CAPACITY",
        "EXTREME_PATH",
        "EXECUTION_SEMANTICS",
        "SECURITY_SCAN",
    }
)


@dataclass(frozen=True, slots=True)
class _EvidenceContext:
    """All relational records that must be bound before an approval is valid."""

    strict_freeze_receipt_fingerprint: str
    candidate: ResearchCandidate
    run: ResearchRun
    hypothesis: ResearchHypothesisVersion
    epoch: ResearchExperimentEpoch
    dataset: ResearchDatasetSnapshot
    sealed_dataset: ResearchDatasetSnapshot
    capability_profile: ResearchCapabilityProfile
    command: ResearchHoldoutEvaluationCommand
    authorization: ResearchHoldoutAuthorization
    evaluation: ResearchEvaluation
    artifact_binding: ResearchHoldoutArtifactBinding
    access_audits: list[ResearchHoldoutAccessAudit]
    terminal_access_audit: ResearchHoldoutAccessAudit
    artifacts: dict[str, ResearchArtifact]
    tasks: list[ResearchTask]
    stage_attempts: list[ResearchStageAttempt]
    trials: list[ResearchTrial]
    model_invocations: list[ResearchModelInvocation]
    gates: list[ResearchGateDecision]
    governance_decisions: list[ResearchGovernanceDecision]


@dataclass(frozen=True, slots=True)
class _EvidenceCommitProbe:
    """Exact immutable row expected after a failed COMMIT acknowledgement."""

    package_id: str
    user_id: str
    run_id: str
    candidate_id: str
    command_id: str
    evaluation_id: str
    artifact_binding_id: str
    terminal_access_audit_id: str
    promotion_policy_version: str
    gate_input_evidence_hash: str
    manifest: dict[str, Any]
    manifest_hash: str
    approval_binding_hash: str


class _EvidenceCommitOutcomeUncertain(Exception):
    """Carry an exact package probe when COMMIT was sent but not acknowledged."""

    def __init__(self, probe: _EvidenceCommitProbe) -> None:
        super().__init__("EVIDENCE_PACKAGE_COMMIT_OUTCOME_UNKNOWN")
        self.probe = probe


class EvidencePackageService:
    """Build and verify immutable evidence packages without exposing raw data."""

    def __init__(self, *, dataset_registry: DatasetRegistry | None = None) -> None:
        """Use a deployment-owned resolver before publishing approval evidence."""

        self._datasets = dataset_registry or DatasetRegistry()

    async def build(
        self,
        *,
        user_id: str,
        candidate_id: str,
        promotion_policy_version: str,
        gate_input_evidence_hash: str,
    ) -> ResearchEvidencePackage:
        """Reject the legacy candidate-wide evidence aggregation boundary."""

        raise ValueError("EVIDENCE_PACKAGE_TERMINAL_COMMAND_REQUIRED")

    async def build_for_terminal_command(
        self,
        *,
        user_id: str,
        command_id: str,
    ) -> ResearchEvidencePackage:
        """Build one package from a single server-finalized holdout command graph."""

        if not user_id.strip() or not command_id.strip():
            raise ValueError("EVIDENCE_PACKAGE_TERMINAL_COMMAND_REQUIRED")
        async with _build_lock(user_id, command_id):
            try:
                return await self._build_for_terminal_command_once(
                    user_id=user_id,
                    command_id=command_id,
                )
            except IntegrityError:
                # The database uniqueness constraint is the cross-process
                # authority. Re-run all validation and accept only its exact winner.
                return await self._build_for_terminal_command_once(
                    user_id=user_id,
                    command_id=command_id,
                )
            except _EvidenceCommitOutcomeUncertain as exc:
                committed = await self._read_committed_package(exc.probe)
                if committed is not None:
                    return committed
                raise ValueError("EVIDENCE_PACKAGE_COMMIT_OUTCOME_UNKNOWN") from None

    async def _build_for_terminal_command_once(
        self,
        *,
        user_id: str,
        command_id: str,
    ) -> ResearchEvidencePackage:
        """Validate and persist once while the caller holds the command build shard."""

        async with database.async_session_maker() as session:
            context = await _load_terminal_context(
                session,
                user_id=user_id,
                command_id=command_id,
                dataset_registry=self._datasets,
            )
            material = _material_manifest(context)
            manifest = {"manifest_version": _MANIFEST_VERSION, "material": material}
            manifest_hash = content_hash(manifest)
            approval_binding_hash = content_hash(material)
            result = await session.execute(
                select(ResearchEvidencePackage)
                .where(
                    ResearchEvidencePackage.user_id == user_id,
                    ResearchEvidencePackage.command_id == context.command.id,
                )
                .with_for_update()
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                _require_exact_existing_package(
                    existing,
                    context=context,
                    manifest=manifest,
                    manifest_hash=manifest_hash,
                    approval_binding_hash=approval_binding_hash,
                )
                return existing

            model = ResearchEvidencePackage(
                user_id=user_id,
                run_id=context.run.id,
                candidate_id=context.candidate.id,
                command_id=context.command.id,
                evaluation_id=context.evaluation.id,
                artifact_binding_id=context.artifact_binding.id,
                terminal_access_audit_id=context.terminal_access_audit.id,
                promotion_policy_version=context.command.policy_version,
                gate_input_evidence_hash=_gate_input_hash(context.evaluation),
                manifest=manifest,
                manifest_hash=manifest_hash,
                approval_binding_hash=approval_binding_hash,
                status="ACTIVE",
            )
            session.add(model)
            await session.flush()
            probe = _commit_probe(model)
            try:
                await self._commit(session)
            except Exception as exc:
                try:
                    await session.rollback()
                except Exception:
                    pass
                raise _EvidenceCommitOutcomeUncertain(probe) from exc
            await session.refresh(model)
            return model

    async def _commit(self, session: AsyncSession) -> None:
        """Commit through a narrow seam so lost acknowledgements are testable."""

        await session.commit()

    async def _read_committed_package(
        self,
        probe: _EvidenceCommitProbe,
    ) -> ResearchEvidencePackage | None:
        """Read back only the exact durable row described by a failed commit probe."""

        try:
            async with database.async_session_maker() as session:
                packages = list(
                    (
                        await session.scalars(
                            select(ResearchEvidencePackage).where(
                                ResearchEvidencePackage.user_id == probe.user_id,
                                ResearchEvidencePackage.command_id == probe.command_id,
                            )
                        )
                    ).all()
                )
                if len(packages) != 1 or not _package_matches_probe(packages[0], probe):
                    return None
                return packages[0]
        except Exception:
            return None

    async def validate_for_approval(
        self,
        *,
        candidate_id: str,
        promotion_policy_version: str,
        gate_input_evidence_hash: str,
        evidence_package_hash: str,
    ) -> ResearchEvidencePackage:
        """Require a current server-built package for exactly one approval input."""

        async with database.async_session_maker() as session:
            return await self.validate_for_approval_in_session(
                session,
                candidate_id=candidate_id,
                promotion_policy_version=promotion_policy_version,
                gate_input_evidence_hash=gate_input_evidence_hash,
                evidence_package_hash=evidence_package_hash,
            )

    async def validate_for_approval_in_session(
        self,
        session: AsyncSession,
        *,
        candidate_id: str,
        promotion_policy_version: str,
        gate_input_evidence_hash: str,
        evidence_package_hash: str,
    ) -> ResearchEvidencePackage:
        """Revalidate a package inside the caller's approval transaction."""

        _validate_binding(
            candidate_id=candidate_id,
            promotion_policy_version=promotion_policy_version,
            gate_input_evidence_hash=gate_input_evidence_hash,
        )
        if not _is_sha256(evidence_package_hash):
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_NOT_FOUND")

        result = await session.execute(
            select(ResearchEvidencePackage)
            .where(
                ResearchEvidencePackage.candidate_id == candidate_id,
                ResearchEvidencePackage.promotion_policy_version == promotion_policy_version,
                ResearchEvidencePackage.gate_input_evidence_hash == gate_input_evidence_hash,
                ResearchEvidencePackage.manifest_hash == evidence_package_hash,
            )
            .with_for_update()
        )
        package = result.scalar_one_or_none()
        if package is None:
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_NOT_FOUND")
        if package.status != "ACTIVE":
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_WITHDRAWN")
        if not isinstance(package.manifest, Mapping):
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_CORRUPT")
        if content_hash(package.manifest) != package.manifest_hash:
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_CORRUPT")
        manifest_version = package.manifest.get("manifest_version")
        if manifest_version == _LEGACY_MANIFEST_VERSION:
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_VERSION_UNSUPPORTED")
        if manifest_version != _MANIFEST_VERSION:
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_CORRUPT")
        if set(package.manifest) != {"manifest_version", "material"}:
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_CORRUPT")
        stored_material = package.manifest.get("material")
        if not isinstance(stored_material, Mapping):
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_CORRUPT")
        if content_hash(dict(stored_material)) != package.approval_binding_hash:
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_CORRUPT")
        if any(
            value is None
            for value in (
                package.command_id,
                package.evaluation_id,
                package.artifact_binding_id,
                package.terminal_access_audit_id,
            )
        ):
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_VERSION_UNSUPPORTED")
        try:
            context = await _load_terminal_context(
                session,
                user_id=package.user_id,
                command_id=str(package.command_id),
                dataset_registry=self._datasets,
            )
        except ValueError as exc:
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_UNVERIFIABLE") from exc

        if (
            package.candidate_id != context.candidate.id
            or package.run_id != context.run.id
            or package.evaluation_id != context.evaluation.id
            or package.artifact_binding_id != context.artifact_binding.id
            or package.terminal_access_audit_id != context.terminal_access_audit.id
            or package.promotion_policy_version != context.command.policy_version
            or package.gate_input_evidence_hash != _gate_input_hash(context.evaluation)
        ):
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_UNVERIFIABLE")
        current_material = _material_manifest(context)
        if (
            dict(stored_material) != current_material
            or content_hash(current_material) != package.approval_binding_hash
        ):
            raise ValueError("APPROVAL_EVIDENCE_PACKAGE_STALE")
        return package


def _commit_probe(model: ResearchEvidencePackage) -> _EvidenceCommitProbe:
    values = (
        model.command_id,
        model.evaluation_id,
        model.artifact_binding_id,
        model.terminal_access_audit_id,
    )
    if any(value is None for value in values):
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    return _EvidenceCommitProbe(
        package_id=model.id,
        user_id=model.user_id,
        run_id=model.run_id,
        candidate_id=model.candidate_id,
        command_id=str(model.command_id),
        evaluation_id=str(model.evaluation_id),
        artifact_binding_id=str(model.artifact_binding_id),
        terminal_access_audit_id=str(model.terminal_access_audit_id),
        promotion_policy_version=model.promotion_policy_version,
        gate_input_evidence_hash=model.gate_input_evidence_hash,
        manifest=dict(model.manifest),
        manifest_hash=model.manifest_hash,
        approval_binding_hash=model.approval_binding_hash,
    )


def _package_matches_probe(
    model: ResearchEvidencePackage,
    probe: _EvidenceCommitProbe,
) -> bool:
    return bool(
        model.id == probe.package_id
        and model.user_id == probe.user_id
        and model.run_id == probe.run_id
        and model.candidate_id == probe.candidate_id
        and model.command_id == probe.command_id
        and model.evaluation_id == probe.evaluation_id
        and model.artifact_binding_id == probe.artifact_binding_id
        and model.terminal_access_audit_id == probe.terminal_access_audit_id
        and model.promotion_policy_version == probe.promotion_policy_version
        and model.gate_input_evidence_hash == probe.gate_input_evidence_hash
        and model.manifest == probe.manifest
        and model.manifest_hash == probe.manifest_hash
        and model.approval_binding_hash == probe.approval_binding_hash
        and model.status == "ACTIVE"
        and model.created_at is not None
        and content_hash(model.manifest) == model.manifest_hash
        and content_hash(model.manifest["material"]) == model.approval_binding_hash
    )


def _require_exact_existing_package(
    model: ResearchEvidencePackage,
    *,
    context: _EvidenceContext,
    manifest: dict[str, Any],
    manifest_hash: str,
    approval_binding_hash: str,
) -> None:
    if model.status == "WITHDRAWN":
        raise ValueError("EVIDENCE_PACKAGE_WITHDRAWN")
    if (
        model.status != "ACTIVE"
        or model.user_id != context.command.user_id
        or model.run_id != context.run.id
        or model.candidate_id != context.candidate.id
        or model.command_id != context.command.id
        or model.evaluation_id != context.evaluation.id
        or model.artifact_binding_id != context.artifact_binding.id
        or model.terminal_access_audit_id != context.terminal_access_audit.id
        or model.promotion_policy_version != context.command.policy_version
        or model.gate_input_evidence_hash != _gate_input_hash(context.evaluation)
        or model.manifest != manifest
        or model.manifest_hash != manifest_hash
        or model.approval_binding_hash != approval_binding_hash
        or model.created_at is None
        or content_hash(model.manifest) != model.manifest_hash
        or content_hash(model.manifest["material"]) != model.approval_binding_hash
    ):
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")


async def _load_terminal_context(
    session: AsyncSession,
    *,
    user_id: str,
    command_id: str,
    dataset_registry: DatasetRegistry,
) -> _EvidenceContext:
    """Lock and validate one complete command authority graph."""

    finalizer = HoldoutFinalizeService()
    try:
        graph = await finalizer._claims._lock_claim_graph(session, command_id=command_id)
    except ValueError as exc:
        raise ValueError("EVIDENCE_PACKAGE_TERMINAL_COMMAND_REQUIRED") from exc
    command = graph.command
    if (
        command.user_id != user_id
        or command.status != "SUCCEEDED"
        or command.stage != "HOLDOUT_PENDING"
        or command.error_code is not None
        or command.authorization_id is None
        or command.evaluation_id is None
        or command.lease_generation < 1
        or command.attempt_count != command.lease_generation
        or command.started_at is None
        or any(
            value is not None
            for value in (
                command.lease_owner,
                command.lease_token_hash,
                command.lease_expires_at,
                command.lease_heartbeat_at,
            )
        )
    ):
        raise ValueError("EVIDENCE_PACKAGE_TERMINAL_COMMAND_REQUIRED")

    terminal_audits = list(
        (
            await session.scalars(
                select(ResearchHoldoutAccessAudit)
                .where(
                    ResearchHoldoutAccessAudit.requested_command_id == command.id,
                    ResearchHoldoutAccessAudit.action.in_(_TERMINAL_ACTIONS),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if len(terminal_audits) != 1:
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    terminal_audit = terminal_audits[0]
    try:
        runtime = HoldoutEvaluatorRuntimeIdentity(
            worker_identity=terminal_audit.actor_identity,
            evaluator_identity=command.evaluator_identity,
            evaluator_image_digest=command.evaluator_version,
        )
        await _validate_static_locked_authority(session, graph, runtime=runtime)
        receipt = await finalizer._terminal_result_if_exact(
            session,
            graph=graph,
            runtime=runtime,
            requested_generation=command.lease_generation,
            expected_action=terminal_audit.action,
        )
    except ValueError as exc:
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID") from exc
    if receipt is None:
        raise ValueError("EVIDENCE_PACKAGE_TERMINAL_COMMAND_REQUIRED")

    authorization, evaluation, claim_audit = await _load_started_authority(session, graph)
    binding = await _load_binding(session, command_id=command.id)
    if authorization is None or evaluation is None or claim_audit is None or binding is None:
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    if evaluation.status != "PASSED" or receipt.eligible is not True:
        raise ValueError("EVIDENCE_PACKAGE_TERMINAL_COMMAND_REQUIRED")
    _require_terminal_authority(
        graph,
        authorization=authorization,
        evaluation=evaluation,
        binding=binding,
        receipt=receipt,
    )

    access_audits = list(
        (
            await session.scalars(
                select(ResearchHoldoutAccessAudit)
                .where(
                    ResearchHoldoutAccessAudit.requested_command_id == command.id,
                    ResearchHoldoutAccessAudit.action.in_(_EVIDENCE_AUDIT_ACTIONS),
                )
                .order_by(
                    ResearchHoldoutAccessAudit.created_at.asc(),
                    ResearchHoldoutAccessAudit.id.asc(),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    _require_access_audit_chain(
        graph,
        authorization=authorization,
        evaluation=evaluation,
        binding=binding,
        audits=access_audits,
        terminal_audit=terminal_audit,
    )

    input_evidence_hash = _gate_input_hash(evaluation)
    gates = list(
        (
            await session.scalars(
                select(ResearchGateDecision)
                .where(
                    ResearchGateDecision.candidate_id == command.candidate_id,
                    ResearchGateDecision.policy_version == command.policy_version,
                    ResearchGateDecision.input_evidence_hash == input_evidence_hash,
                )
                .order_by(ResearchGateDecision.gate_code.asc())
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if (
        len(gates) != len(_REQUIRED_GATE_CODES)
        or {item.gate_code for item in gates} != _REQUIRED_GATE_CODES
        or any(item.evaluation_id != evaluation.id or item.status != "PASS" for item in gates)
    ):
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")

    for snapshot in (graph.discovery, graph.sealed):
        await dataset_registry.revalidate_snapshot_in_session(session, snapshot=snapshot)
        require_verified_snapshot_integrity(snapshot)

    hypothesis = await session.get(
        ResearchHypothesisVersion,
        graph.run.hypothesis_version_id,
        with_for_update=True,
    )
    if (
        graph.run.protocol_version != "v2"
        or hypothesis is None
        or hypothesis.user_id != user_id
        or graph.epoch.hypothesis_version_id != hypothesis.id
    ):
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")

    tasks = list(
        (
            await session.scalars(
                select(ResearchTask)
                .where(ResearchTask.run_id == graph.run.id, ResearchTask.user_id == user_id)
                .order_by(ResearchTask.created_at.asc(), ResearchTask.id.asc())
            )
        ).all()
    )
    task_ids = [item.id for item in tasks]
    stage_attempts: list[ResearchStageAttempt] = []
    if task_ids:
        stage_attempts = list(
            (
                await session.scalars(
                    select(ResearchStageAttempt)
                    .where(ResearchStageAttempt.task_id.in_(task_ids))
                    .order_by(
                        ResearchStageAttempt.stage.asc(),
                        ResearchStageAttempt.attempt_no.asc(),
                        ResearchStageAttempt.id.asc(),
                    )
                )
            ).all()
        )
    trials = list(
        (
            await session.scalars(
                select(ResearchTrial)
                .where(ResearchTrial.run_id == graph.run.id, ResearchTrial.user_id == user_id)
                .order_by(ResearchTrial.ordinal.asc(), ResearchTrial.id.asc())
            )
        ).all()
    )
    model_invocations = list(
        (
            await session.scalars(
                select(ResearchModelInvocation)
                .where(ResearchModelInvocation.run_id == graph.run.id)
                .order_by(
                    ResearchModelInvocation.created_at.asc(),
                    ResearchModelInvocation.id.asc(),
                )
            )
        ).all()
    )
    governance_result = await session.execute(
        select(ResearchGovernanceDecision).order_by(
            ResearchGovernanceDecision.effective_at.asc(),
            ResearchGovernanceDecision.id.asc(),
        )
    )
    governance_decisions = [
        item
        for item in governance_result.scalars()
        if _governance_scope_matches(
            item.scope,
            candidate_id=graph.candidate.id,
            run_id=graph.run.id,
        )
    ]

    security_scan_artifact = await _load_security_scan_artifact(
        session,
        artifact_binding=binding,
    )
    artifact_ids = {
        graph.candidate.code_artifact_id,
        graph.candidate.dependency_artifact_id,
        binding.artifact_id,
        security_scan_artifact.id,
        *(item.returns_artifact_id for item in trials if item.returns_artifact_id is not None),
        *(
            item.output_artifact_id
            for item in stage_attempts
            if item.output_artifact_id is not None
        ),
    }
    artifacts = {
        item.id: item
        for item in (
            await session.scalars(
                select(ResearchArtifact)
                .where(ResearchArtifact.id.in_(sorted(artifact_ids)))
                .with_for_update()
            )
        ).all()
    }
    if set(artifacts) != artifact_ids:
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")

    return _EvidenceContext(
        strict_freeze_receipt_fingerprint=command.freeze_receipt_fingerprint,
        candidate=graph.candidate,
        run=graph.run,
        hypothesis=hypothesis,
        epoch=graph.epoch,
        dataset=graph.discovery,
        sealed_dataset=graph.sealed,
        capability_profile=graph.profile,
        command=command,
        authorization=authorization,
        evaluation=evaluation,
        artifact_binding=binding,
        access_audits=access_audits,
        terminal_access_audit=terminal_audit,
        artifacts=artifacts,
        tasks=tasks,
        stage_attempts=stage_attempts,
        trials=trials,
        model_invocations=model_invocations,
        gates=gates,
        governance_decisions=governance_decisions,
    )


async def _load_security_scan_artifact(
    session: AsyncSession,
    *,
    artifact_binding: ResearchHoldoutArtifactBinding,
) -> ResearchArtifact:
    """Resolve the scan referenced inside sealed bytes without exporting measurements."""

    holdout_artifact = await session.get(
        ResearchArtifact,
        artifact_binding.artifact_id,
        with_for_update=True,
    )
    retained = await session.get(
        ResearchArtifactContent,
        artifact_binding.artifact_id,
        with_for_update=True,
    )
    if holdout_artifact is None:
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    if holdout_artifact.kind == _SEALED_RECEIPT_KIND:
        if retained is not None:
            raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
        execution = await session.scalar(
            select(ResearchHoldoutExecution)
            .where(ResearchHoldoutExecution.command_id == artifact_binding.command_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        try:
            if execution is None or execution.result_json is None:
                raise ValueError
            wire_command = HoldoutExecutionCommand.from_mapping(dict(execution.command_json))
            result = HoldoutExecutionResult.from_mapping(
                dict(execution.result_json),
                command=wire_command,
            )
            terminal = result.snapshot["terminal_receipt"]
            artifact_receipt = terminal["artifact_receipt"]
            safe_metrics = terminal["safe_metrics"]
            scan_hash = safe_metrics.get("security_scan_hash")
            if (
                execution.command_id != artifact_binding.command_id
                or execution.evaluation_id != artifact_binding.evaluation_id
                or execution.command_hash != wire_command.command_hash
                or execution.lease_owner != artifact_binding.lease_owner
                or execution.lease_generation != artifact_binding.lease_generation
                or execution.state not in {"OBSERVED", "SETTLED"}
                or execution.result_hash != sha256(result.payload).hexdigest()
                or result.snapshot["status"] != "SUCCEEDED"
                or artifact_receipt["artifact_hash"] != holdout_artifact.content_hash
                or artifact_receipt["artifact_size_bytes"] != holdout_artifact.size_bytes
                or holdout_artifact.schema_version != _SEALED_RECEIPT_SCHEMA
                or holdout_artifact.media_type != _SEALED_RECEIPT_MEDIA_TYPE
                or holdout_artifact.storage_uri
                != (
                    f"controlled://sealed-holdout-artifact-receipt/{artifact_receipt['receipt_id']}"
                )
                or not _is_sha256(scan_hash)
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID") from None
    else:
        if retained is None:
            raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
        try:
            sealed_content = bytes(retained.content)
            sealed_payload = json.loads(sealed_content.decode("utf-8"))
            if (
                not isinstance(sealed_payload, dict)
                or canonical_json(sealed_payload).encode("utf-8") != sealed_content
            ):
                raise ValueError
            measurements = sealed_payload.get("measurements")
            if not isinstance(measurements, Mapping):
                raise ValueError
            scan_hash = measurements.get("security_scan_hash")
            if not _is_sha256(scan_hash):
                raise ValueError
        except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID") from exc

    scan_artifacts = list(
        (
            await session.scalars(
                select(ResearchArtifact)
                .where(
                    ResearchArtifact.kind == _SECURITY_SCAN_KIND,
                    ResearchArtifact.content_hash == scan_hash,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if len(scan_artifacts) != 1:
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    artifact = scan_artifacts[0]
    scan_retained = await session.get(
        ResearchArtifactContent,
        artifact.id,
        with_for_update=True,
    )
    if scan_retained is None:
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    try:
        scan_content = bytes(scan_retained.content)
        scan_payload = json.loads(scan_content.decode("utf-8"))
        canonical_scan_content = canonical_json(scan_payload).encode("utf-8")
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID") from exc
    if (
        not isinstance(scan_payload, dict)
        or artifact.kind != _SECURITY_SCAN_KIND
        or artifact.schema_version != _SECURITY_SCAN_SCHEMA
        or artifact.media_type != "application/json"
        or artifact.content_hash != scan_hash
        or artifact.content_hash != sha256(scan_content).hexdigest()
        or artifact.size_bytes != len(scan_content)
        or canonical_scan_content != scan_content
    ):
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    return artifact


def _require_terminal_authority(
    graph: Any,
    *,
    authorization: ResearchHoldoutAuthorization,
    evaluation: ResearchEvaluation,
    binding: ResearchHoldoutArtifactBinding,
    receipt: Any,
) -> None:
    """Reject terminal rows that do not exactly preserve their issued authority."""

    command = graph.command
    started_at = _as_utc(command.started_at)
    authorization_expires_at = _as_utc(authorization.expires_at)
    gate_inputs = dict(evaluation.gate_inputs or {})
    gate_statuses = gate_inputs.get("gate_statuses")
    if (
        authorization.id != command.authorization_id
        or authorization.status != "CONSUMED"
        or authorization.experiment_epoch_id != command.experiment_epoch_id
        or authorization.candidate_id != command.candidate_id
        or authorization.candidate_hash != command.candidate_hash
        or authorization.dataset_snapshot_id != command.dataset_snapshot_id
        or authorization.policy_version != command.policy_version
        or authorization.evaluator_identity != command.evaluator_identity
        or authorization.capability_profile_id != command.capability_profile_id
        or authorization.capability_profile_version != command.capability_profile_version
        or authorization.capability_evidence_hash != command.capability_evidence_hash
        or authorization.issued_by != binding.lease_owner
        or not _is_sha256(authorization.token_hash)
        or _as_utc(authorization.issued_at) != started_at
        or _as_utc(authorization.consumed_at) != started_at
        or authorization_expires_at is None
        or started_at is None
        or authorization_expires_at <= started_at
        or evaluation.id != command.evaluation_id
        or evaluation.experiment_epoch_id != command.experiment_epoch_id
        or evaluation.candidate_id != command.candidate_id
        or evaluation.dataset_snapshot_id != command.dataset_snapshot_id
        or evaluation.evaluation_type != "SEALED_HOLDOUT"
        or evaluation.evaluator_identity != command.evaluator_identity
        or evaluation.evaluator_version != command.evaluator_version
        or evaluation.authorization_id != authorization.id
        or evaluation.returns_artifact_id != binding.artifact_id
        or evaluation.policy_version != command.policy_version
        or evaluation.status != "PASSED"
        or (evaluation.metrics or {}) != {"promotion_eligible": True}
        or _as_utc(evaluation.started_at) != started_at
        or evaluation.completed_at is None
        or not _is_sha256(gate_inputs.get("input_evidence_hash"))
        or gate_inputs.get("strict_freeze_receipt_fingerprint")
        != command.freeze_receipt_fingerprint
        or gate_inputs.get("promotion_policy_hash")
        != promotion_policy_material_hash(resolve_server_policy(command.policy_version))
        or not isinstance(gate_statuses, Mapping)
        or set(gate_statuses) != _REQUIRED_GATE_CODES
        or any(gate_statuses[code] != "PASS" for code in _REQUIRED_GATE_CODES)
        or binding.command_id != command.id
        or binding.authorization_id != authorization.id
        or binding.evaluation_id != evaluation.id
        or binding.lease_generation != command.lease_generation
        or receipt.command_id != command.id
        or receipt.evaluation_id != evaluation.id
        or receipt.command_status != "SUCCEEDED"
        or receipt.evaluation_status != "PASSED"
        or receipt.input_evidence_hash != gate_inputs["input_evidence_hash"]
        or receipt.eligible is not True
        or set(receipt.gate_statuses) != _REQUIRED_GATE_CODES
        or any(receipt.gate_statuses[code] != "PASS" for code in _REQUIRED_GATE_CODES)
        or graph.epoch.status != "CLOSED"
        or graph.epoch.selected_candidate_id != command.candidate_id
        or _as_utc(graph.epoch.disclosed_at) != started_at
        or _as_utc(graph.epoch.closed_at) != _as_utc(evaluation.completed_at)
    ):
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")


def _require_access_audit_chain(
    graph: Any,
    *,
    authorization: ResearchHoldoutAuthorization,
    evaluation: ResearchEvaluation,
    binding: ResearchHoldoutArtifactBinding,
    audits: list[ResearchHoldoutAccessAudit],
    terminal_audit: ResearchHoldoutAccessAudit,
) -> None:
    """Require one complete terminal chain, including an exact reconcile fence."""

    command = graph.command
    transition_audits = [item for item in audits if item.action in _TRANSITION_ACTIONS]
    if terminal_audit.action == "FINALIZE_COMPLETED":
        if transition_audits:
            raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    elif terminal_audit.action == "RECONCILE_COMPLETED":
        if len(transition_audits) != 1:
            raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    else:
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    expected_actions = {"CLAIM_STARTED", "CHECKPOINT_RECORDED", terminal_audit.action}
    expected_actions.update(item.action for item in transition_audits)
    if len(audits) != len(expected_actions) or {item.action for item in audits} != expected_actions:
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    contracts = {
        "CLAIM_STARTED": ("ACCEPTED", "HOLDOUT_CLAIM_STARTED"),
        "CHECKPOINT_RECORDED": ("ACCEPTED", "HOLDOUT_FINALIZE_CHECKPOINT_RECORDED"),
        "LEASE_EXPIRED_RECONCILING": ("ACCEPTED", "HOLDOUT_CLAIM_LEASE_EXPIRED"),
        "EXECUTION_OBSERVED_RECONCILING": (
            "ACCEPTED",
            "HOLDOUT_EXECUTION_OBSERVED_RECOVERY",
        ),
        "CHECKPOINT_UNKNOWN": (
            "UNKNOWN",
            "HOLDOUT_FINALIZE_CHECKPOINT_COMMIT_OUTCOME_UNKNOWN",
        ),
        "FINALIZE_UNKNOWN": ("UNKNOWN", "HOLDOUT_FINALIZE_COMMIT_OUTCOME_UNKNOWN"),
        "FINALIZE_COMPLETED": ("ACCEPTED", "HOLDOUT_FINALIZE_COMPLETED"),
        "RECONCILE_COMPLETED": ("ACCEPTED", "HOLDOUT_FINALIZE_RECONCILED"),
    }
    by_action = {item.action: item for item in audits}
    if by_action.get(terminal_audit.action) is None:
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    recovery_audit = by_action.get("EXECUTION_OBSERVED_RECONCILING")
    checkpoint_actor = (
        recovery_audit.actor_identity if recovery_audit is not None else binding.lease_owner
    )
    for action, audit in by_action.items():
        contract = contracts.get(action)
        if contract is None:
            raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
        expected_result, expected_reason = contract
        if action == "CHECKPOINT_RECORDED":
            actor_matches = audit.actor_identity == checkpoint_actor
        elif action in {
            "LEASE_EXPIRED_RECONCILING",
            "EXECUTION_OBSERVED_RECONCILING",
            "RECONCILE_COMPLETED",
        }:
            actor_matches = isinstance(audit.actor_identity, str) and bool(
                audit.actor_identity.strip()
            )
        else:
            actor_matches = audit.actor_identity == binding.lease_owner
        authoritative = action not in {"CHECKPOINT_UNKNOWN", "FINALIZE_UNKNOWN"}
        authority_matches = (
            audit.command_id == command.id
            and audit.authorization_id == authorization.id
            and audit.evaluation_id == evaluation.id
            and audit.experiment_epoch_id == command.experiment_epoch_id
            and audit.candidate_id == command.candidate_id
            and audit.dataset_snapshot_id == command.dataset_snapshot_id
            and audit.lease_generation == command.lease_generation
            and audit.trace_id == command.trace_id
            if authoritative
            else all(
                value is None
                for value in (
                    audit.command_id,
                    audit.authorization_id,
                    audit.evaluation_id,
                    audit.experiment_epoch_id,
                    audit.candidate_id,
                    audit.dataset_snapshot_id,
                    audit.lease_generation,
                    audit.trace_id,
                )
            )
        )
        if (
            audit.result != expected_result
            or audit.reason_code != expected_reason
            or not actor_matches
            or audit.evaluator_version != command.evaluator_version
            or audit.requested_command_id != command.id
            or not authority_matches
            or not _audit_time_is_valid(
                action,
                audit.created_at,
                command=command,
                evaluation=evaluation,
                binding=binding,
            )
        ):
            raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    if by_action[terminal_audit.action].id != terminal_audit.id:
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")


def _audit_time_is_valid(
    action: str,
    created_at: datetime,
    *,
    command: ResearchHoldoutEvaluationCommand,
    evaluation: ResearchEvaluation,
    binding: ResearchHoldoutArtifactBinding,
) -> bool:
    value = _as_utc(created_at)
    if value is None:
        return False
    if action == "CLAIM_STARTED":
        return value == _as_utc(command.started_at)
    if action == "CHECKPOINT_RECORDED":
        return value == _as_utc(binding.created_at)
    if action == "EXECUTION_OBSERVED_RECONCILING":
        return value == _as_utc(binding.created_at)
    if action in _TERMINAL_ACTIONS:
        return value == _as_utc(evaluation.completed_at)
    if action == "LEASE_EXPIRED_RECONCILING":
        lease_expires_at = _as_utc(binding.lease_expires_at)
        completed_at = _as_utc(evaluation.completed_at)
        return (
            lease_expires_at is not None
            and completed_at is not None
            and lease_expires_at <= value <= completed_at
        )
    if action in _TRANSITION_ACTIONS:
        checkpoint_at = _as_utc(binding.created_at)
        completed_at = _as_utc(evaluation.completed_at)
        return (
            checkpoint_at is not None
            and completed_at is not None
            and checkpoint_at <= value <= completed_at
        )
    return False


def _gate_input_hash(evaluation: ResearchEvaluation) -> str:
    value = dict(evaluation.gate_inputs or {}).get("input_evidence_hash")
    if not _is_sha256(value):
        raise ValueError("EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID")
    return str(value)


def _material_manifest(
    context: _EvidenceContext,
) -> dict[str, Any]:
    """Return the immutable non-self-referential input to an approval decision."""

    return {
        "binding_version": _MANIFEST_VERSION,
        "strict_freeze_receipt_fingerprint": context.strict_freeze_receipt_fingerprint,
        "promotion_policy_version": context.command.policy_version,
        "promotion_policy_hash": promotion_policy_material_hash(
            resolve_server_policy(context.command.policy_version)
        ),
        "gate_input_evidence_hash": _gate_input_hash(context.evaluation),
        "run": {
            "id": context.run.id,
            "protocol_version": context.run.protocol_version,
            "request_hash": context.run.request_hash,
            "promotion_policy_version": context.run.promotion_policy_version,
            "trace_id": context.run.trace_id,
            "created_at": _timestamp(context.run.created_at),
        },
        "hypothesis": {
            "id": context.hypothesis.id,
            "hypothesis_id": context.hypothesis.hypothesis_id,
            "version_no": context.hypothesis.version_no,
            "status": context.hypothesis.status,
            "content_hash": context.hypothesis.content_hash,
            "confirmed_at": _timestamp(context.hypothesis.confirmed_at),
        },
        "experiment_epoch": {
            "id": context.epoch.id,
            "family_hash": context.epoch.family_hash,
            "search_budget_hash": content_hash(context.epoch.search_budget),
            "dataset_policy_version": context.epoch.dataset_policy_version,
            "holdout_budget": context.epoch.holdout_budget,
            "status": context.epoch.status,
        },
        "dataset": {
            "id": context.dataset.id,
            "dataset_policy_version": context.dataset.dataset_policy_version,
            "partition_kind": context.dataset.partition_kind,
            "content_hash": context.dataset.content_hash,
            "instrument_manifest_hash": content_hash(context.dataset.instrument_manifest),
            "split_manifest_hash": content_hash(context.dataset.split_manifest),
            "source_manifest_hash": content_hash(context.dataset.source_manifest),
            "execution_policy_hash": content_hash(context.dataset.execution_policy),
            "storage_reference_hash": context.dataset.storage_reference_hash,
            "license_tags": sorted(context.dataset.license_tags or []),
            "point_in_time_cutoff": _timestamp(context.dataset.point_in_time_cutoff),
        },
        "sealed_dataset": {
            "id": context.sealed_dataset.id,
            "dataset_policy_version": context.sealed_dataset.dataset_policy_version,
            "partition_kind": context.sealed_dataset.partition_kind,
            "content_hash": context.sealed_dataset.content_hash,
            "snapshot_identity_hash": context.sealed_dataset.snapshot_identity_hash,
            "instrument_manifest_hash": content_hash(context.sealed_dataset.instrument_manifest),
            "split_manifest_hash": content_hash(context.sealed_dataset.split_manifest),
            "source_manifest_hash": content_hash(context.sealed_dataset.source_manifest),
            "execution_policy_hash": content_hash(context.sealed_dataset.execution_policy),
            "license_tags": sorted(context.sealed_dataset.license_tags or []),
            "point_in_time_cutoff": _timestamp(context.sealed_dataset.point_in_time_cutoff),
        },
        "capability_profile": {
            "profile_id": context.capability_profile.profile_id,
            "version": context.capability_profile.version,
            "topology": context.capability_profile.topology,
            "actor_mode": context.capability_profile.actor_mode,
            "evidence_hash": context.capability_profile.evidence_hash,
            "verified_at": _timestamp(context.capability_profile.verified_at),
            "expires_at": _timestamp(context.capability_profile.expires_at),
        },
        "candidate": {
            "id": context.candidate.id,
            "candidate_hash": context.candidate.candidate_hash,
            "environment_hash": context.candidate.environment_hash,
            "cost_model_hash": context.candidate.cost_model_hash,
            "params_hash": content_hash(context.candidate.params),
            "freeze_status": context.candidate.freeze_status,
            "frozen_at": _timestamp(context.candidate.frozen_at),
            "code_artifact_id": context.candidate.code_artifact_id,
            "dependency_artifact_id": context.candidate.dependency_artifact_id,
        },
        "holdout_command": _command_payload(context.command),
        "holdout_authorization": _authorization_payload(context.authorization),
        "holdout_evaluation": _evaluation_payload(context.evaluation),
        "holdout_artifact_binding": _artifact_binding_payload(context.artifact_binding),
        "holdout_access_audits": [_access_audit_payload(item) for item in context.access_audits],
        "artifacts": [
            _artifact_payload(context.artifacts[artifact_id])
            for artifact_id in sorted(context.artifacts)
        ],
        "tasks": [_task_payload(item) for item in context.tasks],
        "stage_attempts": [_stage_attempt_payload(item) for item in context.stage_attempts],
        "trials": [_trial_payload(item) for item in context.trials],
        "model_invocations": [
            _model_invocation_payload(item) for item in context.model_invocations
        ],
        "gate_decisions": [_gate_payload(item) for item in context.gates],
        "governance_decisions": [
            _governance_payload(item) for item in context.governance_decisions
        ],
    }


def _artifact_payload(model: ResearchArtifact) -> dict[str, Any]:
    """Return an artifact reference with no storage location or download token."""

    return {
        "id": model.id,
        "kind": model.kind,
        "content_hash": model.content_hash,
        "size_bytes": model.size_bytes,
        "media_type": model.media_type,
        "schema_version": model.schema_version,
        "producer_identity": model.producer_identity,
        "container_image_digest": model.container_image_digest,
    }


def _command_payload(model: ResearchHoldoutEvaluationCommand) -> dict[str, Any]:
    """Project terminal command authority without bearer or lease-token material."""

    return {
        "id": model.id,
        "run_id": model.run_id,
        "experiment_epoch_id": model.experiment_epoch_id,
        "candidate_id": model.candidate_id,
        "candidate_hash": model.candidate_hash,
        "freeze_receipt_id": model.freeze_receipt_id,
        "freeze_receipt_fingerprint": model.freeze_receipt_fingerprint,
        "dataset_snapshot_id": model.dataset_snapshot_id,
        "dataset_policy_version": model.dataset_policy_version,
        "sealed_dataset_hash": model.sealed_dataset_hash,
        "sealed_dataset_identity_hash": model.sealed_dataset_identity_hash,
        "policy_version": model.policy_version,
        "evaluator_identity": model.evaluator_identity,
        "evaluator_version": model.evaluator_version,
        "capability_profile_id": model.capability_profile_id,
        "capability_profile_version": model.capability_profile_version,
        "capability_evidence_hash": model.capability_evidence_hash,
        "authorization_id": model.authorization_id,
        "evaluation_id": model.evaluation_id,
        "request_hash": model.request_hash,
        "status": model.status,
        "stage": model.stage,
        "lease_generation": model.lease_generation,
        "attempt_count": model.attempt_count,
        "started_at": _timestamp(model.started_at),
        "updated_at": _timestamp(model.updated_at),
    }


def _authorization_payload(model: ResearchHoldoutAuthorization) -> dict[str, Any]:
    """Project one-time authority without its bearer-token hash."""

    return {
        "id": model.id,
        "experiment_epoch_id": model.experiment_epoch_id,
        "candidate_id": model.candidate_id,
        "candidate_hash": model.candidate_hash,
        "dataset_snapshot_id": model.dataset_snapshot_id,
        "policy_version": model.policy_version,
        "status": model.status,
        "evaluator_identity": model.evaluator_identity,
        "capability_profile_id": model.capability_profile_id,
        "capability_profile_version": model.capability_profile_version,
        "capability_evidence_hash": model.capability_evidence_hash,
        "issued_by": model.issued_by,
        "issued_at": _timestamp(model.issued_at),
        "consumed_at": _timestamp(model.consumed_at),
        "expires_at": _timestamp(model.expires_at),
    }


def _artifact_binding_payload(model: ResearchHoldoutArtifactBinding) -> dict[str, Any]:
    return {
        "id": model.id,
        "run_id": model.run_id,
        "command_id": model.command_id,
        "authorization_id": model.authorization_id,
        "evaluation_id": model.evaluation_id,
        "experiment_epoch_id": model.experiment_epoch_id,
        "candidate_id": model.candidate_id,
        "dataset_snapshot_id": model.dataset_snapshot_id,
        "artifact_id": model.artifact_id,
        "claim_access_audit_id": model.claim_access_audit_id,
        "request_hash": model.request_hash,
        "lease_owner": model.lease_owner,
        "lease_generation": model.lease_generation,
        "lease_expires_at": _timestamp(model.lease_expires_at),
        "binding_schema_version": model.binding_schema_version,
        "authority_binding_hash": model.authority_binding_hash,
        "created_at": _timestamp(model.created_at),
    }


def _access_audit_payload(model: ResearchHoldoutAccessAudit) -> dict[str, Any]:
    return {
        "id": model.id,
        "actor_identity": model.actor_identity,
        "evaluator_version": model.evaluator_version,
        "requested_command_id": model.requested_command_id,
        "action": model.action,
        "result": model.result,
        "reason_code": model.reason_code,
        "command_id": model.command_id,
        "authorization_id": model.authorization_id,
        "evaluation_id": model.evaluation_id,
        "experiment_epoch_id": model.experiment_epoch_id,
        "candidate_id": model.candidate_id,
        "dataset_snapshot_id": model.dataset_snapshot_id,
        "lease_generation": model.lease_generation,
        "trace_id": model.trace_id,
        "created_at": _timestamp(model.created_at),
    }


def _task_payload(model: ResearchTask) -> dict[str, Any]:
    return {
        "id": model.id,
        "status": model.status,
        "stage_cursor": model.stage_cursor,
        "idempotency_request_hash": model.idempotency_request_hash,
        "error_code": model.error_code,
        "attempt_count": model.attempt_count,
        "created_at": _timestamp(model.created_at),
        "completed_at": _timestamp(model.completed_at),
    }


def _stage_attempt_payload(model: ResearchStageAttempt) -> dict[str, Any]:
    return {
        "id": model.id,
        "task_id": model.task_id,
        "stage": model.stage,
        "attempt_no": model.attempt_no,
        "idempotency_key": model.idempotency_key,
        "status": model.status,
        "input_hash": model.input_hash,
        "output_artifact_id": model.output_artifact_id,
        "error_code": model.error_code,
        "started_at": _timestamp(model.started_at),
        "completed_at": _timestamp(model.completed_at),
    }


def _trial_payload(model: ResearchTrial) -> dict[str, Any]:
    return {
        "id": model.id,
        "candidate_id": model.candidate_id,
        "ordinal": model.ordinal,
        "stage": model.stage,
        "status": model.status,
        "input_hash": model.input_hash,
        "metrics_hash": content_hash(model.metrics),
        "returns_artifact_id": model.returns_artifact_id,
        "observed_market_performance": model.observed_market_performance,
        "counts_as_market_trial": model.counts_as_market_trial,
        "counting_reason": redact_sensitive_payload(model.counting_reason),
        "error_code": model.error_code,
        "completed_at": _timestamp(model.completed_at),
    }


def _model_invocation_payload(model: ResearchModelInvocation) -> dict[str, Any]:
    return {
        "id": model.id,
        "trial_id": model.trial_id,
        "provider": model.provider,
        "requested_model": model.requested_model,
        "resolved_model": model.resolved_model,
        "provider_request_id": model.provider_request_id,
        "prompt_template_version": model.prompt_template_version,
        "system_input_hash": model.system_input_hash,
        "input_hash": model.input_hash,
        "output_hash": model.output_hash,
        "sampling_params_hash": content_hash(model.sampling_params),
        "tool_manifest_hash": content_hash(model.tool_manifest),
        "origin": model.origin,
        "transformation_chain_hash": content_hash(model.transformation_chain),
        "fallback_chain_hash": content_hash(model.fallback_chain),
        "token_usage": redact_sensitive_payload(model.token_usage),
        "cost": redact_sensitive_payload(model.cost),
        "error_code": model.error_code,
        "completed_at": _timestamp(model.completed_at),
    }


def _evaluation_payload(model: ResearchEvaluation) -> dict[str, Any]:
    return {
        "id": model.id,
        "dataset_snapshot_id": model.dataset_snapshot_id,
        "evaluation_type": model.evaluation_type,
        "evaluator_identity": model.evaluator_identity,
        "evaluator_version": model.evaluator_version,
        "authorization_id": model.authorization_id,
        "returns_artifact_id": model.returns_artifact_id,
        "metrics_hash": content_hash(model.metrics),
        "gate_inputs_hash": content_hash(model.gate_inputs),
        "policy_version": model.policy_version,
        "status": model.status,
        "completed_at": _timestamp(model.completed_at),
    }


def _gate_payload(model: ResearchGateDecision) -> dict[str, Any]:
    return {
        "id": model.id,
        "evaluation_id": model.evaluation_id,
        "gate_code": model.gate_code,
        "policy_version": model.policy_version,
        "input_evidence_hash": model.input_evidence_hash,
        "status": model.status,
        "reason": redact_sensitive_payload(model.reason),
        "executor_version": model.executor_version,
        "evaluated_at": _timestamp(model.evaluated_at),
    }


def _governance_payload(model: ResearchGovernanceDecision) -> dict[str, Any]:
    return {
        "id": model.id,
        "target_requirement_or_gate": model.target_requirement_or_gate,
        "original_status": model.original_status,
        "reason": redact_sensitive_payload(model.reason),
        "risk": redact_sensitive_payload(model.risk),
        "compensating_controls": redact_sensitive_payload(model.compensating_controls),
        "actor_id": model.actor_id,
        "scope_hash": content_hash(model.scope),
        "effective_at": _timestamp(model.effective_at),
        "expires_at": _timestamp(model.expires_at),
        "revoked_at": _timestamp(model.revoked_at),
    }


def _governance_scope_matches(
    scope: Mapping[str, Any] | None, *, candidate_id: str, run_id: str
) -> bool:
    if not isinstance(scope, Mapping):
        return False
    return scope.get("candidate_id") == candidate_id or scope.get("run_id") == run_id


def _validate_binding(
    *,
    candidate_id: str,
    promotion_policy_version: str,
    gate_input_evidence_hash: str,
) -> None:
    if (
        not candidate_id.strip()
        or not promotion_policy_version.strip()
        or not _is_sha256(gate_input_evidence_hash)
    ):
        raise ValueError("EVIDENCE_PACKAGE_BINDING_INVALID")


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _build_lock(user_id: str, command_id: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    shards = _BUILD_LOCK_SHARDS_BY_LOOP.get(loop)
    if shards is None:
        shards = tuple(asyncio.Lock() for _ in range(_BUILD_LOCK_SHARD_COUNT))
        _BUILD_LOCK_SHARDS_BY_LOOP[loop] = shards
    identity = f"{user_id}\0{command_id}".encode()
    shard = int.from_bytes(hashlib.sha256(identity).digest()[:8], "big")
    return shards[shard % _BUILD_LOCK_SHARD_COUNT]
