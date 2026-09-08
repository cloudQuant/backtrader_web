from __future__ import annotations

import inspect

import pytest
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
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.holdout_authorization import HoldoutAuthorizationRegistry
from app.services.research.independent_evaluator import IndependentEvaluator
from app.services.research.promotion import PromotionGateEngine, PromotionPolicy
from tests.conftest import app
from tests.test_ai_research_holdout_claim import _claim_service, _queued_command
from tests.test_ai_research_holdout_request import (
    _request_context,
    _request_payload,
    _request_url,
)
from tests.test_ai_research_promotion import _POLICY, _authorized_evaluation_context


@pytest.fixture(autouse=True)
def enable_protocol_and_clear_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)
    yield
    app.dependency_overrides.pop(research_api.get_dataset_object_resolver, None)
    app.dependency_overrides.pop(research_api.get_holdout_request_service, None)


def test_promotion_has_no_bare_command_backed_bypass() -> None:
    parameters = inspect.signature(PromotionGateEngine.evaluate_and_record_in_session).parameters

    assert "allow_command_backed" not in parameters
    assert hasattr(PromotionGateEngine, "evaluate_command_and_record_in_session")


@pytest.mark.asyncio
async def test_promotion_in_session_leaves_commit_and_rollback_to_caller(auth_user) -> None:
    context = await _authorized_evaluation_context(
        auth_user,
        "promotion-caller-owned-transaction",
    )
    engine = PromotionGateEngine()

    async with database.async_session_maker() as session:
        result = await engine.evaluate_and_record_in_session(
            session,
            candidate_id=context["candidate"].id,
            evaluation_id=context["evaluation"].id,
            policy=_POLICY,
            evidence={"caller_spoof": "ignored"},
        )
        staged_count = await session.scalar(
            select(func.count())
            .select_from(ResearchGateDecision)
            .where(ResearchGateDecision.evaluation_id == context["evaluation"].id)
        )
        assert result.eligible is True
        assert staged_count == 13
        await session.rollback()

    async with database.async_session_maker() as session:
        persisted_count = await session.scalar(
            select(func.count())
            .select_from(ResearchGateDecision)
            .where(ResearchGateDecision.evaluation_id == context["evaluation"].id)
        )
    assert persisted_count == 0


@pytest.mark.asyncio
async def test_public_promotion_rejects_command_backed_evaluation(client, auth_user) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "promotion-command-fence",
    )
    claim_service, runtime = _claim_service(context)
    claimed = await claim_service.claim(command_id=command["id"], runtime=runtime)

    with pytest.raises(ValueError, match="^PROMOTION_CLAIM_FENCE_REQUIRED$"):
        await PromotionGateEngine().evaluate_and_record(
            candidate_id=context["candidate"].id,
            evaluation_id=claimed.evaluation_id,
            policy=_policy(),
            evidence={},
        )

    async with database.async_session_maker() as session:
        decisions = await session.scalar(
            select(func.count())
            .select_from(ResearchGateDecision)
            .where(ResearchGateDecision.evaluation_id == claimed.evaluation_id)
        )
    assert decisions == 0


@pytest.mark.asyncio
async def test_public_promotion_cannot_omit_evaluation_id_to_bypass_command_fence(
    client,
    auth_user,
) -> None:
    context, _headers, _command = await _queued_command(
        client,
        auth_user,
        "promotion-command-fence-omitted-evaluation",
    )

    with pytest.raises(ValueError, match="^PROMOTION_CLAIM_FENCE_REQUIRED$"):
        await PromotionGateEngine().evaluate_and_record(
            candidate_id=context["candidate"].id,
            policy=_policy(),
            evidence={},
        )

    async with database.async_session_maker() as session:
        decisions = await session.scalar(
            select(func.count())
            .select_from(ResearchGateDecision)
            .where(ResearchGateDecision.candidate_id == context["candidate"].id)
        )
    assert decisions == 0


