from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import database
from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchApprovalDenialFence,
    ResearchApprovalGrant,
    ResearchApprovalGrantAudit,
    ResearchApprovalRequest,
    ResearchCandidate,
    ResearchCapabilityProfile,
    ResearchHumanDecision,
    ResearchRun,
)
from app.models.permission import Role, user_roles
from app.models.user import User
from app.schemas.ai_research_v2 import ResearchApprovalContextResponse
from app.services.research.approval import (
    ApprovalService,
    approval_decision_intent_hash,
    safe_approval_human_text,
)
from app.services.research.approval_authority import (
    ApprovalAuthorityResolver,
    ApprovalGrantService,
    approval_grant_hash,
    server_approval_capabilities,
)
from app.services.research.canonical import content_hash
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.evidence_package import EvidencePackageService
from app.services.research.orchestrator import ResearchOrchestrator
from tests.conftest import register_and_login
from tests.test_ai_research_evidence_package import _terminal_graph


@pytest.fixture(autouse=True)
def enable_protocol_v2_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)


@dataclass
class _MutableDatabaseClock:
    value: datetime

    async def __call__(self, _session) -> datetime:
        return self.value


@pytest.mark.parametrize(
    ("intent", "expected_hash"),
    [
        (
            {
                "approval_request_id": "33333333-3333-3333-3333-333333333333",
                "decision": "APPROVED",
                "reason": "reviewed",
                "gate_input_evidence_hash": "a" * 64,
                "evidence_package_hash": "b" * 64,
                "challenge_keys": (),
                "challenge_responses": {},
                "residual_risk_acknowledgement": None,
            },
            "89901d373e7ddb7d05e0a2b692a3e63d376d8ebf2521e6058a687f06cbf6d6d3",
        ),
        (
            {
                "approval_request_id": "33333333-3333-3333-3333-333333333333",
                "decision": "APPROVED",
                "reason": "  已复核模型与执行风险  ",
                "gate_input_evidence_hash": "a" * 64,
                "evidence_package_hash": "b" * 64,
                "challenge_keys": ("execution_risk", "model_risk"),
                "challenge_responses": {
                    "model_risk": "  模型风险已核验  ",
                    "execution_risk": " 执行风险已核验 ",
                },
                "residual_risk_acknowledgement": "  我接受剩余风险  ",
            },
            "e916b06214b9fae440a1bc5bc5e1613722981350d2f8dc83f98e5e9717bb13b5",
        ),
        (
            {
                "approval_request_id": "33333333-3333-3333-3333-333333333333",
                "decision": "REJECTED",
                "reason": " see s3://private-bucket/raw and SEALED_METRICS_MUST_NOT_ESCAPE ",
                "gate_input_evidence_hash": "a" * 64,
                "evidence_package_hash": "b" * 64,
                "challenge_keys": ("review_note",),
                "challenge_responses": {"review_note": "  请重新验证  "},
                "residual_risk_acknowledgement": "",
            },
            "ea6c4d781ddf3541f224f2b29813d051f69a3cfb865f1e26735c471729bd002f",
        ),
        (
            {
                "approval_request_id": "33333333-3333-3333-3333-333333333333",
                "decision": "APPROVED",
                "reason": "\ufeffBOM保留\ufeff",
                "gate_input_evidence_hash": "a" * 64,
                "evidence_package_hash": "b" * 64,
                "challenge_keys": ("unicode",),
                "challenge_responses": {"unicode": "\u0085答案\u0085"},
                "residual_risk_acknowledgement": "\u0085风险\u0085",
            },
            "6e023614f08ecb90f17f866031ebfbf8b8314ca08edb669d759c2cb402812099",
        ),
    ],
)
def test_decision_intent_hash_cross_language_vectors(
    intent: dict[str, object],
    expected_hash: str,
) -> None:
    """Freeze UTF-8/canonical JSON vectors shared with the browser client."""

    assert approval_decision_intent_hash(**intent) == expected_hash


@pytest.mark.parametrize(
    "value",
    [
        "custom+ssh://user:secret@host/private",
        "data:text/plain",
        "请查data:text/plain,private",
        "file:/srv/private/research/result.json",
        "review,/srv/private/research/result.json",
        "请查/srv/research/private.sqlite",
        r"review=C:\Users\secret\result.json",
        r"请查C:\Users\operator\approval.txt",
        r"review,\\server\share\sealed-result.json",
        r"请查\\fileserver\sealed\result.json",
        "mailto://user@example.test",
        "/var/private/research/result.json",
        r"C:\\private\\research\\result.json",
        r"\\\\server\\share\\sealed-result.json",
        "raw pnl=123.45",
        "sealed_score: 0.91",
        "credential_uri=postgresql://user:password@db/research",
    ],
)
def test_safe_approval_human_text_redacts_uri_paths_and_sealed_values(value: str) -> None:
    assert safe_approval_human_text(value) == "[REDACTED]"


def test_safe_approval_human_text_preserves_ordinary_chinese() -> None:
    value = "这是需要人工复核的中文说明。"

    assert safe_approval_human_text(value) == value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"reason": 7}, "APPROVAL_REASON_REQUIRED"),
        ({"reason": "x" * 10_001}, "APPROVAL_REASON_REQUIRED"),
        (
            {"challenge_responses": {str(index): "ok" for index in range(33)}},
            "APPROVAL_CHALLENGE_INVALID",
        ),
        ({"challenge_responses": {"x" * 129: "ok"}}, "APPROVAL_CHALLENGE_INVALID"),
        ({"challenge_responses": {"key": "x" * 10_001}}, "APPROVAL_CHALLENGE_INVALID"),
        ({"challenge_responses": {"key": 7}}, "APPROVAL_CHALLENGE_INVALID"),
        ({"residual_risk_acknowledgement": "x" * 10_001}, "APPROVAL_RISK_ACKNOWLEDGEMENT_INVALID"),
        ({"residual_risk_acknowledgement": 7}, "APPROVAL_RISK_ACKNOWLEDGEMENT_INVALID"),
    ],
)
async def test_decide_service_boundary_rejects_oversized_or_wrong_typed_human_input(
    override: dict[str, object],
    expected: str,
) -> None:
    payload: dict[str, object] = {
        "authenticated_actor_id": "actor",
        "run_id": "run",
        "candidate_id": "candidate",
        "approval_request_id": "request",
        "decision": "REJECTED",
        "reason": "reviewed",
        "gate_input_evidence_hash": "a" * 64,
        "evidence_package_hash": "b" * 64,
        "idempotency_key": "service-boundary",
        "challenge_responses": {},
        "residual_risk_acknowledgement": None,
    }
    payload.update(override)

    with pytest.raises(ValueError, match=f"^{expected}$"):
        await ApprovalService().decide(**payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["request", "decision"])
@pytest.mark.parametrize("field", ["gate_input_evidence_hash", "evidence_package_hash"])
@pytest.mark.parametrize("invalid_value", [None, 7])
async def test_approval_service_rejects_non_string_evidence_hashes_with_stable_code(
    operation: str,
    field: str,
    invalid_value: object,
) -> None:
    common: dict[str, object] = {
        "authenticated_actor_id": "actor-id",
        "run_id": "run-id",
        "candidate_id": "candidate-id",
        "gate_input_evidence_hash": "a" * 64,
        "evidence_package_hash": "b" * 64,
        "idempotency_key": "invalid-hash-type",
    }
    common[field] = invalid_value

    with pytest.raises(ValueError, match="^APPROVAL_IDEMPOTENCY_OR_EVIDENCE_INVALID$"):
        if operation == "request":
            await ApprovalService().request_approval(**common)
        else:
            await ApprovalService().decide(
                **common,
                approval_request_id="request-id",
                decision="APPROVED",
                reason="reviewed",
            )


@pytest.mark.asyncio
async def test_multi_actor_owner_requests_and_only_exact_granted_reviewer_decides(
    client,
    auth_user,
) -> None:
    context = await _approval_context(client, auth_user, "approval-multi", mode="multi_actor")
    request = await context["service"].request_approval(
        authenticated_actor_id=context["owner_id"],
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key="multi-request",
    )
    assert request.status == "PENDING"
    assert request.policy_version == "approval-multi-v2"
    assert request.policy_material_hash

    reviewer, _headers = await register_and_login(client, username="approval-reviewer")
    reviewer_id = await _user_id(reviewer["username"])
    with pytest.raises(ValueError, match="^APPROVAL_GRANT_REQUIRED$"):
        await context["service"].decide(
            authenticated_actor_id=reviewer_id,
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            approval_request_id=request.id,
            decision="APPROVED",
            reason="independent review passed",
            gate_input_evidence_hash=context["gate_hash"],
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key="multi-decision-no-grant",
        )

    grant = await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    with pytest.raises(ValueError, match="^APPROVAL_SEPARATION_REQUIRED$"):
        await context["service"].decide(
            authenticated_actor_id=context["owner_id"],
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            approval_request_id=request.id,
            decision="APPROVED",
            reason="owner must not review",
            gate_input_evidence_hash=context["gate_hash"],
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key="owner-decision",
        )

    approved = await context["service"].decide(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        approval_request_id=request.id,
        decision="APPROVED",
        reason="independent review passed",
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key="multi-decision",
    )

    assert approved.grant_id == grant.id
    assert approved.grant_hash == grant.grant_hash
    assert approved.approval_request_id == request.id
    assert approved.domain_permissions == ["research:approve"]
    assert approved.decision_material_hash
    assert await context["service"].is_currently_approved(
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        promotion_policy_version="promotion-v1",
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
    )


