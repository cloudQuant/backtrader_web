"""Evidence-package authority tests for trusted protocol-v2 approvals."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import ANY

import pytest
from sqlalchemy import select

from app.api.strategy import research as research_api
from app.config import get_settings
from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchCandidate,
    ResearchCandidateFreezeReceipt,
    ResearchDatasetSnapshot,
    ResearchEvaluation,
    ResearchGateDecision,
    ResearchGovernanceDecision,
    ResearchHumanDecision,
    ResearchRun,
    ResearchTrial,
)
from app.models.user import User
from app.services.research.candidate_registry import (
    CandidateRegistry,
    strict_freeze_receipt_fingerprint,
)
from app.services.research.canonical import canonical_json, content_hash
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    InMemoryDatasetObjectResolver,
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.evidence_package import EvidencePackageService
from app.services.research.orchestrator import ResearchOrchestrator
from tests.conftest import app
from tests.test_ai_research_candidate_freeze_v2 import _published_candidate
from tests.test_ai_research_candidate_registry import (
    _context as _legacy_candidate_context,
)
from tests.test_ai_research_candidate_registry import (
    _dataset_registry as _legacy_dataset_registry,
)


@pytest.fixture(autouse=True)
def enable_protocol_v2_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)


@pytest.fixture(autouse=True)
def clear_holdout_overrides() -> None:
    yield
    app.dependency_overrides.pop(research_api.get_dataset_object_resolver, None)
    app.dependency_overrides.pop(research_api.get_holdout_request_service, None)


@pytest.mark.asyncio
async def test_server_builds_a_redacted_idempotent_evidence_package(client, auth_user) -> None:
    """Evidence used for approval is a server-stored immutable manifest."""

    graph, service, package = await _terminal_package(client, auth_user, "evidence-package-build")
    context = graph["context"]
    repeated = await service.build_for_terminal_command(
        user_id=context["user_id"],
        command_id=graph["claimed"].command_id,
    )

    assert repeated.id == package.id
    assert package.manifest_hash == content_hash(package.manifest)
    assert package.approval_binding_hash == content_hash(package.manifest["material"])
    material = package.manifest["material"]
    assert material["candidate"]["id"] == context["candidate"].id
    assert (
        material["strict_freeze_receipt_fingerprint"] == graph["command"].freeze_receipt_fingerprint
    )
    assert material["dataset"]["content_hash"] == context["discovery"].content_hash
    assert material["capability_profile"]["evidence_hash"] == "e" * 64
    assert material["holdout_command"]["id"] == graph["claimed"].command_id
    assert material["holdout_evaluation"]["id"] == graph["claimed"].evaluation_id
    assert len(material["gate_decisions"]) == 13

    exported = canonical_json(package.manifest)
    assert "controlled://" not in exported
    assert "canary-secret" not in exported
    assert "storage_uri" not in exported
    assert "generation_materialization_hash" not in exported
    assert "ledger_hash" not in exported
    assert "measurements" not in exported
    assert "token_hash" not in exported


@pytest.mark.asyncio
async def test_evidence_package_validation_rejects_changed_material_evidence(
    client,
    auth_user,
) -> None:
    """An approval package cannot remain current after ledger evidence changes."""

    graph, service, package = await _terminal_package(
        client,
        auth_user,
        "evidence-package-material-drift",
    )
    context = graph["context"]

    async with async_session_maker() as session:
        session.add(
            ResearchGovernanceDecision(
                target_requirement_or_gate="NFR-EVIDENCE-DRIFT",
                original_status="BLOCKED",
                reason="new governance evidence",
                risk="material package drift",
                compensating_controls=["rebuild forbidden for the same command"],
                actor_id=context["user_id"],
                scope={
                    "candidate_id": context["candidate"].id,
                    "run_id": context["run"].id,
                },
            )
        )
        await session.commit()

    with pytest.raises(ValueError, match="APPROVAL_EVIDENCE_PACKAGE_STALE"):
        await service.validate_for_approval(
            candidate_id=context["candidate"].id,
            promotion_policy_version="promotion-v1",
            gate_input_evidence_hash=graph["result"].input_evidence_hash,
            evidence_package_hash=package.manifest_hash,
        )


@pytest.mark.asyncio
async def test_evidence_package_keeps_human_decision_audit_outside_approval_binding(
    client,
    auth_user,
) -> None:
    """The approval decision itself is audit evidence, not a self-invalidating input."""

    graph, service, original = await _terminal_package(
        client,
        auth_user,
        "evidence-package-human-decision",
    )
    context = graph["context"]
    decision = ResearchHumanDecision(
        candidate_id=context["candidate"].id,
        decision="APPROVED",
        actor_id=context["user_id"],
        domain_permissions=["approve_research"],
        policy_version="approval-v1",
        approval_mode="single_actor",
        single_actor=True,
        risk_acknowledgement=True,
        challenge_records=[],
        evidence_package_hash=original.manifest_hash,
        idempotency_key="fixture-human-decision",
    )
    async with async_session_maker() as session:
        session.add(decision)
        await session.commit()
        await session.refresh(decision)

    updated = await service.build_for_terminal_command(
        user_id=context["user_id"],
        command_id=graph["claimed"].command_id,
    )

    assert updated.id == original.id
    assert updated.manifest_hash == original.manifest_hash
    assert updated.approval_binding_hash == original.approval_binding_hash
    assert "human_decisions" not in updated.manifest
    workbench = await ResearchOrchestrator().get_workbench(
        context["user_id"],
        context["run"].id,
    )
    assert workbench is not None
    assert any(item["id"] == decision.id for item in workbench["decisions"])
    await service.validate_for_approval(
        candidate_id=context["candidate"].id,
        promotion_policy_version="promotion-v1",
        gate_input_evidence_hash=graph["result"].input_evidence_hash,
        evidence_package_hash=original.manifest_hash,
    )


@pytest.mark.asyncio
async def test_workbench_exposes_only_safe_evidence_package_and_model_summaries(
    client,
    auth_user,
) -> None:
    """The UI projection identifies evidence without receiving its raw manifest."""

    graph, _service, package = await _terminal_package(
        client,
        auth_user,
        "evidence-package-workbench",
    )
    context = graph["context"]

    workbench = await ResearchOrchestrator().get_workbench(context["user_id"], context["run"].id)

    assert workbench is not None
    assert workbench["evidence_packages"] == [
        {
            "id": package.id,
            "candidate_id": context["candidate"].id,
            "command_id": graph["claimed"].command_id,
            "evaluation_id": graph["claimed"].evaluation_id,
            "promotion_policy_version": "promotion-v1",
            "gate_input_evidence_hash": graph["result"].input_evidence_hash,
            "manifest_hash": package.manifest_hash,
            "approval_binding_hash": package.approval_binding_hash,
            "status": "ACTIVE",
            "created_at": package.created_at,
        }
    ]
    assert workbench["model_invocations"] == [
        {
            "id": ANY,
            "provider": "test-provider",
            "requested_model": "research-default",
            "resolved_model": "test-model-v1",
            "prompt_template_version": "generation-v1",
            "token_usage": {"total": 10},
            "cost": {"usd": 0.001},
            "error_code": None,
            "created_at": ANY,
        }
    ]
    assert "controlled://" not in str(workbench["evidence_packages"])
    assert "manifest" not in workbench["evidence_packages"][0]


@pytest.mark.asyncio
async def test_evidence_package_build_requires_an_injected_live_dataset_registry(
    client,
    auth_user,
) -> None:
    """A stored attestation alone cannot authorize a new evidence package."""

    graph = await _terminal_graph(client, auth_user, "evidence-package-no-resolver")
    context = graph["context"]
    with pytest.raises(ValueError, match="DATASET_OBJECT_RESOLVER_REQUIRED"):
        await EvidencePackageService().build_for_terminal_command(
            user_id=context["user_id"],
            command_id=graph["claimed"].command_id,
        )


@pytest.mark.asyncio
async def test_evidence_package_rejects_a_drifted_attested_dataset(client, auth_user) -> None:
    """A changed server object cannot produce or validate approval evidence."""

    graph, service, package = await _terminal_package(
        client,
        auth_user,
        "evidence-package-dataset-drift",
    )
    context = graph["context"]

    _drift_discovery_object(context)
    with pytest.raises(ValueError, match="APPROVAL_EVIDENCE_PACKAGE_UNVERIFIABLE"):
        await service.validate_for_approval(
            candidate_id=context["candidate"].id,
            promotion_policy_version="promotion-v1",
            gate_input_evidence_hash=graph["result"].input_evidence_hash,
            evidence_package_hash=package.manifest_hash,
        )


@pytest.mark.asyncio
async def test_evidence_package_rejects_legacy_frozen_candidate_without_strict_receipt(
    auth_user,
) -> None:
    """A generation-v1 compatibility freeze is not approval authority."""

    user_id = await _user_id(auth_user)
    context = await _legacy_candidate_context(user_id)
    registry = CandidateRegistry(dataset_registry=_legacy_dataset_registry(context))
    candidate = await registry.create_mutable(
        user_id=user_id,
        run_id=context["run"].id,
        experiment_epoch_id=context["epoch"].id,
        dataset_snapshot_id=context["dataset"].id,
        code_artifact_id=context["code_artifact"].id,
        dependency_artifact_id=context["dependency_artifact"].id,
        environment_hash="e" * 64,
        cost_model_hash="c" * 64,
        params={"lookback": 20},
    )
    async with async_session_maker() as session:
        session.add(
            ResearchTrial(
                user_id=user_id,
                run_id=context["run"].id,
                candidate_id=candidate.id,
                ordinal=1,
                idempotency_key="legacy-evidence-package-trial",
                stage="VALIDATE",
                status="SUCCEEDED",
                input_hash="a" * 64,
                observed_market_performance=True,
                counts_as_market_trial=True,
                counting_reason="legacy fixture",
            )
        )
        await session.commit()
    candidate = await registry.freeze(
        user_id,
        candidate.id,
        frozen_by=user_id,
        expected_candidate_hash=candidate.candidate_hash,
    )

    with pytest.raises(ValueError, match="EVIDENCE_PACKAGE_TERMINAL_COMMAND_REQUIRED"):
        await EvidencePackageService(dataset_registry=_legacy_dataset_registry(context)).build(
            user_id=user_id,
            candidate_id=candidate.id,
            promotion_policy_version="promotion-v1",
            gate_input_evidence_hash="1" * 64,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("receipt_field", "drifted_value", "expected_error"),
    [
        ("ledger_hash", "0" * 64, "APPROVAL_EVIDENCE_PACKAGE_UNVERIFIABLE"),
        ("id", "drifted-freeze-receipt-id", "APPROVAL_EVIDENCE_PACKAGE_UNVERIFIABLE"),
    ],
)
async def test_evidence_package_validation_rejects_strict_receipt_drift(
    client,
    auth_user,
    receipt_field: str,
    drifted_value: str,
    expected_error: str,
) -> None:
    """A package cannot authorize approval after its freeze receipt is corrupted."""

    graph, service, package = await _terminal_package(
        client,
        auth_user,
        f"evidence-package-receipt-drift-{receipt_field}",
    )
    context = graph["context"]
    async with async_session_maker() as session:
        receipt = await session.scalar(
            select(ResearchCandidateFreezeReceipt).where(
                ResearchCandidateFreezeReceipt.candidate_id == context["candidate"].id
            )
        )
        assert receipt is not None
        setattr(receipt, receipt_field, drifted_value)
        await session.commit()

    with pytest.raises(ValueError, match=expected_error):
        await service.validate_for_approval(
            candidate_id=context["candidate"].id,
            promotion_policy_version="promotion-v1",
            gate_input_evidence_hash=graph["result"].input_evidence_hash,
            evidence_package_hash=package.manifest_hash,
        )


async def _terminal_graph(client, auth_user, suffix: str):
    """Create approval input through the real request/claim/checkpoint/finalize path."""

    from tests.test_ai_research_evidence_package_command_graph import (
        _finalized_command_graph,
    )

    graph = await _finalized_command_graph(client, auth_user, suffix)
    context = graph["context"]
    async with async_session_maker() as session:
        run = await session.get(ResearchRun, context["candidate"].run_id)
        discovery = await session.get(
            ResearchDatasetSnapshot,
            context["candidate"].dataset_snapshot_id,
        )
    assert run is not None and discovery is not None
    context["run"] = run
    context["discovery"] = discovery
    return graph


async def _terminal_package(client, auth_user, suffix: str):
    graph = await _terminal_graph(client, auth_user, suffix)
    context = graph["context"]
    service = EvidencePackageService(dataset_registry=_dataset_registry(context))
    package = await service.build_for_terminal_command(
        user_id=context["user_id"],
        command_id=graph["claimed"].command_id,
    )
    return graph, service, package


async def _context(auth_user, suffix: str) -> dict[str, object]:
    """Extend the real discovery publication/freeze chain with approval evidence."""

    context, dispatch, _attempt = await _published_candidate(auth_user, suffix)
    user_id = context["task"].user_id
    async with async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, context["candidate_id"])
        assert candidate is not None
        candidate_hash = candidate.candidate_hash

    candidate = await CandidateRegistry(dataset_registry=context["datasets"]).freeze_discovery(
        user_id=user_id,
        candidate_id=context["candidate_id"],
        frozen_by=user_id,
        expected_candidate_hash=candidate_hash,
    )
    async with async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, candidate.id)
        assert candidate is not None
        trial = await session.scalar(
            select(ResearchTrial).where(ResearchTrial.candidate_id == candidate.id)
        )
        receipt = await session.scalar(
            select(ResearchCandidateFreezeReceipt).where(
                ResearchCandidateFreezeReceipt.candidate_id == candidate.id
            )
        )
        assert trial is not None and trial.returns_artifact_id is not None
        assert receipt is not None
        returns_artifact = await session.get(ResearchArtifact, trial.returns_artifact_id)
        assert returns_artifact is not None
        evaluation = ResearchEvaluation(
            experiment_epoch_id=candidate.experiment_epoch_id,
            candidate_id=candidate.id,
            dataset_snapshot_id=candidate.dataset_snapshot_id,
            evaluation_type="ITERATION_VALIDATION",
            evaluator_identity="fixture-evaluator",
            evaluator_version="v1",
            returns_artifact_id=returns_artifact.id,
            metrics={"sharpe": 1.2, "secret": "canary-secret"},
            gate_inputs={"max_drawdown": 0.1},
            policy_version="promotion-v1",
            status="PASSED",
        )
        governance = ResearchGovernanceDecision(
            target_requirement_or_gate="NFR-PERF-001",
            original_status="BLOCKED",
            reason="fixture governance decision",
            risk="controlled fixture risk",
            compensating_controls=["fixture"],
            actor_id=user_id,
            scope={"candidate_id": candidate.id, "run_id": candidate.run_id},
        )
        session.add_all([evaluation, governance])
        await session.flush()
        session.add_all(
            [
                ResearchGateDecision(
                    candidate_id=candidate.id,
                    evaluation_id=evaluation.id,
                    gate_code=code,
                    policy_version="promotion-v1",
                    input_evidence_hash="1" * 64,
                    status="PASS",
                    reason="fixture",
                    executor_version="promotion-gate-v1",
                )
                for code in (
                    "CANDIDATE_FROZEN",
                    "EVIDENCE_BINDING",
                    "DEFLATED_SHARPE",
                    "MAX_DRAWDOWN",
                )
            ]
        )
        await session.commit()
        await session.refresh(governance)
        dataset = await session.get(ResearchDatasetSnapshot, candidate.dataset_snapshot_id)
        run = await session.get(ResearchRun, candidate.run_id)
        assert dataset is not None and run is not None

    return {
        **context,
        "user_id": user_id,
        "candidate": candidate,
        "dataset": dataset,
        "governance": governance,
        "returns_artifact": returns_artifact,
        "run": run,
        "dispatch": dispatch,
        "strict_freeze_receipt_id": receipt.id,
        "strict_freeze_receipt_fingerprint": strict_freeze_receipt_fingerprint(receipt),
    }


def _dataset_registry(context: dict[str, object]) -> DatasetRegistry:
    datasets = context["datasets"]
    assert isinstance(datasets, DatasetRegistry)
    return datasets


def _drift_discovery_object(context: dict[str, object]) -> None:
    resolver = context["resolver"]
    assert isinstance(resolver, InMemoryDatasetObjectResolver)
    if "attestation" not in context:
        snapshot = context["discovery"]
        assert isinstance(snapshot, ResearchDatasetSnapshot)
        assert snapshot.object_receipt_id is not None
        assert snapshot.object_logical_id is not None
        assert snapshot.object_size_bytes is not None
        assert snapshot.storage_uri is not None
        resolver.register(
            DatasetObjectAttestation(
                receipt_id=f"{snapshot.object_receipt_id}-drift",
                user_id=snapshot.user_id,
                logical_object_id=snapshot.object_logical_id,
                object_version="version-2",
                object_digest="f" * 64,
                object_size_bytes=snapshot.object_size_bytes,
                storage_uri=snapshot.storage_uri,
                attested_at=datetime.now(timezone.utc),
            )
        )
        return
    attestation = context["attestation"]
    assert isinstance(attestation, DatasetObjectAttestation)
    resolver.register(
        replace(
            attestation,
            receipt_id=f"{attestation.receipt_id}-drift",
            object_version="version-2",
            object_digest="f" * 64,
        )
    )


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == user["username"]))
        return str(result.scalar_one())
