"""RED contracts for command-scoped holdout evidence packages.

Protocol-v2 approval evidence must come from one exact terminal holdout command
authority graph.  Candidate-wide collections of nearby evaluations or gates are
not authority, even when they can be combined into a superficially complete set.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.strategy import research as research_api
from app.config import get_settings
from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchDatasetSnapshot,
    ResearchEvaluation,
    ResearchEvidencePackage,
    ResearchGateDecision,
    ResearchHoldoutAccessAudit,
    ResearchHoldoutArtifactBinding,
    ResearchHoldoutEvaluationCommand,
    ResearchRun,
)
from app.services.research import holdout_claim as holdout_claim_module
from app.services.research import holdout_finalize as holdout_finalize_module
from app.services.research.canonical import canonical_json, content_hash
from app.services.research.evidence_package import EvidencePackageService
from app.services.research.holdout_claim import HoldoutClaimService
from app.services.research.holdout_finalize import HoldoutFinalizeService
from tests.conftest import app
from tests.test_ai_research_evidence_package import _context as _legacy_evidence_context
from tests.test_ai_research_evidence_package import _dataset_registry
from tests.test_ai_research_holdout_finalize import (
    _claimed_context,
    _trusted_rejecting_measurements,
)
from tests.test_ai_research_promotion import (
    _measurements as _trusted_passing_measurements,
)
from tests.test_ai_research_promotion import _persist_security_scan_artifact

_MANIFEST_V1 = "ai_research_evidence_manifest/v1"
_MANIFEST_V2 = "ai_research_evidence_manifest/v2"
_POLICY_VERSION = "promotion-v1"
_SCANNER_IMAGE_DIGEST = f"sha256:{'5' * 64}"


@pytest.fixture(autouse=True)
def enable_protocol_v2_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)


@pytest.fixture(autouse=True)
def clear_holdout_overrides() -> None:
    yield
    app.dependency_overrides.pop(research_api.get_dataset_object_resolver, None)
    app.dependency_overrides.pop(research_api.get_holdout_request_service, None)


@pytest.mark.asyncio
async def test_terminal_command_builds_one_v2_manifest_from_its_exact_authority_graph(
    client,
    auth_user,
) -> None:
    graph = await _finalized_command_graph(client, auth_user, "evidence-command-happy")

    package = await EvidencePackageService(
        dataset_registry=_dataset_registry(graph["context"])
    ).build_for_terminal_command(
        user_id=graph["context"]["user_id"],
        command_id=graph["claimed"].command_id,
    )

    assert package.manifest["manifest_version"] == _MANIFEST_V2
    material = package.manifest["material"]
    assert material["holdout_command"]["id"] == graph["claimed"].command_id
    assert material["holdout_authorization"]["id"] == graph["command"].authorization_id
    assert material["holdout_evaluation"]["id"] == graph["claimed"].evaluation_id
    assert material["holdout_evaluation"]["status"] == "PASSED"
    assert material["holdout_artifact_binding"]["evaluation_id"] == graph["claimed"].evaluation_id
    assert {item["action"] for item in material["holdout_access_audits"]} == {
        "CLAIM_STARTED",
        "CHECKPOINT_RECORDED",
        "FINALIZE_COMPLETED",
    }
    assert len(material["gate_decisions"]) == 13
    assert {(item["evaluation_id"], item["status"]) for item in material["gate_decisions"]} == {
        (graph["claimed"].evaluation_id, "PASS")
    }
    artifacts = {item["id"]: item for item in material["artifacts"]}
    scan_artifact = graph["security_scan_artifact"]
    assert scan_artifact is not None
    assert artifacts[scan_artifact.id]["content_hash"] == scan_artifact.content_hash
    rendered = canonical_json(package.manifest)
    assert '"measurements"' not in rendered
    assert '"holdout_returns"' not in rendered
    assert '"token_hash"' not in rendered
    assert '"storage_uri"' not in rendered
    assert "human_decisions" not in package.manifest
    assert package.gate_input_evidence_hash == graph["result"].input_evidence_hash
    assert package.manifest_hash == content_hash(package.manifest)
    assert package.approval_binding_hash == content_hash(material)


@pytest.mark.asyncio
async def test_twenty_concurrent_builds_converge_to_one_exact_package(
    client,
    auth_user,
) -> None:
    graph = await _finalized_command_graph(
        client,
        auth_user,
        "evidence-command-concurrent-build",
    )
    registry = _dataset_registry(graph["context"])
    packages = await asyncio.gather(
        *(
            EvidencePackageService(dataset_registry=registry).build_for_terminal_command(
                user_id=graph["context"]["user_id"],
                command_id=graph["claimed"].command_id,
            )
            for _ in range(20)
        )
    )

    assert len({item.id for item in packages}) == 1
    assert len({item.manifest_hash for item in packages}) == 1
    async with database.async_session_maker() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ResearchEvidencePackage)
            .where(ResearchEvidencePackage.command_id == graph["claimed"].command_id)
        )
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_was_applied", [True, False])
async def test_build_commit_ack_loss_reads_exact_winner_or_retries_without_false_success(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    commit_was_applied: bool,
) -> None:
    graph = await _finalized_command_graph(
        client,
        auth_user,
        f"evidence-command-commit-ack-{commit_was_applied}",
    )
    service = EvidencePackageService(dataset_registry=_dataset_registry(graph["context"]))
    original_commit = AsyncSession.commit
    commit_calls = 0

    async def commit_then_lose_ack(session: AsyncSession) -> None:
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 1:
            if commit_was_applied:
                await original_commit(session)
            raise OperationalError("COMMIT", {}, RuntimeError("lost acknowledgement"))
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", commit_then_lose_ack)
    if commit_was_applied:
        package = await service.build_for_terminal_command(
            user_id=graph["context"]["user_id"],
            command_id=graph["claimed"].command_id,
        )
    else:
        with pytest.raises(ValueError, match="^EVIDENCE_PACKAGE_COMMIT_OUTCOME_UNKNOWN$"):
            await service.build_for_terminal_command(
                user_id=graph["context"]["user_id"],
                command_id=graph["claimed"].command_id,
            )
        async with database.async_session_maker() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ResearchEvidencePackage)
                    .where(ResearchEvidencePackage.command_id == graph["claimed"].command_id)
                )
                == 0
            )
        package = await service.build_for_terminal_command(
            user_id=graph["context"]["user_id"],
            command_id=graph["claimed"].command_id,
        )

    repeated = await service.build_for_terminal_command(
        user_id=graph["context"]["user_id"],
        command_id=graph["claimed"].command_id,
    )
    assert repeated.id == package.id
    assert repeated.manifest_hash == package.manifest_hash
    async with database.async_session_maker() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ResearchEvidencePackage)
            .where(ResearchEvidencePackage.command_id == graph["claimed"].command_id)
        )
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tamper", "error_code"),
    [
        ("withdrawn", "EVIDENCE_PACKAGE_WITHDRAWN"),
        ("evaluation_fk", "EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID"),
        ("terminal_audit_fk", "EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID"),
    ],
)
async def test_existing_package_is_reused_only_after_full_active_binding_validation(
    client,
    auth_user,
    tamper: str,
    error_code: str,
) -> None:
    graph = await _finalized_command_graph(
        client,
        auth_user,
        f"evidence-command-existing-{tamper}",
    )
    service = EvidencePackageService(dataset_registry=_dataset_registry(graph["context"]))
    package = await service.build_for_terminal_command(
        user_id=graph["context"]["user_id"],
        command_id=graph["claimed"].command_id,
    )
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchEvidencePackage, package.id)
        assert stored is not None
        if tamper == "withdrawn":
            stored.status = "WITHDRAWN"
        elif tamper == "evaluation_fk":
            stored.evaluation_id = (await _add_decoy_evaluation(session, graph)).id
        else:
            claim_audit = await _access_audit(session, graph, "CLAIM_STARTED")
            stored.terminal_access_audit_id = claim_audit.id
        await session.commit()

    with pytest.raises(ValueError, match=f"^{error_code}$"):
        await service.build_for_terminal_command(
            user_id=graph["context"]["user_id"],
            command_id=graph["claimed"].command_id,
        )


@pytest.mark.asyncio
async def test_candidate_wide_legacy_iteration_validation_cannot_build_approval_evidence(
    auth_user,
) -> None:
    context = await _legacy_evidence_context(auth_user, "evidence-command-legacy")

    with pytest.raises(ValueError, match="^EVIDENCE_PACKAGE_TERMINAL_COMMAND_REQUIRED$"):
        await EvidencePackageService(dataset_registry=_dataset_registry(context)).build(
            user_id=context["user_id"],
            candidate_id=context["candidate"].id,
            promotion_policy_version=_POLICY_VERSION,
            gate_input_evidence_hash="1" * 64,
        )


@pytest.mark.asyncio
async def test_running_holdout_command_cannot_build_approval_evidence(client, auth_user) -> None:
    context, claimed, _runtime = await _claimed_context(
        client,
        auth_user,
        "evidence-command-running",
    )

    with pytest.raises(ValueError, match="^EVIDENCE_PACKAGE_TERMINAL_COMMAND_REQUIRED$"):
        await EvidencePackageService(
            dataset_registry=_dataset_registry(context)
        ).build_for_terminal_command(
            user_id=context["user_id"],
            command_id=claimed.command_id,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "command_id"),
    [
        ("not-the-command-owner", None),
        (None, "00000000-0000-0000-0000-000000000000"),
    ],
    ids=["wrong-user", "unknown-command"],
)
async def test_wrong_user_or_unknown_command_cannot_probe_terminal_evidence(
    client,
    auth_user,
    user_id: str | None,
    command_id: str | None,
) -> None:
    context, claimed, _runtime = await _claimed_context(
        client,
        auth_user,
        f"evidence-command-probe-{user_id or 'unknown'}",
    )

    with pytest.raises(ValueError, match="^EVIDENCE_PACKAGE_TERMINAL_COMMAND_REQUIRED$"):
        await EvidencePackageService(
            dataset_registry=_dataset_registry(context)
        ).build_for_terminal_command(
            user_id=user_id or context["user_id"],
            command_id=command_id or claimed.command_id,
        )


@pytest.mark.asyncio
async def test_succeeded_command_with_rejected_evaluation_cannot_build_approval_evidence(
    client,
    auth_user,
) -> None:
    graph = await _finalized_command_graph(
        client,
        auth_user,
        "evidence-command-rejected",
        passed=False,
    )
    assert graph["result"].command_status == "SUCCEEDED"
    assert graph["result"].evaluation_status == "REJECTED"

    with pytest.raises(ValueError, match="^EVIDENCE_PACKAGE_TERMINAL_COMMAND_REQUIRED$"):
        await EvidencePackageService(
            dataset_registry=_dataset_registry(graph["context"])
        ).build_for_terminal_command(
            user_id=graph["context"]["user_id"],
            command_id=graph["claimed"].command_id,
        )


@pytest.mark.asyncio
async def test_seven_plus_six_gates_from_two_evaluations_cannot_form_one_package(
    client,
    auth_user,
) -> None:
    graph = await _finalized_command_graph(client, auth_user, "evidence-command-split-gates")
    async with database.async_session_maker() as session:
        decoy = await _add_decoy_evaluation(session, graph)
        gates = list(
            (
                await session.scalars(
                    select(ResearchGateDecision)
                    .where(ResearchGateDecision.evaluation_id == graph["claimed"].evaluation_id)
                    .order_by(ResearchGateDecision.gate_code.asc())
                )
            ).all()
        )
        assert len(gates) == 13
        for gate in gates[7:]:
            gate.evaluation_id = decoy.id
        await session.commit()

    await _assert_command_graph_rejected(graph)


@pytest.mark.asyncio
async def test_unrelated_legacy_evaluation_does_not_change_command_scoped_package(
    client,
    auth_user,
) -> None:
    graph = await _finalized_command_graph(
        client,
        auth_user,
        "evidence-command-unrelated-legacy-evaluation",
    )
    service = EvidencePackageService(dataset_registry=_dataset_registry(graph["context"]))
    original = await service.build_for_terminal_command(
        user_id=graph["context"]["user_id"],
        command_id=graph["claimed"].command_id,
    )
    async with database.async_session_maker() as session:
        decoy = await _add_decoy_evaluation(session, graph)
        decoy.gate_inputs = {"input_evidence_hash": "f" * 64}
        await session.commit()

    repeated = await service.build_for_terminal_command(
        user_id=graph["context"]["user_id"],
        command_id=graph["claimed"].command_id,
    )
    assert repeated.id == original.id
    assert repeated.manifest_hash == original.manifest_hash
    validated = await service.validate_for_approval(
        candidate_id=graph["context"]["candidate"].id,
        promotion_policy_version=_POLICY_VERSION,
        gate_input_evidence_hash=graph["result"].input_evidence_hash,
        evidence_package_hash=original.manifest_hash,
    )
    assert validated.id == original.id


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign_evaluation", [False, True], ids=["null", "other-evaluation"])
async def test_extra_unbound_gate_cannot_hide_beside_thirteen_exact_gates(
    client,
    auth_user,
    foreign_evaluation: bool,
) -> None:
    graph = await _finalized_command_graph(
        client,
        auth_user,
        f"evidence-command-extra-gate-{foreign_evaluation}",
    )
    async with database.async_session_maker() as session:
        reference = await session.scalar(
            select(ResearchGateDecision).where(
                ResearchGateDecision.evaluation_id == graph["claimed"].evaluation_id,
                ResearchGateDecision.gate_code == "CANDIDATE_FROZEN",
            )
        )
        assert reference is not None
        evaluation_id = None
        if foreign_evaluation:
            evaluation_id = (await _add_decoy_evaluation(session, graph)).id
        session.add(
            ResearchGateDecision(
                candidate_id=reference.candidate_id,
                evaluation_id=evaluation_id,
                gate_code=reference.gate_code,
                policy_version=reference.policy_version,
                input_evidence_hash=reference.input_evidence_hash,
                status=reference.status,
                reason=reference.reason,
                executor_version=reference.executor_version,
            )
        )
        await session.commit()

    await _assert_command_graph_rejected(graph)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper",
    [
        "binding_missing",
        "binding_wrong",
        "claim_audit_wrong",
        "checkpoint_audit_missing",
        "terminal_audit_wrong",
        "artifact_content_missing",
        "artifact_wrong",
        "scan_content_missing",
        "scan_artifact_wrong",
    ],
)
async def test_missing_or_mismatched_authority_layer_rejects_evidence_package(
    client,
    auth_user,
    tamper: str,
) -> None:
    graph = await _finalized_command_graph(
        client,
        auth_user,
        f"evidence-command-tamper-{tamper}",
    )
    async with database.async_session_maker() as session:
        binding = await session.scalar(
            select(ResearchHoldoutArtifactBinding).where(
                ResearchHoldoutArtifactBinding.command_id == graph["claimed"].command_id
            )
        )
        assert binding is not None
        claim_audit = await _access_audit(session, graph, "CLAIM_STARTED")
        checkpoint_audit = await _access_audit(session, graph, "CHECKPOINT_RECORDED")
        terminal_audit = await _access_audit(session, graph, "FINALIZE_COMPLETED")
        artifact = await session.get(ResearchArtifact, binding.artifact_id)
        retained = await session.get(ResearchArtifactContent, binding.artifact_id)
        assert artifact is not None and retained is not None
        scan_artifact = graph["security_scan_artifact"]
        assert scan_artifact is not None
        stored_scan_artifact = await session.get(ResearchArtifact, scan_artifact.id)
        stored_scan_content = await session.get(ResearchArtifactContent, scan_artifact.id)
        assert stored_scan_artifact is not None and stored_scan_content is not None

        if tamper == "binding_missing":
            await session.delete(binding)
        elif tamper == "binding_wrong":
            binding.authority_binding_hash = "0" * 64
        elif tamper == "claim_audit_wrong":
            claim_audit.reason_code = "FORGED_CLAIM_AUTHORITY"
        elif tamper == "checkpoint_audit_missing":
            await session.delete(checkpoint_audit)
        elif tamper == "terminal_audit_wrong":
            terminal_audit.actor_identity = "not-the-terminal-worker"
        elif tamper == "artifact_content_missing":
            await session.delete(retained)
        elif tamper == "artifact_wrong":
            artifact.size_bytes += 1
        elif tamper == "scan_content_missing":
            await session.delete(stored_scan_content)
        else:
            stored_scan_artifact.size_bytes += 1
        await session.commit()

    await _assert_command_graph_rejected(graph)


@pytest.mark.asyncio
async def test_two_accepted_terminal_audits_cannot_authorize_one_package(
    client,
    auth_user,
) -> None:
    graph = await _finalized_command_graph(client, auth_user, "evidence-command-double-terminal")
    async with database.async_session_maker() as session:
        terminal = await _access_audit(session, graph, "FINALIZE_COMPLETED")
        session.add(
            ResearchHoldoutAccessAudit(
                actor_identity="forged-reconciler",
                evaluator_version=terminal.evaluator_version,
                requested_command_id=terminal.requested_command_id,
                action="RECONCILE_COMPLETED",
                result="ACCEPTED",
                reason_code="HOLDOUT_FINALIZE_RECONCILED",
                command_id=terminal.command_id,
                authorization_id=terminal.authorization_id,
                evaluation_id=terminal.evaluation_id,
                experiment_epoch_id=terminal.experiment_epoch_id,
                candidate_id=terminal.candidate_id,
                dataset_snapshot_id=terminal.dataset_snapshot_id,
                lease_generation=terminal.lease_generation,
                trace_id=terminal.trace_id,
                created_at=terminal.created_at,
            )
        )
        await session.commit()

    await _assert_command_graph_rejected(graph)


@pytest.mark.asyncio
async def test_finalize_unknown_then_new_worker_reconcile_builds_transition_bound_package(
    client,
    auth_user,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "evidence-command-finalize-unknown",
    )
    measurements, scan_artifact = await _passing_measurements(context, claimed, runtime)
    finalizer = HoldoutFinalizeService._for_test_only_inline_measurements()
    await finalizer.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=measurements,
    )
    await finalizer._fence_unknown(
        command_id=claimed.command_id,
        runtime=runtime,
        action="FINALIZE_UNKNOWN",
        reason_code="HOLDOUT_FINALIZE_COMMIT_OUTCOME_UNKNOWN",
    )
    reconciler = replace(runtime, worker_identity="evidence-finalize-unknown-reconciler")
    result = await finalizer.reconcile_checkpointed_evaluation(
        command_id=claimed.command_id,
        runtime=reconciler,
    )
    assert result.evaluation_status == "PASSED"

    package = await EvidencePackageService(
        dataset_registry=_dataset_registry(context)
    ).build_for_terminal_command(
        user_id=context["user_id"],
        command_id=claimed.command_id,
    )
    audits = {
        item["action"]: item for item in package.manifest["material"]["holdout_access_audits"]
    }
    assert set(audits) == {
        "CLAIM_STARTED",
        "CHECKPOINT_RECORDED",
        "FINALIZE_UNKNOWN",
        "RECONCILE_COMPLETED",
    }
    assert audits["FINALIZE_UNKNOWN"]["actor_identity"] == runtime.worker_identity
    assert audits["FINALIZE_UNKNOWN"]["result"] == "UNKNOWN"
    assert audits["FINALIZE_UNKNOWN"]["command_id"] is None
    assert audits["RECONCILE_COMPLETED"]["actor_identity"] == reconciler.worker_identity
    assert any(
        item["id"] == scan_artifact.id and item["content_hash"] == scan_artifact.content_hash
        for item in package.manifest["material"]["artifacts"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("backdated_recovery_audit", [False, True], ids=["valid", "backdated"])
async def test_new_worker_recovers_expired_lease_then_reconciles_evidence_package(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    backdated_recovery_audit: bool,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "evidence-command-new-worker-recovery",
    )
    measurements, _scan_artifact = await _passing_measurements(context, claimed, runtime)
    finalizer = HoldoutFinalizeService._for_test_only_inline_measurements()
    await finalizer.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=measurements,
    )
    async with database.async_session_maker() as session:
        binding = await session.scalar(
            select(ResearchHoldoutArtifactBinding).where(
                ResearchHoldoutArtifactBinding.command_id == claimed.command_id
            )
        )
        assert binding is not None
        lease_expires_at = binding.lease_expires_at
        if lease_expires_at.tzinfo is None or lease_expires_at.utcoffset() is None:
            lease_expires_at = lease_expires_at.replace(tzinfo=timezone.utc)
    recovery_time = lease_expires_at + timedelta(seconds=1)

    async def database_time_after_expiry(_session: AsyncSession) -> datetime:
        return recovery_time

    monkeypatch.setattr(holdout_claim_module, "database_utc_now", database_time_after_expiry)
    monkeypatch.setattr(holdout_finalize_module, "database_utc_now", database_time_after_expiry)
    recovery_runtime = replace(runtime, worker_identity="evidence-expired-recovery-worker")
    reconciler = replace(runtime, worker_identity="evidence-expired-reconcile-worker")
    recovered = await HoldoutClaimService().recover_expired(
        command_id=claimed.command_id,
        runtime=recovery_runtime,
    )
    assert recovered.status == "RECONCILING"
    result = await finalizer.reconcile_checkpointed_evaluation(
        command_id=claimed.command_id,
        runtime=reconciler,
    )
    assert result.evaluation_status == "PASSED"

    if backdated_recovery_audit:
        async with database.async_session_maker() as session:
            audit = await _access_audit(session, {"claimed": claimed}, "LEASE_EXPIRED_RECONCILING")
            audit.created_at = lease_expires_at - timedelta(microseconds=1)
            await session.commit()

    service = EvidencePackageService(dataset_registry=_dataset_registry(context))
    if backdated_recovery_audit:
        with pytest.raises(ValueError, match="^EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID$"):
            await service.build_for_terminal_command(
                user_id=context["user_id"],
                command_id=claimed.command_id,
            )
        return

    package = await service.build_for_terminal_command(
        user_id=context["user_id"], command_id=claimed.command_id
    )
    audits = {
        item["action"]: item for item in package.manifest["material"]["holdout_access_audits"]
    }
    assert set(audits) == {
        "CLAIM_STARTED",
        "CHECKPOINT_RECORDED",
        "LEASE_EXPIRED_RECONCILING",
        "RECONCILE_COMPLETED",
    }
    assert audits["LEASE_EXPIRED_RECONCILING"]["actor_identity"] == recovery_runtime.worker_identity
    assert audits["RECONCILE_COMPLETED"]["actor_identity"] == reconciler.worker_identity


@pytest.mark.asyncio
async def test_manifest_v1_is_never_valid_approval_authority(auth_user) -> None:
    context = await _legacy_evidence_context(auth_user, "evidence-command-v1-approval")
    material = {
        "binding_version": _MANIFEST_V1,
        "candidate_id": context["candidate"].id,
    }
    manifest = {
        "manifest_version": _MANIFEST_V1,
        "material": material,
        "human_decisions": [],
    }
    package = ResearchEvidencePackage(
        user_id=context["user_id"],
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        promotion_policy_version=_POLICY_VERSION,
        gate_input_evidence_hash="1" * 64,
        manifest=manifest,
        manifest_hash=content_hash(manifest),
        approval_binding_hash=content_hash(material),
        status="ACTIVE",
    )
    async with database.async_session_maker() as session:
        session.add(package)
        await session.commit()
        await session.refresh(package)

    with pytest.raises(
        ValueError,
        match="^APPROVAL_EVIDENCE_PACKAGE_VERSION_UNSUPPORTED$",
    ):
        await EvidencePackageService(
            dataset_registry=_dataset_registry(context)
        ).validate_for_approval(
            candidate_id=context["candidate"].id,
            promotion_policy_version=_POLICY_VERSION,
            gate_input_evidence_hash="1" * 64,
            evidence_package_hash=package.manifest_hash,
        )


async def _finalized_command_graph(
    client,
    auth_user,
    suffix: str,
    *,
    passed: bool = True,
) -> dict[str, Any]:
    """Create terminal evidence only through the real claim/checkpoint/finalize services."""

    context, claimed, runtime = await _claimed_context(client, auth_user, suffix)
    security_scan_artifact = None
    if passed:
        measurements, security_scan_artifact = await _passing_measurements(
            context,
            claimed,
            runtime,
        )
    else:
        measurements = await _trusted_rejecting_measurements(context)
    finalize = HoldoutFinalizeService._for_test_only_inline_measurements()
    checkpoint = await finalize.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=measurements,
    )
    result = await finalize.finalize_claimed_evaluation(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
    )
    assert result.command_status == "SUCCEEDED"
    assert result.evaluation_status == ("PASSED" if passed else "REJECTED")
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
    assert command is not None
    return {
        "context": context,
        "claimed": claimed,
        "runtime": runtime,
        "checkpoint": checkpoint,
        "result": result,
        "command": command,
        "security_scan_artifact": security_scan_artifact,
    }


async def _passing_measurements(
    context: dict[str, Any],
    claimed,
    runtime,
) -> tuple[dict[str, Any], ResearchArtifact]:
    candidate = context["candidate"]
    async with database.async_session_maker() as session:
        run = await session.get(ResearchRun, candidate.run_id)
        discovery = await session.get(ResearchDatasetSnapshot, candidate.dataset_snapshot_id)
        code = await session.get(ResearchArtifact, candidate.code_artifact_id)
        dependency = await session.get(ResearchArtifact, candidate.dependency_artifact_id)
    assert run is not None and discovery is not None
    assert code is not None and dependency is not None
    measurements = await _trusted_passing_measurements(
        {"candidate": candidate, "discovery": discovery, "run": run}
    )
    scan_payload = {
        "schema_version": "security-scan-evidence-v1",
        "candidate_id": candidate.id,
        "candidate_hash": candidate.candidate_hash,
        "code_artifact_id": code.id,
        "code_hash": code.content_hash,
        "dependency_artifact_id": dependency.id,
        "dependency_hash": dependency.content_hash,
        "evaluator_identity": runtime.evaluator_identity,
        "evaluator_version": runtime.evaluator_image_digest,
        "scan_policy_version": "security-scan-policy-v1",
        "scanner_identity": "research-security-scanner",
        "scanner_image_digest": _SCANNER_IMAGE_DIGEST,
        "critical_findings": 0,
    }
    scan_artifact = await _persist_security_scan_artifact(scan_payload)
    measurements["security_scan_hash"] = scan_artifact.content_hash
    assert claimed.evaluation_id
    return measurements, scan_artifact


async def _add_decoy_evaluation(session, graph: dict[str, Any]) -> ResearchEvaluation:
    target = await session.get(ResearchEvaluation, graph["claimed"].evaluation_id)
    assert target is not None
    decoy = ResearchEvaluation(
        experiment_epoch_id=target.experiment_epoch_id,
        candidate_id=target.candidate_id,
        dataset_snapshot_id=target.dataset_snapshot_id,
        evaluation_type="ITERATION_VALIDATION",
        evaluator_identity=target.evaluator_identity,
        evaluator_version=target.evaluator_version,
        authorization_id=None,
        returns_artifact_id=target.returns_artifact_id,
        metrics={"promotion_eligible": True},
        gate_inputs=dict(target.gate_inputs),
        policy_version=target.policy_version,
        status="PASSED",
        started_at=target.started_at,
        completed_at=datetime.now(timezone.utc),
    )
    session.add(decoy)
    await session.flush()
    return decoy


async def _access_audit(session, graph: dict[str, Any], action: str):
    audit = await session.scalar(
        select(ResearchHoldoutAccessAudit).where(
            ResearchHoldoutAccessAudit.command_id == graph["claimed"].command_id,
            ResearchHoldoutAccessAudit.action == action,
        )
    )
    assert audit is not None
    return audit


async def _assert_command_graph_rejected(graph: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="^EVIDENCE_PACKAGE_COMMAND_GRAPH_INVALID$"):
        await EvidencePackageService(
            dataset_registry=_dataset_registry(graph["context"])
        ).build_for_terminal_command(
            user_id=graph["context"]["user_id"],
            command_id=graph["claimed"].command_id,
        )