@pytest.mark.asyncio
async def test_single_actor_uses_database_clock_cooldown_challenges_and_residual_risk(
    client,
    auth_user,
) -> None:
    context = await _approval_context(client, auth_user, "approval-single", mode="single_actor")
    owner_context = await context["service"].approval_context(
        authenticated_actor_id=context["owner_id"],
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
    )
    assert owner_context.can_request is True
    assert owner_context.can_decide is False
    assert owner_context.decision_blocked_reason == "AUTHORITY_REQUIRED"
    await _issue_grant(
        actor_id=context["owner_id"],
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    request = await context["service"].request_approval(
        authenticated_actor_id=context["owner_id"],
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key="single-request",
    )
    assert request.eligible_at > request.requested_at
    assert _utc(request.requested_at) == context["clock"].value
    assert _utc(request.eligible_at) == context["clock"].value + timedelta(seconds=60)
    assert _utc(request.expires_at) == context["clock"].value + timedelta(hours=1)

    decision_args = {
        "authenticated_actor_id": context["owner_id"],
        "run_id": context["run"].id,
        "candidate_id": context["candidate"].id,
        "approval_request_id": request.id,
        "decision": "APPROVED",
        "reason": "owner accepts explicitly documented residual risk",
        "gate_input_evidence_hash": context["gate_hash"],
        "evidence_package_hash": context["package"].manifest_hash,
        "idempotency_key": "single-decision",
    }
    challenges = {"model_risk": "reviewed", "execution_risk": "reviewed"}
    with pytest.raises(ValueError, match="^APPROVAL_COOLDOWN_ACTIVE$"):
        await context["service"].decide(
            **decision_args,
            challenge_responses=challenges,
            residual_risk_acknowledgement="I accept the documented residual model risk",
        )

    context["clock"].value = _utc(request.eligible_at)
    with pytest.raises(ValueError, match="^APPROVAL_CHALLENGE_INCOMPLETE"):
        await context["service"].decide(**decision_args)
    with pytest.raises(ValueError, match="^APPROVAL_RISK_ACKNOWLEDGEMENT_REQUIRED$"):
        await context["service"].decide(**decision_args, challenge_responses=challenges)

    approved = await context["service"].decide(
        **decision_args,
        challenge_responses=challenges,
        residual_risk_acknowledgement="I accept the documented residual model risk",
    )
    assert approved.single_actor is True
    assert approved.risk_acknowledgement is True
    assert len(approved.challenge_records) == 2
    expected_intent_hash = approval_decision_intent_hash(
        approval_request_id=request.id,
        decision="APPROVED",
        reason=decision_args["reason"],
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        challenge_keys=("execution_risk", "model_risk"),
        challenge_responses=challenges,
        residual_risk_acknowledgement="I accept the documented residual model risk",
    )
    replayed = await context["service"].decide(
        **decision_args,
        challenge_responses=challenges,
        residual_risk_acknowledgement="I accept the documented residual model risk",
    )
    assert replayed.id == approved.id
    view = await context["service"].approval_context(
        authenticated_actor_id=context["owner_id"],
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
    )
    assert view.latest_decision is not None
    assert view.latest_decision.decision_intent_hash == expected_intent_hash
    assert expected_intent_hash != approval_decision_intent_hash(
        approval_request_id=request.id,
        decision="APPROVED",
        reason=decision_args["reason"],
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        challenge_keys=("execution_risk", "model_risk"),
        challenge_responses={**challenges, "model_risk": "different answer"},
        residual_risk_acknowledgement="I accept the documented residual model risk",
    )
    assert expected_intent_hash != approval_decision_intent_hash(
        approval_request_id=request.id,
        decision="APPROVED",
        reason=decision_args["reason"],
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        challenge_keys=("execution_risk", "model_risk"),
        challenge_responses=challenges,
        residual_risk_acknowledgement="a different residual risk statement",
    )


@pytest.mark.asyncio
async def test_request_ttl_expiry_uses_the_injected_database_clock(
    client,
    auth_user,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        "approval-request-expiry",
        mode="single_actor",
        profile_expires_at_offset=timedelta(days=2),
    )
    await _issue_grant(
        actor_id=context["owner_id"],
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
        expires_at_offset=timedelta(days=1),
    )
    request = await _request(context, "approval-request-expiry-request")
    context["clock"].value = _utc(request.expires_at)

    with pytest.raises(ValueError, match="^APPROVAL_REQUEST_EXPIRED$"):
        await context["service"].decide(
            authenticated_actor_id=context["owner_id"],
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            approval_request_id=request.id,
            decision="REJECTED",
            reason="request expired before the decision transaction",
            gate_input_evidence_hash=context["gate_hash"],
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key="approval-request-expiry-decision",
        )


@pytest.mark.asyncio
async def test_single_actor_idempotency_compares_request_reason_challenges_risk_and_grant(
    client,
    auth_user,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        "approval-exact-replay",
        mode="single_actor",
    )
    original_grant = await _issue_grant(
        actor_id=context["owner_id"],
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    request = await _request(context, "exact-replay-request")
    context["clock"].value = _utc(request.eligible_at)
    kwargs = {
        "authenticated_actor_id": context["owner_id"],
        "run_id": context["run"].id,
        "candidate_id": context["candidate"].id,
        "approval_request_id": request.id,
        "decision": "APPROVED",
        "reason": "all semantic fields reviewed",
        "gate_input_evidence_hash": context["gate_hash"],
        "evidence_package_hash": context["package"].manifest_hash,
        "idempotency_key": "exact-replay-decision",
        "challenge_responses": {
            "model_risk": "model reviewed",
            "execution_risk": "execution reviewed",
        },
        "residual_risk_acknowledgement": "accepted residual risk A",
    }
    first = await context["service"].decide(**kwargs)
    assert (await context["service"].decide(**kwargs)).id == first.id

    variants = (
        {"reason": "changed reason"},
        {
            "challenge_responses": {
                "model_risk": "different model answer",
                "execution_risk": "execution reviewed",
            }
        },
        {"residual_risk_acknowledgement": "accepted residual risk B"},
    )
    for variant in variants:
        with pytest.raises(ValueError, match="^APPROVAL_IDEMPOTENCY_CONFLICT$"):
            await context["service"].decide(**{**kwargs, **variant})

    second_request = await _request(context, "exact-replay-second-request")
    with pytest.raises(ValueError, match="^APPROVAL_IDEMPOTENCY_CONFLICT$"):
        await context["service"].decide(**{**kwargs, "approval_request_id": second_request.id})

    context["clock"].value = _utc(first.decided_at) + timedelta(seconds=1)
    await ApprovalGrantService(clock=context["clock"]).revoke(
        authenticated_actor_id=context["owner_id"],
        run_id=context["run"].id,
        grant_id=original_grant.id,
        reason="grant rotation",
        idempotency_key="exact-replay-grant-revoke",
    )
    await _issue_grant(
        actor_id=context["owner_id"],
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    assert (await context["service"].decide(**kwargs)).id == first.id
    assert not await _is_approved(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("later_decision", ["REJECTED", "REQUESTED_CHANGES"])
async def test_decision_replay_is_exact_and_later_nonapproval_invalidates_old_approval(
    client,
    auth_user,
    later_decision: str,
) -> None:
    suffix = later_decision.lower()
    context = await _approval_context(
        client,
        auth_user,
        f"approval-replay-{suffix}",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username=f"approval-replay-reviewer-{suffix}",
    )
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    request = await _request(context, "approval-replay-request")
    kwargs = {
        "authenticated_actor_id": reviewer_id,
        "run_id": context["run"].id,
        "candidate_id": context["candidate"].id,
        "approval_request_id": request.id,
        "decision": "APPROVED",
        "reason": "exact evidence reviewed",
        "gate_input_evidence_hash": context["gate_hash"],
        "evidence_package_hash": context["package"].manifest_hash,
        "idempotency_key": "approval-replay-decision",
    }
    first = await context["service"].decide(**kwargs)
    replay = await context["service"].decide(**kwargs)
    assert replay.id == first.id
    with pytest.raises(ValueError, match="^APPROVAL_IDEMPOTENCY_CONFLICT$"):
        await context["service"].decide(**{**kwargs, "reason": "different reason"})

    context["clock"].value += timedelta(seconds=1)
    rejection_request = await _request(context, f"approval-later-request-{suffix}")
    rejected = await context["service"].decide(
        **{
            **kwargs,
            "approval_request_id": rejection_request.id,
            "decision": later_decision,
            "reason": "new review found a material issue",
            "idempotency_key": f"approval-later-decision-{suffix}",
        }
    )
    assert rejected.decision == later_decision
    assert not await context["service"].is_currently_approved(
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        promotion_policy_version="promotion-v1",
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("denial", ["REJECTED", "REQUESTED_CHANGES"])
async def test_exact_evidence_denial_fence_blocks_new_request_key(
    client,
    auth_user,
    denial: str,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        f"approval-denial-fence-{denial.lower()}",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username=f"approval-denial-fence-reviewer-{denial.lower()}",
    )
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    request = await _request(context, f"approval-denial-request-{denial.lower()}")
    await context["service"].decide(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        approval_request_id=request.id,
        decision=denial,
        reason="the exact evidence is denied",
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key=f"approval-denial-decision-{denial.lower()}",
    )

    with pytest.raises(ValueError, match="^APPROVAL_EVIDENCE_DENIED$"):
        await _request(context, f"approval-denial-retry-{denial.lower()}")


@pytest.mark.asyncio
async def test_exact_evidence_denial_fence_blocks_preexisting_pending_request(
    client,
    auth_user,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        "approval-denial-preexisting",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username="approval-denial-preexisting-reviewer",
    )
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    stale_request = await _request(context, "approval-denial-stale-request")
    denial_request = await _request(context, "approval-denial-current-request")
    await context["service"].decide(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        approval_request_id=denial_request.id,
        decision="REJECTED",
        reason="the exact evidence is denied",
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key="approval-denial-current-decision",
    )

    owner_view = await context["service"].approval_context(
        authenticated_actor_id=context["owner_id"],
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
    )
    assert owner_view.current_request is not None
    assert owner_view.current_request.id == stale_request.id
    assert owner_view.can_request is False
    assert owner_view.can_decide is False
    assert owner_view.can_approve is False
    assert owner_view.request_blocked_reason == "APPROVAL_EVIDENCE_DENIED"
    assert owner_view.decision_blocked_reason == "APPROVAL_EVIDENCE_DENIED"

    with pytest.raises(ValueError, match="^APPROVAL_EVIDENCE_DENIED$"):
        await context["service"].decide(
            authenticated_actor_id=reviewer_id,
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            approval_request_id=stale_request.id,
            decision="APPROVED",
            reason="a stale request must not override the denial",
            gate_input_evidence_hash=context["gate_hash"],
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key="approval-denial-stale-decision",
        )


@pytest.mark.asyncio
async def test_twenty_way_distinct_decision_race_cannot_bypass_denial_fence(
    client,
    auth_user,
) -> None:
    """SQLite proves one event-loop linearization, not cross-process database locking."""

    context = await _approval_context(
        client,
        auth_user,
        "approval-denial-twenty-way",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username="approval-denial-twenty-way-reviewer",
    )
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    requests = await asyncio.gather(
        *(_request(context, f"approval-denial-race-request-{index}") for index in range(20))
    )
    preexisting_pending = await _request(context, "approval-denial-race-preexisting-pending")
    release = asyncio.Event()
    all_ready = asyncio.Event()
    ready_lock = asyncio.Lock()
    ready_count = 0

    async def decide(index: int):
        nonlocal ready_count
        async with ready_lock:
            ready_count += 1
            if ready_count == 20:
                all_ready.set()
        await release.wait()
        return await context["service"].decide(
            authenticated_actor_id=reviewer_id,
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            approval_request_id=requests[index].id,
            decision="REJECTED" if index == 0 else "APPROVED",
            reason="exact evidence denied" if index == 0 else "concurrent approval attempt",
            gate_input_evidence_hash=context["gate_hash"],
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key=f"approval-denial-race-decision-{index}",
        )

    tasks = [asyncio.create_task(decide(index)) for index in range(20)]
    await asyncio.wait_for(all_ready.wait(), timeout=5)
    release.set()
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    rejected = outcomes[0]
    assert isinstance(rejected, ResearchHumanDecision)
    assert rejected.decision == "REJECTED"
    approval_outcomes = outcomes[1:]
    successful_approvals = [
        item
        for item in approval_outcomes
        if isinstance(item, ResearchHumanDecision) and item.decision == "APPROVED"
    ]
    failures = [item for item in approval_outcomes if isinstance(item, Exception)]
    assert len(successful_approvals) + len(failures) == 19
    assert {str(item) for item in failures} <= {
        "APPROVAL_EVIDENCE_DENIED",
        "APPROVAL_REQUEST_NOT_PENDING",
    }
    assert not await _is_approved(context)
    with pytest.raises(ValueError, match="^APPROVAL_EVIDENCE_DENIED$"):
        await _request(context, "approval-denial-race-after-fence")
    with pytest.raises(ValueError, match="^APPROVAL_EVIDENCE_DENIED$"):
        await context["service"].decide(
            authenticated_actor_id=reviewer_id,
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            approval_request_id=preexisting_pending.id,
            decision="APPROVED",
            reason="pending work cannot outlive an exact denial fence",
            gate_input_evidence_hash=context["gate_hash"],
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key="approval-denial-race-pending-decision",
        )
    async with async_session_maker() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ResearchApprovalDenialFence)) == 1
        )
        assert await session.scalar(
            select(func.count())
            .select_from(ResearchHumanDecision)
            .where(ResearchHumanDecision.decision == "APPROVED")
        ) == len(successful_approvals)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ResearchHumanDecision)
                .where(ResearchHumanDecision.decision.in_(("REJECTED", "REQUESTED_CHANGES")))
            )
            == 1
        )


