from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.strategy import research as research_api
from app.config import get_settings
from app.db import database
from app.models.ai_research_v2 import (
    ResearchCandidate,
    ResearchCandidateFreezeReceipt,
    ResearchCapabilityProfile,
    ResearchDatasetSnapshot,
    ResearchEvaluation,
    ResearchExperimentEpoch,
    ResearchHoldoutAuthorization,
    ResearchHoldoutEvaluationCommand,
)
from app.services.research import holdout_request as holdout_request_module
from app.services.research.capabilities import CapabilityProfile
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.holdout_claim import (
    HoldoutClaimService,
    HoldoutEvaluatorRuntimeIdentity,
)
from app.services.research.holdout_request import HoldoutRequestService
from tests.conftest import app, register_and_login
from tests.test_ai_research_holdout_authorization import (
    _create_additional_sealed_snapshot,
    _dataset_registry,
    _drift_sealed_object,
    _strict_context,
)

_EVALUATOR_IDENTITY = "ai_research_evaluator"
_EVALUATOR_IMAGE = "evaluator-image@sha256:test"
_COMMAND_TABLE = "ai_research_holdout_evaluation_commands"
_AUDIT_TABLE = "ai_research_holdout_request_audits"


@pytest.fixture(autouse=True)
def enable_protocol_v2_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the opt-in command API only after enabling protocol-v2 writes."""

    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)


@pytest.fixture(autouse=True)
def clear_holdout_request_overrides() -> None:
    """Keep the deployment-owned resolver override local to each test."""

    yield
    app.dependency_overrides.pop(research_api.get_dataset_object_resolver, None)
    app.dependency_overrides.pop(research_api.get_holdout_request_service, None)


@pytest.mark.asyncio
async def test_holdout_request_queues_once_without_exposing_authorization_token(
    client,
    auth_user,
) -> None:
    """Dropping the private-token projection or durable command must fail this test."""

    context, headers = await _request_context(auth_user, "holdout-request-once")
    payload = _request_payload(context)

    created = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-once"},
        json=payload,
    )
    repeated = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-once"},
        json=payload,
    )

    assert created.status_code == 202, created.text
    assert repeated.status_code == 202, repeated.text
    assert repeated.json() == created.json()
    recovered = await client.get(
        f"/api/v1/strategy/ai-research/v2/holdout-evaluations/{created.json()['id']}",
        headers=headers,
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json() == created.json()
    command = created.json()
    candidate = context["candidate"]
    sealed = context["sealed"]
    assert command == {
        "id": command["id"],
        "run_id": candidate.run_id,
        "status": "QUEUED",
        "stage": "REQUEST_HOLDOUT",
        "candidate_id": candidate.id,
        "candidate_hash": candidate.candidate_hash,
        "experiment_epoch_id": candidate.experiment_epoch_id,
        "dataset_snapshot_id": sealed.id,
        "policy_version": "promotion-v1",
        "evaluator_identity": _EVALUATOR_IDENTITY,
        "capability_profile_id": "holdout-request-once-profile",
        "capability_profile_version": "v1",
        "capability_evidence_hash": "e" * 64,
        "error_code": None,
        "request_hash": command["request_hash"],
        "created_at": command["created_at"],
        "updated_at": command["updated_at"],
    }
    assert len(command["request_hash"]) == 64
    rendered = created.text.lower()
    assert "authorization_token" not in rendered
    assert "token_hash" not in rendered
    assert "sealed://" not in rendered

    workbench = await client.get(
        f"/api/v1/strategy/ai-research/v2/runs/{candidate.run_id}",
        headers=headers,
    )
    assert workbench.status_code == 200, workbench.text
    assert workbench.json()["holdout_commands"] == [command]
    workbench_rendered = workbench.text.lower()
    assert "authorization_token" not in workbench_rendered
    assert "token_hash" not in workbench_rendered
    assert "sealed://" not in workbench_rendered

    async with database.async_session_maker() as session:
        authorizations = list((await session.scalars(select(ResearchHoldoutAuthorization))).all())
        evaluations = await session.scalar(select(func.count()).select_from(ResearchEvaluation))
        epoch = await session.get(ResearchExperimentEpoch, candidate.experiment_epoch_id)
        command_rows = (
            (
                await session.execute(
                    text(
                        f"SELECT id, authorization_id, evaluation_id, dataset_policy_version, "
                        f"sealed_dataset_hash, status, stage, request_hash "
                        f"FROM {_COMMAND_TABLE}"
                    )
                )
            )
            .mappings()
            .all()
        )
        audit_rows = (
            (
                await session.execute(
                    text(
                        f"SELECT actor_user_id, candidate_id, resolved_snapshot_id, purpose, "
                        f"result, reason_code, command_id, request_hash FROM {_AUDIT_TABLE}"
                    )
                )
            )
            .mappings()
            .all()
        )
        command_columns = {
            row[1] for row in (await session.execute(text(f"PRAGMA table_info({_COMMAND_TABLE})")))
        }

    assert authorizations == []
    assert len(command_rows) == 1
    assert command_rows[0]["id"] == command["id"]
    assert command_rows[0]["authorization_id"] is None
    assert command_rows[0]["evaluation_id"] is None
    assert command_rows[0]["dataset_policy_version"] == "policy-v1"
    assert command_rows[0]["sealed_dataset_hash"] == sealed.content_hash
    assert command_rows[0]["status"] == "QUEUED"
    assert command_rows[0]["stage"] == "REQUEST_HOLDOUT"
    assert command_rows[0]["request_hash"] == command["request_hash"]
    assert evaluations == 0
    assert epoch is not None and epoch.status == "SELECTED"
    assert epoch.disclosed_at is None and epoch.closed_at is None
    assert "lease_token_hash" in command_columns
    assert {
        "lease_token",
        "authorization_token",
        "authorization_token_hash",
    }.isdisjoint(command_columns)
    assert audit_rows == [
        {
            "actor_user_id": context["user_id"],
            "candidate_id": candidate.id,
            "resolved_snapshot_id": sealed.id,
            "purpose": "HOLDOUT_EVALUATION_REQUEST",
            "result": "ACCEPTED",
            "reason_code": "HOLDOUT_REQUEST_QUEUED",
            "command_id": command["id"],
            "request_hash": command["request_hash"],
        }
    ]


@pytest.mark.asyncio
async def test_workbench_projects_production_claim_as_metric_free_sealed_holdout(
    client,
    auth_user,
) -> None:
    """A real claim keeps SEALED_HOLDOUT identity while canaries stay server-side."""

    context, headers = await _request_context(auth_user, "evaluation-safe-projection")
    candidate = context["candidate"]
    queued = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "evaluation-safe-projection"},
        json=_request_payload(context),
    )
    assert queued.status_code == 202, queued.text
    claimed = await HoldoutClaimService(
        dataset_registry=_dataset_registry(context),
        lease_seconds=60,
    ).claim(
        command_id=queued.json()["id"],
        runtime=HoldoutEvaluatorRuntimeIdentity(
            worker_identity="holdout-evaluator-worker-1",
            evaluator_identity=_EVALUATOR_IDENTITY,
            evaluator_image_digest=_EVALUATOR_IMAGE,
        ),
    )
    production_response = await client.get(
        f"/api/v1/strategy/ai-research/v2/runs/{candidate.run_id}",
        headers=headers,
    )
    assert production_response.status_code == 200, production_response.text
    assert production_response.json()["evaluations"] == [
        {
            "id": claimed.evaluation_id,
            "experiment_epoch_id": candidate.experiment_epoch_id,
            "candidate_id": candidate.id,
            "dataset_snapshot_id": context["sealed"].id,
            "evaluation_type": "SEALED_HOLDOUT",
            "evaluator_identity": _EVALUATOR_IDENTITY,
            "evaluator_version": _EVALUATOR_IMAGE,
            "policy_version": "promotion-v1",
            "status": "RUNNING",
            "completed_at": None,
        }
    ]

    completed_at = datetime(2026, 9, 8, 1, 2, 3, tzinfo=timezone.utc)
    async with database.async_session_maker() as session:
        evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
        assert evaluation is not None
        evaluation.metrics = {
            "sharpe": 9.9,
            "max_drawdown": -0.01,
            "failure_reason": "must-never-cross-api",
            "token": "must-never-cross-api",
        }
        evaluation.gate_inputs = {
            "raw_sealed": {"returns": [1, 2, 3]},
            "storage_uri": "sealed://must-never-cross-api",
        }
        evaluation.status = "REJECTED"
        evaluation.completed_at = completed_at
        await session.commit()
        await session.refresh(evaluation)

    response = await client.get(
        f"/api/v1/strategy/ai-research/v2/runs/{candidate.run_id}",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["evaluations"] == [
        {
            "id": evaluation.id,
            "experiment_epoch_id": candidate.experiment_epoch_id,
            "candidate_id": candidate.id,
            "dataset_snapshot_id": context["sealed"].id,
            "evaluation_type": "SEALED_HOLDOUT",
            "evaluator_identity": _EVALUATOR_IDENTITY,
            "evaluator_version": _EVALUATOR_IMAGE,
            "policy_version": "promotion-v1",
            "status": "REJECTED",
            "completed_at": "2026-09-08T01:02:03",
        }
    ]
    rendered = repr(payload["evaluations"]).lower()
    for prohibited in (
        "metrics",
        "gate_inputs",
        "sharpe",
        "max_drawdown",
        "failure_reason",
        "token",
        "raw_sealed",
        "sealed://must-never-cross-api",
    ):
        assert prohibited not in rendered


def test_holdout_request_openapi_declares_required_body_and_idempotency_header() -> None:
    """Generated clients see the same request contract enforced by the audited route."""

    app.openapi_schema = None
    paths = app.openapi()["paths"]
    matching_paths = [
        path for path in paths if path.endswith("/candidates/{candidate_id}/holdout-evaluation")
    ]
    assert len(matching_paths) == 1
    operation = paths[matching_paths[0]]["post"]

    request_body = operation["requestBody"]
    assert request_body["required"] is True
    body_schema = request_body["content"]["application/json"]["schema"]
    expected_hash = body_schema["properties"]["expected_candidate_hash"]
    assert body_schema["required"] == ["expected_candidate_hash"]
    assert body_schema["additionalProperties"] is False
    assert expected_hash["minLength"] == 64
    assert expected_hash["maxLength"] == 64
    assert expected_hash["pattern"] == "^[0-9a-f]{64}$"

    idempotency = next(
        parameter
        for parameter in operation["parameters"]
        if parameter["in"] == "header" and parameter["name"] == "Idempotency-Key"
    )
    assert idempotency["required"] is True
    assert idempotency["schema"]["minLength"] == 1
    assert idempotency["schema"]["maxLength"] == 128


def test_workbench_openapi_requires_safe_holdout_command_projection() -> None:
    """The browser must never guess whether command recovery is supported."""

    app.openapi_schema = None
    schemas = app.openapi()["components"]["schemas"]
    workbench_schema = schemas["ResearchWorkbenchResponse"]
    command_schema = schemas["ResearchHoldoutEvaluationCommandResponse"]

    assert "holdout_commands" in workbench_schema["required"]
    assert workbench_schema["properties"]["holdout_commands"]["items"]["$ref"].endswith(
        "/ResearchHoldoutEvaluationCommandResponse"
    )
    prohibited = {
        "authorization_token",
        "token",
        "token_hash",
        "lease_token_hash",
        "storage_uri",
        "sealed_dataset_hash",
        "sealed_dataset_identity_hash",
        "metrics",
        "gate_inputs",
        "evaluator_credentials",
    }
    assert prohibited.isdisjoint(command_schema["properties"])


def test_workbench_openapi_uses_a_closed_evaluation_summary() -> None:
    """Generated clients receive an explicit allowlist instead of an open metrics object."""

    app.openapi_schema = None
    schemas = app.openapi()["components"]["schemas"]
    workbench_schema = schemas["ResearchWorkbenchResponse"]
    evaluation_items = workbench_schema["properties"]["evaluations"]["items"]

    assert evaluation_items["$ref"].endswith("/ResearchEvaluationSummary")
    evaluation_schema = schemas["ResearchEvaluationSummary"]
    assert evaluation_schema["additionalProperties"] is False
    assert set(evaluation_schema["properties"]) == {
        "id",
        "experiment_epoch_id",
        "candidate_id",
        "dataset_snapshot_id",
        "evaluation_type",
        "evaluator_identity",
        "evaluator_version",
        "policy_version",
        "status",
        "completed_at",
    }
    assert evaluation_schema["properties"]["evaluation_type"].get("enum") == [
        "SEALED_HOLDOUT",
        "ITERATION_VALIDATION",
    ]
    package_schema = schemas["ResearchEvidencePackageSummary"]
    assert {"command_id", "evaluation_id"}.issubset(package_schema["properties"])


@pytest.mark.asyncio
async def test_holdout_request_rejects_idempotency_key_reuse_for_different_binding(
    client,
    auth_user,
) -> None:
    """A reused caller key must not silently select another candidate."""

    context, headers = await _request_context(auth_user, "holdout-request-conflict-first")
    first = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-conflict"},
        json=_request_payload(context),
    )
    conflicting_candidate_id = str(uuid.uuid4())
    conflicting = await client.post(
        f"/api/v1/strategy/ai-research/v2/candidates/{conflicting_candidate_id}/holdout-evaluation",
        headers={**headers, "Idempotency-Key": "holdout-request-conflict"},
        json={"expected_candidate_hash": "f" * 64},
    )

    assert first.status_code == 202, first.text
    assert conflicting.status_code == 409, conflicting.text
    assert conflicting.json()["message"] == "HOLDOUT_REQUEST_IDEMPOTENCY_CONFLICT"
    assert await _table_count(_COMMAND_TABLE) == 1
    assert await _table_count(_AUDIT_TABLE) == 2
    assert await _authorization_count() == 0


@pytest.mark.asyncio
async def test_holdout_request_rejects_client_selected_snapshot(client, auth_user) -> None:
    """The browser cannot choose which sealed partition the evaluator will see."""

    context, headers = await _request_context(auth_user, "holdout-request-client-snapshot")
    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-client-snapshot"},
        json={
            **_request_payload(context),
            "dataset_snapshot_id": context["sealed"].id,
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["message"] == "HOLDOUT_REQUEST_BODY_INVALID"
    assert await _table_count(_COMMAND_TABLE) == 0
    assert await _audit_rows() == [
        {
            "actor_user_id": context["user_id"],
            "candidate_id": context["candidate"].id,
            "expected_candidate_hash": context["candidate"].candidate_hash,
            "resolved_snapshot_id": None,
            "result": "REJECTED",
            "reason_code": "HOLDOUT_REQUEST_BODY_INVALID",
            "command_id": None,
        }
    ]


@pytest.mark.asyncio
async def test_holdout_request_fails_closed_when_snapshot_selection_is_ambiguous(
    client,
    auth_user,
) -> None:
    """Two eligible same-policy sealed snapshots must produce no side effect."""

    context, headers = await _request_context(auth_user, "holdout-request-ambiguous")
    await _create_additional_sealed_snapshot(context, suffix="also-eligible")
    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-ambiguous"},
        json=_request_payload(context),
    )

    assert response.status_code == 409, response.text
    assert response.json()["message"] == "HOLDOUT_SNAPSHOT_SELECTION_AMBIGUOUS"
    assert await _table_count(_COMMAND_TABLE) == 0
    assert await _authorization_count() == 0
    async with database.async_session_maker() as session:
        audit = (
            (
                await session.execute(
                    text(
                        f"SELECT result, reason_code, command_id, resolved_snapshot_id "
                        f"FROM {_AUDIT_TABLE}"
                    )
                )
            )
            .mappings()
            .one()
        )
    assert dict(audit) == {
        "result": "REJECTED",
        "reason_code": "HOLDOUT_SNAPSHOT_SELECTION_AMBIGUOUS",
        "command_id": None,
        "resolved_snapshot_id": None,
    }


@pytest.mark.asyncio
async def test_holdout_request_concurrent_replay_creates_one_command_and_audit(
    client,
    auth_user,
) -> None:
    """Twenty same-key HTTP retries converge on one accepted operation."""

    context, headers = await _request_context(auth_user, "holdout-request-concurrent")
    request_headers = {**headers, "Idempotency-Key": "holdout-request-concurrent"}
    responses = await asyncio.gather(
        *(
            client.post(
                _request_url(context),
                headers=request_headers,
                json=_request_payload(context),
            )
            for _ in range(20)
        )
    )

    assert [response.status_code for response in responses] == [202] * 20
    assert len({response.json()["id"] for response in responses}) == 1
    assert await _table_count(_COMMAND_TABLE) == 1
    assert await _table_count(_AUDIT_TABLE) == 1


@pytest.mark.asyncio
async def test_holdout_request_replay_returns_accepted_command_after_epoch_advances(
    client,
    auth_user,
) -> None:
    """An accepted request remains retrievable after downstream state advances."""

    context, headers = await _request_context(auth_user, "holdout-request-late-replay")
    request_headers = {**headers, "Idempotency-Key": "holdout-request-late-replay"}
    first = await client.post(
        _request_url(context),
        headers=request_headers,
        json=_request_payload(context),
    )
    assert first.status_code == 202, first.text
    async with database.async_session_maker() as session:
        epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
        assert epoch is not None
        epoch.status = "DISCLOSED"
        epoch.disclosed_at = datetime.now(timezone.utc)
        await session.commit()

    repeated = await client.post(
        _request_url(context),
        headers=request_headers,
        json=_request_payload(context),
    )

    assert repeated.status_code == 202, repeated.text
    assert repeated.json() == first.json()
    assert await _table_count(_COMMAND_TABLE) == 1


@pytest.mark.asyncio
async def test_holdout_request_rejects_second_key_for_same_epoch(client, auth_user) -> None:
    """An epoch has one durable holdout intent even if callers rotate request keys."""

    context, headers = await _request_context(auth_user, "holdout-request-second-key")
    payload = _request_payload(context)
    first = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-first-key"},
        json=payload,
    )
    second = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-second-key"},
        json=payload,
    )

    assert first.status_code == 202, first.text
    assert second.status_code == 409, second.text
    assert second.json()["message"] == "HOLDOUT_REQUEST_ALREADY_QUEUED"
    assert await _table_count(_COMMAND_TABLE) == 1
    assert await _table_count(_AUDIT_TABLE) == 2
    assert await _authorization_count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("header_value", [None, "   "], ids=["missing", "blank"])
async def test_holdout_request_requires_idempotency_key(
    client,
    auth_user,
    header_value: str | None,
) -> None:
    """Requests without a caller retry identity never enter the durable queue."""

    context, headers = await _request_context(auth_user, "holdout-request-missing-key")
    request_headers = dict(headers)
    if header_value is not None:
        request_headers["Idempotency-Key"] = header_value
    response = await client.post(
        _request_url(context),
        headers=request_headers,
        json=_request_payload(context),
    )

    assert response.status_code == 422, response.text
    assert response.json()["message"] == "HOLDOUT_REQUEST_IDEMPOTENCY_KEY_REQUIRED"
    assert await _table_count(_COMMAND_TABLE) == 0
    audit = (await _audit_rows())[0]
    assert audit["reason_code"] == "HOLDOUT_REQUEST_IDEMPOTENCY_KEY_REQUIRED"
    assert audit["candidate_id"] == context["candidate"].id
    assert audit["expected_candidate_hash"] == context["candidate"].candidate_hash


@pytest.mark.asyncio
async def test_holdout_request_rejects_invalid_idempotency_key_with_audit(
    client,
    auth_user,
) -> None:
    """An overlong caller key is rejected and leaves only safe audit evidence."""

    context, headers = await _request_context(auth_user, "holdout-request-invalid-key")
    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "x" * 129},
        json=_request_payload(context),
    )

    assert response.status_code == 422, response.text
    assert response.json()["message"] == "HOLDOUT_REQUEST_IDEMPOTENCY_KEY_INVALID"
    assert await _table_count(_COMMAND_TABLE) == 0
    audit = (await _audit_rows())[0]
    assert audit["reason_code"] == "HOLDOUT_REQUEST_IDEMPOTENCY_KEY_INVALID"
    assert audit["command_id"] is None


@pytest.mark.asyncio
async def test_holdout_command_get_hides_foreign_operation(client, auth_user) -> None:
    """Operation recovery is owner-scoped and resists command-id enumeration."""

    context, headers = await _request_context(auth_user, "holdout-request-foreign-get")
    created = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-foreign-get"},
        json=_request_payload(context),
    )
    assert created.status_code == 202, created.text
    _, foreign_headers = await register_and_login(client)

    response = await client.get(
        f"/api/v1/strategy/ai-research/v2/holdout-evaluations/{created.json()['id']}",
        headers=foreign_headers,
    )

    assert response.status_code == 404, response.text
    assert response.json()["message"] == "HOLDOUT_REQUEST_NOT_FOUND"


@pytest.mark.asyncio
async def test_holdout_request_hides_foreign_candidate(client, auth_user) -> None:
    """The request path cannot enumerate another owner's frozen candidate."""

    context, _ = await _request_context(auth_user, "holdout-request-foreign-candidate")
    _, foreign_headers = await register_and_login(client)
    response = await client.post(
        _request_url(context),
        headers={**foreign_headers, "Idempotency-Key": "foreign-candidate"},
        json=_request_payload(context),
    )

    assert response.status_code == 404, response.text
    assert response.json()["message"] == "CANDIDATE_NOT_FOUND"
    assert await _table_count(_COMMAND_TABLE) == 0


