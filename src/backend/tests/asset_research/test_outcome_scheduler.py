"""Durable scheduling contracts for mature multi-asset outcome evaluation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.asset_research import (
    AssetDataSourceRegistry,
    AssetSignalOutcome,
    AssetSignalPrediction,
    AssetSourceSnapshot,
)
from app.models.user import User
from app.schemas.asset_research import (
    AssetAnalysisCreateRequest,
    FuturesIdentityDetails,
    InstrumentIdentity,
    RawAssetSnapshot,
)
from app.services.asset_research import outcome_scheduler as outcome_scheduler_module
from app.services.asset_research.orchestrator import AssetResearchOrchestrator
from app.services.asset_research.outcome_scheduler import AssetResearchOutcomeRunner

_ENTRY_CUTOFF = datetime(2026, 8, 1, tzinfo=timezone.utc)
_EVALUATION_CUTOFF = datetime(2026, 8, 22, tzinfo=timezone.utc)


def _identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="futures",
        identity_level="CONTRACT",
        canonical_id="futures:CFFEX:IF2609:CNY",
        display_symbol="IF2609",
        name="沪深300期货2609",
        venue="CFFEX",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="CONTRACT_CODE",
        identifier_value="IF2609",
        product_type="FUTURE",
        metadata_version="outcome-runner-v1",
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            expiry_at="2026-09-18T07:15:00+00:00",
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )


class _FuturesData:
    def __init__(self) -> None:
        self.fail = False

    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        if self.fail:
            raise RuntimeError("fixture outcome source unavailable")
        is_entry = cutoff_at <= _ENTRY_CUTOFF
        bid, ask, price = (99.0, 100.0, 99.5) if is_entry else (109.0, 110.0, 109.5)
        last_close = 102.0 if is_entry else price
        return RawAssetSnapshot(
            identity=identity,
            cutoff_at=cutoff_at,
            retrieved_at=cutoff_at,
            raw_schema_version="outcome-runner-v1",
            raw_fields={
                "snapshot": {"bid": bid, "ask": ask, "price": price},
                "futures": {
                    "cost_snapshot": {
                        "cost_model_version": "outcome-runner-fixture-v1",
                        "total_cost_rate": 0.0,
                    }
                },
            },
            history_rows=[
                {"date": "2026-07-31", "close": 98.0},
                {"date": cutoff_at.date().isoformat(), "close": last_close},
            ],
            source_manifest={
                "provider": "outcome-runner-fixture",
                "source_id": "outcome-runner-fixture",
                "capabilities": ["price", "contract_calendar"],
            },
            license_tags=[],
            content_hash=("a" if is_entry else "b") * 64,
        )


async def _seed_mature_prediction() -> str:
    async with async_session_maker() as db:
        user = User(
            username="asset_outcome_runner_user",
            email="asset-outcome-runner@example.test",
            hashed_password="hash",
        )
        db.add_all(
            [
                user,
                AssetDataSourceRegistry(
                    source_id="outcome-runner-fixture",
                    asset_types=["futures"],
                    jurisdictions=["GLOBAL"],
                    license_status="APPROVED",
                    allowed_uses=["RESEARCH_ONLY"],
                    redistribution_policy="NO_REDISTRIBUTION",
                    derived_data_policy="ALLOWED",
                    retention_policy="research-v1",
                    effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                    freshness_sla={},
                    enabled=True,
                ),
            ]
        )
        await db.flush()
        service = AssetResearchOrchestrator(db, data_adapter=_FuturesData())
        await service.persist_identity(_identity())
        await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="futures",
                canonical_id="futures:CFFEX:IF2609:CNY",
            ),
            cutoff_at=_ENTRY_CUTOFF,
        )
        prediction = (
            await db.execute(select(AssetSignalPrediction).where(AssetSignalPrediction.user_id == user.id))
        ).scalar_one()
        outcomes = list(
            (
                await db.execute(
                    select(AssetSignalOutcome).where(
                        AssetSignalOutcome.prediction_id == prediction.id
                    )
                )
            ).scalars()
        )
        for outcome in outcomes:
            outcome.maturity_at = _EVALUATION_CUTOFF
        await db.commit()
        return prediction.id


def _runner(data: _FuturesData) -> AssetResearchOutcomeRunner:
    return AssetResearchOutcomeRunner(
        session_maker=async_session_maker,
        orchestrator_factory=lambda db: AssetResearchOrchestrator(db, data_adapter=data),
        lease_seconds=120,
        max_batch=10,
    )


@pytest.mark.asyncio
async def test_concurrent_outcome_workers_lease_one_prediction_once() -> None:
    prediction_id = await _seed_mature_prediction()
    first = _runner(_FuturesData())
    second = _runner(_FuturesData())

    first_claim, second_claim = await asyncio.gather(
        first.claim_due(now=_EVALUATION_CUTOFF),
        second.claim_due(now=_EVALUATION_CUTOFF),
    )

    assert len(first_claim) + len(second_claim) == 1
    assert {claim.prediction_id for claim in [*first_claim, *second_claim]} == {prediction_id}


@pytest.mark.asyncio
async def test_outcome_runner_scores_all_mature_heads_from_one_observed_snapshot() -> None:
    prediction_id = await _seed_mature_prediction()
    runner = _runner(_FuturesData())

    assert await runner.run_due(now=_EVALUATION_CUTOFF) == 1
    async with async_session_maker() as db:
        prediction = await db.get(AssetSignalPrediction, prediction_id)
        outcomes = list(
            (
                await db.execute(
                    select(AssetSignalOutcome).where(
                        AssetSignalOutcome.prediction_id == prediction_id
                    )
                )
            ).scalars()
        )
        snapshots = list((await db.execute(select(AssetSourceSnapshot))).scalars())

    assert prediction is not None
    assert prediction.outcome_lease_token is None
    assert prediction.outcome_lease_expires_at is None
    assert prediction.outcome_last_error_code is None
    assert {outcome.status for outcome in outcomes} == {"SCORED"}
    assert len(snapshots) == 2


@pytest.mark.asyncio
async def test_outcome_runner_refreshes_per_asset_mature_head_backlog(monkeypatch) -> None:
    """The worker exposes both its pre-run backlog and the drained value."""
    await _seed_mature_prediction()
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        outcome_scheduler_module,
        "set_asset_research_outcome_backlog",
        lambda **event: events.append(event),
    )

    assert await _runner(_FuturesData()).run_due(now=_EVALUATION_CUTOFF) == 1

    assert events == [
        {"asset_type": "futures", "count": 3},
        {"asset_type": "futures", "count": 0},
    ]


@pytest.mark.asyncio
async def test_outcome_runner_releases_a_failed_attempt_for_a_later_retry() -> None:
    prediction_id = await _seed_mature_prediction()
    data = _FuturesData()
    data.fail = True
    runner = _runner(data)

    assert await runner.run_due(now=_EVALUATION_CUTOFF) == 1
    async with async_session_maker() as db:
        prediction = await db.get(AssetSignalPrediction, prediction_id)
        outcomes = list(
            (
                await db.execute(
                    select(AssetSignalOutcome).where(
                        AssetSignalOutcome.prediction_id == prediction_id
                    )
                )
            ).scalars()
        )

    assert prediction is not None
    assert prediction.outcome_lease_token is None
    assert prediction.outcome_last_error_code == "RuntimeError"
    assert {outcome.status for outcome in outcomes} == {"PENDING"}

    data.fail = False
    assert await runner.run_due(now=_EVALUATION_CUTOFF) == 1
    async with async_session_maker() as db:
        outcomes = list(
            (
                await db.execute(
                    select(AssetSignalOutcome).where(
                        AssetSignalOutcome.prediction_id == prediction_id
                    )
                )
            ).scalars()
        )

    assert {outcome.status for outcome in outcomes} == {"SCORED"}