@pytest.mark.asyncio
async def test_denial_fence_beats_same_timestamp_lexically_later_approval_in_currentness_and_context(
    client,
    auth_user,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        "approval-denial-same-timestamp",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username="approval-denial-same-timestamp-reviewer",
    )
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    approved_request = await _request(context, "approval-denial-same-approved-request")
    approved = await context["service"].decide(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        approval_request_id=approved_request.id,
        decision="APPROVED",
        reason="approved before the exact evidence was denied",
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key="approval-denial-same-approved-decision",
    )
    async with async_session_maker() as session:
        stored = await session.get(ResearchHumanDecision, approved.id)
        assert stored is not None
        stored.id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        await session.commit()

    denied_request = await _request(context, "approval-denial-same-denied-request")
    denied = await context["service"].decide(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        approval_request_id=denied_request.id,
        decision="REJECTED",
        reason="the exact evidence is now denied",
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key="approval-denial-same-denied-decision",
    )
    assert _utc(denied.decided_at) == _utc(approved.decided_at)
    assert not await _is_approved(context)

    view = await context["service"].approval_context(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
    )
    assert view.can_request is False
    assert view.can_decide is False
    assert view.can_approve is False
    assert view.request_blocked_reason == "APPROVAL_EVIDENCE_DENIED"
    assert view.decision_blocked_reason == "APPROVAL_EVIDENCE_DENIED"
    assert view.latest_decision is not None
    assert view.latest_decision.id == denied.id
    assert view.latest_decision.decision == "REJECTED"


@pytest.mark.asyncio
async def test_foreign_inactive_revoked_and_profile_drift_fail_closed(client, auth_user) -> None:
    context = await _approval_context(client, auth_user, "approval-fail-closed", mode="multi_actor")
    reviewer, _headers = await register_and_login(client, username="approval-fail-reviewer")
    reviewer_id = await _user_id(reviewer["username"])
    grant = await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    request = await _request(context, "approval-fail-request")
    approved = await context["service"].decide(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        approval_request_id=request.id,
        decision="APPROVED",
        reason="independent review passed",
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key="approval-fail-decision",
    )
    assert approved.decision == "APPROVED"

    foreign, _headers = await register_and_login(client, username="approval-foreign")
    foreign_id = await _user_id(foreign["username"])
    with pytest.raises(ValueError, match="^APPROVAL_SCOPE_NOT_FOUND$"):
        await context["service"].request_approval(
            authenticated_actor_id=foreign_id,
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            gate_input_evidence_hash=context["gate_hash"],
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key="foreign-request",
        )

    async with async_session_maker() as session:
        stored_grant = await session.get(ResearchApprovalGrant, grant.id)
        assert stored_grant is not None
        stored_grant.revoked_at = context["clock"].value
        stored_grant.revoked_by = context["owner_id"]
        stored_grant.revocation_reason = "rotation"
        await session.commit()
    assert not await _is_approved(context)

    async with async_session_maker() as session:
        stored_grant = await session.get(ResearchApprovalGrant, grant.id)
        reviewer_user = await session.get(User, reviewer_id)
        assert stored_grant is not None and reviewer_user is not None
        stored_grant.revoked_at = None
        stored_grant.revoked_by = None
        stored_grant.revocation_reason = None
        reviewer_user.is_active = False
        await session.commit()
    assert not await _is_approved(context)

    async with async_session_maker() as session:
        reviewer_user = await session.get(User, reviewer_id)
        profile = await session.scalar(
            select(ResearchCapabilityProfile).where(
                ResearchCapabilityProfile.profile_id == context["run"].capability_profile_id,
                ResearchCapabilityProfile.version == context["run"].capability_profile_version,
            )
        )
        owner_user = await session.get(User, context["owner_id"])
        assert reviewer_user is not None and owner_user is not None and profile is not None
        reviewer_user.is_active = True
        owner_user.is_active = False
        await session.commit()
    assert not await _is_approved(context)

    async with async_session_maker() as session:
        owner_user = await session.get(User, context["owner_id"])
        profile = await session.scalar(
            select(ResearchCapabilityProfile).where(
                ResearchCapabilityProfile.profile_id == context["run"].capability_profile_id,
                ResearchCapabilityProfile.version == context["run"].capability_profile_version,
            )
        )
        assert owner_user is not None and profile is not None
        owner_user.is_active = True
        profile.approval_capabilities = server_approval_capabilities("single_actor")
        await session.commit()
    assert not await _is_approved(context)

    async with async_session_maker() as session:
        profile = await session.scalar(
            select(ResearchCapabilityProfile).where(
                ResearchCapabilityProfile.profile_id == context["run"].capability_profile_id,
                ResearchCapabilityProfile.version == context["run"].capability_profile_version,
            )
        )
        assert profile is not None
        profile.approval_capabilities = {
            **server_approval_capabilities("multi_actor"),
            "policy_material_hash": "0" * 64,
        }
        await session.commit()
    assert not await _is_approved(context)


@pytest.mark.asyncio
async def test_approval_recomputes_complete_profile_material_after_request(
    client,
    auth_user,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        "approval-profile-material-tamper",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username="approval-profile-material-reviewer",
    )
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    request = await _request(context, "approval-profile-material-request")

    async with async_session_maker() as session:
        profile = await session.scalar(
            select(ResearchCapabilityProfile).where(
                ResearchCapabilityProfile.profile_id == context["run"].capability_profile_id,
                ResearchCapabilityProfile.version == context["run"].capability_profile_version,
            )
        )
        assert profile is not None
        profile.network_capabilities = {
            **dict(profile.network_capabilities or {}),
            "unexpected_mutation": True,
        }
        await session.commit()

    with pytest.raises(ValueError, match="^APPROVAL_REQUEST_EVIDENCE_MISMATCH$"):
        await context["service"].decide(
            authenticated_actor_id=reviewer_id,
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            approval_request_id=request.id,
            decision="APPROVED",
            reason="profile mutation must invalidate the request",
            gate_input_evidence_hash=context["gate_hash"],
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key="approval-profile-material-decision",
        )


@pytest.mark.asyncio
async def test_grant_service_requires_explicit_manager_and_issues_exact_human_scope(
    client,
    auth_user,
) -> None:
    from app.models.ai_research_v2 import ResearchApprovalGrantAudit
    from app.models.permission import Role, user_roles
    from app.services.research.approval_authority import ApprovalGrantService

    context = await _approval_context(
        client,
        auth_user,
        "approval-managed-grant",
        mode="multi_actor",
    )
    manager, _manager_headers = await register_and_login(
        client,
        username="approval-managed-grant-manager",
    )
    reviewer, _reviewer_headers = await register_and_login(
        client,
        username="approval-managed-grant-reviewer",
    )
    manager_id = await _user_id(manager["username"])
    reviewer_id = await _user_id(reviewer["username"])
    grants = ApprovalGrantService(clock=context["clock"])

    with pytest.raises(ValueError, match="^APPROVAL_GRANT_MANAGER_REQUIRED$"):
        await grants.issue(
            authenticated_actor_id=manager_id,
            run_id=context["run"].id,
            subject_id=reviewer_id,
            ttl_seconds=3600,
            idempotency_key="managed-grant-issue",
        )

    async with async_session_maker() as session:
        await session.execute(
            user_roles.insert().values(
                user_id=manager_id,
                role=Role.RESEARCH_APPROVAL_ADMIN.value,
            )
        )
        await session.commit()

    issued = await grants.issue(
        authenticated_actor_id=manager_id,
        run_id=context["run"].id,
        subject_id=reviewer_id,
        ttl_seconds=3600,
        idempotency_key="managed-grant-issue",
    )
    replay = await grants.issue(
        authenticated_actor_id=manager_id,
        run_id=context["run"].id,
        subject_id=reviewer_id,
        ttl_seconds=3600,
        idempotency_key="managed-grant-issue",
    )
    assert replay.id == issued.id
    assert issued.actor_id == reviewer_id
    assert issued.issuer_id == manager_id
    assert issued.run_id == context["run"].id
    assert issued.workspace_id == context["run"].workspace_id
    assert issued.permission == "research:approve"
    assert issued.subject_kind == issued.issuer_kind == "HUMAN"
    assert _utc(issued.expires_at) - _utc(issued.issued_at) == timedelta(hours=1)
    async with async_session_maker() as session:
        assert await session.scalar(select(func.count()).select_from(ResearchApprovalGrant)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(ResearchApprovalGrantAudit)) == 1
        )

    request = await _request(context, "managed-grant-approval-request")
    decision = await context["service"].decide(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        approval_request_id=request.id,
        decision="APPROVED",
        reason="reviewed with a control-plane-issued grant",
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key="managed-grant-approval-decision",
    )
    assert decision.grant_id == issued.id


