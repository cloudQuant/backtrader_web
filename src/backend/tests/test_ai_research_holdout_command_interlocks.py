from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest
from httpx import Response
from sqlalchemy import func, select

from app.api.strategy import research as research_api
from app.config import get_settings
from app.db import database
from app.models.ai_research_v2 import (
    ResearchEvaluation,
    ResearchExperimentEpoch,
    ResearchGateDecision,
    ResearchHoldoutAuthorization,
    ResearchHoldoutEvaluationCommand,
    ResearchHoldoutRequestAudit,
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.holdout_authorization import HoldoutAuthorizationRegistry
from app.services.research.holdout_finalize import HoldoutFinalizeService
from tests.conftest import app
from tests.test_ai_research_holdout_claim import _claim_service, _queued_command
from tests.test_ai_research_holdout_finalize import _trusted_rejecting_measurements
from tests.test_ai_research_holdout_request import (
    _request_context,
    _request_payload,
    _request_url,
)


@pytest.fixture(autouse=True)
def enable_protocol_and_clear_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)
    yield
    app.dependency_overrides.pop(research_api.get_dataset_object_resolver, None)
    app.dependency_overrides.pop(research_api.get_holdout_request_service, None)


@pytest.mark.asyncio
async def test_request_rejects_existing_raw_authorization_without_accepted_command(
    client,
    auth_user,
) -> None:
    suffix = "interlock-authorization-before-request"
    context, headers = await _request_context(auth_user, suffix)
    registry = HoldoutAuthorizationRegistry(dataset_registry=_datasets(context))
    issued = await registry.issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="promotion-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=f"{suffix}-profile",
        profile_version="v1",
    )

    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": suffix},
        json=_request_payload(context),
    )

    assert response.status_code == 409, response.text
    assert response.json()["message"] == "HOLDOUT_REQUEST_AUTHORIZATION_ALREADY_EXISTS"
    async with database.async_session_maker() as session:
        authorization = await session.get(ResearchHoldoutAuthorization, issued.authorization.id)
        epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
        command_count = await _count(session, ResearchHoldoutEvaluationCommand)
        accepted_count = await session.scalar(
            select(func.count())
            .select_from(ResearchHoldoutRequestAudit)
            .where(ResearchHoldoutRequestAudit.result == "ACCEPTED")
        )
    assert authorization is not None and authorization.status == "ISSUED"
    assert epoch is not None and epoch.status == "SELECTED"
    assert command_count == 0
    assert accepted_count == 0


@pytest.mark.asyncio
async def test_request_and_public_issue_race_leave_exactly_one_authority(
    client,
    auth_user,
) -> None:
    suffix = "interlock-request-issue-race"
    context, headers = await _request_context(auth_user, suffix)
    registry = HoldoutAuthorizationRegistry(dataset_registry=_datasets(context))

    issue_result, request_result = await asyncio.gather(
        registry.issue(
            user_id=context["user_id"],
            candidate_id=context["candidate"].id,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="promotion-v1",
            evaluator_identity="ai_research_evaluator",
            profile_id=f"{suffix}-profile",
            profile_version="v1",
        ),
        client.post(
            _request_url(context),
            headers={**headers, "Idempotency-Key": suffix},
            json=_request_payload(context),
        ),
        return_exceptions=True,
    )

    async with database.async_session_maker() as session:
        authorization_count = await _count(session, ResearchHoldoutAuthorization)
        command_count = await _count(session, ResearchHoldoutEvaluationCommand)
        accepted_count = int(
            await session.scalar(
                select(func.count())
                .select_from(ResearchHoldoutRequestAudit)
                .where(ResearchHoldoutRequestAudit.result == "ACCEPTED")
            )
            or 0
        )
    assert authorization_count + command_count == 1
    assert accepted_count == command_count
    assert isinstance(request_result, Response)
    if authorization_count == 1:
        assert not isinstance(issue_result, BaseException)
        assert request_result.status_code == 409
        assert request_result.json()["message"] == "HOLDOUT_REQUEST_AUTHORIZATION_ALREADY_EXISTS"
    else:
        assert isinstance(issue_result, ValueError)
        assert str(issue_result) == "HOLDOUT_AUTHORIZATION_CLAIM_FENCE_REQUIRED"
        assert request_result.status_code == 202