@pytest.mark.asyncio
async def test_holdout_request_rejects_candidate_that_is_no_longer_frozen(
    client,
    auth_user,
) -> None:
    """AC-SEAL-002 retains its stable not-frozen failure code."""

    context, headers = await _request_context(auth_user, "holdout-request-mutable")
    async with database.async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, context["candidate"].id)
        assert candidate is not None
        candidate.freeze_status = "MUTABLE"
        await session.commit()

    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-mutable"},
        json=_request_payload(context),
    )

    assert response.status_code == 409, response.text
    assert response.json()["details"]["code"] == "CANDIDATE_NOT_FROZEN"
    assert await _table_count(_COMMAND_TABLE) == 0


@pytest.mark.asyncio
async def test_holdout_request_revalidates_strict_freeze_receipt(client, auth_user) -> None:
    """A drifted discovery ledger receipt cannot enter the holdout queue."""

    context, headers = await _request_context(auth_user, "holdout-request-receipt-drift")
    async with database.async_session_maker() as session:
        receipt = await session.scalar(
            select(ResearchCandidateFreezeReceipt).where(
                ResearchCandidateFreezeReceipt.candidate_id == context["candidate"].id
            )
        )
        assert receipt is not None
        receipt.ledger_hash = "0" * 64
        await session.commit()

    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-receipt-drift"},
        json=_request_payload(context),
    )

    assert response.status_code == 409, response.text
    assert response.json()["details"]["code"] == "CANDIDATE_STRICT_FREEZE_RECEIPT_REQUIRED"
    assert await _table_count(_COMMAND_TABLE) == 0