@pytest.mark.asyncio
@pytest.mark.parametrize("audit_fault", ["orphan", "tampered", "duplicate"])
async def test_decision_authority_requires_one_complete_issued_grant_audit(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    audit_fault: str,
) -> None:
    import app.services.research.approval_authority as authority_module

    context = await _approval_context(
        client,
        auth_user,
        f"approval-grant-audit-{audit_fault}",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username=f"approval-grant-audit-reviewer-{audit_fault}",
    )
    reviewer_id = await _user_id(reviewer["username"])
    grant = await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    request = await _request(context, f"approval-grant-audit-request-{audit_fault}")
    if audit_fault in {"orphan", "tampered"}:
        async with async_session_maker() as session:
            audit = await session.scalar(
                select(ResearchApprovalGrantAudit).where(
                    ResearchApprovalGrantAudit.grant_id == grant.id,
                    ResearchApprovalGrantAudit.event_type == "ISSUED",
                )
            )
            assert audit is not None
            if audit_fault == "orphan":
                await session.execute(
                    delete(ResearchApprovalGrantAudit).where(
                        ResearchApprovalGrantAudit.id == audit.id
                    )
                )
            else:
                audit.command_material_hash = "f" * 64
            await session.commit()
    else:
        original_loader = authority_module._load_locked_issued_grant_audits

        async def duplicate_loader(session, grant_ids):
            audits = await original_loader(session, grant_ids)
            return [*audits, *audits]

        monkeypatch.setattr(
            authority_module,
            "_load_locked_issued_grant_audits",
            duplicate_loader,
        )

    with pytest.raises(ValueError, match="^APPROVAL_GRANT_AUDIT_INVALID$"):
        await context["service"].decide(
            authenticated_actor_id=reviewer_id,
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            approval_request_id=request.id,
            decision="APPROVED",
            reason="an unaudited grant cannot authorize a decision",
            gate_input_evidence_hash=context["gate_hash"],
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key=f"approval-grant-audit-decision-{audit_fault}",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("time_fault", "revocation_audit_fault"),
    [
        ("before_issue", None),
        ("at_expiry", None),
        ("revoked_before_decision", "missing"),
        ("revoked_before_decision", "tampered"),
        ("revoked_at_decision", "exact"),
        ("revoked_after_decision", "missing"),
        ("revoked_after_decision", "tampered"),
        ("revoked_after_decision", "duplicate"),
    ],
    ids=[
        "before-issued",
        "at-expiry",
        "revoked-before-missing-audit",
        "revoked-before-tampered-audit",
        "revoked-at-decision-exact-audit",
        "revoked-after-missing-audit",
        "revoked-after-tampered-audit",
        "revoked-after-duplicate-audit",
    ],
)
async def test_historical_decision_replay_requires_exact_grant_time_and_revocation_audit(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    time_fault: str,
    revocation_audit_fault: str | None,
) -> None:
    fixture = await _historical_replay_fixture(
        client,
        auth_user,
        f"approval-historical-window-{time_fault}-{revocation_audit_fault}",
    )
    context = fixture["context"]
    grant = fixture["grant"]
    written = fixture["decision"]

    if time_fault in {"before_issue", "at_expiry"}:
        async with async_session_maker() as session:
            stored = await session.get(ResearchHumanDecision, written.id)
            assert stored is not None
            if time_fault == "before_issue":
                stored.requested_at = _utc(grant.issued_at) - timedelta(seconds=2)
                stored.eligible_at = _utc(grant.issued_at) - timedelta(seconds=2)
                stored.decided_at = _utc(grant.issued_at) - timedelta(seconds=1)
            else:
                stored.decided_at = _utc(grant.expires_at)
                stored.expires_at = _utc(grant.expires_at) + timedelta(seconds=1)
            await session.commit()
    else:
        offset = {
            "revoked_before_decision": -1,
            "revoked_at_decision": 0,
            "revoked_after_decision": 1,
        }[time_fault]
        revoked_at = _utc(written.decided_at) + timedelta(seconds=offset)
        if revocation_audit_fault == "missing":
            async with async_session_maker() as session:
                stored_grant = await session.get(ResearchApprovalGrant, grant.id)
                assert stored_grant is not None
                stored_grant.revoked_at = revoked_at
                stored_grant.revoked_by = context["owner_id"]
                stored_grant.revocation_reason = "historical grant rotation"
                await session.commit()
        else:
            context["clock"].value = revoked_at
            await ApprovalGrantService(clock=context["clock"]).revoke(
                authenticated_actor_id=context["owner_id"],
                run_id=context["run"].id,
                grant_id=grant.id,
                reason="historical grant rotation",
                idempotency_key=f"historical-window-revoke-{time_fault}",
            )
            if revocation_audit_fault == "tampered":
                async with async_session_maker() as session:
                    audit = await session.scalar(
                        select(ResearchApprovalGrantAudit).where(
                            ResearchApprovalGrantAudit.grant_id == grant.id,
                            ResearchApprovalGrantAudit.event_type == "REVOKED",
                        )
                    )
                    assert audit is not None
                    audit.command_material_hash = "f" * 64
                    await session.commit()
            elif revocation_audit_fault == "duplicate":
                import app.services.research.approval_authority as authority_module

                original_loader = authority_module._load_locked_grant_audits

                async def duplicate_revocation_loader(session, grant_ids):
                    audits = await original_loader(session, grant_ids)
                    revoked = [audit for audit in audits if audit.event_type == "REVOKED"]
                    assert len(revoked) == 1
                    return [*audits, revoked[0]]

                monkeypatch.setattr(
                    authority_module,
                    "_load_locked_grant_audits",
                    duplicate_revocation_loader,
                )

    with pytest.raises(ValueError, match="^APPROVAL_IDEMPOTENCY_CONFLICT$"):
        await context["service"].decide(**fixture["decision_args"])


@pytest.mark.asyncio
@pytest.mark.parametrize("later_change", ["revoked", "expired"])
async def test_historical_decision_replay_allows_exact_later_revoke_or_expiry(
    client,
    auth_user,
    later_change: str,
) -> None:
    fixture = await _historical_replay_fixture(
        client,
        auth_user,
        f"approval-historical-later-{later_change}",
        grant_ttl=timedelta(seconds=60),
    )
    context = fixture["context"]
    grant = fixture["grant"]
    written = fixture["decision"]
    if later_change == "revoked":
        context["clock"].value = _utc(written.decided_at) + timedelta(seconds=1)
        await ApprovalGrantService(clock=context["clock"]).revoke(
            authenticated_actor_id=context["owner_id"],
            run_id=context["run"].id,
            grant_id=grant.id,
            reason="grant retired after the recorded decision",
            idempotency_key="historical-later-revoke",
        )
    else:
        context["clock"].value = _utc(grant.expires_at)

    replay = await context["service"].decide(**fixture["decision_args"])

    assert replay.id == written.id


@pytest.mark.asyncio
@pytest.mark.parametrize("non_human_identity", ["actor", "issuer"])
async def test_historical_decision_replay_requires_human_identity_but_not_current_grant(
    client,
    auth_user,
    non_human_identity: str,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        f"approval-historical-human-{non_human_identity}",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username=f"approval-historical-human-reviewer-{non_human_identity}",
    )
    reviewer_id = await _user_id(reviewer["username"])
    grant = await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    request = await _request(context, f"approval-historical-request-{non_human_identity}")
    decision_args = {
        "authenticated_actor_id": reviewer_id,
        "run_id": context["run"].id,
        "candidate_id": context["candidate"].id,
        "approval_request_id": request.id,
        "decision": "APPROVED",
        "reason": "historical exact replay",
        "gate_input_evidence_hash": context["gate_hash"],
        "evidence_package_hash": context["package"].manifest_hash,
        "idempotency_key": f"approval-historical-decision-{non_human_identity}",
    }
    written = await context["service"].decide(**decision_args)
    grants = ApprovalGrantService(clock=context["clock"])
    context["clock"].value = _utc(written.decided_at) + timedelta(seconds=1)
    await grants.revoke(
        authenticated_actor_id=context["owner_id"],
        run_id=context["run"].id,
        grant_id=grant.id,
        reason="grant retired after decision",
        idempotency_key=f"approval-historical-revoke-{non_human_identity}",
    )
    async with async_session_maker() as session:
        issuer = await session.get(User, context["owner_id"])
        assert issuer is not None
        issuer.is_active = False
        await session.commit()
    replay = await context["service"].decide(**decision_args)
    assert replay.id == written.id

    async with async_session_maker() as session:
        identity_id = reviewer_id if non_human_identity == "actor" else context["owner_id"]
        identity = await session.get(User, identity_id)
        assert identity is not None
        identity.principal_kind = "SERVICE"
        await session.commit()
    with pytest.raises(ValueError, match="^APPROVAL_IDEMPOTENCY_CONFLICT$"):
        await context["service"].decide(**decision_args)


@pytest.mark.asyncio
async def test_grant_revoke_exact_replay_is_one_complete_transition_with_fixed_lock_order(
    client,
    auth_user,
) -> None:
    from app.models.ai_research_v2 import ResearchApprovalGrantAudit
    from app.models.permission import Role, user_roles
    from app.services.research.approval_authority import ApprovalGrantService
    from tests.test_ai_research_discovery_trial_materialization import _row_lock_order

    context = await _approval_context(
        client,
        auth_user,
        "approval-managed-grant-revoke",
        mode="multi_actor",
    )
    manager, _manager_headers = await register_and_login(
        client,
        username="approval-managed-grant-revoke-manager",
    )
    reviewer, _reviewer_headers = await register_and_login(
        client,
        username="approval-managed-grant-revoke-reviewer",
    )
    manager_id = await _user_id(manager["username"])
    reviewer_id = await _user_id(reviewer["username"])
    async with async_session_maker() as session:
        await session.execute(
            user_roles.insert().values(
                user_id=manager_id,
                role=Role.RESEARCH_APPROVAL_ADMIN.value,
            )
        )
        await session.commit()
    grants = ApprovalGrantService(clock=context["clock"])
    issued = await grants.issue(
        authenticated_actor_id=manager_id,
        run_id=context["run"].id,
        subject_id=reviewer_id,
        ttl_seconds=3600,
        idempotency_key="managed-grant-revoke-issue",
    )

    async with async_session_maker() as observer_session:
        with _row_lock_order(observer_session.bind.sync_engine) as lock_order:
            revoked = await grants.revoke(
                authenticated_actor_id=manager_id,
                run_id=context["run"].id,
                grant_id=issued.id,
                reason="reviewer rotation",
                idempotency_key="managed-grant-revoke",
            )
    assert lock_order.index("ai_research_runs") < lock_order.index("users")
    assert lock_order.index("users") < lock_order.index("ai_research_approval_grants")
    replay = await grants.revoke(
        authenticated_actor_id=manager_id,
        run_id=context["run"].id,
        grant_id=issued.id,
        reason="reviewer rotation",
        idempotency_key="managed-grant-revoke",
    )
    assert replay.id == revoked.id
    assert _utc(replay.revoked_at) == context["clock"].value
    with pytest.raises(ValueError, match="^APPROVAL_GRANT_IDEMPOTENCY_CONFLICT$"):
        await grants.revoke(
            authenticated_actor_id=manager_id,
            run_id=context["run"].id,
            grant_id=issued.id,
            reason="different reason",
            idempotency_key="managed-grant-revoke",
        )
    with pytest.raises(ValueError, match="^APPROVAL_GRANT_ALREADY_REVOKED$"):
        await grants.revoke(
            authenticated_actor_id=manager_id,
            run_id=context["run"].id,
            grant_id=issued.id,
            reason="reviewer rotation",
            idempotency_key="managed-grant-revoke-new-key",
        )
    async with async_session_maker() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ResearchApprovalGrantAudit)) == 2
        )


