"""End-to-end persistence contract for one deterministic multi-asset research run."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.asset_research import (
    AssetDataSourceRegistry,
    AssetSignalOutcome,
    AssetSignalPrediction,
    AssetSignalRun,
    AssetSourceSnapshot,
)
from app.models.user import User
from app.schemas.asset_research import (
    AssetAnalysisCreateRequest,
    FuturesIdentityDetails,
    FxIdentityDetails,
    InstrumentIdentity,
    OptionIdentityDetails,
    PositionContextCreateRequest,
    RawAssetSnapshot,
)
from app.services.asset_research import orchestrator as orchestrator_module
from app.services.asset_research.compliance import AssetResearchCompliancePolicy
from app.services.asset_research.orchestrator import AssetResearchOrchestrator
from app.services.asset_research.plugins.option.pricing import (
    OptionPricingInput,
    calculate_option_analytics,
)


class _ApprovedFuturesData:
    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        return RawAssetSnapshot(
            identity=identity,
            cutoff_at=cutoff_at,
            retrieved_at=cutoff_at,
            raw_schema_version="fixture-v1",
            raw_fields={
                "snapshot": {"price": 110, "bid": 109.9, "ask": 110.1},
                "calendar": {
                    "calendar_id": "CFFEX",
                    "sessions": [
                        (
                            datetime(2026, 8, 2, 16, tzinfo=timezone.utc) + timedelta(days=index)
                        ).isoformat()
                        for index in range(25)
                    ],
                },
            },
            history_rows=[
                {"date": "2026-07-31", "close": 100},
                {"date": "2026-08-01", "close": 110},
            ],
            source_manifest={
                "provider": "fixture-futures",
                "license_status": "APPROVED",
                "capabilities": ["price", "contract_calendar"],
            },
            license_tags=["APPROVED"],
            content_hash="b" * 64,
        )


class _SecretBearingFuturesData(_ApprovedFuturesData):
    """Bypass the standard adapter to prove persistence has its own redaction boundary."""

    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        snapshot = await super().collect(identity, cutoff_at=cutoff_at)
        return snapshot.model_copy(
            update={
                "raw_fields": {
                    **snapshot.raw_fields,
                    "snapshot": {
                        **snapshot.raw_fields["snapshot"],
                        "api_key": "injected-snapshot-secret",
                    },
                },
                "history_rows": [
                    *snapshot.history_rows,
                    {
                        "date": "2026-08-01",
                        "close": 110,
                        "password": "injected-history-secret",
                    },
                ],
                "source_manifest": {
                    **snapshot.source_manifest,
                    "authorization": "Bearer injected-manifest-secret",
                },
            }
        )


class _ApprovedFxData:
    """One licensed executable FX snapshot for the public compliance gate."""

    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        return RawAssetSnapshot(
            identity=identity,
            cutoff_at=cutoff_at,
            retrieved_at=cutoff_at,
            raw_schema_version="fixture-v1",
            raw_fields={
                "snapshot": {"price": 1.1020, "bid": 1.1019, "ask": 1.1021},
                "fx": {"completed_bar": True, "price_convention": "EUR_PER_USD"},
                "calendar": {
                    "calendar_id": "FX",
                    "sessions": [
                        (cutoff_at + timedelta(days=offset)).isoformat() for offset in range(1, 25)
                    ],
                },
            },
            history_rows=[
                {"date": "2026-07-31", "close": 1.1000},
                {"date": "2026-08-01", "close": 1.1020},
            ],
            source_manifest={
                "provider": "fixture-fx",
                "license_status": "APPROVED",
                "capabilities": ["price", "calendar", "price_convention"],
            },
            license_tags=["APPROVED"],
            content_hash="d" * 64,
        )


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


def _fx_identity() -> InstrumentIdentity:
    """Return one exact venue-bound FX spot product for compliance coverage."""
    return InstrumentIdentity(
        asset_type="fx",
        identity_level="PRODUCT",
        canonical_id="fx:FIXTURE:EURUSD:USD",
        display_symbol="EUR/USD",
        name="Fixture EUR/USD spot",
        venue="FIXTURE",
        currency="USD",
        timezone="UTC",
        identifier_type="CURRENCY_PAIR",
        identifier_value="EUR/USD",
        product_type="SPOT",
        metadata_version="fixture-v1",
        details=FxIdentityDetails(
            base_currency="EUR",
            quote_currency="USD",
            settlement_type="SPOT",
            settlement_currency="USD",
            calendar_id="FX",
            price_convention="EUR_PER_USD",
        ),
    )


def _option_identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="option",
        identity_level="CONTRACT",
        canonical_id="option:FIXTURE:OPT-C-100:CALL:2027-08-01:100:USD",
        display_symbol="OPT-C-100",
        name="Fixture call 100",
        venue="FIXTURE",
        currency="USD",
        timezone="UTC",
        identifier_type="OPTION_CONTRACT_CODE",
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


def _approved_source(*, asset_type: str, source_id: str) -> AssetDataSourceRegistry:
    """Return a source-registry fixture that allows one asset test to run."""
    return AssetDataSourceRegistry(
        source_id=source_id,
        asset_types=[asset_type],
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


class _ApprovedOptionData:
    """One fully specified point-in-time option chain for persistence testing."""

    @staticmethod
    def _chain(cutoff_at: datetime) -> list[dict[str, float | str]]:
        rows: list[dict[str, float | str]] = []
        for expiry_index, expiry_at in enumerate(
            (
                datetime(2027, 8, 1, tzinfo=timezone.utc),
                datetime(2027, 11, 1, tzinfo=timezone.utc),
            )
        ):
            time_to_expiry = (expiry_at - cutoff_at).total_seconds() / (365 * 24 * 60 * 60)
            for strike in (90.0, 100.0, 110.0):
                for right in ("CALL", "PUT"):
                    analytics = calculate_option_analytics(
                        OptionPricingInput(
                            model="BSM",
                            option_right=right,
                            underlying_price=100.0,
                            strike=strike,
                            time_to_expiry_years=time_to_expiry,
                            risk_free_rate=0.05,
                            dividend_yield=0.0,
                            volatility=0.20 + 0.03 * expiry_index,
                        )
                    )
                    assert analytics.theoretical_value is not None
                    rows.append(
                        {
                            "expiry_at": expiry_at.isoformat(),
                            "strike": strike,
                            "option_right": right,
                            "bid": analytics.theoretical_value * 0.995,
                            "ask": analytics.theoretical_value * 1.005,
                            "bid_size": 100.0,
                            "ask_size": 100.0,
                            "volume": 500.0,
                            "open_interest": 1000.0,
                            "quote_at": cutoff_at.isoformat(),
                        }
                    )
        return rows

    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        chain = self._chain(cutoff_at)
        target = next(
            row
            for row in chain
            if row["expiry_at"] == identity.details.expiry_at.isoformat()
            and row["strike"] == float(identity.details.strike)
            and row["option_right"] == identity.details.option_right
        )
        return RawAssetSnapshot(
            identity=identity,
            cutoff_at=cutoff_at,
            retrieved_at=cutoff_at,
            raw_schema_version="fixture-v1",
            raw_fields={
                "snapshot": {
                    "price": (float(target["bid"]) + float(target["ask"])) / 2,
                    "bid": target["bid"],
                    "ask": target["ask"],
                    "quote_at": cutoff_at.isoformat(),
                },
                "option": {
                    "contract_terms": "fixture option master v1",
                    "underlying_price": 100.0,
                    "underlying_kind": "SPOT",
                    "risk_free_rate": 0.05,
                    "dividend_yield": 0.0,
                    "underlying_quote_at": cutoff_at.isoformat(),
                    "chain": chain,
                    "chain_quality_policy": {
                        "version": "fixture-v1",
                        "min_expiries": 2,
                        "min_strikes_per_expiry": 3,
                        "min_calendar_pairs": 2,
                        "max_quote_age_seconds": 60.0,
                        "max_underlying_lag_seconds": 60.0,
                        "max_relative_spread": 0.10,
                        "min_visible_size": 1.0,
                        "min_volume": 1.0,
                        "min_open_interest": 1.0,
                        "parity_tolerance": 0.02,
                        "static_arbitrage_tolerance": 1e-8,
                    },
                    "cost_snapshot": {
                        "cost_model_version": "fixture-v1",
                        "commission_rate": 0.002,
                        "exchange_fee_rate": 0.001,
                        "entry_slippage_rate": 0.002,
                        "exit_slippage_rate": 0.002,
                        "funding_cost_rate": 0.001,
                        "exercise_settlement_cost_rate": 0.001,
                        "other_cost_rate": 0.001,
                    },
                },
                "calendar": {
                    "calendar_id": "FIXTURE",
                    "sessions": [
                        (cutoff_at + timedelta(days=offset)).isoformat() for offset in range(1, 26)
                    ],
                },
            },
            history_rows=[
                {"date": "2026-07-31", "close": float(target["bid"])},
                {"date": "2026-08-01", "close": float(target["ask"])},
            ],
            source_manifest={
                "provider": "fixture-option",
                "license_status": "APPROVED",
                "capabilities": ["price", "option_chain", "contract_terms"],
            },
            license_tags=["APPROVED"],
            content_hash="c" * 64,
        )


class _SubstitutedOptionData(_ApprovedOptionData):
    """Simulate a provider returning another strike under a stale canonical key."""

    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        snapshot = await super().collect(identity, cutoff_at=cutoff_at)
        substituted_identity = identity.model_copy(
            update={"details": identity.details.model_copy(update={"strike": Decimal("101")})}
        )
        return snapshot.model_copy(update={"identity": substituted_identity})


class _MismatchedOptionCutoffData(_ApprovedOptionData):
    """Simulate a provider returning an otherwise valid snapshot from another instant."""

    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        snapshot = await super().collect(identity, cutoff_at=cutoff_at)
        return snapshot.model_copy(update={"cutoff_at": cutoff_at + timedelta(minutes=1)})


class _SubstitutedOptionSourcePolicy:
    """Simulate an unauthorized source-policy rewrite after provider collection."""

    async def authorize(self, snapshot: RawAssetSnapshot) -> RawAssetSnapshot:
        substituted_identity = snapshot.identity.model_copy(
            update={
                "details": snapshot.identity.details.model_copy(update={"strike": Decimal("101")})
            }
        )
        return snapshot.model_copy(update={"identity": substituted_identity})


class _SubstitutedOptionCutoffSourcePolicy:
    """Simulate an unauthorized source-policy rewrite of the analysis instant."""

    async def authorize(self, snapshot: RawAssetSnapshot) -> RawAssetSnapshot:
        return snapshot.model_copy(update={"cutoff_at": snapshot.cutoff_at + timedelta(minutes=1)})


@pytest.mark.asyncio
async def test_orchestrator_persists_raw_then_hides_unpromoted_candidate_from_public_result() -> (
    None
):
    async with async_session_maker() as db:
        user = User(
            username="asset_research_user", email="asset@example.test", hashed_password="hash"
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="fixture-futures",
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
        service = AssetResearchOrchestrator(db, data_adapter=_ApprovedFuturesData())
        await service.persist_identity(_identity())
        await db.commit()

        task = await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="futures",
                canonical_id="futures:CFFEX:IF2609:CNY",
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        await db.commit()

        result = await service.get_result(user_id=user.id, task_id=task.id)
        prediction = (await db.execute(select(AssetSignalPrediction))).scalar_one()
        outcomes = list((await db.execute(select(AssetSignalOutcome))).scalars())
        snapshots = list((await db.execute(select(AssetSourceSnapshot))).scalars())

    assert task.status == "SUCCEEDED"
    assert len(snapshots) == 1
    assert prediction.candidate_decision_json["normalized_direction"] == "LONG"
    assert prediction.candidate_decision_json["prediction_heads"]
    assert prediction.head_spec_set_hash != ""
    assert {outcome.outcome_kind for outcome in outcomes} == {
        "futures.contract_pnl",
        "futures.roll_aware_pnl",
        "futures.close_avoided_loss",
    }
    candidate_heads = {
        head["head_spec_hash"] for head in prediction.candidate_decision_json["prediction_heads"]
    }
    assert {outcome.head_spec_hash for outcome in outcomes}.issubset(candidate_heads)
    assert all(outcome.maturity_at is not None for outcome in outcomes)
    # Historical replays can complete after their frozen horizon. Maturity is
    # anchored to the prediction cutoff, not to the wall-clock completion time.
    assert all(
        outcome.maturity_at is not None and outcome.maturity_at > prediction.as_of_at
        for outcome in outcomes
    )
    assert prediction.published_decision_json["actionability"] == "RESEARCH_ONLY"
    assert result is not None
    assert result.published_decision is not None
    assert result.published_decision.normalized_direction == "INDETERMINATE"
    assert result.published_decision.prediction_heads == []
    assert result.report is not None
    assert len(result.report["sections"]) == 13
    assert "candidate_decision" not in result.model_dump()


@pytest.mark.asyncio
async def test_orchestrator_redacts_credentials_before_raw_snapshot_persistence() -> None:
    """A custom adapter cannot bypass the pre-persistence credential boundary."""
    async with async_session_maker() as db:
        user = User(
            username="asset_redaction_user",
            email="asset-redaction@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(_approved_source(asset_type="futures", source_id="fixture-futures"))
        await db.flush()
        service = AssetResearchOrchestrator(db, data_adapter=_SecretBearingFuturesData())
        await service.persist_identity(_identity())

        task = await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="futures",
                canonical_id="futures:CFFEX:IF2609:CNY",
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        stored = (await db.execute(select(AssetSourceSnapshot))).scalar_one()

    serialized = json.dumps(
        {
            "raw_fields": stored.raw_fields_json,
            "source_manifest": stored.source_manifest_json,
        },
        ensure_ascii=False,
    )

    assert task.status == "SUCCEEDED"
    for secret in (
        "injected-snapshot-secret",
        "injected-history-secret",
        "injected-manifest-secret",
    ):
        assert secret not in serialized
    assert stored.raw_fields_json["fields"]["snapshot"]["api_key"] == "[REDACTED]"
    assert stored.raw_fields_json["history_rows"][-1]["password"] == "[REDACTED]"
    assert stored.source_manifest_json["authorization"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_orchestrator_applies_server_owned_mainland_fx_restriction() -> None:
    """A client task cannot bypass or reuse a server jurisdiction decision."""
    async with async_session_maker() as db:
        user = User(
            username="asset_fx_compliance_user",
            email="asset-fx-compliance@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(_approved_source(asset_type="fx", source_id="fixture-fx"))
        await db.flush()

        identity = _fx_identity()
        mainland_service = AssetResearchOrchestrator(
            db,
            data_adapter=_ApprovedFxData(),
            compliance_policy=AssetResearchCompliancePolicy(
                operator_jurisdiction="CN",
                directional_fx_crypto_enabled=True,
            ),
        )
        await mainland_service.persist_identity(identity)

        mainland_task = await mainland_service.create_and_run(
            user_id=str(user.id),
            request=AssetAnalysisCreateRequest(asset_type="fx", canonical_id=identity.canonical_id),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        us_service = AssetResearchOrchestrator(
            db,
            data_adapter=_ApprovedFxData(),
            compliance_policy=AssetResearchCompliancePolicy(
                operator_jurisdiction="US",
                directional_fx_crypto_enabled=True,
            ),
        )
        us_task = await us_service.create_and_run(
            user_id=str(user.id),
            request=AssetAnalysisCreateRequest(asset_type="fx", canonical_id=identity.canonical_id),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        predictions = list((await db.execute(select(AssetSignalPrediction))).scalars())

    assert mainland_task.status == "SUCCEEDED"
    assert us_task.status == "SUCCEEDED"
    assert len(predictions) == 2
    mainland_prediction = next(
        prediction
        for prediction in predictions
        if prediction.published_decision_json["actionability"] == "REGION_RESTRICTED"
    )
    us_prediction = next(
        prediction
        for prediction in predictions
        if prediction.published_decision_json["actionability"] == "RESEARCH_ONLY"
    )
    assert mainland_prediction.quality_status == "ELIGIBLE"
    assert mainland_prediction.published_decision_json["recommendation"] == "AVOID"
    assert mainland_prediction.published_decision_json["trade_intent"] == "NONE"
    assert mainland_prediction.published_decision_json["reason_codes"] == ["FX.REGION_RESTRICTED"]
    assert us_prediction.published_decision_json["recommendation"] == "HOLD"
    assert us_prediction.published_decision_json["reason_codes"] == ["COMMON.MODEL_NOT_PROMOTED"]
    assert mainland_prediction.decision_input_hash != us_prediction.decision_input_hash


@pytest.mark.asyncio
async def test_orchestrator_persists_an_exact_option_cost_envelope_and_all_option_heads() -> None:
    """Option cost evidence must survive the task boundary for later P&L scoring."""
    async with async_session_maker() as db:
        user = User(
            username="asset_option_user",
            email="asset-option@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="fixture-option",
                asset_types=["option"],
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
        service = AssetResearchOrchestrator(db, data_adapter=_ApprovedOptionData())
        identity = _option_identity()
        await service.persist_identity(identity)

        task = await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="option",
                canonical_id=identity.canonical_id,
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        prediction = (await db.execute(select(AssetSignalPrediction))).scalar_one()
        outcomes = list((await db.execute(select(AssetSignalOutcome))).scalars())

    assert task.status == "SUCCEEDED"
    assert prediction.quality_status == "ELIGIBLE"
    assert prediction.cost_snapshot_json["cost_model_version"] == "fixture-v1"
    assert prediction.cost_snapshot_json["total_cost_rate"] == pytest.approx(0.010)
    assert {outcome.outcome_kind for outcome in outcomes} == {
        "option.underlying_direction",
        "option.iv_direction",
        "option.exact_contract_net_profit",
        "option.close_avoided_loss",
    }
    assert all(outcome.maturity_at is not None for outcome in outcomes)


@pytest.mark.asyncio
async def test_orchestrator_persists_the_valid_option_context_binding_window() -> None:
    """A valid option LONG context keeps its exact ownership-window evidence."""
    cutoff_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    async with async_session_maker() as db:
        user = User(
            username="asset_option_context_user",
            email="asset-option-context@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(_approved_source(asset_type="option", source_id="fixture-option"))
        await db.flush()
        service = AssetResearchOrchestrator(db, data_adapter=_ApprovedOptionData())
        identity = _option_identity()
        await service.persist_identity(identity)
        context = await service.create_position_context(
            user_id=user.id,
            request=PositionContextCreateRequest(
                canonical_id=identity.canonical_id,
                position_context="LONG",
                long_quantity=Decimal("1"),
                as_of_at=cutoff_at - timedelta(minutes=1),
                expires_at=cutoff_at + timedelta(days=1),
            ),
        )

        task = await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="option",
                canonical_id=identity.canonical_id,
                position_context="LONG",
                position_context_snapshot_id=context.id,
            ),
            cutoff_at=cutoff_at,
        )
        prediction = (await db.execute(select(AssetSignalPrediction))).scalar_one()

    assert task.status == "SUCCEEDED"
    assert prediction.position_context == "LONG"
    assert prediction.position_context_snapshot_id == context.id
    assert prediction.position_context_snapshot_as_of_at is not None
    assert prediction.position_context_snapshot_available_at is not None
    assert prediction.position_context_snapshot_expires_at is not None
    assert prediction.position_context_snapshot_as_of_at.replace(tzinfo=None) == (
        context.as_of_at.replace(tzinfo=None)
    )
    assert prediction.position_context_snapshot_available_at.replace(tzinfo=None) == (
        context.available_at.replace(tzinfo=None)
    )
    assert prediction.position_context_snapshot_expires_at.replace(tzinfo=None) == (
        context.expires_at.replace(tzinfo=None)
    )


@pytest.mark.asyncio
async def test_orchestrator_rejects_option_snapshot_with_changed_contract_terms() -> None:
    """A provider must not substitute another contract under the requested canonical ID."""
    async with async_session_maker() as db:
        user = User(
            username="asset_option_identity_user",
            email="asset-option-identity@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="fixture-option",
                asset_types=["option"],
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
        identity = _option_identity()
        service = AssetResearchOrchestrator(db, data_adapter=_SubstitutedOptionData())
        await service.persist_identity(identity)

        task = await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="option",
                canonical_id=identity.canonical_id,
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        snapshots = list((await db.execute(select(AssetSourceSnapshot))).scalars())

    assert task.status == "FAILED"
    assert task.error_code == "SNAPSHOT_IDENTITY_MISMATCH"
    assert snapshots == []


@pytest.mark.asyncio
async def test_orchestrator_rejects_snapshot_with_a_different_cutoff_at() -> None:
    """A decision must not retain one cutoff while its source snapshot is from another instant."""
    async with async_session_maker() as db:
        user = User(
            username="asset_option_cutoff_user",
            email="asset-option-cutoff@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(_approved_source(asset_type="option", source_id="fixture-option"))
        await db.flush()
        identity = _option_identity()
        service = AssetResearchOrchestrator(db, data_adapter=_MismatchedOptionCutoffData())
        await service.persist_identity(identity)

        task = await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="option",
                canonical_id=identity.canonical_id,
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        snapshots = list((await db.execute(select(AssetSourceSnapshot))).scalars())

    assert task.status == "FAILED"
    assert task.error_code == "SNAPSHOT_CUTOFF_MISMATCH"
    assert snapshots == []


@pytest.mark.asyncio
async def test_orchestrator_rejects_identity_rewritten_by_source_authorization() -> None:
    """Authorization metadata enrichment must not be allowed to replace the contract terms."""
    async with async_session_maker() as db:
        user = User(
            username="asset_option_source_identity_user",
            email="asset-option-source-identity@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(_approved_source(asset_type="option", source_id="fixture-option"))
        await db.flush()
        identity = _option_identity()
        service = AssetResearchOrchestrator(
            db,
            data_adapter=_ApprovedOptionData(),
            source_policy=_SubstitutedOptionSourcePolicy(),
        )
        await service.persist_identity(identity)

        task = await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="option",
                canonical_id=identity.canonical_id,
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        snapshots = list((await db.execute(select(AssetSourceSnapshot))).scalars())

    assert task.status == "FAILED"
    assert task.error_code == "SNAPSHOT_IDENTITY_MISMATCH"
    assert snapshots == []


@pytest.mark.asyncio
async def test_orchestrator_rejects_cutoff_rewritten_by_source_authorization() -> None:
    """Authorization metadata enrichment must not alter the frozen analysis instant."""
    async with async_session_maker() as db:
        user = User(
            username="asset_option_source_cutoff_user",
            email="asset-option-source-cutoff@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(_approved_source(asset_type="option", source_id="fixture-option"))
        await db.flush()
        identity = _option_identity()
        service = AssetResearchOrchestrator(
            db,
            data_adapter=_ApprovedOptionData(),
            source_policy=_SubstitutedOptionCutoffSourcePolicy(),
        )
        await service.persist_identity(identity)

        task = await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="option",
                canonical_id=identity.canonical_id,
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        snapshots = list((await db.execute(select(AssetSourceSnapshot))).scalars())

    assert task.status == "FAILED"
    assert task.error_code == "SNAPSHOT_CUTOFF_MISMATCH"
    assert snapshots == []


@pytest.mark.asyncio
async def test_orchestrator_records_task_lifecycle_and_authorized_source_metrics(
    monkeypatch,
) -> None:
    """The persisted lifecycle must have matching bounded monitoring events."""
    task_events: list[dict[str, object]] = []
    source_events: list[dict[str, object]] = []
    monkeypatch.setattr(
        orchestrator_module,
        "record_asset_research_task",
        lambda **event: task_events.append(event),
    )
    monkeypatch.setattr(
        orchestrator_module,
        "record_asset_research_source",
        lambda **event: source_events.append(event),
    )
    async with async_session_maker() as db:
        user = User(
            username="asset_metric_user", email="asset-metric@example.test", hashed_password="hash"
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="fixture-futures",
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
        service = AssetResearchOrchestrator(db, data_adapter=_ApprovedFuturesData())
        await service.persist_identity(_identity())

        task = await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="futures",
                canonical_id="futures:CFFEX:IF2609:CNY",
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )

    assert task.status == "SUCCEEDED"
    assert [event["status"] for event in task_events] == ["QUEUED", "RUNNING", "SUCCEEDED"]
    assert task_events[-1]["duration_seconds"] >= 0
    assert len(source_events) == 1
    assert source_events[0]["source_id"] == "fixture-futures"
    assert source_events[0]["result"] == "AUTHORIZED"
    assert source_events[0]["duration_seconds"] >= 0


@pytest.mark.asyncio
async def test_report_render_failure_does_not_downgrade_an_already_committed_research_run() -> None:
    """Report rendering is a secondary resource, not the decision transaction's status."""
    async with async_session_maker() as db:
        user = User(
            username="asset_report_failure_user",
            email="asset-report-failure@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="fixture-futures",
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
        service = AssetResearchOrchestrator(db, data_adapter=_ApprovedFuturesData())
        await service.persist_identity(_identity())

        with patch(
            "app.services.asset_research.orchestrator.build_report_payload",
            side_effect=RuntimeError("template unavailable"),
        ):
            task = await service.create_and_run(
                user_id=user.id,
                request=AssetAnalysisCreateRequest(
                    asset_type="futures",
                    canonical_id="futures:CFFEX:IF2609:CNY",
                ),
                cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            )
        run = (await db.execute(select(AssetSignalRun))).scalar_one()
        result = await service.get_result(user_id=user.id, task_id=task.id)

    assert task.status == "SUCCEEDED"
    assert task.error_code == "REPORT_RENDER_FAILED"
    assert run.status == "SUCCEEDED"
    assert run.prediction_id is not None
    assert run.prediction_link_role == "CREATED"
    assert result is not None
    assert result.report is None
    assert result.published_decision is not None
    assert result.published_decision.actionability == "RESEARCH_ONLY"


@pytest.mark.asyncio
async def test_prediction_unique_conflict_recovers_to_the_existing_immutable_record() -> None:
    """A losing concurrent insert must reuse rather than fail its run transaction."""
    async with async_session_maker() as db:
        user = User(
            username="asset_prediction_conflict_user",
            email="asset-prediction-conflict@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="fixture-futures",
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
        service = AssetResearchOrchestrator(db, data_adapter=_ApprovedFuturesData())
        await service.persist_identity(_identity())
        await service.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="futures",
                canonical_id="futures:CFFEX:IF2609:CNY",
            ),
            cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        existing = (await db.execute(select(AssetSignalPrediction))).scalar_one()
        duplicate_values = {
            column.name: getattr(existing, column.name)
            for column in AssetSignalPrediction.__table__.columns
            if column.name != "id"
        }
        duplicate = AssetSignalPrediction(**duplicate_values)

        recovered, role = await service._insert_or_reuse_prediction_record(duplicate)
        predictions = list((await db.execute(select(AssetSignalPrediction))).scalars())

    assert role == "REUSED"
    assert recovered.id == existing.id
    assert [prediction.id for prediction in predictions] == [existing.id]
