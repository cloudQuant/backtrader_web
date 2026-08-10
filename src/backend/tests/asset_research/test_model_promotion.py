"""Promotion gates must match the exact identity, head and required approvals."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.db.database import async_session_maker
from app.models.asset_research import AssetModelRegistry, AssetModelStatusEvent
from app.schemas.asset_research import (
    CryptoProductIdentityDetails,
    FuturesIdentityDetails,
    InstrumentIdentity,
    PromotionScope,
    RawAssetSnapshot,
)
from app.services.asset_research.data import canonical_json_hash
from app.services.asset_research.orchestrator import AssetResearchOrchestrator
from app.services.asset_research.registry import DEFAULT_ASSET_RESEARCH_REGISTRY


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


def _candidate():
    identity = _identity()
    raw = RawAssetSnapshot(
        identity=identity,
        cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        raw_schema_version="fixture-v1",
        raw_fields={"snapshot": {"price": 101, "bid": 100.9, "ask": 101.1}},
        history_rows=[{"date": "2026-07-31", "close": 100}, {"date": "2026-08-01", "close": 101}],
        source_manifest={
            "license_status": "APPROVED",
            "capabilities": ["price", "contract_calendar"],
        },
        license_tags=["APPROVED"],
        content_hash="a" * 64,
    )
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("futures")
    quality = plugin.assess_quality(raw)
    eligible = plugin.promote_snapshot(raw, quality)
    assert eligible is not None
    return identity, plugin.make_decision(
        plugin.compute_features(eligible),
        quality,
        position_context="UNKNOWN",
        horizon_code="standard",
        snapshot=raw,
    )


def _crypto_identity(*, quote_asset_id: str) -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="crypto",
        identity_level="PRODUCT",
        canonical_id=f"crypto:BINANCE:BTC-{quote_asset_id}:SPOT",
        display_symbol=f"BTC/{quote_asset_id}",
        name="BTC spot fixture",
        venue="BINANCE",
        currency=quote_asset_id,
        timezone="UTC",
        identifier_type="MARKET",
        identifier_value=f"BTC/{quote_asset_id}",
        product_type="SPOT",
        metadata_version="fixture-v1",
        details=CryptoProductIdentityDetails(
            base_asset_id="BTC",
            quote_asset_id=quote_asset_id,
            market_type="SPOT",
            linear_or_inverse="NOT_APPLICABLE",
        ),
    )


def _scope_key(
    *,
    scope_type: str,
    asset_type: str,
    instrument_class: str,
    canonical_id: str | None,
    venue: str | None,
    product_type: str | None,
    quote_or_settlement_asset: str | None,
    signal_head: str,
    horizon_code: str,
    scope_parameters: dict[str, str],
) -> str:
    return PromotionScope(
        scope_type=scope_type,
        asset_type=asset_type,
        instrument_class=instrument_class,
        canonical_id=canonical_id,
        venue=venue,
        product_type=product_type,
        quote_or_settlement_asset=quote_or_settlement_asset,
        signal_head=signal_head,
        horizon_code=horizon_code,
        scope_parameters=scope_parameters,
    ).scope_key()


def _t2_metrics(head_hash: str) -> dict[str, object]:
    return {
        "head_spec_hash": head_hash,
        "sample_count": 200,
        "unique_evaluation_days": 60,
        "market_regime_count": 3,
        "walk_forward_train_before_test": True,
        "overlap_purged": True,
        "embargo_applied": True,
        "vintage_data_enforced": True,
        "block_length_covers_max_overlap": True,
        "brier_score": 0.20,
        "baseline_brier_score": 0.25,
        "brier_skill_score": 0.20,
        "expected_calibration_error": 0.02,
        "mean_net_utility": 0.001,
        "delta_net_utility_ci_lower": 0.0,
        "forward_shadow_days": 60,
        "reliability_reviewed": True,
        "tail_risk_approved": True,
        "maximum_drawdown_approved": True,
        "coverage_approved": True,
        "data_failure_rate_approved": True,
        "multiple_comparisons_controlled": True,
        "all_attempts_manifest_hash": "e" * 64,
        "evaluation_artifact_hash": "f" * 64,
        "model_card_hash": "8" * 64,
        "drift_report_hash": "9" * 64,
        "futures_contract_month_count": 3,
    }


def _model(
    *,
    scope_key: str,
    canonical_id_scope: str | None,
    head_hash: str,
    promotion_scope_type: str = "INSTRUMENT_SPECIFIC",
    asset_type: str = "futures",
    instrument_class: str = "FUTURE",
    venue_scope: str | None = "CFFEX",
    product_type_scope: str | None = "FUTURE",
    signal_head: str = "futures.contract_pnl",
    scope_parameters: dict[str, str] | None = None,
) -> AssetModelRegistry:
    parameters = {"fixture_scope": scope_key, **(scope_parameters or {})}
    quote_or_settlement_asset = parameters.pop("quote_or_settlement_asset", None)
    return AssetModelRegistry(
        promotion_scope_key=_scope_key(
            scope_type=promotion_scope_type,
            asset_type=asset_type,
            instrument_class=instrument_class,
            canonical_id=canonical_id_scope,
            venue=venue_scope,
            product_type=product_type_scope,
            quote_or_settlement_asset=quote_or_settlement_asset,
            signal_head=signal_head,
            horizon_code="standard",
            scope_parameters=parameters,
        ),
        promotion_scope_type=promotion_scope_type,
        asset_type=asset_type,
        instrument_class=instrument_class,
        canonical_id_scope=canonical_id_scope,
        venue_scope=venue_scope,
        product_type_scope=product_type_scope,
        scope_parameters_json={
            **parameters,
            **(
                {"quote_or_settlement_asset": quote_or_settlement_asset}
                if quote_or_settlement_asset is not None
                else {}
            ),
        },
        signal_head=signal_head,
        horizon_code="standard",
        head_spec_hash=head_hash,
        target_spec_version="target-v2",
        scoreability_rule_version="scoreability-v2",
        baseline_version="baseline-v1",
        policy_version="asset-research-policy-v2",
        model_version="asset-research-shadow-v2",
        probability_artifact_hash="b" * 64,
        calibration_version="not-promoted-v2",
        calibration_artifact_hash="c" * 64,
        training_cutoff_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        status="PROMOTED",
        metrics_json=_t2_metrics(head_hash),
        approval_set_json={
            "model_quality": True,
            "product": True,
            "compliance": True,
            "data_license": True,
            "security": True,
        },
        evidence_uri="s3://evidence/model.json",
        evidence_content_hash="d" * 64,
        approved_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        effective_from=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )


async def _record_promotion_event(db, record: AssetModelRegistry) -> None:
    db.add(
        AssetModelStatusEvent(
            model_registry_id=record.id,
            from_status="SHADOW",
            to_status="PROMOTED",
            reason_codes_json=["COMMON.T2_GATE_PASSED"],
            metrics_snapshot_json=record.metrics_json,
            evidence_uri=record.evidence_uri,
            evidence_content_hash=record.evidence_content_hash,
            created_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )
    )
    await db.flush()


@pytest.mark.asyncio
async def test_promotion_requires_exact_scope_head_and_approval_set() -> None:
    identity, candidate = _candidate()
    head = candidate.prediction_heads[0]
    async with async_session_maker() as db:
        wrong_scope = _model(
            scope_key="wrong-scope",
            canonical_id_scope="futures:CFFEX:IH2609:CNY",
            head_hash=head.head_spec_hash,
        )
        db.add(wrong_scope)
        await db.flush()
        await _record_promotion_event(db, wrong_scope)
        service = AssetResearchOrchestrator(db)
        assert not await service._is_promoted(
            asset_type="futures",
            horizon_code="standard",
            as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            identity=identity,
            candidate=candidate,
        )

        right_scope = _model(
            scope_key="right-scope",
            canonical_id_scope=identity.canonical_id,
            head_hash=head.head_spec_hash,
        )
        db.add(right_scope)
        await db.flush()
        await _record_promotion_event(db, right_scope)
        assert await service._is_promoted(
            asset_type="futures",
            horizon_code="standard",
            as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            identity=identity,
            candidate=candidate,
        )


@pytest.mark.asyncio
async def test_promotion_rejects_matching_registry_row_without_t2_metrics() -> None:
    identity, candidate = _candidate()
    head = candidate.prediction_heads[0]

    async with async_session_maker() as db:
        record = _model(
            scope_key="missing-t2-metrics",
            canonical_id_scope=identity.canonical_id,
            head_hash=head.head_spec_hash,
        )
        record.metrics_json = {"sample_count": 200}
        db.add(record)
        await db.flush()
        await _record_promotion_event(db, record)

        assert not await AssetResearchOrchestrator(db)._is_promoted(
            asset_type="futures",
            horizon_code="standard",
            as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            identity=identity,
            candidate=candidate,
        )


@pytest.mark.asyncio
async def test_promotion_rejects_registry_row_with_an_unverifiable_scope_key() -> None:
    identity, candidate = _candidate()
    head = candidate.prediction_heads[0]

    async with async_session_maker() as db:
        record = _model(
            scope_key="invalid-scope-key",
            canonical_id_scope=identity.canonical_id,
            head_hash=head.head_spec_hash,
        )
        record.promotion_scope_key = "f" * 64
        db.add(record)
        await db.flush()
        await _record_promotion_event(db, record)

        assert not await AssetResearchOrchestrator(db)._is_promoted(
            asset_type="futures",
            horizon_code="standard",
            as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            identity=identity,
            candidate=candidate,
        )


def test_venue_product_scope_rejects_another_quote_or_settlement_asset() -> None:
    record = _model(
        scope_key="crypto-usdt-venue-scope",
        canonical_id_scope=None,
        head_hash="a" * 64,
        promotion_scope_type="VENUE_PRODUCT",
        asset_type="crypto",
        instrument_class="SPOT",
        venue_scope="BINANCE",
        product_type_scope="SPOT",
        signal_head="crypto.spot_pnl",
        scope_parameters={"quote_or_settlement_asset": "USDT"},
    )

    assert not AssetResearchOrchestrator._model_scope_matches(
        record,
        identity=_crypto_identity(quote_asset_id="USDC"),
        as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def test_promotion_scope_key_uses_the_normalized_canonical_contract() -> None:
    scope = PromotionScope(
        scope_type="VENUE_PRODUCT",
        asset_type="crypto",
        instrument_class="spot",
        canonical_id=None,
        venue="binance",
        product_type="spot",
        quote_or_settlement_asset="usdt",
        signal_head="crypto.spot_pnl",
        horizon_code="standard",
        scope_parameters={"market_region": "global", "fixture_scope": "exact-key"},
    )

    assert scope.scope_key() == canonical_json_hash(
        {
            "scope_type": "VENUE_PRODUCT",
            "asset_type": "crypto",
            "instrument_class": "SPOT",
            "canonical_id": None,
            "venue": "BINANCE",
            "product_type": "SPOT",
            "quote_or_settlement_asset": "USDT",
            "signal_head": "crypto.spot_pnl",
            "horizon_code": "standard",
            "scope_parameters": {"fixture_scope": "exact-key", "market_region": "global"},
        }
    )


def test_venue_product_scope_requires_an_explicit_quote_or_settlement_asset() -> None:
    with pytest.raises(ValidationError, match="VENUE_PRODUCT scope requires"):
        PromotionScope(
            scope_type="VENUE_PRODUCT",
            asset_type="crypto",
            instrument_class="SPOT",
            canonical_id=None,
            venue="BINANCE",
            product_type="SPOT",
            quote_or_settlement_asset=None,
            signal_head="crypto.spot_pnl",
            horizon_code="standard",
            scope_parameters={},
        )


def test_scope_matching_rejects_a_non_mapping_registry_scope_projection() -> None:
    record = _model(
        scope_key="invalid-json-scope",
        canonical_id_scope=_identity().canonical_id,
        head_hash="a" * 64,
    )
    record.scope_parameters_json = ["not-a-mapping"]

    assert not AssetResearchOrchestrator._model_scope_matches(
        record,
        identity=_identity(),
        as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def test_venue_product_scope_rejects_a_registry_projection_without_quote() -> None:
    record = _model(
        scope_key="crypto-usdt-venue-scope",
        canonical_id_scope=None,
        head_hash="a" * 64,
        promotion_scope_type="VENUE_PRODUCT",
        asset_type="crypto",
        instrument_class="SPOT",
        venue_scope="BINANCE",
        product_type_scope="SPOT",
        signal_head="crypto.spot_pnl",
        scope_parameters={"quote_or_settlement_asset": "USDT"},
    )
    record.scope_parameters_json = {"fixture_scope": "crypto-usdt-venue-scope"}

    assert not AssetResearchOrchestrator._model_scope_matches(
        record,
        identity=_crypto_identity(quote_asset_id="USDT"),
        as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def test_venue_product_scope_matches_the_exact_quote_or_settlement_asset() -> None:
    record = _model(
        scope_key="crypto-usdt-venue-scope",
        canonical_id_scope=None,
        head_hash="a" * 64,
        promotion_scope_type="VENUE_PRODUCT",
        asset_type="crypto",
        instrument_class="SPOT",
        venue_scope="BINANCE",
        product_type_scope="SPOT",
        signal_head="crypto.spot_pnl",
        scope_parameters={"quote_or_settlement_asset": "USDT"},
    )

    assert AssetResearchOrchestrator._model_scope_matches(
        record,
        identity=_crypto_identity(quote_asset_id="USDT"),
        as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_promotion_rejects_matching_registry_row_without_append_only_event() -> None:
    identity, candidate = _candidate()
    head = candidate.prediction_heads[0]

    async with async_session_maker() as db:
        record = _model(
            scope_key="missing-promotion-event",
            canonical_id_scope=identity.canonical_id,
            head_hash=head.head_spec_hash,
        )
        db.add(record)
        await db.flush()

        assert not await AssetResearchOrchestrator(db)._is_promoted(
            asset_type="futures",
            horizon_code="standard",
            as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            identity=identity,
            candidate=candidate,
        )


@pytest.mark.asyncio
async def test_promotion_rejects_event_with_different_frozen_metrics() -> None:
    identity, candidate = _candidate()
    head = candidate.prediction_heads[0]

    async with async_session_maker() as db:
        record = _model(
            scope_key="mismatched-event-metrics",
            canonical_id_scope=identity.canonical_id,
            head_hash=head.head_spec_hash,
        )
        db.add(record)
        await db.flush()
        db.add(
            AssetModelStatusEvent(
                model_registry_id=record.id,
                from_status="SHADOW",
                to_status="PROMOTED",
                reason_codes_json=["COMMON.T2_GATE_PASSED"],
                metrics_snapshot_json={**record.metrics_json, "sample_count": 201},
                evidence_uri=record.evidence_uri,
                evidence_content_hash=record.evidence_content_hash,
                created_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
            )
        )
        await db.flush()

        assert not await AssetResearchOrchestrator(db)._is_promoted(
            asset_type="futures",
            horizon_code="standard",
            as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            identity=identity,
            candidate=candidate,
        )


@pytest.mark.asyncio
async def test_promotion_rejects_nonpositive_brier_skill_even_with_matching_event() -> None:
    identity, candidate = _candidate()
    head = candidate.prediction_heads[0]

    async with async_session_maker() as db:
        record = _model(
            scope_key="nonpositive-brier-skill",
            canonical_id_scope=identity.canonical_id,
            head_hash=head.head_spec_hash,
        )
        record.metrics_json = {
            **record.metrics_json,
            "brier_score": 0.25,
            "baseline_brier_score": 0.25,
            "brier_skill_score": 0.0,
        }
        db.add(record)
        await db.flush()
        await _record_promotion_event(db, record)

        assert not await AssetResearchOrchestrator(db)._is_promoted(
            asset_type="futures",
            horizon_code="standard",
            as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            identity=identity,
            candidate=candidate,
        )


@pytest.mark.asyncio
async def test_promotion_rejects_an_event_written_after_the_prediction_cutoff() -> None:
    identity, candidate = _candidate()
    head = candidate.prediction_heads[0]

    async with async_session_maker() as db:
        record = _model(
            scope_key="future-promotion-event",
            canonical_id_scope=identity.canonical_id,
            head_hash=head.head_spec_hash,
        )
        db.add(record)
        await db.flush()
        db.add(
            AssetModelStatusEvent(
                model_registry_id=record.id,
                from_status="SHADOW",
                to_status="PROMOTED",
                reason_codes_json=["COMMON.T2_GATE_PASSED"],
                metrics_snapshot_json=record.metrics_json,
                evidence_uri=record.evidence_uri,
                evidence_content_hash=record.evidence_content_hash,
                created_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
            )
        )
        await db.flush()

        assert not await AssetResearchOrchestrator(db)._is_promoted(
            asset_type="futures",
            horizon_code="standard",
            as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            identity=identity,
            candidate=candidate,
        )


@pytest.mark.asyncio
async def test_promotion_rejects_pooled_scope_above_concentration_limit() -> None:
    identity, candidate = _candidate()
    head = candidate.prediction_heads[0]

    async with async_session_maker() as db:
        record = _model(
            scope_key="pooled-over-concentration-limit",
            canonical_id_scope=None,
            head_hash=head.head_spec_hash,
            promotion_scope_type="POOLED",
        )
        record.metrics_json = {
            **record.metrics_json,
            "max_instrument_share": 0.41,
            "cross_instrument_extrapolation_reviewed": True,
        }
        db.add(record)
        await db.flush()
        await _record_promotion_event(db, record)

        assert not await AssetResearchOrchestrator(db)._is_promoted(
            asset_type="futures",
            horizon_code="standard",
            as_of_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            identity=identity,
            candidate=candidate,
        )
