from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.api.strategy import research as research_api
from app.config import get_settings
from app.db.database import async_session_maker
from app.models.permission import Role, user_roles
from app.models.user import User
from app.services.research.approval import (
    ApprovalContext,
    ApprovalRequestSummary,
    approval_decision_intent_hash,
)
from app.services.research.canonical import content_hash
from tests.conftest import app

_RUN_ID = "11111111-1111-1111-1111-111111111111"
_CANDIDATE_ID = "22222222-2222-2222-2222-222222222222"
_REQUEST_ID = "33333333-3333-3333-3333-333333333333"
_PACKAGE_ID = "44444444-4444-4444-4444-444444444444"
_GATE_HASH = "a" * 64
_PACKAGE_HASH = "b" * 64
_POLICY_HASH = "c" * 64
_REQUEST_MATERIAL_HASH = "e" * 64
_DECISION_MATERIAL_HASH = "f" * 64
_DECISION_INTENT_HASH = "89901d373e7ddb7d05e0a2b692a3e63d376d8ebf2521e6058a687f06cbf6d6d3"


class _ApprovalApiSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.error: str | None = None
        self.decision_reason = "reviewed"

    async def approval_context(self, **kwargs):
        self.calls.append(("context", kwargs))
        self._raise_if_needed()
        now = datetime.now(timezone.utc)
        return ApprovalContext(
            run_id=_RUN_ID,
            candidate_id=_CANDIDATE_ID,
            candidate_hash="d" * 64,
            policy_version="approval-multi-v2",
            policy_material_hash=_POLICY_HASH,
            approval_mode="multi_actor",
            can_request=True,
            can_decide=False,
            can_approve=False,
            request_blocked_reason=None,
            decision_blocked_reason="AUTHORITY_REQUIRED",
            cooldown_seconds=0,
            required_challenge_keys=(),
            risk_acknowledgement_required=False,
            current_request=ApprovalRequestSummary(
                id=_REQUEST_ID,
                run_id=_RUN_ID,
                candidate_id=_CANDIDATE_ID,
                evidence_package_id=_PACKAGE_ID,
                policy_version="approval-multi-v2",
                policy_material_hash=_POLICY_HASH,
                approval_mode="multi_actor",
                gate_input_evidence_hash=_GATE_HASH,
                evidence_package_hash=_PACKAGE_HASH,
                request_material_hash=_REQUEST_MATERIAL_HASH,
                status="PENDING",
                requested_at=now,
                eligible_at=now,
                expires_at=now + timedelta(hours=1),
                decided_at=None,
            ),
        )

    async def request_approval(self, **kwargs):
        self.calls.append(("request", kwargs))
        self._raise_if_needed()
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id=_REQUEST_ID,
            run_id=_RUN_ID,
            candidate_id=_CANDIDATE_ID,
            evidence_package_id=_PACKAGE_ID,
            policy_version="approval-multi-v2",
            policy_material_hash=_POLICY_HASH,
            approval_mode="multi_actor",
            gate_input_evidence_hash=_GATE_HASH,
            evidence_package_hash=_PACKAGE_HASH,
            request_material_hash=_REQUEST_MATERIAL_HASH,
            status="PENDING",
            requested_at=now,
            eligible_at=now,
            expires_at=now + timedelta(hours=1),
            decided_at=None,
        )

    async def decide(self, **kwargs):
        self.calls.append(("decision", kwargs))
        self._raise_if_needed()
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id="55555555-5555-5555-5555-555555555555",
            run_id=_RUN_ID,
            candidate_id=_CANDIDATE_ID,
            approval_request_id=_REQUEST_ID,
            decision="APPROVED",
            policy_version="approval-multi-v2",
            policy_material_hash=_POLICY_HASH,
            approval_mode="multi_actor",
            gate_input_evidence_hash=_GATE_HASH,
            evidence_package_hash=_PACKAGE_HASH,
            decision_material_hash=_DECISION_MATERIAL_HASH,
            risk_acknowledgement=False,
            challenge_records=[],
            challenge_hash=content_hash([]),
            risk_acknowledgement_hash=content_hash(""),
            reason_hash=content_hash(self.decision_reason),
            comment=self.decision_reason,
            decided_at=now,
            expires_at=now + timedelta(hours=1),
        )

    def _raise_if_needed(self) -> None:
        if self.error is not None:
            raise ValueError(self.error)