@pytest.mark.asyncio
async def test_independent_resume_rejects_command_backed_evaluation(client, auth_user) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "resume-command-fence",
    )
    claim_service, runtime = _claim_service(context)
    claimed = await claim_service.claim(command_id=command["id"], runtime=runtime)

    with pytest.raises(
        ValueError,
        match="^INDEPENDENT_EVALUATOR_CLAIM_FENCE_REQUIRED$",
    ):
        await IndependentEvaluator(dataset_registry=_datasets(context)).resume_evaluation(
            evaluation_id=claimed.evaluation_id,
            policy=_policy(),
            evaluator_identity=runtime.evaluator_identity,
        )

    async with database.async_session_maker() as session:
        evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
    assert evaluation is not None and evaluation.status == "RUNNING"


@pytest.mark.asyncio
async def test_raw_authorization_issue_cannot_preempt_queued_command(client, auth_user) -> None:
    suffix = "authorization-command-fence"
    context, _headers, _command = await _queued_command(client, auth_user, suffix)

    with pytest.raises(
        ValueError,
        match="^HOLDOUT_AUTHORIZATION_CLAIM_FENCE_REQUIRED$",
    ):
        await HoldoutAuthorizationRegistry(dataset_registry=_datasets(context)).issue(
            user_id=context["user_id"],
            candidate_id=context["candidate"].id,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="promotion-v1",
            evaluator_identity="ai_research_evaluator",
            profile_id=f"{suffix}-profile",
            profile_version="v1",
        )

    async with database.async_session_maker() as session:
        authorization_count = await session.scalar(
            select(func.count()).select_from(ResearchHoldoutAuthorization)
        )
        epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
    assert authorization_count == 0
    assert epoch is not None and epoch.status == "SELECTED"


@pytest.mark.asyncio
@pytest.mark.parametrize("command_status", ["RUNNING", "RECONCILING", "SUCCEEDED"])
async def test_raw_authorization_issue_rejects_started_command_authority(
    client,
    auth_user,
    command_status: str,
) -> None:
    suffix = f"authorization-started-command-fence-{command_status.lower()}"
    context, _headers, command = await _queued_command(client, auth_user, suffix)
    claim_service, runtime = _claim_service(context)
    await claim_service.claim(command_id=command["id"], runtime=runtime)
    if command_status != "RUNNING":
        async with database.async_session_maker() as session:
            stored = await session.get(
                ResearchHoldoutEvaluationCommand,
                command["id"],
            )
            assert stored is not None
            stored.status = command_status
            stored.error_code = (
                "HOLDOUT_RECONCILIATION_REQUIRED" if command_status == "RECONCILING" else None
            )
            stored.lease_owner = None
            stored.lease_token_hash = None
            stored.lease_expires_at = None
            stored.lease_heartbeat_at = None
            await session.commit()

    with pytest.raises(
        ValueError,
        match="^HOLDOUT_AUTHORIZATION_CLAIM_FENCE_REQUIRED$",
    ):
        await HoldoutAuthorizationRegistry(dataset_registry=_datasets(context)).issue(
            user_id=context["user_id"],
            candidate_id=context["candidate"].id,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="promotion-v1",
            evaluator_identity="ai_research_evaluator",
            profile_id=f"{suffix}-profile",
            profile_version="v1",
        )


@pytest.mark.asyncio
async def test_request_rejects_existing_raw_authorization_before_legacy_evaluation(
    client,
    auth_user,
) -> None:
    suffix = "evaluate-command-fence"
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
        authorization = await session.get(
            ResearchHoldoutAuthorization,
            issued.authorization.id,
        )
        epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
        command_count = await session.scalar(
            select(func.count()).select_from(ResearchHoldoutEvaluationCommand)
        )
    assert authorization is not None and authorization.status == "ISSUED"
    assert authorization.consumed_at is None
    assert epoch is not None and epoch.status == "SELECTED"
    assert command_count == 0


def _datasets(context: dict[str, object]) -> DatasetRegistry:
    datasets = context["datasets"]
    assert isinstance(datasets, DatasetRegistry)
    return datasets


def _policy() -> PromotionPolicy:
    return PromotionPolicy(
        version="promotion-v1",
        min_deflated_sharpe=0.95,
        max_drawdown=0.2,
    )
