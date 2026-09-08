from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_research_v2 import ResearchGovernanceDecision, ResearchRun
from app.models.user import User
from app.services.research.orchestrator import (
    ResearchOrchestrator,
    _evidence_class,
    _evidence_package_payload,
    _gate_payload,
)


def test_evidence_class_reports_recorded_layer_without_implying_gate_pass() -> None:
    assert (
        _evidence_class(candidates=[], trials=[], evaluations=[], gates=[], decisions=[])
        == "PROTOCOL_V2_PENDING"
    )


def test_evidence_package_projection_includes_exact_command_and_evaluation_binding() -> None:
    """The UI can prove package linkage without receiving the controlled manifest."""

    package = SimpleNamespace(
        id="package-1",
        candidate_id="candidate-1",
        command_id="command-1",
        evaluation_id="evaluation-1",
        promotion_policy_version="promotion-v1",
        gate_input_evidence_hash="a" * 64,
        manifest={"raw_sealed": "must-never-cross-api"},
        manifest_hash="b" * 64,
        approval_binding_hash="c" * 64,
        status="ACTIVE",
        created_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )

    assert _evidence_package_payload(package) == {
        "id": "package-1",
        "candidate_id": "candidate-1",
        "command_id": "command-1",
        "evaluation_id": "evaluation-1",
        "promotion_policy_version": "promotion-v1",
        "gate_input_evidence_hash": "a" * 64,
        "manifest_hash": "b" * 64,
        "approval_binding_hash": "c" * 64,
        "status": "ACTIVE",
        "created_at": datetime(2026, 9, 8, tzinfo=timezone.utc),
    }
    assert (
        _evidence_class(candidates=[object()], trials=[], evaluations=[], gates=[], decisions=[])
        == "PROTOCOL_V2_CANDIDATE_RECORDED"
    )
    assert (
        _evidence_class(candidates=[], trials=[object()], evaluations=[], gates=[], decisions=[])
        == "PROTOCOL_V2_TRIALS_RECORDED"
    )
    assert (
        _evidence_class(candidates=[], trials=[], evaluations=[object()], gates=[], decisions=[])
        == "PROTOCOL_V2_EVALUATION_RECORDED"
    )
    assert (
        _evidence_class(candidates=[], trials=[], evaluations=[], gates=[object()], decisions=[])
        == "PROTOCOL_V2_GATE_DECISIONS_RECORDED"
    )
    assert (
        _evidence_class(candidates=[], trials=[], evaluations=[], gates=[], decisions=[object()])
        == "PROTOCOL_V2_HUMAN_DECISION_RECORDED"
    )


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("HOLDOUT_SECURITY_SCAN_PASSED", "HOLDOUT_SECURITY_SCAN_PASSED"),
        ("custom+ssh://user:secret@host/private", "RESEARCH_GATE_REASON_REDACTED"),
        ("data:text/plain", "RESEARCH_GATE_REASON_REDACTED"),
        ("请查data:text/plain,private", "RESEARCH_GATE_REASON_REDACTED"),
        ("file:/srv/private/result.json", "RESEARCH_GATE_REASON_REDACTED"),
        ("review,/srv/private/result.json", "RESEARCH_GATE_REASON_REDACTED"),
        ("请查/srv/research/private.sqlite", "RESEARCH_GATE_REASON_REDACTED"),
        (r"review=C:\Users\secret\result.json", "RESEARCH_GATE_REASON_REDACTED"),
        (r"请查C:\Users\operator\approval.txt", "RESEARCH_GATE_REASON_REDACTED"),
        (r"review,\\server\share\secret.json", "RESEARCH_GATE_REASON_REDACTED"),
        (r"请查\\fileserver\sealed\result.json", "RESEARCH_GATE_REASON_REDACTED"),
        (r"C:\\private\\sealed-result.json", "RESEARCH_GATE_REASON_REDACTED"),
        ("raw sharpe=4.2", "RESEARCH_GATE_REASON_REDACTED"),
        ("free-form evaluator prose", "RESEARCH_GATE_REASON_REDACTED"),
    ],
)
def test_workbench_gate_projection_allows_only_registered_reason_codes(
    reason: str,
    expected: str,
) -> None:
    gate = SimpleNamespace(
        id="gate-1",
        candidate_id="candidate-1",
        evaluation_id="evaluation-1",
        gate_code="SECURITY_SCAN",
        policy_version="promotion-v1",
        input_evidence_hash="a" * 64,
        status="PASS",
        reason=reason,
        executor_version="private-evaluator-build+credential",
        evaluated_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )

    payload = _gate_payload(gate)
    assert payload["reason"] == expected
    assert "executor_version" not in payload