class _GrantApiSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.grant_id = "66666666-6666-6666-6666-666666666666"
        self.status = "ACTIVE"

    async def issue(self, **kwargs):
        self.calls.append(("issue", kwargs))
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id=self.grant_id,
            run_id=kwargs["run_id"],
            workspace_id="workspace-safe",
            actor_id=kwargs["subject_id"],
            permission="research:approve",
            issuer_id="must-not-leak",
            grant_hash="f" * 64,
            issued_at=now,
            expires_at=now + timedelta(seconds=kwargs["ttl_seconds"]),
            revoked_at=None,
        )

    async def revoke(self, **kwargs):
        self.calls.append(("revoke", kwargs))
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id=kwargs["grant_id"],
            run_id=kwargs["run_id"],
            workspace_id="workspace-safe",
            actor_id="reviewer-safe-id",
            permission="research:approve",
            issuer_id="must-not-leak",
            revoked_by="must-not-leak",
            revocation_reason=kwargs["reason"],
            grant_hash="f" * 64,
            issued_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=1),
            revoked_at=now,
        )

    async def response_status(self, grant):
        self.calls.append(("response_status", {"grant_id": grant.id}))
        if grant.revoked_at is not None:
            return "REVOKED"
        return self.status


@pytest.fixture(autouse=True)
def approval_api_dependencies(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)
    spy = _ApprovalApiSpy()
    app.dependency_overrides[research_api.get_approval_service] = lambda: spy
    yield spy
    app.dependency_overrides.pop(research_api.get_approval_service, None)


@pytest.mark.asyncio
async def test_approval_api_uses_only_authenticated_token_actor(
    client, auth_user, approval_api_dependencies
):
    user, headers = auth_user
    actor_id = await _user_id(user["username"])
    response = await client.post(
        _url("approval-requests"),
        headers={**headers, "Idempotency-Key": "api-request-key"},
        json={
            "gate_input_evidence_hash": _GATE_HASH,
            "evidence_package_hash": _PACKAGE_HASH,
        },
    )
    assert response.status_code == 201, response.text
    assert approval_api_dependencies.calls == [
        (
            "request",
            {
                "authenticated_actor_id": actor_id,
                "run_id": _RUN_ID,
                "candidate_id": _CANDIDATE_ID,
                "gate_input_evidence_hash": _GATE_HASH,
                "evidence_package_hash": _PACKAGE_HASH,
                "idempotency_key": "api-request-key",
            },
        )
    ]
    assert {"requested_by", "actor_id", "grant_id", "permissions"}.isdisjoint(response.json())
    assert response.json()["request_material_hash"] == _REQUEST_MATERIAL_HASH


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "forbidden_field",
    ["actor_id", "policy", "mode", "domain_permissions", "now"],
)
async def test_approval_request_api_forbids_every_client_authority_field(
    client,
    auth_user,
    approval_api_dependencies,
    forbidden_field: str,
) -> None:
    _user, headers = auth_user
    response = await client.post(
        _url("approval-requests"),
        headers={**headers, "Idempotency-Key": "api-forbidden-key"},
        json={
            "gate_input_evidence_hash": _GATE_HASH,
            "evidence_package_hash": _PACKAGE_HASH,
            forbidden_field: "attacker-controlled",
        },
    )
    assert response.status_code == 422
    assert approval_api_dependencies.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("idempotency_key", [None, " ", "x" * 129])
async def test_approval_request_api_requires_a_bounded_idempotency_key(
    client,
    auth_user,
    approval_api_dependencies,
    idempotency_key: str | None,
) -> None:
    _user, headers = auth_user
    if idempotency_key is not None:
        headers = {**headers, "Idempotency-Key": idempotency_key}
    response = await client.post(
        _url("approval-requests"),
        headers=headers,
        json={
            "gate_input_evidence_hash": _GATE_HASH,
            "evidence_package_hash": _PACKAGE_HASH,
        },
    )
    assert response.status_code == 422
    assert response.json()["details"] == {
        "code": "APPROVAL_IDEMPOTENCY_KEY_REQUIRED",
        "message": "APPROVAL_IDEMPOTENCY_KEY_REQUIRED",
        "retryable": False,
    }
    assert approval_api_dependencies.calls == []