@pytest.mark.asyncio
async def test_holdout_request_revalidates_sealed_object(client, auth_user) -> None:
    """A changed sealed object fails closed before any durable command exists."""

    context, headers = await _request_context(auth_user, "holdout-request-sealed-drift")
    _drift_sealed_object(context)
    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-sealed-drift"},
        json=_request_payload(context),
    )

    assert response.status_code == 409, response.text
    assert response.json()["message"] == "DATASET_OBJECT_ATTESTATION_MISMATCH"
    assert await _table_count(_COMMAND_TABLE) == 0
    assert await _authorization_count() == 0
    async with database.async_session_maker() as session:
        sealed = await session.get(ResearchDatasetSnapshot, context["sealed"].id)
    assert sealed is not None
    assert sealed.integrity_status == "FAILED"
    assert sealed.integrity_checked_at is not None


@pytest.mark.asyncio
async def test_holdout_request_revalidation_unavailable_is_retryable_and_quarantines_snapshot(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolver outages quarantine the selected object and map to retryable infrastructure."""

    context, headers = await _request_context(auth_user, "holdout-request-sealed-unavailable")

    async def unavailable(**_kwargs: object) -> object:
        raise ValueError("resolver unavailable")

    monkeypatch.setattr(context["resolver"], "resolve_current", unavailable)
    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-sealed-unavailable"},
        json=_request_payload(context),
    )

    assert response.status_code == 503, response.text
    assert response.json()["details"] == {
        "code": "DATASET_OBJECT_REVALIDATION_UNAVAILABLE",
        "message": "DATASET_OBJECT_REVALIDATION_UNAVAILABLE",
        "retryable": True,
    }
    assert await _table_count(_COMMAND_TABLE) == 0
    assert await _authorization_count() == 0
    async with database.async_session_maker() as session:
        sealed = await session.get(ResearchDatasetSnapshot, context["sealed"].id)
    assert sealed is not None
    assert sealed.integrity_status == "FAILED"
    assert sealed.integrity_checked_at is not None
    assert [row["reason_code"] for row in await _audit_rows()] == [
        "DATASET_OBJECT_REVALIDATION_UNAVAILABLE"
    ]


@pytest.mark.asyncio
async def test_holdout_request_snapshot_quarantine_persistence_failure_is_retryable(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed quarantine write is never misreported as a deterministic conflict."""

    context, headers = await _request_context(auth_user, "holdout-request-quarantine-failure")
    _drift_sealed_object(context)
    registry = DatasetRegistry(object_resolver=context["resolver"])

    async def fail_quarantine(**_kwargs: object) -> None:
        raise OperationalError("UPDATE", {}, RuntimeError("forced quarantine failure"))

    monkeypatch.setattr(registry, "persist_failed_snapshot", fail_quarantine, raising=False)
    service = HoldoutRequestService(dataset_registry=registry)
    app.dependency_overrides[research_api.get_holdout_request_service] = lambda: service

    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-quarantine-failure"},
        json=_request_payload(context),
    )

    assert response.status_code == 503, response.text
    assert response.json()["details"] == {
        "code": "HOLDOUT_REQUEST_SNAPSHOT_FAILURE_PERSISTENCE_FAILED",
        "message": "HOLDOUT_REQUEST_SNAPSHOT_FAILURE_PERSISTENCE_FAILED",
        "retryable": True,
    }
    assert await _table_count(_COMMAND_TABLE) == 0
    assert await _authorization_count() == 0


