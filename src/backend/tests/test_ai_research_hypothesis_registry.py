from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_research_v2 import ResearchExperimentEpoch
from app.models.user import User
from app.services.research.canonical import content_hash
from app.services.research.experiment_registry import ExperimentEpochRegistry
from app.services.research.hypothesis_registry import HypothesisRegistry


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "research_question": "成本与滑点后，趋势信号是否仍有可检验优势？",
        "economic_mechanism": "趋势持续由信息扩散与风险补偿共同驱动。",
        "asset_scope": {"symbols": ["RB0"], "asset_class": "futures"},
        "frequency": "1d",
        "time_window": {"start": "2022-01-01", "end": "2025-12-31"},
        "information_cutoff": "2025-12-31T00:00:00Z",
        "cost_model": {"commission_bps": 2.0, "slippage_bps": 1.0},
        "execution_model": {"fill": "next_bar_open"},
        "primary_metric": "deflated_sharpe",
        "secondary_metrics": ["max_drawdown", "turnover"],
        "capacity_assumptions": {"max_participation_rate": 0.1},
        "falsification_criteria": {"max_drawdown": 0.2},
        "search_space": {"lookback": [10, 20]},
        "max_budget": {"max_trials": 20},
        "dataset_policy_version": "dataset-policy-v1",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_parse_create_is_draft_and_confirmation_requires_complete_server_hash(
    auth_user,
) -> None:
    user, _headers = auth_user
    user_id = await _user_id(user["username"])
    registry = HypothesisRegistry()
    incomplete = await registry.create_draft(user_id, _payload(primary_metric=""))

    assert incomplete.status == "DRAFT"
    with pytest.raises(ValueError, match="HYPOTHESIS_REQUIRED_FIELDS_MISSING"):
        await registry.confirm(user_id, incomplete.id, request_hash=incomplete.content_hash)

    draft = await registry.create_draft(user_id, _payload())
    with pytest.raises(ValueError, match="HYPOTHESIS_CONFIRMATION_HASH_MISMATCH"):
        await registry.confirm(user_id, draft.id, request_hash="0" * 64)

    confirmed = await registry.confirm(
        user_id,
        draft.id,
        request_hash=content_hash(_payload()),
    )

    assert confirmed.status == "CONFIRMED"
    assert confirmed.confirmed_by == user_id
    assert confirmed.confirmed_at is not None


@pytest.mark.asyncio
async def test_confirmation_rejects_missing_preregistered_contract_fields(auth_user) -> None:
    """The server, rather than a browser form, owns the full preregistration contract."""

    user, _headers = auth_user
    user_id = await _user_id(user["username"])
    registry = HypothesisRegistry()
    draft = await registry.create_draft(user_id, _payload(frequency=""))

    with pytest.raises(ValueError, match="HYPOTHESIS_REQUIRED_FIELDS_MISSING:frequency"):
        await registry.confirm(user_id, draft.id, request_hash=draft.content_hash)


@pytest.mark.asyncio
async def test_confirmation_rejects_invalid_preregistered_time_window(auth_user) -> None:
    """A non-empty payload still cannot confirm if its declared window is incoherent."""

    user, _headers = auth_user
    user_id = await _user_id(user["username"])
    registry = HypothesisRegistry()
    draft = await registry.create_draft(
        user_id,
        _payload(time_window={"start": "2025-12-31", "end": "2022-01-01"}),
    )

    with pytest.raises(ValueError, match="HYPOTHESIS_REQUIRED_FIELDS_INVALID:time_window"):
        await registry.confirm(user_id, draft.id, request_hash=draft.content_hash)


@pytest.mark.asyncio
async def test_revision_of_confirmed_hypothesis_creates_child_and_supersedes_parent(
    auth_user,
) -> None:
    user, _headers = auth_user
    user_id = await _user_id(user["username"])
    registry = HypothesisRegistry()
    draft = await registry.create_draft(user_id, _payload())
    confirmed = await registry.confirm(user_id, draft.id, request_hash=draft.content_hash)

    revised = await registry.revise(
        user_id,
        confirmed.id,
        _payload(search_space={"lookback": [10, 30]}),
    )
    original = await registry.get_version(user_id, confirmed.id)

    assert revised.status == "DRAFT"
    assert revised.hypothesis_id == confirmed.hypothesis_id
    assert revised.version_no == 2
    assert revised.parent_version_id == confirmed.id
    assert revised.content_hash != confirmed.content_hash
    assert original is not None
    assert original.status == "SUPERSEDED"


@pytest.mark.asyncio
async def test_disclosed_family_cannot_open_a_second_epoch(auth_user) -> None:
    """A client cannot obtain another sealed-disclosure budget by recreating a family."""

    user, _headers = auth_user
    user_id = await _user_id(user["username"])
    hypothesis_registry = HypothesisRegistry()
    payload = _payload()
    hypothesis = await hypothesis_registry.create_draft(user_id, payload)
    hypothesis = await hypothesis_registry.confirm(
        user_id,
        hypothesis.id,
        request_hash=hypothesis.content_hash,
    )
    registry = ExperimentEpochRegistry()
    epoch = await registry.create_epoch(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        search_budget={"max_trials": 3},
        dataset_policy_version="dataset-policy-v1",
    )

    assert epoch.family_hash == content_hash(
        {
            key: payload[key]
            for key in (
                "research_question",
                "asset_scope",
                "frequency",
                "time_window",
                "primary_metric",
                "search_space",
            )
        }
    )
    repeated_open_epoch = await registry.create_epoch(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        search_budget={"max_trials": 3},
        dataset_policy_version="dataset-policy-v1",
    )
    assert repeated_open_epoch.id == epoch.id
    async with async_session_maker() as session:
        stored = await session.get(ResearchExperimentEpoch, epoch.id)
        assert stored is not None
        stored.status = "CLOSED"
        await session.commit()

    with pytest.raises(ValueError, match="EXPERIMENT_EPOCH_FAMILY_ALREADY_EXISTS"):
        await registry.create_epoch(
            user_id=user_id,
            hypothesis_version_id=hypothesis.id,
            search_budget={"max_trials": 3},
            dataset_policy_version="dataset-policy-v1",
        )


@pytest.mark.asyncio
async def test_hypothesis_registry_does_not_disclose_another_users_version(
    auth_user, client
) -> None:
    user, _headers = auth_user
    user_id = await _user_id(user["username"])
    registry = HypothesisRegistry()
    draft = await registry.create_draft(user_id, _payload())

    from tests.conftest import register_and_login

    other, _other_headers = await register_and_login(client, username="research-v2-other")
    assert await registry.get_version(await _user_id(other["username"]), draft.id) is None


async def _user_id(username: str) -> str:
    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == username))
        return str(result.scalar_one())