@pytest.mark.asyncio
async def test_approval_decision_api_forbids_authority_and_returns_safe_projection(
    client,
    auth_user,
    approval_api_dependencies,
) -> None:
    user, headers = auth_user
    actor_id = await _user_id(user["username"])
    payload = {
        "approval_request_id": _REQUEST_ID,
        "decision": "APPROVED",
        "reason": "reviewed",
        "gate_input_evidence_hash": _GATE_HASH,
        "evidence_package_hash": _PACKAGE_HASH,
        "challenge_responses": {},
        "residual_risk_acknowledgement": None,
    }
    response = await client.post(
        _url("approval-decisions"),
        headers={**headers, "Idempotency-Key": "api-decision-key"},
        json=payload,
    )
    assert response.status_code == 201, response.text
    assert approval_api_dependencies.calls == [
        (
            "decision",
            {
                "authenticated_actor_id": actor_id,
                "run_id": _RUN_ID,
                "candidate_id": _CANDIDATE_ID,
                "idempotency_key": "api-decision-key",
                **payload,
            },
        )
    ]
    assert {"actor_id", "grant_id", "grant_hash", "domain_permissions"}.isdisjoint(response.json())
    assert response.json()["decision_material_hash"] == _DECISION_MATERIAL_HASH
    assert response.json()["decision_intent_hash"] == _DECISION_INTENT_HASH

    for forbidden_field in ("actor_id", "policy", "mode", "domain_permissions", "now"):
        approval_api_dependencies.calls.clear()
        rejected = await client.post(
            _url("approval-decisions"),
            headers={**headers, "Idempotency-Key": "api-forbidden-decision"},
            json={**payload, forbidden_field: "attacker-controlled"},
        )
        assert rejected.status_code == 422
        assert approval_api_dependencies.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_reason",
    [
        "data:text/plain",
        "请查data:text/plain,private",
        "file:/srv/private/result.json",
        "review,/srv/private/result.json",
        "请查/srv/research/private.sqlite",
        r"review=C:\Users\secret\result.json",
        r"请查C:\Users\operator\approval.txt",
        r"review,\\server\share\secret.json",
        r"请查\\fileserver\sealed\result.json",
    ],
)
async def test_approval_decision_api_redacts_uri_or_path_reason_but_preserves_intent_receipt(
    client,
    auth_user,
    approval_api_dependencies,
    raw_reason: str,
) -> None:
    _user, headers = auth_user
    approval_api_dependencies.decision_reason = raw_reason
    response = await client.post(
        _url("approval-decisions"),
        headers={**headers, "Idempotency-Key": "api-decision-redaction"},
        json={
            "approval_request_id": _REQUEST_ID,
            "decision": "APPROVED",
            "reason": raw_reason,
            "gate_input_evidence_hash": _GATE_HASH,
            "evidence_package_hash": _PACKAGE_HASH,
            "challenge_responses": {},
            "residual_risk_acknowledgement": None,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["reason"] == "[REDACTED]"
    assert response.json()["decision_intent_hash"] == approval_decision_intent_hash(
        approval_request_id=_REQUEST_ID,
        decision="APPROVED",
        reason=raw_reason,
        gate_input_evidence_hash=_GATE_HASH,
        evidence_package_hash=_PACKAGE_HASH,
        challenge_keys=(),
        challenge_responses={},
        residual_risk_acknowledgement=None,
    )
    assert raw_reason not in response.text


@pytest.mark.asyncio
async def test_approval_context_is_server_derived_and_contains_no_grant_details(
    client,
    auth_user,
    approval_api_dependencies,
) -> None:
    user, headers = auth_user
    response = await client.get(_url("approval-context"), headers=headers)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "run_id": _RUN_ID,
        "candidate_id": _CANDIDATE_ID,
        "candidate_hash": "d" * 64,
        "policy_version": "approval-multi-v2",
        "policy_material_hash": _POLICY_HASH,
        "approval_mode": "multi_actor",
        "can_request": True,
        "can_decide": False,
        "can_approve": False,
        "request_blocked_reason": None,
        "decision_blocked_reason": "AUTHORITY_REQUIRED",
        "cooldown_seconds": 0,
        "required_challenge_keys": [],
        "risk_acknowledgement_required": False,
        "current_request": {
            "id": _REQUEST_ID,
            "run_id": _RUN_ID,
            "candidate_id": _CANDIDATE_ID,
            "evidence_package_id": _PACKAGE_ID,
            "policy_version": "approval-multi-v2",
            "policy_material_hash": _POLICY_HASH,
            "approval_mode": "multi_actor",
            "gate_input_evidence_hash": _GATE_HASH,
            "evidence_package_hash": _PACKAGE_HASH,
            "request_material_hash": _REQUEST_MATERIAL_HASH,
            "status": "PENDING",
            "requested_at": response.json()["current_request"]["requested_at"],
            "eligible_at": response.json()["current_request"]["eligible_at"],
            "expires_at": response.json()["current_request"]["expires_at"],
            "decided_at": None,
        },
        "latest_decision": None,
        "machine_evidence_summary": None,
    }
    actor_id = await _user_id(user["username"])
    assert approval_api_dependencies.calls == [
        (
            "context",
            {
                "authenticated_actor_id": actor_id,
                "run_id": _RUN_ID,
                "candidate_id": _CANDIDATE_ID,
            },
        )
    ]


@pytest.mark.asyncio
async def test_grant_management_api_requires_explicit_nondefault_permission(
    client,
    auth_user,
    approval_api_dependencies,
) -> None:
    _user, headers = auth_user
    response = await client.post(
        f"/api/v1/strategy/ai-research/v2/runs/{_RUN_ID}/approval-grants",
        headers={**headers, "Idempotency-Key": "grant-api-denied"},
        json={"subject_id": _CANDIDATE_ID, "ttl_seconds": 3600},
    )
    assert response.status_code == 403
    assert approval_api_dependencies.calls == []


@pytest.mark.asyncio
async def test_grant_management_api_uses_explicit_permission_and_minimal_receipts(
    client,
    auth_user,
) -> None:
    user, headers = auth_user
    actor_id = await _user_id(user["username"])
    async with async_session_maker() as session:
        await session.execute(
            user_roles.insert().values(
                user_id=actor_id,
                role=Role.RESEARCH_APPROVAL_ADMIN.value,
            )
        )
        await session.commit()
    spy = _GrantApiSpy()
    app.dependency_overrides[research_api.get_approval_grant_service] = lambda: spy
    try:
        issued = await client.post(
            f"/api/v1/strategy/ai-research/v2/runs/{_RUN_ID}/approval-grants",
            headers={**headers, "Idempotency-Key": "grant-api-issue"},
            json={"subject_id": "reviewer-safe-id", "ttl_seconds": 3600},
        )
        assert issued.status_code == 201, issued.text
        assert spy.calls == [
            (
                "issue",
                {
                    "authenticated_actor_id": actor_id,
                    "run_id": _RUN_ID,
                    "subject_id": "reviewer-safe-id",
                    "ttl_seconds": 3600,
                    "idempotency_key": "grant-api-issue",
                },
            ),
            ("response_status", {"grant_id": spy.grant_id}),
        ]
        assert issued.json()["subject_id"] == "reviewer-safe-id"
        assert issued.json()["status"] == "ACTIVE"
        assert {
            "grant_hash",
            "issuer_id",
            "revoked_by",
            "revocation_reason",
            "policy_material_hash",
        }.isdisjoint(issued.json())

        revoked = await client.post(
            f"/api/v1/strategy/ai-research/v2/runs/{_RUN_ID}/approval-grants/{spy.grant_id}/revoke",
            headers={**headers, "Idempotency-Key": "grant-api-revoke"},
            json={"reason": " operator rotation "},
        )
        assert revoked.status_code == 200, revoked.text
        assert spy.calls[-2] == (
            "revoke",
            {
                "authenticated_actor_id": actor_id,
                "run_id": _RUN_ID,
                "grant_id": spy.grant_id,
                "reason": "operator rotation",
                "idempotency_key": "grant-api-revoke",
            },
        )
        assert revoked.json()["status"] == "REVOKED"
        assert spy.calls[-1] == ("response_status", {"grant_id": spy.grant_id})
        assert {
            "grant_hash",
            "issuer_id",
            "revoked_by",
            "revocation_reason",
            "policy_material_hash",
        }.isdisjoint(revoked.json())

        before = list(spy.calls)
        extra = await client.post(
            f"/api/v1/strategy/ai-research/v2/runs/{_RUN_ID}/approval-grants",
            headers={**headers, "Idempotency-Key": "grant-api-extra"},
            json={
                "subject_id": "reviewer-safe-id",
                "ttl_seconds": 3600,
                "issuer_id": actor_id,
            },
        )
        assert extra.status_code == 422
        assert spy.calls == before
    finally:
        app.dependency_overrides.pop(research_api.get_approval_grant_service, None)


@pytest.mark.asyncio
async def test_grant_management_api_rejects_non_human_manager_even_with_dedicated_role(
    client,
    auth_user,
) -> None:
    user, headers = auth_user
    actor_id = await _user_id(user["username"])
    async with async_session_maker() as session:
        actor = await session.get(User, actor_id)
        assert actor is not None
        actor.principal_kind = "SERVICE"
        await session.execute(
            user_roles.insert().values(
                user_id=actor_id,
                role=Role.RESEARCH_APPROVAL_ADMIN.value,
            )
        )
        await session.commit()
    spy = _GrantApiSpy()
    app.dependency_overrides[research_api.get_approval_grant_service] = lambda: spy
    try:
        response = await client.post(
            f"/api/v1/strategy/ai-research/v2/runs/{_RUN_ID}/approval-grants",
            headers={**headers, "Idempotency-Key": "grant-api-service-manager"},
            json={"subject_id": "reviewer-safe-id", "ttl_seconds": 3600},
        )
        assert response.status_code == 403
        assert spy.calls == []
    finally:
        app.dependency_overrides.pop(research_api.get_approval_grant_service, None)


@pytest.mark.asyncio
async def test_grant_response_uses_server_status_projection_for_expired_grant(
    client,
    auth_user,
) -> None:
    user, headers = auth_user
    actor_id = await _user_id(user["username"])
    async with async_session_maker() as session:
        await session.execute(
            user_roles.insert().values(
                user_id=actor_id,
                role=Role.RESEARCH_APPROVAL_ADMIN.value,
            )
        )
        await session.commit()
    spy = _GrantApiSpy()
    spy.status = "EXPIRED"
    app.dependency_overrides[research_api.get_approval_grant_service] = lambda: spy
    try:
        response = await client.post(
            f"/api/v1/strategy/ai-research/v2/runs/{_RUN_ID}/approval-grants",
            headers={**headers, "Idempotency-Key": "grant-api-expired"},
            json={"subject_id": "reviewer-safe-id", "ttl_seconds": 3600},
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "EXPIRED"
        assert spy.calls[-1] == ("response_status", {"grant_id": spy.grant_id})
    finally:
        app.dependency_overrides.pop(research_api.get_approval_grant_service, None)


@pytest.mark.asyncio
async def test_approval_api_public_error_catalog_is_an_exact_safe_allowlist() -> None:
    assert research_api._APPROVAL_PUBLIC_ERROR_CATALOG_VERSION == ("ai-research-approval-errors/v1")
    assert len(research_api._APPROVAL_PUBLIC_ERROR_CATALOG) == 48
    assert research_api._APPROVAL_PUBLIC_ERROR_CATALOG_HASH == (
        "6dd9f6ce55ec595c9441ae08e26f6cc0845549eb1c950a6a28481ad973870d53"
    )
    assert tuple(sorted(research_api._APPROVAL_PUBLIC_ERROR_CATALOG)) == (
        research_api._APPROVAL_PUBLIC_ERROR_CATALOG
    )
    assert research_api._APPROVAL_PUBLIC_ERROR_CODES == frozenset(
        code for code, _status, _retryable in research_api._APPROVAL_PUBLIC_ERROR_CATALOG
    )
    assert {
        "APPROVAL_DATABASE_CLOCK_INVALID",
        "APPROVAL_DECISION_EVIDENCE_MISMATCH",
        "APPROVAL_DECISION_INTENT_INVALID",
        "APPROVAL_DENIAL_FENCE_CONFLICT",
        "APPROVAL_MACHINE_EVIDENCE_INCOMPLETE",
        "APPROVAL_POLICY_CATALOG_INVALID",
        "APPROVAL_REQUEST_TRANSITION_INVALID",
    }.isdisjoint(research_api._APPROVAL_PUBLIC_ERROR_CODES)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_error", "expected_code"),
    [
        ("APPROVAL_CHALLENGE_INCOMPLETE:model_risk,secret", "APPROVAL_CHALLENGE_INCOMPLETE"),
        ("APPROVAL_DATABASE_CLOCK_INVALID", "RESEARCH_APPROVAL_OPERATION_FAILED"),
        ("APPROVAL_DECISION_EVIDENCE_MISMATCH", "RESEARCH_APPROVAL_OPERATION_FAILED"),
        ("APPROVAL_DENIAL_FENCE_CONFLICT", "RESEARCH_APPROVAL_OPERATION_FAILED"),
        ("APPROVAL_MACHINE_EVIDENCE_INCOMPLETE", "RESEARCH_APPROVAL_OPERATION_FAILED"),
        ("APPROVAL_POLICY_CATALOG_INVALID", "RESEARCH_APPROVAL_OPERATION_FAILED"),
        (
            "APPROVAL_PRIVATE_INTERNAL:postgresql://user:pass@host/db",
            "RESEARCH_APPROVAL_OPERATION_FAILED",
        ),
    ],
)
async def test_approval_api_error_codes_are_exact_allowlisted_and_never_echo_suffixes(
    client,
    auth_user,
    approval_api_dependencies,
    raw_error: str,
    expected_code: str,
) -> None:
    _user, headers = auth_user
    approval_api_dependencies.error = raw_error
    response = await client.post(
        _url("approval-requests"),
        headers={**headers, "Idempotency-Key": "api-error-redaction"},
        json={
            "gate_input_evidence_hash": _GATE_HASH,
            "evidence_package_hash": _PACKAGE_HASH,
        },
    )
    assert response.status_code in {409, 422}
    assert response.json()["details"]["code"] == expected_code
    assert response.json()["details"]["message"] == expected_code
    assert "postgresql" not in response.text
    assert "model_risk" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        ("APPROVAL_SCOPE_NOT_FOUND", 404),
        ("APPROVAL_GRANT_REQUIRED", 403),
        ("APPROVAL_GRANT_AMBIGUOUS", 403),
        ("APPROVAL_GRANT_AUDIT_INVALID", 403),
        ("APPROVAL_REQUEST_COMMIT_OUTCOME_UNKNOWN", 503),
        ("APPROVAL_REQUEST_IDEMPOTENCY_CONFLICT", 409),
        ("APPROVAL_EVIDENCE_PACKAGE_NOT_FOUND", 404),
        ("APPROVAL_EVIDENCE_PACKAGE_CORRUPT", 409),
        ("APPROVAL_EVIDENCE_PACKAGE_STALE", 409),
        ("APPROVAL_EVIDENCE_PACKAGE_UNVERIFIABLE", 409),
        ("APPROVAL_EVIDENCE_PACKAGE_VERSION_UNSUPPORTED", 409),
        ("APPROVAL_EVIDENCE_PACKAGE_WITHDRAWN", 409),
    ],
)
async def test_approval_api_maps_scope_authority_and_commit_errors_without_leakage(
    client,
    auth_user,
    approval_api_dependencies,
    error: str,
    status_code: int,
) -> None:
    _user, headers = auth_user
    approval_api_dependencies.error = error
    response = await client.post(
        _url("approval-requests"),
        headers={**headers, "Idempotency-Key": "api-error-key"},
        json={
            "gate_input_evidence_hash": _GATE_HASH,
            "evidence_package_hash": _PACKAGE_HASH,
        },
    )
    assert response.status_code == status_code
    assert response.json()["details"]["code"] == error


def _url(action: str) -> str:
    return f"/api/v1/strategy/ai-research/v2/runs/{_RUN_ID}/candidates/{_CANDIDATE_ID}/{action}"


async def _user_id(username: str) -> str:
    async with async_session_maker() as session:
        return str(await session.scalar(select(User.id).where(User.username == username)))