@pytest.mark.asyncio
async def test_grant_service_requires_human_manager_and_subject_principals(
    client,
    auth_user,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        "approval-grant-principal-kind",
        mode="multi_actor",
    )
    manager, _manager_headers = await register_and_login(
        client,
        username="approval-grant-principal-manager",
    )
    reviewer, _reviewer_headers = await register_and_login(
        client,
        username="approval-grant-principal-reviewer",
    )
    manager_id = await _user_id(manager["username"])
    reviewer_id = await _user_id(reviewer["username"])
    async with async_session_maker() as session:
        await session.execute(
            user_roles.insert().values(
                user_id=manager_id,
                role=Role.RESEARCH_APPROVAL_ADMIN.value,
            )
        )
        manager_user = await session.get(User, manager_id)
        assert manager_user is not None
        manager_user.principal_kind = "SERVICE"
        await session.commit()
    grants = ApprovalGrantService(clock=context["clock"])
    with pytest.raises(ValueError, match="^APPROVAL_GRANT_MANAGER_REQUIRED$"):
        await grants.issue(
            authenticated_actor_id=manager_id,
            run_id=context["run"].id,
            subject_id=reviewer_id,
            ttl_seconds=3600,
            idempotency_key="approval-grant-service-manager",
        )

    async with async_session_maker() as session:
        manager_user = await session.get(User, manager_id)
        reviewer_user = await session.get(User, reviewer_id)
        assert manager_user is not None and reviewer_user is not None
        manager_user.principal_kind = "HUMAN"
        reviewer_user.principal_kind = "UNKNOWN"
        await session.commit()
    with pytest.raises(ValueError, match="^APPROVAL_GRANT_SUBJECT_INVALID$"):
        await grants.issue(
            authenticated_actor_id=manager_id,
            run_id=context["run"].id,
            subject_id=reviewer_id,
            ttl_seconds=3600,
            idempotency_key="approval-grant-unknown-subject",
        )

    async with async_session_maker() as session:
        reviewer_user = await session.get(User, reviewer_id)
        assert reviewer_user is not None
        reviewer_user.principal_kind = "HUMAN"
        await session.commit()
    await grants.issue(
        authenticated_actor_id=manager_id,
        run_id=context["run"].id,
        subject_id=reviewer_id,
        ttl_seconds=3600,
        idempotency_key="approval-grant-human-subject",
    )
    request = await _request(context, "approval-grant-principal-request")
    async with async_session_maker() as session:
        reviewer_user = await session.get(User, reviewer_id)
        assert reviewer_user is not None
        reviewer_user.principal_kind = "SERVICE"
        await session.commit()
    with pytest.raises(ValueError, match="^APPROVAL_SCOPE_NOT_FOUND$"):
        await context["service"].decide(
            authenticated_actor_id=reviewer_id,
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            approval_request_id=request.id,
            decision="APPROVED",
            reason="service principals may not decide",
            gate_input_evidence_hash=context["gate_hash"],
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key="approval-grant-service-decision",
        )


@pytest.mark.asyncio
async def test_grant_response_status_uses_database_clock_for_expiry(
    client,
    auth_user,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        "approval-grant-response-status",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username="approval-grant-response-status-reviewer",
    )
    reviewer_id = await _user_id(reviewer["username"])
    grant = await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
        expires_at_offset=timedelta(seconds=60),
    )
    service = ApprovalGrantService(clock=context["clock"])
    assert await service.response_status(grant) == "ACTIVE"
    context["clock"].value += timedelta(seconds=60)
    assert await service.response_status(grant) == "EXPIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize("grant_fault", ["revoked", "expired", "wrong_workspace", "wrong_issuer"])
async def test_revoked_expired_or_wrong_scope_grant_cannot_create_a_decision(
    client,
    auth_user,
    grant_fault: str,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        f"approval-grant-{grant_fault}",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username=f"approval-grant-reviewer-{grant_fault}",
    )
    reviewer_id = await _user_id(reviewer["username"])
    grant = await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
        expires_at_offset=(
            timedelta(seconds=60) if grant_fault == "expired" else timedelta(hours=1)
        ),
    )
    request = await _request(context, f"approval-grant-request-{grant_fault}")
    if grant_fault == "expired":
        context["clock"].value = _utc(grant.expires_at)
    else:
        async with async_session_maker() as session:
            stored = await session.get(ResearchApprovalGrant, grant.id)
            assert stored is not None
            if grant_fault == "revoked":
                stored.revoked_at = context["clock"].value
                stored.revoked_by = context["owner_id"]
                stored.revocation_reason = "revoked before use"
            elif grant_fault == "wrong_workspace":
                stored.workspace_id = "foreign-workspace"
                stored.grant_hash = approval_grant_hash(stored)
            else:
                stored.issuer_id = reviewer_id
                stored.grant_hash = approval_grant_hash(stored)
            await session.commit()

    with pytest.raises(ValueError, match="^APPROVAL_GRANT_REQUIRED$"):
        await context["service"].decide(
            authenticated_actor_id=reviewer_id,
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            approval_request_id=request.id,
            decision="APPROVED",
            reason="should not be authorized",
            gate_input_evidence_hash=context["gate_hash"],
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key=f"approval-grant-decision-{grant_fault}",
        )


@pytest.mark.asyncio
async def test_multiple_current_exact_scope_grants_fail_closed_as_ambiguous(
    client,
    auth_user,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        "approval-ambiguous-grant",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username="approval-ambiguous-grant-reviewer",
    )
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    # Negative ambiguity fixture: model an externally imported, fully audited grant
    # whose validity interval overlaps the service-issued replacement.
    import app.services.research.approval_authority as authority_module

    second = ResearchApprovalGrant(
        actor_id=reviewer_id,
        run_id=context["run"].id,
        workspace_id=context["run"].workspace_id,
        permission="research:approve",
        subject_kind="HUMAN",
        issuer_id=context["owner_id"],
        issuer_kind="HUMAN",
        grant_hash="0" * 64,
        issued_at=context["clock"].value,
        expires_at=context["clock"].value + timedelta(hours=2),
        created_at=context["clock"].value,
    )
    second.grant_hash = approval_grant_hash(second)
    async with async_session_maker() as session:
        session.add(second)
        await session.flush()
        session.add(
            authority_module._grant_audit_model(
                grant=second,
                event_type="ISSUED",
                actor_id=context["owner_id"],
                idempotency_key="approval-ambiguous-negative-fixture",
                command_material=authority_module._grant_issue_command_material(
                    run_id=second.run_id,
                    subject_id=second.actor_id,
                    ttl_seconds=7200,
                ),
                occurred_at=context["clock"].value,
                reason_hash=None,
            )
        )
        await session.commit()
    request = await _request(context, "approval-ambiguous-grant-request")

    with pytest.raises(ValueError, match="^APPROVAL_GRANT_AMBIGUOUS$"):
        await context["service"].decide(
            authenticated_actor_id=reviewer_id,
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            approval_request_id=request.id,
            decision="APPROVED",
            reason="ambiguous authority must not select a grant implicitly",
            gate_input_evidence_hash=context["gate_hash"],
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key="approval-ambiguous-grant-decision",
        )


@pytest.mark.asyncio
async def test_service_identity_cannot_be_provisioned_as_a_human_approval_grant(
    client,
    auth_user,
) -> None:
    context = await _approval_context(
        client, auth_user, "approval-service-grant", mode="multi_actor"
    )
    reviewer, _headers = await register_and_login(client, username="approval-service-identity")
    reviewer_id = await _user_id(reviewer["username"])
    grant = ResearchApprovalGrant(
        actor_id=reviewer_id,
        run_id=context["run"].id,
        workspace_id=context["run"].workspace_id,
        permission="research:approve",
        subject_kind="SERVICE",
        issuer_id=context["owner_id"],
        issuer_kind="HUMAN",
        grant_hash="0" * 64,
        issued_at=context["clock"].value - timedelta(minutes=1),
        expires_at=context["clock"].value + timedelta(hours=1),
    )
    grant.grant_hash = approval_grant_hash(grant)
    async with async_session_maker() as session:
        session.add(grant)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_user_principal_kind_is_human_for_orm_and_unknown_for_unclassified_server_insert() -> (
    None
):
    async with async_session_maker() as session:
        human = User(
            username="approval-principal-orm-human",
            email="approval-principal-orm-human@example.test",
            hashed_password="not-used",
        )
        session.add(human)
        await session.flush()
        assert human.principal_kind == "HUMAN"
        await session.execute(
            text(
                "INSERT INTO users (id, username, email, hashed_password) "
                "VALUES (:id, :username, :email, :hashed_password)"
            ),
            {
                "id": "99999999-9999-9999-9999-999999999999",
                "username": "approval-principal-server-unknown",
                "email": "approval-principal-server-unknown@example.test",
                "hashed_password": "not-used",
            },
        )
        await session.commit()
    async with async_session_maker() as session:
        unknown = await session.get(User, "99999999-9999-9999-9999-999999999999")
        assert unknown is not None
        assert unknown.principal_kind == "UNKNOWN"


@pytest.mark.asyncio
async def test_hashes_are_strict_lowercase_hex_before_database_access(client, auth_user) -> None:
    context = await _approval_context(client, auth_user, "approval-hash", mode="multi_actor")
    with pytest.raises(ValueError, match="^APPROVAL_IDEMPOTENCY_OR_EVIDENCE_INVALID$"):
        await context["service"].request_approval(
            authenticated_actor_id=context["owner_id"],
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            gate_input_evidence_hash=context["gate_hash"].upper(),
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key="uppercase-hash",
        )


