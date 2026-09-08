from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.database import Base, async_session_maker
from app.models.ai_research_v2 import (
    ResearchExperimentEpoch,
    ResearchHoldoutAuthorization,
    ResearchHypothesisVersion,
    ResearchTask,
)


def test_v2_research_tables_are_registered_with_metadata() -> None:
    required_tables = {
        "ai_research_hypothesis_versions",
        "ai_research_capability_profiles",
        "ai_research_config_profiles",
        "ai_research_experiment_epochs",
        "ai_research_dataset_snapshots",
        "ai_research_forward_observation_epochs",
        "ai_research_forward_observation_snapshots",
        "ai_research_runs",
        "ai_research_tasks",
        "ai_research_task_events",
        "ai_research_trials",
        "ai_research_model_invocations",
        "ai_research_evaluations",
        "ai_research_holdout_authorizations",
        "ai_research_gate_decisions",
        "ai_research_human_decisions",
        "ai_research_candidate_freeze_receipts",
        "ai_research_artifacts",
        "ai_research_evidence_packages",
        "ai_research_quota_buckets",
        "ai_research_quota_reservations",
    }

    assert required_tables.issubset(Base.metadata.tables)


def test_quota_budget_context_is_nullable_json_for_legacy_reservations() -> None:
    from sqlalchemy import JSON

    column = Base.metadata.tables["ai_research_quota_reservations"].c.get("reservation_context")
    assert column is not None
    assert column.nullable is True
    assert isinstance(column.type, JSON)


@pytest.mark.asyncio
async def test_hypothesis_versions_are_immutable_versioned_rows(auth_user) -> None:
    user_id = await _user_id(auth_user)
    hypothesis_id = str(uuid.uuid4())
    model = ResearchHypothesisVersion(
        user_id=user_id,
        hypothesis_id=hypothesis_id,
        version_no=1,
        status="DRAFT",
        canonical_payload={"research_question": "成本后趋势是否有效？"},
        content_hash="a" * 64,
    )
    async with async_session_maker() as session:
        session.add(model)
        await session.commit()

    duplicate = ResearchHypothesisVersion(
        user_id=user_id,
        hypothesis_id=hypothesis_id,
        version_no=1,
        status="DRAFT",
        canonical_payload={"research_question": "另一个问题"},
        content_hash="b" * 64,
    )
    async with async_session_maker() as session:
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async with async_session_maker() as session:
        loaded = await session.scalar(
            select(ResearchHypothesisVersion).where(ResearchHypothesisVersion.id == model.id)
        )
    assert loaded is not None
    assert loaded.content_hash == "a" * 64


@pytest.mark.asyncio
async def test_task_idempotency_and_holdout_consumption_are_constrained(auth_user) -> None:
    user_id = await _user_id(auth_user)
    epoch = ResearchExperimentEpoch(
        user_id=user_id,
        hypothesis_version_id=str(uuid.uuid4()),
        family_hash="f" * 64,
        search_budget={"max_trials": 3},
        dataset_policy_version="policy-v1",
        status="OPEN",
    )
    task = ResearchTask(
        user_id=user_id,
        run_id=str(uuid.uuid4()),
        status="QUEUED",
        stage_cursor="CLARIFY",
        request_json={"hypothesis_version_id": str(uuid.uuid4())},
        idempotency_key="same-request",
        idempotency_request_hash="r" * 64,
    )
    async with async_session_maker() as session:
        session.add_all([epoch, task])
        await session.commit()

    duplicate_task = ResearchTask(
        user_id=user_id,
        run_id=str(uuid.uuid4()),
        status="QUEUED",
        stage_cursor="CLARIFY",
        request_json={},
        idempotency_key="same-request",
        idempotency_request_hash="r" * 64,
    )
    async with async_session_maker() as session:
        session.add(duplicate_task)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    authorization = ResearchHoldoutAuthorization(
        experiment_epoch_id=epoch.id,
        candidate_id="candidate-1",
        candidate_hash="c" * 64,
        dataset_snapshot_id="snapshot-1",
        policy_version="policy-v1",
        token_hash="t" * 64,
        status="ISSUED",
        evaluator_identity="ai_research_evaluator",
        capability_profile_id="single-node-isolated-services",
        capability_profile_version="v1",
        capability_evidence_hash="e" * 64,
    )
    async with async_session_maker() as session:
        session.add(authorization)
        await session.commit()

    duplicate_authorization = ResearchHoldoutAuthorization(
        experiment_epoch_id=epoch.id,
        candidate_id="candidate-2",
        candidate_hash="d" * 64,
        dataset_snapshot_id="snapshot-2",
        policy_version="policy-v2",
        token_hash="u" * 64,
        status="ISSUED",
        evaluator_identity="ai_research_evaluator",
    )
    async with async_session_maker() as session:
        session.add(duplicate_authorization)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    from app.models.user import User

    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == user["username"]))
        return str(result.scalar_one())
