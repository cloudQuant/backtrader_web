"""Contracts for append-only trusted-research governance deviations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_research_v2 import ResearchGovernanceDecision, ResearchRun
from app.models.user import User


@pytest.mark.asyncio
async def test_governance_deviation_preserves_original_failure_and_is_idempotent(auth_user) -> None:
    """A permitted deviation records risk without rewriting the failed requirement."""

    try:
        from app.services.research.governance import (
            GovernanceDecisionService,
            GovernanceDeviationPolicy,
        )
    except ImportError as exc:
        pytest.fail(f"governance deviation service is missing: {exc}")

    user_id = await _user_id(auth_user)
    run = await _run(user_id)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    policy = GovernanceDeviationPolicy(
        version="governance-v1",
        waivable_targets=frozenset({"NFR-PERF-001"}),
    )
    service = GovernanceDecisionService()

    recorded = await service.record(
        actor_id=user_id,
        policy=policy,
        target_requirement_or_gate="NFR-PERF-001",
        original_status="FAIL",
        reason="Target hardware capacity is temporarily unavailable.",
        risk="The response-time target has not been demonstrated on the target topology.",
        compensating_controls=("Keep protocol v2 disabled.", "Re-test before enablement."),
        scope={"run_id": run.id},
        idempotency_key="performance-deviation-1",
        expires_at=expires_at,
    )
    replayed = await service.record(
        actor_id=user_id,
        policy=policy,
        target_requirement_or_gate="NFR-PERF-001",
        original_status="FAIL",
        reason="Target hardware capacity is temporarily unavailable.",
        risk="The response-time target has not been demonstrated on the target topology.",
        compensating_controls=("Keep protocol v2 disabled.", "Re-test before enablement."),
        scope={"run_id": run.id},
        idempotency_key="performance-deviation-1",
        expires_at=expires_at,
    )

    assert replayed.id == recorded.id
    assert recorded.original_status == "FAIL"
    assert recorded.target_requirement_or_gate == "NFR-PERF-001"
    assert recorded.expires_at is not None
    assert recorded.expires_at.replace(tzinfo=timezone.utc) == expires_at
    async with async_session_maker() as session:
        stored = await session.get(ResearchGovernanceDecision, recorded.id)
    assert stored is not None
    assert stored.original_status == "FAIL"
    assert stored.scope == {"run_id": run.id}
    assert stored.revoked_at is None


@pytest.mark.asyncio
async def test_governance_deviation_can_be_revoked_by_its_recorded_actor(auth_user) -> None:
    """Revocation changes only the explicit revocation field, never the original status."""

    from app.services.research.governance import (
        GovernanceDecisionService,
        GovernanceDeviationPolicy,
    )

    user_id = await _user_id(auth_user)
    run = await _run(user_id)
    service = GovernanceDecisionService()
    recorded = await service.record(
        actor_id=user_id,
        policy=GovernanceDeviationPolicy(
            version="governance-v1",
            waivable_targets=frozenset({"NFR-PERF-001"}),
        ),
        target_requirement_or_gate="NFR-PERF-001",
        original_status="BLOCKED",
        reason="Capacity benchmark is deferred.",
        risk="Latency target remains unproven.",
        compensating_controls=("Keep protocol v2 disabled.",),
        scope={"run_id": run.id},
        idempotency_key="performance-deviation-revoke",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    revoked = await service.revoke(
        decision_id=recorded.id,
        actor_id=user_id,
        now=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )

    assert revoked.original_status == "BLOCKED"
    assert revoked.revoked_at is not None
    assert revoked.revoked_at.replace(tzinfo=timezone.utc) == datetime(
        2026, 9, 6, tzinfo=timezone.utc
    )


@pytest.mark.asyncio
async def test_governance_policy_rejects_non_performance_targets_even_if_allowlisted() -> None:
    """A deployment setting cannot turn a security requirement into a waivable target."""

    from app.services.research.governance import (
        GovernanceDecisionService,
        GovernanceDeviationPolicy,
    )

    with pytest.raises(ValueError, match="GOVERNANCE_DEVIATION_POLICY_INVALID"):
        await GovernanceDecisionService().record(
            actor_id="unused-because-policy-fails-first",
            policy=GovernanceDeviationPolicy(
                version="governance-v1",
                waivable_targets=frozenset({"FR-SEC-001"}),
            ),
            target_requirement_or_gate="FR-SEC-001",
            original_status="BLOCKED",
            reason="Security deviations are never allowed.",
            risk="Security deviations are never allowed.",
            compensating_controls=("Not applicable.",),
            scope={"run_id": "not-read"},
            idempotency_key="invalid-security-policy",
            now=datetime.now(timezone.utc) - timedelta(hours=1),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == user["username"]))
    return str(result.scalar_one())


async def _run(user_id: str) -> ResearchRun:
    run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id="governance-hypothesis",
        promotion_policy_version="promotion-v1",
        request_hash="a" * 64,
        capability_profile_id="governance-profile",
        capability_profile_version="v1",
        capability_evidence_hash="b" * 64,
        trace_id="trace-governance",
    )
    async with async_session_maker() as session:
        session.add(run)
        await session.commit()
        await session.refresh(run)
    return run
