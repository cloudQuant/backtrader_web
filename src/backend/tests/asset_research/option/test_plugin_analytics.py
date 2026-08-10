"""Integration contract between frozen option snapshots and analytics output."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.schemas.asset_research import (
    InstrumentIdentity,
    OptionIdentityDetails,
    OptionResearchDetails,
    RawAssetSnapshot,
)
from app.services.asset_research.plugins.option.pricing import (
    OptionPricingInput,
    calculate_option_analytics,
)
from app.services.asset_research.registry import DEFAULT_ASSET_RESEARCH_REGISTRY


def _chain_quality_policy() -> dict[str, float | int | str]:
    return {
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
    }


def _cost_snapshot() -> dict[str, float | str]:
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


def _chain_records(cutoff: datetime) -> list[dict[str, float | str]]:
    expiries = (datetime(2027, 8, 1, tzinfo=timezone.utc), datetime(2027, 11, 1, tzinfo=timezone.utc))
    records: list[dict[str, float | str]] = []
    for expiry_index, expiry_at in enumerate(expiries):
        time_to_expiry = (expiry_at - cutoff).total_seconds() / (365.0 * 24 * 60 * 60)
        for strike in (90.0, 100.0, 110.0):
            for option_right in ("CALL", "PUT"):
                analytics = calculate_option_analytics(
                    OptionPricingInput(
                        model="BSM",
                        option_right=option_right,
                        underlying_price=100.0,
                        strike=strike,
                        time_to_expiry_years=time_to_expiry,
                        risk_free_rate=0.05,
                        dividend_yield=0.0,
                        volatility=0.20 + 0.03 * expiry_index,
                    )
                )
                assert analytics.theoretical_value is not None
                records.append(
                    {
                        "expiry_at": expiry_at.isoformat(),
                        "strike": strike,
                        "option_right": option_right,
                        "bid": analytics.theoretical_value * 0.995,
                        "ask": analytics.theoretical_value * 1.005,
                        "bid_size": 100.0,
                        "ask_size": 100.0,
                        "volume": 500.0,
                        "open_interest": 1000.0,
                        "quote_at": cutoff.isoformat(),
                    }
                )
    return records


def _option_snapshot() -> RawAssetSnapshot:
    cutoff = datetime(2026, 8, 1, tzinfo=timezone.utc)
    identity = InstrumentIdentity(
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
    return RawAssetSnapshot(
        identity=identity,
        cutoff_at=cutoff,
        retrieved_at=cutoff,
        raw_schema_version="fixture-v1",
        raw_fields={
            "snapshot": {
                "price": 10.45,
                "bid": 10.40,
                "ask": 10.50,
                "quote_at": cutoff.isoformat(),
            },
            "option": {
                "contract_terms": "fixture",
                "underlying_price": 100.0,
                "underlying_kind": "SPOT",
                "risk_free_rate": 0.05,
                "dividend_yield": 0.0,
                "implied_volatility": 0.20,
                "underlying_quote_at": cutoff.isoformat(),
                "chain_quality_policy": _chain_quality_policy(),
                "cost_snapshot": _cost_snapshot(),
                "chain": _chain_records(cutoff),
            },
        },
        history_rows=[
            {"date": "2026-07-31", "close": 10.20},
            {"date": "2026-08-01", "close": 10.45},
        ],
        source_manifest={
            "license_status": "APPROVED",
            "capabilities": ["price", "option_chain", "contract_terms"],
        },
        license_tags=["APPROVED"],
        content_hash=hashlib.sha256(b"option-analytics").hexdigest(),
    )


def test_option_plugin_derives_model_valuation_greeks_and_bid_ask_iv() -> None:
    raw = _option_snapshot()
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("option")
    quality = plugin.assess_quality(raw)
    eligible = plugin.promote_snapshot(raw, quality)

    assert eligible is not None
    features = plugin.compute_features(eligible)
    assert features.values["pricing_model"] == "BSM"
    assert features.values["theoretical_value"] == pytest.approx(10.4505835722, abs=1e-8)
    assert features.values["implied_volatility"] == pytest.approx(0.20, abs=1e-8)
    assert features.values["implied_volatility_bid"] is not None
    assert features.values["implied_volatility_ask"] is not None
    assert features.values["delta"] == pytest.approx(0.6368306512, abs=1e-8)
    assert features.values["gamma"] == pytest.approx(0.0187620173, abs=1e-8)

    candidate = plugin.make_decision(
        features,
        quality,
        position_context="UNKNOWN",
        horizon_code="standard",
        snapshot=raw,
    )

    assert isinstance(candidate.asset_details, OptionResearchDetails)
    assert candidate.asset_details.pricing_model == "BSM"
    assert float(candidate.asset_details.theoretical_value) == pytest.approx(10.4505835722, abs=1e-8)
    assert float(candidate.asset_details.delta) == pytest.approx(0.6368306512, abs=1e-8)
    assert float(candidate.asset_details.break_even) == pytest.approx(110.4505835722, abs=1e-8)
    heads = {head.head_code: head for head in candidate.prediction_heads}
    assert heads["option.iv_direction"].target_spec_version == "option.iv_direction.v1"
    assert (
        heads["option.iv_direction"].scoreability_rule_version
        == "option.iv_direction.scoreability.v1"
    )
    assert heads["option.exact_contract_net_profit"].labels == ["PROFIT", "LOSS"]
    assert heads["option.exact_contract_net_profit"].primary_for_promotion is True


def test_option_plugin_rejects_a_two_sided_quote_outside_no_arbitrage_bounds() -> None:
    raw = _option_snapshot().model_copy(
        update={
            "raw_fields": {
                **_option_snapshot().raw_fields,
                "snapshot": {
                    "price": 120.0,
                    "bid": 119.0,
                    "ask": 121.0,
                    "quote_at": _option_snapshot().cutoff_at.isoformat(),
                },
            }
        }
    )
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("option")

    quality = plugin.assess_quality(raw)

    assert quality.status == "REJECTED"
    assert "OPTION.IV_SOLVER_FAILED" in quality.reason_codes
    assert quality.checks["option_bid_iv_reason"] == "OPTION.PRICE_OUTSIDE_ARBITRAGE_BOUNDS"


def test_option_plugin_rejects_a_contract_after_its_last_trade_time() -> None:
    raw = _option_snapshot()
    identity = raw.identity.model_copy(
        update={
            "details": raw.identity.details.model_copy(
                update={"last_trade_at": raw.cutoff_at}
            )
        }
    )
    stopped = raw.model_copy(update={"identity": identity})

    quality = DEFAULT_ASSET_RESEARCH_REGISTRY.get("option").assess_quality(stopped)

    assert quality.status == "REJECTED"
    assert "OPTION.CONTRACT_NOT_TRADABLE" in quality.reason_codes


def test_option_plugin_does_not_treat_a_chain_complete_boolean_as_chain_evidence() -> None:
    raw = _option_snapshot()
    option = dict(raw.raw_fields["option"])
    option.pop("chain")
    option["chain_complete"] = True
    raw = raw.model_copy(update={"raw_fields": {**raw.raw_fields, "option": option}})
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("option")

    quality = plugin.assess_quality(raw)

    assert quality.status == "REJECTED"
    assert "OPTION.CHAIN_INCOMPLETE" in quality.reason_codes
    assert quality.checks["option_chain_payload_present"] is False


def test_option_plugin_rejects_a_contract_when_its_cost_snapshot_is_missing() -> None:
    raw = _option_snapshot()
    option = dict(raw.raw_fields["option"])
    option.pop("cost_snapshot")
    raw = raw.model_copy(update={"raw_fields": {**raw.raw_fields, "option": option}})
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("option")

    quality = plugin.assess_quality(raw)

    assert quality.status == "REJECTED"
    assert "OPTION.COST_SNAPSHOT_MISSING" in quality.reason_codes
    assert quality.checks["option_cost_snapshot_present"] is False


def test_option_plugin_rejects_an_exact_quote_without_a_frozen_quote_timestamp() -> None:
    raw = _option_snapshot()
    snapshot = dict(raw.raw_fields["snapshot"])
    snapshot.pop("quote_at")
    raw = raw.model_copy(update={"raw_fields": {**raw.raw_fields, "snapshot": snapshot}})
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("option")

    quality = plugin.assess_quality(raw)

    assert quality.status == "REJECTED"
    assert "OPTION.QUOTE_TIMESTAMP_MISSING" in quality.reason_codes
    assert quality.checks["option_quote_timestamp_present"] is False


def test_option_contract_edge_uses_the_executable_ask_not_a_mid_or_last_mark() -> None:
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("option")
    raw = _option_snapshot().model_copy(
        update={
            "raw_fields": {
                **_option_snapshot().raw_fields,
                "snapshot": {
                    "price": 99.0,
                    "mid": 99.0,
                    "bid": 10.40,
                    "ask": 10.50,
                    "quote_at": _option_snapshot().cutoff_at.isoformat(),
                },
            }
        }
    )
    altered_mark = raw.model_copy(
        update={
            "raw_fields": {
                **raw.raw_fields,
                "snapshot": {
                    "price": 0.01,
                    "mid": 0.01,
                    "bid": 10.40,
                    "ask": 10.50,
                    "quote_at": _option_snapshot().cutoff_at.isoformat(),
                },
            }
        }
    )

    baseline = plugin.compute_features(plugin.promote_snapshot(raw, plugin.assess_quality(raw)))
    changed_mark = plugin.compute_features(
        plugin.promote_snapshot(altered_mark, plugin.assess_quality(altered_mark))
    )

    assert baseline.values["contract_edge"] == pytest.approx(-0.0047063265, abs=1e-8)
    assert changed_mark.values["contract_edge"] == baseline.values["contract_edge"]


def test_option_head_hash_freezes_the_training_cutoff_with_its_target_contract() -> None:
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("option")
    raw = _option_snapshot()
    later = raw.model_copy(update={"cutoff_at": raw.cutoff_at + timedelta(days=1)})

    initial_head = next(
        head
        for head in plugin._prediction_heads(snapshot=raw, signal_score=0.0)
        if head.head_code == "option.exact_contract_net_profit"
    )
    later_head = next(
        head
        for head in plugin._prediction_heads(snapshot=later, signal_score=0.0)
        if head.head_code == "option.exact_contract_net_profit"
    )

    assert initial_head.training_cutoff_at != later_head.training_cutoff_at
    assert initial_head.head_spec_hash != later_head.head_spec_hash