@pytest.mark.asyncio
async def test_public_consume_rejects_command_before_mutating_issued_authorization(
    client,
    auth_user,
) -> None:
    suffix = "interlock-public-consume"
    context, _headers, command_ref = await _queued_command(client, auth_user, suffix)
    raw_token = "public-token-must-remain-unconsumed"
    now = datetime.now(timezone.utc)
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, command_ref["id"])
        assert command is not None
        authorization = ResearchHoldoutAuthorization(
            experiment_epoch_id=command.experiment_epoch_id,
            candidate_id=command.candidate_id,
            candidate_hash=command.candidate_hash,
            dataset_snapshot_id=command.dataset_snapshot_id,
            policy_version=command.policy_version,
            token_hash=sha256(raw_token.encode("utf-8")).hexdigest(),
            status="ISSUED",
            evaluator_identity=command.evaluator_identity,
            capability_profile_id=command.capability_profile_id,
            capability_profile_version=command.capability_profile_version,
            capability_evidence_hash=command.capability_evidence_hash,
            issued_by=context["user_id"],
            issued_at=now,
            expires_at=now + timedelta(minutes=15),
        )
        session.add(authorization)
        await session.commit()
        authorization_id = authorization.id

    registry = HoldoutAuthorizationRegistry(dataset_registry=_datasets(context))
    async with database.async_session_maker() as session:
        with pytest.raises(
            ValueError,
            match="^HOLDOUT_AUTHORIZATION_CLAIM_FENCE_REQUIRED$",
        ):
            await registry.consume_in_session(
                session,
                raw_token,
                candidate_id=context["candidate"].id,
                candidate_hash=context["candidate"].candidate_hash,
                dataset_snapshot_id=context["sealed"].id,
                policy_version="promotion-v1",
                evaluator_identity="ai_research_evaluator",
            )
        await session.rollback()

    async with database.async_session_maker() as session:
        authorization = await session.get(ResearchHoldoutAuthorization, authorization_id)
        epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
    assert authorization is not None and authorization.status == "ISSUED"
    assert authorization.consumed_at is None
    assert epoch is not None and epoch.status == "SELECTED"


@pytest.mark.asyncio
async def test_expired_checkpointed_claim_recovers_then_reconciles_from_persisted_evidence(
    client,
    auth_user,
) -> None:
    suffix = "interlock-checkpoint-recovery"
    context, _headers, command = await _queued_command(client, auth_user, suffix)
    claim_service, runtime = _claim_service(context)
    claimed = await claim_service.claim(command_id=command["id"], runtime=runtime)
    finalize_service = HoldoutFinalizeService._for_test_only_inline_measurements()
    checkpoint = await finalize_service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert stored is not None
        stored.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    recovered = await claim_service.recover_expired(
        command_id=claimed.command_id,
        runtime=runtime,
    )

    assert recovered.status == "RECONCILING"
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
    assert stored is not None
    assert stored.error_code == "HOLDOUT_CLAIM_LEASE_EXPIRED"
    assert stored.lease_owner is None and stored.lease_token_hash is None
    assert stored.lease_expires_at is None and stored.lease_heartbeat_at is None
    assert evaluation is not None and evaluation.returns_artifact_id == checkpoint.artifact_id

    result = await finalize_service.reconcile_checkpointed_evaluation(
        command_id=claimed.command_id,
        runtime=runtime,
    )

    assert result.command_status == "SUCCEEDED"
    assert result.evaluation_status == "REJECTED"
    async with database.async_session_maker() as session:
        assert await _count(session, ResearchHoldoutAuthorization) == 1
        assert await _count(session, ResearchEvaluation) == 1
        assert await _count(session, ResearchGateDecision) == 13


@pytest.mark.asyncio
async def test_expired_checkpointed_claim_rejects_tampered_authority_graph(
    client,
    auth_user,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "interlock-checkpoint-tamper",
    )
    claim_service, runtime = _claim_service(context)
    claimed = await claim_service.claim(command_id=command["id"], runtime=runtime)
    await HoldoutFinalizeService._for_test_only_inline_measurements().checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements={},
    )
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert stored is not None and stored.authorization_id is not None
        authorization = await session.get(
            ResearchHoldoutAuthorization,
            stored.authorization_id,
        )
        assert authorization is not None
        stored.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        authorization.issued_by = "tampered-worker"
        await session.commit()

    with pytest.raises(ValueError, match="^HOLDOUT_CLAIM_AUTHORITY_INCONSISTENT$"):
        await claim_service.recover_expired(command_id=claimed.command_id, runtime=runtime)

    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
    assert stored is not None and stored.status == "RUNNING"
    assert stored.error_code is None
    assert stored.lease_owner == runtime.worker_identity
    assert stored.lease_token_hash == sha256(claimed.lease_token.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_expired_uncheckpointed_claim_fences_without_reissuing_authority(
    client,
    auth_user,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "interlock-uncheckpointed-recovery",
    )
    claim_service, runtime = _claim_service(context)
    claimed = await claim_service.claim(command_id=command["id"], runtime=runtime)
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert stored is not None
        stored.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    await claim_service.recover_expired(command_id=claimed.command_id, runtime=runtime)

    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        authorization_count = await _count(session, ResearchHoldoutAuthorization)
        evaluation_count = await _count(session, ResearchEvaluation)
    assert stored is not None and stored.status == "RECONCILING"
    assert stored.error_code == "HOLDOUT_CLAIM_LEASE_EXPIRED"
    assert authorization_count == 1
    assert evaluation_count == 1
    with pytest.raises(ValueError, match="^HOLDOUT_CLAIM_ALREADY_STARTED$"):
        await claim_service.claim(command_id=claimed.command_id, runtime=runtime)


def _datasets(context: dict[str, object]) -> DatasetRegistry:
    datasets = context["datasets"]
    assert isinstance(datasets, DatasetRegistry)
    return datasets


async def _count(session, model: object) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)