@pytest.mark.asyncio
async def test_workbench_exposes_governance_deviation_without_upgrading_evidence_status(
    auth_user,
) -> None:
    """A deviation is visible as a limitation and never becomes a research-evidence PASS."""

    user, _headers = auth_user
    async with async_session_maker() as session:
        user_id = str(
            (
                await session.execute(select(User.id).where(User.username == user["username"]))
            ).scalar_one()
        )
        run = ResearchRun(
            user_id=user_id,
            hypothesis_version_id="governance-workbench-hypothesis",
            promotion_policy_version="promotion-v1",
            request_hash="a" * 64,
            capability_profile_id="governance-workbench-profile",
            capability_profile_version="v1",
            capability_evidence_hash="b" * 64,
            trace_id="trace-governance-workbench",
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        decision = ResearchGovernanceDecision(
            target_requirement_or_gate="NFR-PERF-001",
            original_status="BLOCKED",
            reason="Capacity benchmark is pending.",
            risk="Latency target is unproven.",
            compensating_controls=["Keep protocol v2 disabled."],
            actor_id=user_id,
            scope={"run_id": run.id},
            effective_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
            expires_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
        )
        session.add(decision)
        await session.commit()
        await session.refresh(decision)

    workbench = await ResearchOrchestrator().get_workbench(user_id, run.id)

    assert workbench is not None
    assert workbench["evidence_class"] == "PROTOCOL_V2_PENDING"
    assert workbench["governance_decisions"] == [
        {
            "id": decision.id,
            "target_requirement_or_gate": "NFR-PERF-001",
            "original_status": "BLOCKED",
            "reason": "Capacity benchmark is pending.",
            "risk": "Latency target is unproven.",
            "compensating_controls": ["Keep protocol v2 disabled."],
            "effective_at": decision.effective_at,
            "expires_at": decision.expires_at,
            "revoked_at": None,
        }
    ]


@pytest.mark.asyncio
async def test_workbench_does_not_project_a_foreign_actors_governance_deviation(auth_user) -> None:
    """A legacy/imported record cannot cross the actor boundary through a shared scope."""

    user, _headers = auth_user
    async with async_session_maker() as session:
        user_id = str(
            (
                await session.execute(select(User.id).where(User.username == user["username"]))
            ).scalar_one()
        )
        run = ResearchRun(
            user_id=user_id,
            hypothesis_version_id="foreign-governance-hypothesis",
            promotion_policy_version="promotion-v1",
            request_hash="c" * 64,
            capability_profile_id="foreign-governance-profile",
            capability_profile_version="v1",
            capability_evidence_hash="d" * 64,
            trace_id="trace-foreign-governance",
        )
        foreign_actor = User(
            id=str(uuid4()),
            username=f"foreign_governance_{uuid4().hex[:8]}",
            email=f"foreign_governance_{uuid4().hex[:8]}@test.com",
            hashed_password="not-used-by-this-test",
        )
        session.add_all([run, foreign_actor])
        await session.flush()
        session.add(
            ResearchGovernanceDecision(
                target_requirement_or_gate="NFR-PERF-001",
                original_status="BLOCKED",
                reason="Foreign record.",
                risk="Foreign record.",
                compensating_controls=["Foreign record."],
                actor_id=foreign_actor.id,
                scope={"run_id": run.id},
                effective_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
                expires_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
            )
        )
        await session.commit()
        await session.refresh(run)

    workbench = await ResearchOrchestrator().get_workbench(user_id, run.id)

    assert workbench is not None
    assert workbench["governance_decisions"] == []