@pytest.mark.asyncio
async def test_concurrent_request_and_decision_replays_converge_to_one_exact_row(
    client,
    auth_user,
) -> None:
    context = await _approval_context(client, auth_user, "approval-concurrency", mode="multi_actor")
    requests = await asyncio.gather(*(_request(context, "concurrent-request") for _ in range(20)))
    assert len({item.id for item in requests}) == 1

    reviewer, _headers = await register_and_login(client, username="approval-concurrent-reviewer")
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    decision_args = {
        "authenticated_actor_id": reviewer_id,
        "run_id": context["run"].id,
        "candidate_id": context["candidate"].id,
        "approval_request_id": requests[0].id,
        "decision": "APPROVED",
        "reason": "concurrent exact review",
        "gate_input_evidence_hash": context["gate_hash"],
        "evidence_package_hash": context["package"].manifest_hash,
        "idempotency_key": "concurrent-decision",
    }
    decisions = await asyncio.gather(
        *(context["service"].decide(**decision_args) for _ in range(20))
    )
    assert len({item.id for item in decisions}) == 1
    async with async_session_maker() as session:
        assert await session.scalar(select(func.count()).select_from(ResearchApprovalRequest)) == 1
        assert await session.scalar(select(func.count()).select_from(ResearchHumanDecision)) == 1


@pytest.mark.asyncio
async def test_approval_write_lock_order_is_epoch_candidate_package_request_decision(
    client,
    auth_user,
) -> None:
    from tests.test_ai_research_discovery_trial_materialization import _row_lock_order

    context = await _approval_context(client, auth_user, "approval-lock-order", mode="multi_actor")
    async with async_session_maker() as observer_session:
        with _row_lock_order(observer_session.bind.sync_engine) as request_order:
            request = await _request(context, "approval-lock-request")
    assert request_order.index("ai_research_experiment_epochs") < request_order.index(
        "ai_research_candidates"
    )
    assert request_order.index("ai_research_candidates") < request_order.index(
        "ai_research_evidence_packages"
    )
    assert request_order.index("ai_research_evidence_packages") < request_order.index(
        "ai_research_approval_requests"
    )

    reviewer, _headers = await register_and_login(client, username="approval-lock-reviewer")
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    async with async_session_maker() as observer_session:
        with _row_lock_order(observer_session.bind.sync_engine) as decision_order:
            await context["service"].decide(
                authenticated_actor_id=reviewer_id,
                run_id=context["run"].id,
                candidate_id=context["candidate"].id,
                approval_request_id=request.id,
                decision="APPROVED",
                reason="lock order reviewed",
                gate_input_evidence_hash=context["gate_hash"],
                evidence_package_hash=context["package"].manifest_hash,
                idempotency_key="approval-lock-decision",
            )
    assert decision_order.index("ai_research_experiment_epochs") < decision_order.index(
        "ai_research_candidates"
    )
    assert decision_order.index("ai_research_candidates") < decision_order.index(
        "ai_research_evidence_packages"
    )
    assert decision_order.index("ai_research_evidence_packages") < decision_order.index(
        "ai_research_approval_requests"
    )
    assert decision_order.index("ai_research_approval_requests") < decision_order.index(
        "ai_research_human_decisions"
    )


@pytest.mark.asyncio
async def test_request_replay_compares_complete_server_material(client, auth_user) -> None:
    context = await _approval_context(
        client, auth_user, "approval-request-exact", mode="multi_actor"
    )
    request = await _request(context, "request-exact-key")
    assert (await _request(context, "request-exact-key")).id == request.id
    async with async_session_maker() as session:
        stored = await session.get(ResearchApprovalRequest, request.id)
        assert stored is not None
        stored.approval_mode = "single_actor"
        await session.commit()
    with pytest.raises(ValueError, match="^APPROVAL_REQUEST_IDEMPOTENCY_CONFLICT$"):
        await _request(context, "request-exact-key")


@pytest.mark.asyncio
async def test_exact_replay_recovers_record_after_live_authority_changes_but_is_not_current(
    client,
    auth_user,
) -> None:
    context = await _approval_context(
        client, auth_user, "approval-stale-replay", mode="multi_actor"
    )
    reviewer, _headers = await register_and_login(client, username="approval-stale-reviewer")
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    request = await _request(context, "stale-replay-request")
    kwargs = {
        "authenticated_actor_id": reviewer_id,
        "run_id": context["run"].id,
        "candidate_id": context["candidate"].id,
        "approval_request_id": request.id,
        "decision": "APPROVED",
        "reason": "original exact decision",
        "gate_input_evidence_hash": context["gate_hash"],
        "evidence_package_hash": context["package"].manifest_hash,
        "idempotency_key": "stale-replay-decision",
    }
    original = await context["service"].decide(**kwargs)
    async with async_session_maker() as session:
        package = await session.get(type(context["package"]), context["package"].id)
        profile = await session.scalar(
            select(ResearchCapabilityProfile).where(
                ResearchCapabilityProfile.profile_id == context["run"].capability_profile_id,
                ResearchCapabilityProfile.version == context["run"].capability_profile_version,
            )
        )
        assert package is not None and profile is not None
        package.status = "WITHDRAWN"
        profile.approval_capabilities = {
            **server_approval_capabilities("multi_actor"),
            "policy_material_hash": "0" * 64,
        }
        await session.commit()

    assert (await context["service"].decide(**kwargs)).id == original.id
    assert (await _request(context, "stale-replay-request")).id == request.id
    with pytest.raises(ValueError, match="^APPROVAL_IDEMPOTENCY_CONFLICT$"):
        await context["service"].decide(**{**kwargs, "reason": "changed after drift"})
    assert not await _is_approved(context)


@pytest.mark.asyncio
async def test_current_approval_rediscovers_latest_decision_inside_candidate_lock(
    client,
    auth_user,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        "approval-latest-decision-toctou",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username="approval-latest-decision-toctou-reviewer",
    )
    reviewer_id = await _user_id(reviewer["username"])
    grant = await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    approved_request = await _request(context, "approval-toctou-approved-request")
    later_request = await _request(context, "approval-toctou-later-request")
    approved = await context["service"].decide(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        approval_request_id=approved_request.id,
        decision="APPROVED",
        reason="approved before the concurrent decision",
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key="approval-toctou-approved-decision",
    )

    class _InsertConcurrentRejection:
        inserted = False

        async def is_eligible_in_session(self, session: AsyncSession, **_kwargs) -> bool:
            if not self.inserted:
                self.inserted = True
                request = await session.get(ResearchApprovalRequest, later_request.id)
                assert request is not None
                decided_at = _utc(approved.decided_at) + timedelta(seconds=1)
                request.status = "DECIDED"
                request.decided_at = decided_at
                reason = "concurrent rejection wins"
                session.add(
                    ResearchHumanDecision(
                        candidate_id=approved.candidate_id,
                        run_id=approved.run_id,
                        workspace_id=approved.workspace_id,
                        approval_request_id=later_request.id,
                        evidence_package_id=approved.evidence_package_id,
                        decision="REJECTED",
                        actor_id=reviewer_id,
                        domain_permissions=["research:approve"],
                        policy_version=approved.policy_version,
                        policy_material_hash=approved.policy_material_hash,
                        approval_mode=approved.approval_mode,
                        capability_profile_id=approved.capability_profile_id,
                        capability_profile_version=approved.capability_profile_version,
                        capability_evidence_hash=approved.capability_evidence_hash,
                        grant_id=grant.id,
                        grant_hash=grant.grant_hash,
                        single_actor=False,
                        risk_acknowledgement=False,
                        comment=reason,
                        challenge_records=[],
                        challenge_hash=content_hash([]),
                        risk_acknowledgement_hash=content_hash(""),
                        reason_hash=content_hash(reason),
                        gate_input_evidence_hash=context["gate_hash"],
                        evidence_package_hash=context["package"].manifest_hash,
                        idempotency_key="approval-toctou-concurrent-rejection",
                        decision_material_hash="f" * 64,
                        requested_at=later_request.requested_at,
                        eligible_at=later_request.eligible_at,
                        decided_at=decided_at,
                        expires_at=later_request.expires_at,
                    )
                )
                await session.flush()
            return True

    context["service"]._promotion_gates = _InsertConcurrentRejection()
    assert not await _is_approved(context)


@pytest.mark.asyncio
async def test_approval_context_is_safe_and_server_authorized(client, auth_user) -> None:
    context = await _approval_context(client, auth_user, "approval-context", mode="multi_actor")
    owner_view = await context["service"].approval_context(
        authenticated_actor_id=context["owner_id"],
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
    )
    assert owner_view.can_request is True, owner_view.request_blocked_reason
    assert owner_view.request_blocked_reason is None
    assert owner_view.can_decide is False
    assert owner_view.can_approve is False
    assert owner_view.current_request is None
    assert owner_view.latest_decision is None
    assert owner_view.machine_evidence_summary is not None
    assert owner_view.machine_evidence_summary.package.id == context["package"].id
    assert len(owner_view.machine_evidence_summary.gates) == 13
    assert all(
        gate.reason_code == f"HOLDOUT_{gate.gate_code}_PASSED"
        for gate in owner_view.machine_evidence_summary.gates
    )
    assert all(not hasattr(gate, "reason") for gate in owner_view.machine_evidence_summary.gates)

    reviewer, _headers = await register_and_login(client, username="approval-context-reviewer")
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    request = await _request(context, "approval-context-request")
    reviewer_view = await context["service"].approval_context(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
    )
    assert reviewer_view.can_request is False
    assert reviewer_view.can_decide is True
    assert reviewer_view.can_approve is True
    assert reviewer_view.candidate_hash == context["candidate"].candidate_hash
    assert reviewer_view.current_request is not None
    assert reviewer_view.current_request.id == request.id
    assert reviewer_view.current_request.gate_input_evidence_hash == context["gate_hash"]
    assert reviewer_view.current_request.evidence_package_hash == context["package"].manifest_hash
    assert reviewer_view.machine_evidence_summary is not None
    machine = reviewer_view.machine_evidence_summary
    assert machine.package.id == context["package"].id
    assert machine.package.status == "ACTIVE"
    assert machine.package.candidate_id == context["candidate"].id
    assert machine.package.command_id == context["package"].command_id
    assert machine.package.evaluation_id == context["package"].evaluation_id
    assert len(machine.gates) == 13
    assert {gate.status for gate in machine.gates} == {"PASS"}
    assert {gate.input_evidence_hash for gate in machine.gates} == {context["gate_hash"]}
    assert {
        "metrics",
        "gate_inputs",
        "manifest",
        "storage_uri",
        "lease_token",
        "grant_id",
    }.isdisjoint(machine.__dataclass_fields__ | machine.package.__dataclass_fields__)
    serialized = ResearchApprovalContextResponse.model_validate(reviewer_view).model_dump()
    assert len(serialized["machine_evidence_summary"]["gates"]) == 13
    assert {
        "metrics",
        "gate_inputs",
        "manifest",
        "storage_uri",
        "lease_token",
        "grant_id",
    }.isdisjoint(serialized["machine_evidence_summary"]["package"])
    decision = await context["service"].decide(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        approval_request_id=request.id,
        decision="REQUESTED_CHANGES",
        reason="revalidate the execution assumptions",
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key="approval-context-decision",
    )
    reloaded = await context["service"].approval_context(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
    )
    assert reloaded.current_request is None
    assert reloaded.latest_decision is not None
    assert reloaded.latest_decision.id == decision.id
    assert reloaded.latest_decision.approval_request_id == request.id
    assert reloaded.latest_decision.decision == "REQUESTED_CHANGES"
    assert reloaded.can_request is False
    assert reloaded.request_blocked_reason == "APPROVAL_EVIDENCE_DENIED"
    assert {"grant_id", "permissions", "actor_id"}.isdisjoint(reviewer_view.__dataclass_fields__)