@pytest.mark.asyncio
async def test_holdout_request_fails_when_server_has_no_eligible_snapshot(
    client,
    auth_user,
) -> None:
    """The selector never falls back from an absent verified sealed partition."""

    context, headers = await _request_context(auth_user, "holdout-request-no-snapshot")
    async with database.async_session_maker() as session:
        sealed = await session.get(ResearchDatasetSnapshot, context["sealed"].id)
        assert sealed is not None
        sealed.integrity_status = "FAILED"
        await session.commit()
    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-no-snapshot"},
        json=_request_payload(context),
    )

    assert response.status_code == 404, response.text
    assert response.json()["message"] == "HOLDOUT_SNAPSHOT_NOT_FOUND"
    assert await _table_count(_COMMAND_TABLE) == 0
    assert await _table_count(_AUDIT_TABLE) == 1


@pytest.mark.asyncio
async def test_holdout_request_rejects_client_owned_authority_fields(
    client,
    auth_user,
) -> None:
    """Removing extra=forbid would let a browser attempt to choose evaluator authority."""

    context, headers = await _request_context(auth_user, "holdout-request-extra")
    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-extra"},
        json={
            **_request_payload(context),
            "evaluator_identity": "browser-selected-evaluator",
            "policy_version": "browser-policy",
            "profile_id": "browser-profile",
            "profile_version": "browser-version",
        },
    )

    assert response.status_code == 422, response.text
    assert await _authorization_count() == 0
    assert await _table_count(_COMMAND_TABLE) == 0
    audit = (await _audit_rows())[0]
    assert audit["reason_code"] == "HOLDOUT_REQUEST_BODY_INVALID"
    assert audit["resolved_snapshot_id"] is None
    assert audit["command_id"] is None


