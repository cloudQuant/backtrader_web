"""Point-in-time outcome scoring for the daily prediction quality loop."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

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
    OptionIdentityDetails,
    RawAssetSnapshot,
)
from app.services.asset_research.orchestrator import (
    AssetResearchOrchestrationError,
    AssetResearchOrchestrator,
)
from app.services.asset_research.outcomes import AssetOutcomeEvaluator
from app.services.asset_research.plugins.option.pricing import (
    build_option_pricing_input,
    calculate_option_analytics,
)


def _calendar_sessions() -> list[str]:
    """Fixture-supplied CFFEX closes; never infer these from weekdays in code."""
    return [
        (datetime(2026, 8, 2, 16, tzinfo=timezone.utc) + timedelta(days=index)).isoformat()
        for index in range(25)
    ]


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
        metadata_version="fixture-v1",
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            expiry_at="2026-09-18T07:15:00+00:00",
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )


class _InitialFuturesData:
    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        return RawAssetSnapshot(
            identity=identity,
            cutoff_at=cutoff_at,
            retrieved_at=cutoff_at,
            raw_schema_version="fixture-v1",
            raw_fields={
                "snapshot": {"bid": 99.0, "ask": 100.0, "price": 99.5},
                "futures": {
                    "cost_snapshot": {
                        "cost_model_version": "fixture-v1",
                        "total_cost_rate": 0.0,
                    }
                },
                "calendar": {"calendar_id": "CFFEX", "sessions": _calendar_sessions()},
            },
            history_rows=[
                {"date": "2026-07-31", "close": 98.0},
                {"date": "2026-08-01", "close": 102.0},
            ],
            source_manifest={
                "provider": "outcome-fixture",
                "capabilities": ["price", "contract_calendar"],
            },
            license_tags=[],
            content_hash="a" * 64,
        )


class _RollingFuturesData:
    """A deterministic collector that exposes only the relevant vintage per cutoff."""

    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        if cutoff_at.date() <= datetime(2026, 8, 1, tzinfo=timezone.utc).date():
            return await _InitialFuturesData().collect(identity, cutoff_at=cutoff_at)
        return _matured_futures_snapshot()


class _NoUnlicensedOutcomeFetch(_RollingFuturesData):
    """Make an accidental post-revocation source call fail the test immediately."""

    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        if cutoff_at.date() > datetime(2026, 8, 1, tzinfo=timezone.utc).date():
            raise AssertionError("revoked source must be blocked before collection")
        return await super().collect(identity, cutoff_at=cutoff_at)


def _matured_futures_snapshot() -> RawAssetSnapshot:
    return RawAssetSnapshot(
        identity=_identity(),
        cutoff_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
        raw_schema_version="fixture-v1",
        raw_fields={"snapshot": {"bid": 109.0, "ask": 110.0, "price": 109.5}},
        history_rows=[
            {"date": "2026-08-01", "close": 102.0},
            {"date": "2026-08-22", "close": 109.5},
        ],
        source_manifest={
            "provider": "outcome-fixture",
            "license_status": "APPROVED",
            "capabilities": ["price", "contract_calendar"],
        },
        license_tags=["APPROVED"],
        content_hash="b" * 64,
    )


@pytest.mark.asyncio
async def test_empty_scorecard_uses_null_metrics_instead_of_zero_percent() -> None:
    """No generated cohort must remain visibly insufficient rather than statistically neutral."""
    async with async_session_maker() as db:
        summary = await AssetResearchOrchestrator(db).get_signal_summary(
            user_id="missing-user",
            asset_type="futures",
            canonical_id="futures:CFFEX:IF2609:CNY",
        )

    assert summary.generated_count == 0
    assert summary.scorable_count == 0
    assert summary.actioned_success_rate is None
    assert summary.coverage_rate is None
    assert summary.maturity_rate is None
    assert summary.brier_score is None
    assert summary.brier_skill_score is None
    assert summary.average_net_return is None
    assert summary.max_drawdown is None


@pytest.mark.asyncio
async def test_due_primary_outcome_uses_frozen_bid_ask_and_feeds_public_scorecard() -> None:
    """A futures LONG must be scored ask-to-bid, while shadow directions stay private."""
    async with async_session_maker() as db:
        user = User(
            username="outcome_evaluator_user",
            email="outcome-evaluator@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="outcome-fixture",
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
            )
        )
        await db.flush()
        orchestrator = AssetResearchOrchestrator(db, data_adapter=_InitialFuturesData())
        await orchestrator.persist_identity(_identity())
        task = await orchestrator.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="futures",
                canonical_id="futures:CFFEX:IF2609:CNY",
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        prediction = (
            await db.execute(
                select(AssetSignalPrediction).where(AssetSignalPrediction.id.is_not(None))
            )
        ).scalar_one()

        scored = await AssetOutcomeEvaluator(db).score_prediction(
            prediction_id=prediction.id,
            observed_snapshot=_matured_futures_snapshot(),
        )
        await db.flush()
        summary = await orchestrator.get_signal_summary(
            user_id=user.id,
            asset_type="futures",
            canonical_id="futures:CFFEX:IF2609:CNY",
        )
        primary = (
            await db.execute(
                select(AssetSignalOutcome).where(
                    AssetSignalOutcome.prediction_id == prediction.id,
                    AssetSignalOutcome.outcome_kind == "futures.contract_pnl",
                )
            )
        ).scalar_one()

    assert task.status == "SUCCEEDED"
    assert any(outcome.outcome_kind == "futures.contract_pnl" for outcome in scored)
    assert primary.status == "SCORED"
    assert prediction.cost_snapshot_json == {
        "cost_model_version": "fixture-v1",
        "total_cost_rate": 0.0,
    }
    assert float(primary.entry_price) == 100.0
    assert float(primary.exit_price) == 109.0
    assert float(primary.gross_return) == pytest.approx(0.09)
    assert float(primary.net_return) == pytest.approx(0.09)
    assert primary.success_label is True
    assert primary.maturity_at is not None
    assert primary.maturity_at.replace(tzinfo=timezone.utc) == datetime(
        2026, 8, 21, 16, tzinfo=timezone.utc
    )
    assert primary.entry_at is not None
    assert primary.entry_at.replace(tzinfo=timezone.utc) == datetime(
        2026, 8, 1, tzinfo=timezone.utc
    )
    assert primary.exit_at is not None
    assert primary.exit_at.replace(tzinfo=timezone.utc) == datetime(
        2026, 8, 22, tzinfo=timezone.utc
    )
    assert summary.actioned_generated_count == 1
    assert summary.actioned_scorable_count == 1
    assert summary.actioned_success_rate == 1.0
    assert summary.brier_score is not None
    assert summary.average_net_return == pytest.approx(0.09)


@pytest.mark.asyncio
async def test_outcome_evaluator_refuses_a_prediction_with_a_mismatched_entry_cutoff() -> None:
    """Legacy/corrupt entry snapshots cannot be scored under another prediction instant."""
    async with async_session_maker() as db:
        user = User(
            username="outcome-entry-cutoff-user",
            email="outcome-entry-cutoff@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="outcome-fixture",
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
            )
        )
        await db.flush()
        orchestrator = AssetResearchOrchestrator(db, data_adapter=_InitialFuturesData())
        await orchestrator.persist_identity(_identity())
        await orchestrator.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="futures",
                canonical_id="futures:CFFEX:IF2609:CNY",
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        prediction = (await db.execute(select(AssetSignalPrediction))).scalar_one()
        entry_snapshot = await db.get(AssetSourceSnapshot, prediction.snapshot_id)
        assert entry_snapshot is not None
        entry_snapshot.cutoff_at = datetime(2026, 8, 2, tzinfo=timezone.utc)
        await db.flush()

        outcomes = await AssetOutcomeEvaluator(db).score_prediction(
            prediction_id=prediction.id,
            observed_snapshot=_matured_futures_snapshot(),
        )

    assert outcomes
    assert all(outcome.status == "UNSCORABLE" for outcome in outcomes)
    assert all(
        "COMMON.OUTCOME_ENTRY_CUTOFF_MISMATCH" in outcome.reason_codes_json for outcome in outcomes
    )


@pytest.mark.asyncio
async def test_scorecard_partitions_predictions_by_primary_head_spec_hash() -> None:
    """A changed target definition must produce a separate scorecard cohort."""
    async with async_session_maker() as db:
        user = User(
            username="outcome_cohort_user",
            email="outcome-cohort@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="outcome-fixture",
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
            )
        )
        await db.flush()
        orchestrator = AssetResearchOrchestrator(db, data_adapter=_InitialFuturesData())
        await orchestrator.persist_identity(_identity())
        for cutoff_at in (
            datetime(2026, 8, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 2, tzinfo=timezone.utc),
        ):
            await orchestrator.create_and_run(
                user_id=user.id,
                request=AssetAnalysisCreateRequest(
                    asset_type="futures",
                    canonical_id="futures:CFFEX:IF2609:CNY",
                ),
                cutoff_at=cutoff_at,
            )

        predictions = list(
            (
                await db.execute(
                    select(AssetSignalPrediction)
                    .where(AssetSignalPrediction.user_id == user.id)
                    .order_by(AssetSignalPrediction.as_of_at)
                )
            ).scalars()
        )
        primary_code = str(predictions[0].candidate_decision_json["primary_head_code"])
        old_hash = "a" * 64
        new_hash = "b" * 64
        for prediction, head_hash in zip(predictions, (old_hash, new_hash), strict=True):
            candidate = deepcopy(prediction.candidate_decision_json)
            for head in candidate["prediction_heads"]:
                if head["head_code"] == primary_code:
                    head["head_spec_hash"] = head_hash
            prediction.candidate_decision_json = candidate
            primary_outcome = (
                await db.execute(
                    select(AssetSignalOutcome).where(
                        AssetSignalOutcome.prediction_id == prediction.id,
                        AssetSignalOutcome.outcome_kind == primary_code,
                    )
                )
            ).scalar_one()
            primary_outcome.head_spec_hash = head_hash
            primary_outcome.status = "SCORED"
            primary_outcome.success_label = prediction is predictions[-1]
            primary_outcome.net_return = 0.01

        await db.flush()
        default_summary = await orchestrator.get_signal_summary(
            user_id=user.id,
            asset_type="futures",
            canonical_id="futures:CFFEX:IF2609:CNY",
        )
        old_summary = await orchestrator.get_signal_summary(
            user_id=user.id,
            asset_type="futures",
            canonical_id="futures:CFFEX:IF2609:CNY",
            head_spec_hash=old_hash,
        )
        with pytest.raises(AssetResearchOrchestrationError, match="SCORECARD_COHORT_NOT_FOUND"):
            await orchestrator.get_signal_summary(
                user_id=user.id,
                asset_type="futures",
                canonical_id="futures:CFFEX:IF2609:CNY",
                head_spec_hash="c" * 64,
            )

    assert default_summary.head_spec_hash is None
    assert default_summary.available_head_spec_hashes == [new_hash, old_hash]
    assert default_summary.cohort_selection_required is True
    assert default_summary.total_generated_count == 2
    assert default_summary.generated_count == 0
    assert default_summary.excluded_prediction_count == 2
    assert old_summary.head_spec_hash == old_hash
    assert old_summary.cohort_selection_required is False
    assert old_summary.generated_count == 1
    assert old_summary.excluded_prediction_count == 1


@pytest.mark.asyncio
async def test_due_outcome_worker_collects_a_new_licensed_snapshot_once_per_prediction() -> None:
    """Daily scoring must retain its own observed vintage instead of mutating the entry snapshot."""
    async with async_session_maker() as db:
        user = User(
            username="outcome_worker_user",
            email="outcome-worker@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="outcome-fixture",
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
            )
        )
        await db.flush()
        service = AssetResearchOrchestrator(db, data_adapter=_RollingFuturesData())
        await service.persist_identity(_identity())
        task = await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="futures", canonical_id="futures:CFFEX:IF2609:CNY"
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )

        scored_count = await service.evaluate_due_outcomes(
            cutoff_at=datetime(2026, 8, 22, tzinfo=timezone.utc)
        )
        snapshots = list((await db.execute(select(AssetSourceSnapshot))).scalars())
        outcomes = list(
            (
                await db.execute(
                    select(AssetSignalOutcome).where(AssetSignalOutcome.status == "SCORED")
                )
            ).scalars()
        )

    assert task.status == "SUCCEEDED"
    assert scored_count == 3
    assert len(snapshots) == 2
    assert len(outcomes) == 3
    assert {outcome.outcome_kind for outcome in outcomes} == {
        "futures.contract_pnl",
        "futures.roll_aware_pnl",
        "futures.close_avoided_loss",
    }


@pytest.mark.asyncio
async def test_outcome_worker_never_scores_from_a_source_that_loses_its_license() -> None:
    """A later outcome vintage needs its own permission; entry permission is insufficient."""
    async with async_session_maker() as db:
        user = User(
            username="outcome_license_user",
            email="outcome-license@example.test",
            hashed_password="hash",
        )
        registry = AssetDataSourceRegistry(
            source_id="outcome-fixture",
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
        )
        db.add_all([user, registry])
        await db.flush()
        service = AssetResearchOrchestrator(db, data_adapter=_NoUnlicensedOutcomeFetch())
        await service.persist_identity(_identity())
        await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="futures", canonical_id="futures:CFFEX:IF2609:CNY"
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        registry.enabled = False
        await db.flush()

        scored_count = await service.evaluate_due_outcomes(
            cutoff_at=datetime(2026, 8, 22, tzinfo=timezone.utc)
        )
        outcomes = list((await db.execute(select(AssetSignalOutcome))).scalars())

    assert scored_count == 0
    assert all(outcome.status == "UNSCORABLE" for outcome in outcomes)
    assert all("COMMON.SOURCE_LICENSE_BLOCKED" in outcome.reason_codes_json for outcome in outcomes)


def _option_identity_for_outcome() -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="option",
        identity_level="CONTRACT",
        canonical_id="option:fixture:CALL:2027-08-01:100:USD",
        display_symbol="OPT-C-100",
        name="fixture call",
        venue="FIXTURE",
        currency="USD",
        timezone="UTC",
        identifier_type="FIXTURE",
        identifier_value="OPT-C-100",
        product_type="OPTION",
        metadata_version="fixture-v1",
        details=OptionIdentityDetails(
            option_contract_id="OPT-C-100",
            exchange="FIXTURE",
            underlying_instrument_id="fixture-underlying",
            underlying_contract_id="fixture-underlying",
            expiry_at=datetime(2027, 8, 1, tzinfo=timezone.utc),
            last_trade_at=datetime(2027, 8, 1, tzinfo=timezone.utc),
            strike=Decimal("100"),
            option_right="CALL",
            exercise_style="EUROPEAN",
            contract_multiplier=Decimal("100"),
            settlement_type="CASH",
            deliverable="100 cash units",
            quote_unit="USD_PER_UNIT",
            tick_size=Decimal("0.01"),
            trading_calendar_id="FIXTURE",
            automatic_exercise_rule="EXERCISE_IF_ITM",
            position_limit_rule="FIXTURE_LIMIT_V1",
            margin_rule_version="FIXTURE_MARGIN_V1",
        ),
    )


def _option_fields_for_outcome(
    *,
    identity: InstrumentIdentity,
    cutoff_at: datetime,
    volatility: float,
    provider_iv: float,
    underlying_price: float = 100.0,
) -> dict[str, object]:
    option = {
        "underlying_price": underlying_price,
        "underlying_kind": "SPOT",
        "risk_free_rate": 0.05,
        "dividend_yield": 0.0,
        "implied_volatility": provider_iv,
    }
    pricing_input, reason = build_option_pricing_input(
        identity=identity,
        cutoff_at=cutoff_at,
        raw_fields={"option": option},
    )
    assert reason is None
    assert pricing_input is not None
    analytics = calculate_option_analytics(replace(pricing_input, volatility=volatility))
    assert analytics.theoretical_value is not None
    return {
        "option": option,
        "snapshot": {
            "bid": analytics.theoretical_value - 0.01,
            "ask": analytics.theoretical_value + 0.01,
        },
    }


def _option_cost_snapshot() -> dict[str, float | str]:
    return {
        "cost_model_version": "fixture-v1",
        "commission_rate": 0.002,
        "exchange_fee_rate": 0.001,
        "entry_slippage_rate": 0.002,
        "exit_slippage_rate": 0.002,
        "funding_cost_rate": 0.001,
        "exercise_settlement_cost_rate": 0.001,
        "other_cost_rate": 0.001,
    }


def test_option_direction_and_iv_heads_use_their_own_observables() -> None:
    """IV labels must be re-solved from exact-contract bid/ask, never provider IV."""
    identity = _option_identity_for_outcome()
    entry_cutoff = datetime(2026, 8, 1, tzinfo=timezone.utc)
    observed_cutoff = datetime(2026, 8, 15, tzinfo=timezone.utc)
    entry = _option_fields_for_outcome(
        identity=identity,
        cutoff_at=entry_cutoff,
        volatility=0.20,
        provider_iv=0.90,
    )
    observed = _option_fields_for_outcome(
        identity=identity,
        cutoff_at=observed_cutoff,
        volatility=0.30,
        provider_iv=0.01,
        underlying_price=108.0,
    )

    direction = AssetOutcomeEvaluator._score_option_head(
        outcome_kind="option.underlying_direction",
        probabilities={"BULLISH": 0.58, "BEARISH": 0.18, "NEUTRAL": 0.24},
        entry_fields=entry,
        observed_fields=observed,
    )
    volatility = AssetOutcomeEvaluator._score_option_head(
        outcome_kind="option.iv_direction",
        probabilities={"VOL_UP": 0.54, "VOL_DOWN": 0.18, "NEUTRAL": 0.28},
        entry_fields=entry,
        observed_fields=observed,
        entry_identity=identity,
        entry_cutoff_at=entry_cutoff,
        observed_identity=identity,
        observed_cutoff_at=observed_cutoff,
    )

    assert direction is not None
    assert direction.success_label is True
    assert direction.metrics is not None
    assert direction.metrics["observed_label"] == "BULLISH"
    assert direction.entry_price_basis == "underlying_price"
    assert volatility is not None
    assert volatility.success_label is True
    assert volatility.metrics is not None
    assert volatility.metrics["observed_label"] == "VOL_UP"
    assert volatility.entry_price_basis == "iv_ask_solver"
    assert volatility.exit_price_basis == "iv_bid_solver"


def test_option_iv_head_refuses_an_invalid_exact_contract_bid_ask_solver_input() -> None:
    """An IV outcome may not fall back to a supplied IV or an executable mid."""
    identity = _option_identity_for_outcome()
    entry_cutoff = datetime(2026, 8, 1, tzinfo=timezone.utc)
    observed_cutoff = datetime(2026, 8, 15, tzinfo=timezone.utc)
    entry = _option_fields_for_outcome(
        identity=identity,
        cutoff_at=entry_cutoff,
        volatility=0.20,
        provider_iv=0.20,
    )
    observed = _option_fields_for_outcome(
        identity=identity,
        cutoff_at=observed_cutoff,
        volatility=0.30,
        provider_iv=0.30,
    )
    observed["snapshot"] = {"bid": 120.0, "ask": 121.0}

    result = AssetOutcomeEvaluator._score_option_head(
        outcome_kind="option.iv_direction",
        probabilities={"VOL_UP": 0.54, "VOL_DOWN": 0.18, "NEUTRAL": 0.28},
        entry_fields=entry,
        observed_fields=observed,
        entry_identity=identity,
        entry_cutoff_at=entry_cutoff,
        observed_identity=identity,
        observed_cutoff_at=observed_cutoff,
    )

    assert result is not None
    assert result.status == "UNSCORABLE"
    assert result.reason_codes == ["OPTION.OUTCOME_IV_SOLVER_FAILED"]


def test_option_iv_head_refuses_an_observation_after_the_last_trade_time() -> None:
    identity = _option_identity_for_outcome().model_copy(
        update={
            "details": _option_identity_for_outcome().details.model_copy(
                update={"last_trade_at": datetime(2026, 8, 10, tzinfo=timezone.utc)}
            )
        }
    )
    entry_cutoff = datetime(2026, 8, 1, tzinfo=timezone.utc)
    observed_cutoff = datetime(2026, 8, 15, tzinfo=timezone.utc)
    result = AssetOutcomeEvaluator._score_option_head(
        outcome_kind="option.iv_direction",
        probabilities={"VOL_UP": 0.54, "VOL_DOWN": 0.18, "NEUTRAL": 0.28},
        entry_fields=_option_fields_for_outcome(
            identity=identity,
            cutoff_at=entry_cutoff,
            volatility=0.20,
            provider_iv=0.20,
        ),
        observed_fields=_option_fields_for_outcome(
            identity=identity,
            cutoff_at=observed_cutoff,
            volatility=0.30,
            provider_iv=0.30,
        ),
        entry_identity=identity,
        entry_cutoff_at=entry_cutoff,
        observed_identity=identity,
        observed_cutoff_at=observed_cutoff,
    )

    assert result is not None
    assert result.status == "UNSCORABLE"
    assert result.reason_codes == ["OPTION.OUTCOME_IV_CONTRACT_NOT_TRADABLE"]


def test_option_iv_head_refuses_same_canonical_id_with_changed_contract_terms() -> None:
    """A forged snapshot cannot substitute a different strike under the same identity key."""
    entry_identity = _option_identity_for_outcome()
    observed_identity = entry_identity.model_copy(
        update={"details": entry_identity.details.model_copy(update={"strike": Decimal("101")})}
    )
    entry_cutoff = datetime(2026, 8, 1, tzinfo=timezone.utc)
    observed_cutoff = datetime(2026, 8, 15, tzinfo=timezone.utc)

    result = AssetOutcomeEvaluator._score_option_head(
        outcome_kind="option.iv_direction",
        probabilities={"VOL_UP": 0.54, "VOL_DOWN": 0.18, "NEUTRAL": 0.28},
        entry_fields=_option_fields_for_outcome(
            identity=entry_identity,
            cutoff_at=entry_cutoff,
            volatility=0.20,
            provider_iv=0.20,
        ),
        observed_fields=_option_fields_for_outcome(
            identity=observed_identity,
            cutoff_at=observed_cutoff,
            volatility=0.30,
            provider_iv=0.30,
        ),
        entry_identity=entry_identity,
        entry_cutoff_at=entry_cutoff,
        observed_identity=observed_identity,
        observed_cutoff_at=observed_cutoff,
    )

    assert result is not None
    assert result.status == "UNSCORABLE"
    assert result.reason_codes == ["COMMON.OUTCOME_IDENTITY_MISMATCH"]


def test_option_exact_contract_profit_uses_ask_entry_bid_exit_and_frozen_costs() -> None:
    identity = _option_identity_for_outcome()
    entry_cutoff = datetime(2026, 8, 1, tzinfo=timezone.utc)
    observed_cutoff = datetime(2026, 8, 15, tzinfo=timezone.utc)
    result = AssetOutcomeEvaluator._score_option_head(
        outcome_kind="option.exact_contract_net_profit",
        probabilities={"PROFIT": 0.60, "LOSS": 0.40},
        entry_fields={"snapshot": {"ask": 10.0}},
        observed_fields={"snapshot": {"bid": 11.0}},
        entry_identity=identity,
        entry_cutoff_at=entry_cutoff,
        observed_identity=identity,
        observed_cutoff_at=observed_cutoff,
        cost_snapshot=_option_cost_snapshot(),
    )

    assert result is not None
    assert result.status == "SCORED"
    assert result.entry_price == Decimal("10.0")
    assert result.exit_price == Decimal("11.0")
    assert result.entry_price_basis == "ask"
    assert result.exit_price_basis == "bid"
    assert result.gross_return == Decimal("0.1")
    assert result.net_return == Decimal("0.091")
    assert result.success_label is True
    assert result.metrics is not None
    assert result.metrics["observed_label"] == "PROFIT"
    assert result.metrics["gross_pnl"] == pytest.approx(100.0)
    assert result.metrics["total_cost_amount"] == pytest.approx(9.0)
    assert result.metrics["net_pnl"] == pytest.approx(91.0)
    assert result.metrics["contract_multiplier"] == pytest.approx(100.0)


def test_option_contract_profit_refuses_same_canonical_id_with_changed_contract_terms() -> None:
    """Contract P&L must not cross-score a different contract sharing a stale key."""
    entry_identity = _option_identity_for_outcome()
    observed_identity = entry_identity.model_copy(
        update={"details": entry_identity.details.model_copy(update={"strike": Decimal("101")})}
    )

    result = AssetOutcomeEvaluator._score_option_head(
        outcome_kind="option.exact_contract_net_profit",
        probabilities={"PROFIT": 0.60, "LOSS": 0.40},
        entry_fields={"snapshot": {"ask": 10.0}},
        observed_fields={"snapshot": {"bid": 11.0}},
        entry_identity=entry_identity,
        entry_cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        observed_identity=observed_identity,
        observed_cutoff_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        cost_snapshot=_option_cost_snapshot(),
    )

    assert result is not None
    assert result.status == "UNSCORABLE"
    assert result.reason_codes == ["COMMON.OUTCOME_IDENTITY_MISMATCH"]


def test_option_exact_contract_profit_uses_final_settlement_at_expiry() -> None:
    identity = _option_identity_for_outcome()
    entry_cutoff = datetime(2026, 8, 1, tzinfo=timezone.utc)
    expiry = identity.details.expiry_at
    result = AssetOutcomeEvaluator._score_option_head(
        outcome_kind="option.exact_contract_net_profit",
        probabilities={"PROFIT": 0.40, "LOSS": 0.60},
        entry_fields={"snapshot": {"ask": 10.0}},
        observed_fields={
            "option": {
                "official_settlement": 0.0,
                "official_settlement_final": True,
                "settlement_rule_version": "fixture-v1",
            }
        },
        entry_identity=identity,
        entry_cutoff_at=entry_cutoff,
        observed_identity=identity,
        observed_cutoff_at=expiry,
        cost_snapshot=_option_cost_snapshot(),
    )

    assert result is not None
    assert result.status == "SCORED"
    assert result.exit_price == Decimal("0.0")
    assert result.exit_price_basis == "official_settlement"
    assert result.net_return == Decimal("-1.01")
    assert result.maturity_reason == "EXPIRY"
    assert result.success_label is True
    assert result.metrics is not None
    assert result.metrics["settlement_type"] == "CASH"
    assert result.metrics["deliverable"] == "100 cash units"
    assert result.metrics["automatic_exercise_rule"] == "EXERCISE_IF_ITM"


def test_option_exact_contract_profit_refuses_to_replace_expiry_settlement_with_a_bid() -> None:
    identity = _option_identity_for_outcome()
    entry_cutoff = datetime(2026, 8, 1, tzinfo=timezone.utc)
    result = AssetOutcomeEvaluator._score_option_head(
        outcome_kind="option.exact_contract_net_profit",
        probabilities={"PROFIT": 0.40, "LOSS": 0.60},
        entry_fields={"snapshot": {"ask": 10.0}},
        observed_fields={"snapshot": {"bid": 11.0}},
        entry_identity=identity,
        entry_cutoff_at=entry_cutoff,
        observed_identity=identity,
        observed_cutoff_at=identity.details.expiry_at,
        cost_snapshot=_option_cost_snapshot(),
    )

    assert result is not None
    assert result.status == "UNSCORABLE"
    assert result.reason_codes == ["OPTION.OUTCOME_SETTLEMENT_MISSING"]


def test_option_exact_contract_profit_refuses_a_bid_after_last_trade_before_expiry() -> None:
    identity = _option_identity_for_outcome().model_copy(
        update={
            "details": _option_identity_for_outcome().details.model_copy(
                update={"last_trade_at": datetime(2027, 7, 15, tzinfo=timezone.utc)}
            )
        }
    )
    result = AssetOutcomeEvaluator._score_option_head(
        outcome_kind="option.exact_contract_net_profit",
        probabilities={"PROFIT": 0.40, "LOSS": 0.60},
        entry_fields={"snapshot": {"ask": 10.0}},
        observed_fields={"snapshot": {"bid": 11.0}},
        entry_identity=identity,
        entry_cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        observed_identity=identity,
        observed_cutoff_at=datetime(2027, 7, 20, tzinfo=timezone.utc),
        cost_snapshot=_option_cost_snapshot(),
    )

    assert result is not None
    assert result.status == "UNSCORABLE"
    assert result.reason_codes == ["OPTION.OUTCOME_SETTLEMENT_MISSING"]


def test_option_exact_contract_profit_refuses_to_assume_missing_costs_are_zero() -> None:
    identity = _option_identity_for_outcome()
    result = AssetOutcomeEvaluator._score_option_head(
        outcome_kind="option.exact_contract_net_profit",
        probabilities={"PROFIT": 0.60, "LOSS": 0.40},
        entry_fields={"snapshot": {"ask": 10.0}},
        observed_fields={"snapshot": {"bid": 11.0}},
        entry_identity=identity,
        entry_cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        observed_identity=identity,
        observed_cutoff_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        cost_snapshot={},
    )

    assert result is not None
    assert result.status == "UNSCORABLE"
    assert result.reason_codes == ["OPTION.COST_SNAPSHOT_INCOMPLETE"]


@pytest.mark.parametrize(
    ("asset_type", "outcome_kind"),
    [
        ("bond", "bond.executable_total_return"),
        ("crypto", "crypto.spot_pnl"),
    ],
)
def test_executable_bond_and_crypto_heads_use_bid_ask_sides(
    asset_type: str, outcome_kind: str
) -> None:
    quotes = AssetOutcomeEvaluator._select_quotes(
        asset_type=asset_type,
        outcome_kind=outcome_kind,
        direction="LONG",
        entry_fields={"snapshot": {"bid": 99.0, "ask": 100.0, "price": 99.5}},
        observed_fields={"snapshot": {"bid": 109.0, "ask": 110.0, "price": 109.5}},
    )

    assert quotes is not None
    entry, entry_basis, exit_price, exit_basis = quotes
    assert entry == 100
    assert exit_price == 109
    assert (entry_basis, exit_basis) == ("ask", "bid")


def test_standard_executable_outcome_refuses_to_assume_a_missing_cost_snapshot_is_zero() -> None:
    result = AssetOutcomeEvaluator._score_standard_execution(
        asset_type="futures",
        outcome_kind="futures.contract_pnl",
        direction="LONG",
        probabilities={"LONG": 0.7, "SHORT": 0.2, "NEUTRAL": 0.1},
        entry_fields={"snapshot": {"bid": 99.0, "ask": 100.0}},
        observed_fields={"snapshot": {"bid": 109.0, "ask": 110.0}},
        cost_snapshot={},
        primary_for_promotion=True,
    )

    assert result.status == "UNSCORABLE"
    assert result.reason_codes == ["COMMON.OUTCOME_COST_SNAPSHOT_MISSING"]