@pytest.mark.asyncio
async def test_approval_context_redacts_human_uri_and_sealed_value_recursively(
    client,
    auth_user,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        "approval-context-human-redaction",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username="approval-context-human-redaction-reviewer",
    )
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    request = await _request(context, "approval-context-human-redaction-request")
    raw_reason = "see s3://private-bucket/raw and SEALED_METRICS_MUST_NOT_ESCAPE"
    decision = await context["service"].decide(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        approval_request_id=request.id,
        decision="REJECTED",
        reason=raw_reason,
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key="approval-context-human-redaction-decision",
    )

    view = await context["service"].approval_context(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
    )
    assert view.latest_decision is not None
    assert view.latest_decision.reason == "[REDACTED]"
    assert view.latest_decision.decision_material_hash == decision.decision_material_hash
    assert view.latest_decision.decision_intent_hash == approval_decision_intent_hash(
        approval_request_id=request.id,
        decision="REJECTED",
        reason=raw_reason,
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        challenge_keys=(),
        challenge_responses={},
        residual_risk_acknowledgement=None,
    )
    assert view.latest_decision.decision_intent_hash != approval_decision_intent_hash(
        approval_request_id=request.id,
        decision="REJECTED",
        reason=raw_reason,
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        challenge_keys=(),
        challenge_responses={},
        residual_risk_acknowledgement="a different risk acknowledgement",
    )
    assert "s3://" not in repr(view)
    assert "SEALED_METRICS_MUST_NOT_ESCAPE" not in repr(view)


@pytest.mark.asyncio
async def test_workbench_recovers_safe_approval_request_and_decision_receipts(
    client,
    auth_user,
) -> None:
    context = await _approval_context(client, auth_user, "approval-workbench", mode="multi_actor")
    reviewer, _headers = await register_and_login(client, username="approval-workbench-reviewer")
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    request = await _request(context, "workbench-request")
    decision = await context["service"].decide(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        approval_request_id=request.id,
        decision="REJECTED",
        reason="hold for another independent validation pass",
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key="workbench-decision",
    )

    workbench = await ResearchOrchestrator().get_workbench(context["owner_id"], context["run"].id)
    assert workbench is not None
    assert workbench["approval_requests"] == [
        {
            "id": request.id,
            "run_id": context["run"].id,
            "candidate_id": context["candidate"].id,
            "evidence_package_id": context["package"].id,
            "policy_version": "approval-multi-v2",
            "policy_material_hash": request.policy_material_hash,
            "approval_mode": "multi_actor",
            "gate_input_evidence_hash": context["gate_hash"],
            "evidence_package_hash": context["package"].manifest_hash,
            "request_material_hash": request.request_material_hash,
            "status": "DECIDED",
            "requested_at": request.requested_at,
            "eligible_at": request.eligible_at,
            "expires_at": request.expires_at,
            "decided_at": decision.decided_at,
        }
    ]
    assert workbench["decisions"] == [
        {
            "authority_version": "v2",
            "id": decision.id,
            "run_id": context["run"].id,
            "candidate_id": context["candidate"].id,
            "approval_request_id": request.id,
            "decision": "REJECTED",
            "policy_version": "approval-multi-v2",
            "policy_material_hash": decision.policy_material_hash,
            "approval_mode": "multi_actor",
            "gate_input_evidence_hash": context["gate_hash"],
            "evidence_package_hash": context["package"].manifest_hash,
            "decision_material_hash": decision.decision_material_hash,
            "decision_intent_hash": approval_decision_intent_hash(
                approval_request_id=request.id,
                decision="REJECTED",
                reason="hold for another independent validation pass",
                gate_input_evidence_hash=context["gate_hash"],
                evidence_package_hash=context["package"].manifest_hash,
                challenge_keys=(),
                challenge_responses={},
                residual_risk_acknowledgement=None,
            ),
            "risk_acknowledgement": False,
            "challenge_keys": [],
            "reason": "hold for another independent validation pass",
            "decided_at": decision.decided_at,
            "expires_at": decision.expires_at,
        }
    ]
    assert {"requested_by", "actor_id", "grant_id", "grant_hash", "domain_permissions"}.isdisjoint(
        workbench["approval_requests"][0] | workbench["decisions"][0]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["withdrawn", "request_hash", "sealed_canary"])
async def test_approval_context_fails_closed_for_withdrawn_wrong_or_stale_machine_evidence(
    client,
    auth_user,
    drift: str,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        f"approval-context-drift-{drift}",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client, username=f"approval-context-drift-reviewer-{drift}"
    )
    reviewer_id = await _user_id(reviewer["username"])
    await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
    )
    request = await _request(context, f"approval-context-drift-request-{drift}")
    async with async_session_maker() as session:
        stored_request = await session.get(ResearchApprovalRequest, request.id)
        package = await session.get(type(context["package"]), context["package"].id)
        assert stored_request is not None and package is not None
        if drift == "withdrawn":
            package.status = "WITHDRAWN"
        elif drift == "request_hash":
            stored_request.gate_input_evidence_hash = "0" * 64
        else:
            package.manifest = {
                **package.manifest,
                "sealed_canary": "secret=SEALED_METRICS_MUST_NOT_ESCAPE",
            }
        await session.commit()

    view = await context["service"].approval_context(
        authenticated_actor_id=reviewer_id,
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
    )
    assert view.can_decide is False
    assert view.decision_blocked_reason == "EVIDENCE_NOT_CURRENT"
    assert view.machine_evidence_summary is None
    assert "SEALED_METRICS_MUST_NOT_ESCAPE" not in repr(view)


@pytest.mark.asyncio
async def test_approval_context_rejects_cross_candidate_scope(client, auth_user) -> None:
    left = await _approval_context(client, auth_user, "approval-context-left", mode="multi_actor")
    original = left["candidate"]
    foreign_run = ResearchRun(
        user_id=left["owner_id"],
        workspace_id=left["run"].workspace_id,
        hypothesis_version_id=left["run"].hypothesis_version_id,
        dataset_snapshot_id=left["run"].dataset_snapshot_id,
        experiment_epoch_id=left["run"].experiment_epoch_id,
        protocol_version=left["run"].protocol_version,
        workflow_version=left["run"].workflow_version,
        status="SUCCEEDED",
        stage_cursor=left["run"].stage_cursor,
        promotion_policy_version=left["run"].promotion_policy_version,
        request_hash="1" * 64,
        capability_profile_id=left["run"].capability_profile_id,
        capability_profile_version=left["run"].capability_profile_version,
        capability_evidence_hash=left["run"].capability_evidence_hash,
        trace_id="approval-context-cross-candidate",
    )
    async with async_session_maker() as session:
        session.add(foreign_run)
        await session.flush()
        context_time = left["clock"].value
        foreign_candidate = ResearchCandidate(
            user_id=left["owner_id"],
            run_id=foreign_run.id,
            experiment_epoch_id=original.experiment_epoch_id,
            dataset_snapshot_id=original.dataset_snapshot_id,
            code_artifact_id=original.code_artifact_id,
            dependency_artifact_id=original.dependency_artifact_id,
            candidate_hash="2" * 64,
            environment_hash=original.environment_hash,
            cost_model_hash=original.cost_model_hash,
            params={},
            freeze_status="FROZEN",
            frozen_at=context_time,
            frozen_by=left["owner_id"],
            created_at=context_time,
        )
        session.add(foreign_candidate)
        await session.commit()
        await session.refresh(foreign_candidate)
    with pytest.raises(ValueError, match="^APPROVAL_SCOPE_NOT_FOUND$"):
        await left["service"].approval_context(
            authenticated_actor_id=left["owner_id"],
            run_id=left["run"].id,
            candidate_id=foreign_candidate.id,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["request", "decision"])
@pytest.mark.parametrize("commit_was_applied", [True, False])
async def test_commit_ack_loss_reads_exact_applied_write_or_fails_closed_for_retry(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    commit_was_applied: bool,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        f"approval-ack-{operation}-{commit_was_applied}",
        mode="multi_actor",
    )
    reviewer_id: str | None = None
    request: ResearchApprovalRequest | None = None
    if operation == "decision":
        reviewer, _headers = await register_and_login(
            client,
            username=f"approval-ack-reviewer-{commit_was_applied}",
        )
        reviewer_id = await _user_id(reviewer["username"])
        await _issue_grant(
            actor_id=reviewer_id,
            issuer_id=context["owner_id"],
            run=context["run"],
            clock=context["clock"],
        )
        request = await _request(context, f"ack-request-{commit_was_applied}")

    original_commit = AsyncSession.commit
    commit_calls = 0

    async def lose_first_ack(session: AsyncSession) -> None:
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 1:
            if commit_was_applied:
                await original_commit(session)
            raise OperationalError("COMMIT", {}, RuntimeError("lost acknowledgement"))
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", lose_first_ack)

    async def invoke():
        if operation == "request":
            return await _request(context, f"ack-operation-{commit_was_applied}")
        assert reviewer_id is not None and request is not None
        return await context["service"].decide(
            authenticated_actor_id=reviewer_id,
            run_id=context["run"].id,
            candidate_id=context["candidate"].id,
            approval_request_id=request.id,
            decision="APPROVED",
            reason="ack outcome review",
            gate_input_evidence_hash=context["gate_hash"],
            evidence_package_hash=context["package"].manifest_hash,
            idempotency_key=f"ack-operation-{commit_was_applied}",
        )

    if commit_was_applied:
        written = await invoke()
    else:
        error = (
            "APPROVAL_REQUEST_COMMIT_OUTCOME_UNKNOWN"
            if operation == "request"
            else "APPROVAL_DECISION_COMMIT_OUTCOME_UNKNOWN"
        )
        with pytest.raises(ValueError, match=f"^{error}$"):
            await invoke()
        async with async_session_maker() as session:
            model = ResearchApprovalRequest if operation == "request" else ResearchHumanDecision
            assert await session.scalar(select(func.count()).select_from(model)) == 0
        written = await invoke()

    replayed = await invoke()
    assert replayed.id == written.id
    async with async_session_maker() as session:
        model = ResearchApprovalRequest if operation == "request" else ResearchHumanDecision
        expected = 1
        assert await session.scalar(select(func.count()).select_from(model)) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["issue", "revoke"])