@pytest.mark.asyncio
async def test_holdout_request_fails_closed_before_authorization_without_capability(
    client,
    auth_user,
) -> None:
    """Weak topology evidence must never leave an issued authorization or command."""

    context, headers = await _request_context(
        auth_user,
        "holdout-request-capability",
    )
    async with database.async_session_maker() as session:
        profile = await session.scalar(
            select(ResearchCapabilityProfile).where(
                ResearchCapabilityProfile.profile_id == "holdout-request-capability-profile",
                ResearchCapabilityProfile.version == "v1",
            )
        )
        assert profile is not None
        profile.queue_capabilities = {"isolated": False}
        await session.commit()
    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-capability"},
        json=_request_payload(context),
    )

    assert response.status_code == 409, response.text
    assert response.json()["message"] == "BLOCKED_TOPOLOGY_CAPABILITY"
    assert response.json()["details"] == {
        "code": "BLOCKED_TOPOLOGY_CAPABILITY",
        "message": "BLOCKED_TOPOLOGY_CAPABILITY",
        "missing_capabilities": ["sealed_evaluation"],
    }
    assert await _authorization_count() == 0
    assert await _table_count(_COMMAND_TABLE) == 0
    async with database.async_session_maker() as session:
        audit = (
            (
                await session.execute(
                    text(f"SELECT result, reason_code, command_id FROM {_AUDIT_TABLE}")
                )
            )
            .mappings()
            .one()
        )
    assert dict(audit) == {
        "result": "REJECTED",
        "reason_code": "BLOCKED_TOPOLOGY_CAPABILITY",
        "command_id": None,
    }