async def test_grant_commit_ack_loss_reads_exact_audit_without_duplicate_transition(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        f"approval-grant-ack-{operation}",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username=f"approval-grant-ack-reviewer-{operation}",
    )
    reviewer_id = await _user_id(reviewer["username"])
    grant = None
    if operation == "revoke":
        grant = await _issue_grant(
            actor_id=reviewer_id,
            issuer_id=context["owner_id"],
            run=context["run"],
            clock=context["clock"],
        )
    else:
        await _ensure_grant_manager_role(context["owner_id"])

    service = ApprovalGrantService(clock=context["clock"])
    original_commit = AsyncSession.commit
    commit_calls = 0

    async def commit_then_lose_ack(session: AsyncSession) -> None:
        nonlocal commit_calls
        commit_calls += 1
        await original_commit(session)
        if commit_calls == 1:
            raise OperationalError("COMMIT", {}, RuntimeError("lost acknowledgement"))

    monkeypatch.setattr(AsyncSession, "commit", commit_then_lose_ack)

    async def invoke(*, different_material: bool = False):
        if operation == "issue":
            return await service.issue(
                authenticated_actor_id=context["owner_id"],
                run_id=context["run"].id,
                subject_id=reviewer_id,
                ttl_seconds=1801 if different_material else 1800,
                idempotency_key="approval-grant-ack-issue",
            )
        assert grant is not None
        return await service.revoke(
            authenticated_actor_id=context["owner_id"],
            run_id=context["run"].id,
            grant_id=grant.id,
            reason="different reason" if different_material else "reviewer rotation",
            idempotency_key="approval-grant-ack-revoke",
        )

    written = await invoke()
    replay = await invoke()
    assert replay.id == written.id
    with pytest.raises(ValueError, match="^APPROVAL_GRANT_IDEMPOTENCY_CONFLICT$"):
        await invoke(different_material=True)
    async with async_session_maker() as session:
        audits = list(
            (
                await session.scalars(
                    select(ResearchApprovalGrantAudit).where(
                        ResearchApprovalGrantAudit.grant_id == written.id
                    )
                )
            ).all()
        )
        expected_events = {"ISSUED"} if operation == "issue" else {"ISSUED", "REVOKED"}
        assert {audit.event_type for audit in audits} == expected_events
        assert len(audits) == len(expected_events)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["issue", "revoke"])
@pytest.mark.parametrize(
    "readback_fault",
    ["unavailable", "audit_drift", "none", "scalar", "mapping", "namespace", "wrong_orm"],
)
async def test_grant_commit_unknown_normalizes_readback_failure_without_leaking_cause(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    readback_fault: str,
) -> None:
    context = await _approval_context(
        client,
        auth_user,
        f"approval-grant-unknown-{operation}-{readback_fault}",
        mode="multi_actor",
    )
    reviewer, _headers = await register_and_login(
        client,
        username=f"grant-unknown-{operation}-{readback_fault}",
    )
    reviewer_id = await _user_id(reviewer["username"])
    grant = None
    if operation == "revoke":
        grant = await _issue_grant(
            actor_id=reviewer_id,
            issuer_id=context["owner_id"],
            run=context["run"],
            clock=context["clock"],
        )
    else:
        await _ensure_grant_manager_role(context["owner_id"])

    service = ApprovalGrantService(clock=context["clock"])
    idempotency_key = f"grant-unknown-{operation}-{readback_fault}"
    original_commit = AsyncSession.commit
    if readback_fault == "unavailable":

        async def commit_not_applied(_session: AsyncSession) -> None:
            raise OperationalError("COMMIT", {}, RuntimeError("write unavailable"))

        async def readback_unavailable(_probe):
            raise RuntimeError("postgresql://operator:secret@internal/grants")

        monkeypatch.setattr(AsyncSession, "commit", commit_not_applied)
        monkeypatch.setattr(service, "_read_probe", readback_unavailable)
    elif readback_fault == "audit_drift":

        async def commit_then_lose_ack(session: AsyncSession) -> None:
            await original_commit(session)
            raise OperationalError("COMMIT", {}, RuntimeError("lost acknowledgement"))

        original_read_probe = service._read_probe

        async def drift_audit_then_read(probe):
            async with database.engine.begin() as connection:
                await connection.execute(
                    ResearchApprovalGrantAudit.__table__.update()
                    .where(
                        ResearchApprovalGrantAudit.actor_id == context["owner_id"],
                        ResearchApprovalGrantAudit.idempotency_key == idempotency_key,
                    )
                    .values(command_material_hash="f" * 64)
                )
            return await original_read_probe(probe)

        monkeypatch.setattr(AsyncSession, "commit", commit_then_lose_ack)
        monkeypatch.setattr(service, "_read_probe", drift_audit_then_read)
    else:

        async def commit_then_lose_ack(session: AsyncSession) -> None:
            await original_commit(session)
            raise OperationalError("COMMIT", {}, RuntimeError("lost acknowledgement"))

        invalid_readbacks = {
            "none": None,
            "scalar": 7,
            "mapping": {"id": "not-a-persisted-grant"},
            "namespace": SimpleNamespace(id="not-a-persisted-grant"),
            "wrong_orm": ResearchApprovalGrantAudit(),
        }

        async def readback_with_wrong_type(_probe):
            return invalid_readbacks[readback_fault]

        monkeypatch.setattr(AsyncSession, "commit", commit_then_lose_ack)
        monkeypatch.setattr(service, "_read_probe", readback_with_wrong_type)

    async def invoke():
        if operation == "issue":
            return await service.issue(
                authenticated_actor_id=context["owner_id"],
                run_id=context["run"].id,
                subject_id=reviewer_id,
                ttl_seconds=1800,
                idempotency_key=idempotency_key,
            )
        assert grant is not None
        return await service.revoke(
            authenticated_actor_id=context["owner_id"],
            run_id=context["run"].id,
            grant_id=grant.id,
            reason="reviewer rotation",
            idempotency_key=idempotency_key,
        )

    with pytest.raises(ValueError, match="^APPROVAL_GRANT_COMMIT_OUTCOME_UNKNOWN$") as error:
        await invoke()
    assert "postgresql" not in str(error.value)


async def _approval_context(
    client,
    auth_user,
    suffix: str,
    *,
    mode: str,
    profile_expires_at_offset: timedelta | None = None,
) -> dict:
    graph = await _terminal_graph(client, auth_user, suffix)
    raw = graph["context"]
    datasets = raw["datasets"]
    assert isinstance(datasets, DatasetRegistry)
    run = raw["run"]
    assert isinstance(run, ResearchRun)
    if mode != "multi_actor" or profile_expires_at_offset is not None:
        async with async_session_maker() as session:
            profile = await session.scalar(
                select(ResearchCapabilityProfile).where(
                    ResearchCapabilityProfile.profile_id == run.capability_profile_id,
                    ResearchCapabilityProfile.version == run.capability_profile_version,
                )
            )
            assert profile is not None
            if mode != "multi_actor":
                profile.actor_mode = mode
                profile.approval_capabilities = server_approval_capabilities(mode)
            if profile_expires_at_offset is not None:
                profile.expires_at = datetime.now(timezone.utc) + profile_expires_at_offset
            await session.commit()
    evidence = EvidencePackageService(dataset_registry=datasets)
    package = await evidence.build_for_terminal_command(
        user_id=raw["user_id"],
        command_id=graph["claimed"].command_id,
    )
    clock = _MutableDatabaseClock(datetime.now(timezone.utc))
    service = ApprovalService(
        evidence_packages=evidence,
        authority_resolver=ApprovalAuthorityResolver(clock=clock),
    )
    return {
        "service": service,
        "clock": clock,
        "owner_id": raw["user_id"],
        "candidate": raw["candidate"],
        "run": run,
        "gate_hash": graph["result"].input_evidence_hash,
        "package": package,
    }


async def _request(context: dict, key: str) -> ResearchApprovalRequest:
    return await context["service"].request_approval(
        authenticated_actor_id=context["owner_id"],
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
        idempotency_key=key,
    )


async def _issue_grant(
    *,
    actor_id: str,
    issuer_id: str,
    run: ResearchRun,
    clock: _MutableDatabaseClock,
    expires_at_offset: timedelta = timedelta(hours=1),
) -> ResearchApprovalGrant:
    await _ensure_grant_manager_role(issuer_id)
    ttl_seconds = int(expires_at_offset.total_seconds())
    return await ApprovalGrantService(clock=clock).issue(
        authenticated_actor_id=issuer_id,
        run_id=run.id,
        subject_id=actor_id,
        ttl_seconds=ttl_seconds,
        idempotency_key=f"fixture-grant-{uuid4()}",
    )


async def _historical_replay_fixture(
    client,
    auth_user,
    suffix: str,
    *,
    grant_ttl: timedelta = timedelta(hours=1),
) -> dict[str, object]:
    context = await _approval_context(client, auth_user, suffix, mode="multi_actor")
    reviewer, _headers = await register_and_login(
        client,
        username=f"historical-{content_hash(suffix)[:16]}",
    )
    reviewer_id = await _user_id(reviewer["username"])
    grant = await _issue_grant(
        actor_id=reviewer_id,
        issuer_id=context["owner_id"],
        run=context["run"],
        clock=context["clock"],
        expires_at_offset=grant_ttl,
    )
    request = await _request(context, f"{suffix}-request")
    context["clock"].value += timedelta(seconds=10)
    decision_args = {
        "authenticated_actor_id": reviewer_id,
        "run_id": context["run"].id,
        "candidate_id": context["candidate"].id,
        "approval_request_id": request.id,
        "decision": "APPROVED",
        "reason": "historical grant window review",
        "gate_input_evidence_hash": context["gate_hash"],
        "evidence_package_hash": context["package"].manifest_hash,
        "idempotency_key": f"{suffix}-decision",
    }
    decision = await context["service"].decide(**decision_args)
    return {
        "context": context,
        "reviewer_id": reviewer_id,
        "grant": grant,
        "decision": decision,
        "decision_args": decision_args,
    }


async def _ensure_grant_manager_role(user_id: str) -> None:
    async with async_session_maker() as session:
        existing_role = await session.scalar(
            select(user_roles.c.role).where(
                user_roles.c.user_id == user_id,
                user_roles.c.role == Role.RESEARCH_APPROVAL_ADMIN.value,
            )
        )
        if existing_role is None:
            await session.execute(
                user_roles.insert().values(
                    user_id=user_id,
                    role=Role.RESEARCH_APPROVAL_ADMIN.value,
                )
            )
        await session.commit()


async def _user_id(username: str) -> str:
    async with async_session_maker() as session:
        return str(await session.scalar(select(User.id).where(User.username == username)))


async def _is_approved(context: dict) -> bool:
    return await context["service"].is_currently_approved(
        run_id=context["run"].id,
        candidate_id=context["candidate"].id,
        promotion_policy_version="promotion-v1",
        gate_input_evidence_hash=context["gate_hash"],
        evidence_package_hash=context["package"].manifest_hash,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