@pytest.mark.asyncio
async def test_holdout_request_route_audit_failure_is_retryable_503(client, auth_user) -> None:
    """A pre-service body rejection also fails closed when its audit cannot persist."""

    context, headers = await _request_context(auth_user, "holdout-request-route-audit-failure")

    def fail_audit_insert(
        _conn: Any,
        _cursor: Any,
        statement: str,
        parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if f"insert into {_AUDIT_TABLE}" in statement.lower():
            raise OperationalError(statement, parameters, RuntimeError("forced audit failure"))

    sync_engine = database.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", fail_audit_insert)
    try:
        response = await client.post(
            _request_url(context),
            headers={**headers, "Idempotency-Key": "holdout-request-route-audit-failure"},
            json={**_request_payload(context), "dataset_snapshot_id": context["sealed"].id},
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", fail_audit_insert)

    assert response.status_code == 503, response.text
    assert response.json()["details"] == {
        "code": "HOLDOUT_REQUEST_AUDIT_UNAVAILABLE",
        "message": "HOLDOUT_REQUEST_AUDIT_UNAVAILABLE",
        "retryable": True,
    }
    assert await _table_count(_COMMAND_TABLE) == 0
    assert await _table_count(_AUDIT_TABLE) == 0


@pytest.mark.asyncio
async def test_holdout_request_rate_limit_caps_rejected_audit_growth(client, auth_user) -> None:
    """The shared user/IP bucket rejects excess traffic before immutable audit writes."""

    context, headers = await _request_context(auth_user, "holdout-request-rate-limit")
    request_headers = {**headers, "Idempotency-Key": "holdout-request-rate-limit"}

    responses = [
        await client.post(
            _request_url(context),
            headers=request_headers,
            json={**_request_payload(context), "dataset_snapshot_id": context["sealed"].id},
        )
        for _ in range(31)
    ]

    assert [response.status_code for response in responses[:30]] == [422] * 30
    assert responses[30].status_code == 429
    assert await _table_count(_COMMAND_TABLE) == 0
    assert await _table_count(_AUDIT_TABLE) == 30


@pytest.mark.asyncio
async def test_holdout_request_reconciles_commit_ack_loss_without_false_rejection(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A durable winner is returned when COMMIT succeeds but its acknowledgement is lost."""

    context, headers = await _request_context(auth_user, "holdout-request-commit-ack-loss")
    original_commit = AsyncSession.commit
    commit_calls = 0

    async def commit_then_lose_ack(session: AsyncSession) -> None:
        nonlocal commit_calls
        commit_calls += 1
        await original_commit(session)
        if commit_calls == 1:
            raise OperationalError("COMMIT", {}, RuntimeError("lost acknowledgement"))

    monkeypatch.setattr(AsyncSession, "commit", commit_then_lose_ack)
    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-commit-ack-loss"},
        json=_request_payload(context),
    )

    assert response.status_code == 202, response.text
    assert await _table_count(_COMMAND_TABLE) == 1
    assert [(row["result"], row["reason_code"]) for row in await _audit_rows()] == [
        ("ACCEPTED", "HOLDOUT_REQUEST_QUEUED")
    ]


@pytest.mark.asyncio
async def test_holdout_request_readback_failure_never_appends_false_rejection(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unreadable commit state records UNKNOWN while preserving accepted evidence."""

    context, headers = await _request_context(auth_user, "holdout-request-readback-failure")
    service = HoldoutRequestService(
        dataset_registry=DatasetRegistry(object_resolver=context["resolver"])
    )
    app.dependency_overrides[research_api.get_holdout_request_service] = lambda: service
    original_commit = AsyncSession.commit
    commit_calls = 0

    async def commit_then_lose_ack(session: AsyncSession) -> None:
        nonlocal commit_calls
        commit_calls += 1
        await original_commit(session)
        if commit_calls == 1:
            raise OperationalError("COMMIT", {}, RuntimeError("lost acknowledgement"))

    async def fail_readback(_probe: object) -> None:
        raise OperationalError("SELECT", {}, RuntimeError("readback unavailable"))

    monkeypatch.setattr(AsyncSession, "commit", commit_then_lose_ack)
    monkeypatch.setattr(service, "_reconcile_commit_outcome", fail_readback)
    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-readback-failure"},
        json=_request_payload(context),
    )

    assert response.status_code == 503, response.text
    assert response.json()["details"]["code"] == "HOLDOUT_REQUEST_COMMIT_OUTCOME_UNKNOWN"
    assert await _table_count(_COMMAND_TABLE) == 1
    results = [(row["result"], row["reason_code"]) for row in await _audit_rows()]
    assert ("ACCEPTED", "HOLDOUT_REQUEST_QUEUED") in results
    assert ("UNKNOWN", "HOLDOUT_REQUEST_COMMIT_OUTCOME_UNKNOWN") in results
    assert all(result != "REJECTED" for result, _reason in results)


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_failure", ["database", "timeout", "rollback"])
async def test_holdout_request_records_unknown_when_commit_outcome_cannot_be_confirmed(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    commit_failure: str,
) -> None:
    """A failed COMMIT with no durable winner is UNKNOWN, never a contradictory rejection."""

    context, headers = await _request_context(auth_user, "holdout-request-commit-unknown")
    original_commit = AsyncSession.commit
    original_rollback = AsyncSession.rollback
    commit_calls = 0
    rollback_calls = 0

    async def fail_first_commit(session: AsyncSession) -> None:
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 1:
            if commit_failure == "timeout":
                raise TimeoutError("commit acknowledgement timed out")
            raise OperationalError("COMMIT", {}, RuntimeError("unknown outcome"))
        await original_commit(session)

    async def fail_first_rollback(session: AsyncSession) -> None:
        nonlocal rollback_calls
        rollback_calls += 1
        if rollback_calls == 1:
            raise OperationalError("ROLLBACK", {}, RuntimeError("connection unavailable"))
        await original_rollback(session)

    monkeypatch.setattr(AsyncSession, "commit", fail_first_commit)
    if commit_failure == "rollback":
        monkeypatch.setattr(AsyncSession, "rollback", fail_first_rollback)
    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": "holdout-request-commit-unknown"},
        json=_request_payload(context),
    )

    assert response.status_code == 503, response.text
    assert response.json()["details"] == {
        "code": "HOLDOUT_REQUEST_COMMIT_OUTCOME_UNKNOWN",
        "message": "HOLDOUT_REQUEST_COMMIT_OUTCOME_UNKNOWN",
        "retryable": True,
    }
    assert await _table_count(_COMMAND_TABLE) == 0
    rows = await _audit_rows()
    assert [(row["result"], row["reason_code"]) for row in rows] == [
        ("UNKNOWN", "HOLDOUT_REQUEST_COMMIT_OUTCOME_UNKNOWN")
    ]


@pytest.mark.asyncio
async def test_holdout_request_retries_database_unique_winner_readback(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cross-process uniqueness loser revalidates and returns the exact committed winner."""

    context, headers = await _request_context(auth_user, "holdout-request-unique-winner")
    request_headers = {**headers, "Idempotency-Key": "holdout-request-unique-winner"}
    created = await client.post(
        _request_url(context),
        headers=request_headers,
        json=_request_payload(context),
    )
    assert created.status_code == 202, created.text

    service = HoldoutRequestService(
        dataset_registry=DatasetRegistry(object_resolver=context["resolver"])
    )
    original_request_once = service._request_once
    request_once_calls = 0

    async def lose_unique_race(**kwargs: object) -> ResearchHoldoutEvaluationCommand:
        nonlocal request_once_calls
        request_once_calls += 1
        if request_once_calls == 1:
            raise IntegrityError("INSERT", {}, RuntimeError("forced unique race"))
        return await original_request_once(**kwargs)

    monkeypatch.setattr(service, "_request_once", lose_unique_race)
    replayed = await service.request(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        expected_candidate_hash=context["candidate"].candidate_hash,
        idempotency_key="holdout-request-unique-winner",
    )

    assert replayed.id == created.json()["id"]
    assert request_once_calls == 2
    assert await _table_count(_COMMAND_TABLE) == 1
    assert await _table_count(_AUDIT_TABLE) == 1


@pytest.mark.asyncio
async def test_holdout_request_lock_pool_has_a_fixed_upper_bound() -> None:
    """Untrusted idempotency keys cannot grow a process-local lock dictionary forever."""

    locks = {
        holdout_request_module._request_lock("actor", f"untrusted-key-{index}")
        for index in range(1_000)
    }

    assert 1 < len(locks) <= 64


@pytest.mark.asyncio
async def test_holdout_command_insert_failure_leaves_no_partial_authority(
    client,
    auth_user,
) -> None:
    """Splitting authorization and outbox commits would leave a consumed budget stranded."""

    context, headers = await _request_context(auth_user, "holdout-request-rollback")

    def fail_command_insert(
        _conn: Any,
        _cursor: Any,
        statement: str,
        parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if f"insert into {_COMMAND_TABLE}" in statement.lower():
            raise OperationalError(statement, parameters, RuntimeError("forced command failure"))

    sync_engine = database.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", fail_command_insert)
    try:
        response = await client.post(
            _request_url(context),
            headers={**headers, "Idempotency-Key": "holdout-request-rollback"},
            json=_request_payload(context),
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", fail_command_insert)

    assert response.status_code == 503, response.text
    assert response.json()["details"] == {
        "code": "HOLDOUT_REQUEST_PERSISTENCE_FAILED",
        "message": "HOLDOUT_REQUEST_PERSISTENCE_FAILED",
        "retryable": True,
    }
    assert await _authorization_count() == 0
    assert await _table_count(_COMMAND_TABLE) == 0
    assert await _table_count(_AUDIT_TABLE) == 1
    async with database.async_session_maker() as session:
        epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
    assert epoch is not None and epoch.status == "SELECTED"
    assert epoch.disclosed_at is None and epoch.closed_at is None


@pytest.mark.asyncio
async def test_holdout_audit_insert_failure_rolls_back_command(client, auth_user) -> None:
    """An accepted command without its audit event must never commit."""

    context, headers = await _request_context(auth_user, "holdout-request-audit-failure")

    def fail_audit_insert(
        _conn: Any,
        _cursor: Any,
        statement: str,
        parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if f"insert into {_AUDIT_TABLE}" in statement.lower():
            raise OperationalError(statement, parameters, RuntimeError("forced audit failure"))

    sync_engine = database.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", fail_audit_insert)
    try:
        response = await client.post(
            _request_url(context),
            headers={**headers, "Idempotency-Key": "holdout-request-audit-failure"},
            json=_request_payload(context),
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", fail_audit_insert)

    assert response.status_code == 503, response.text
    assert response.json()["details"]["code"] == "HOLDOUT_REQUEST_AUDIT_UNAVAILABLE"
    assert response.json()["details"]["retryable"] is True
    assert await _table_count(_COMMAND_TABLE) == 0
    assert await _table_count(_AUDIT_TABLE) == 0
    assert await _authorization_count() == 0


async def _request_context(
    auth_user,
    suffix: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    user, headers = auth_user
    profile = CapabilityProfile(
        profile_id=f"{suffix}-profile",
        version="v1",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": _EVALUATOR_IDENTITY,
            "runner": "discovery-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        stage_image_digests={
            "evaluator": _EVALUATOR_IMAGE,
            "scanner": f"sha256:{'5' * 64}",
        },
    )
    await CapabilityRegistry().register(profile)
    context = await _strict_context(
        auth_user,
        suffix,
        capability_profile_id=profile.profile_id,
        capability_profile_version=profile.version,
        capability_evidence_hash=profile.evidence_hash,
    )
    app.dependency_overrides[research_api.get_dataset_object_resolver] = lambda: context["resolver"]
    return context, headers


def _request_url(context: dict[str, Any]) -> str:
    return (
        f"/api/v1/strategy/ai-research/v2/candidates/{context['candidate'].id}/holdout-evaluation"
    )


def _request_payload(context: dict[str, Any]) -> dict[str, str]:
    return {
        "expected_candidate_hash": context["candidate"].candidate_hash,
    }


async def _authorization_count() -> int:
    async with database.async_session_maker() as session:
        return int(
            await session.scalar(select(func.count()).select_from(ResearchHoldoutAuthorization))
            or 0
        )


async def _table_count(table_name: str) -> int:
    async with database.async_session_maker() as session:
        return int(await session.scalar(text(f"SELECT COUNT(*) FROM {table_name}")) or 0)


async def _audit_rows() -> list[dict[str, Any]]:
    async with database.async_session_maker() as session:
        rows = (
            (
                await session.execute(
                    text(
                        f"SELECT actor_user_id, candidate_id, expected_candidate_hash, "
                        f"resolved_snapshot_id, result, reason_code, command_id "
                        f"FROM {_AUDIT_TABLE} ORDER BY created_at, id"
                    )
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]
