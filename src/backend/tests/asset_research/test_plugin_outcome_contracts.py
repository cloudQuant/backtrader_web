"""Every asset plugin must declare its non-interchangeable outcome contract."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.schemas.asset_research import (
    BondIdentityDetails,
    CryptoProductIdentityDetails,
    FundIdentityDetails,
    FuturesIdentityDetails,
    FxIdentityDetails,
    InstrumentIdentity,
    OptionIdentityDetails,
    RawAssetSnapshot,
)
from app.services.asset_research.decision import apply_publication_gate
from app.services.asset_research.plugins.option.pricing import (
    OptionPricingInput,
    calculate_option_analytics,
)
from app.services.asset_research.registry import DEFAULT_ASSET_RESEARCH_REGISTRY


def _identity(asset_type: str) -> InstrumentIdentity:
    common = {
        "canonical_id": f"{asset_type}:fixture:instrument",
        "display_symbol": f"{asset_type.upper()}-FIXTURE",
        "name": f"{asset_type} fixture",
        "venue": "FIXTURE",
        "currency": "USD",
        "timezone": "UTC",
        "identifier_type": "FIXTURE",
        "identifier_value": f"{asset_type}-fixture",
        "product_type": asset_type.upper(),
        "metadata_version": "fixture-v1",
    }
    if asset_type == "bond":
        return InstrumentIdentity(
            asset_type="bond",
            identity_level="PRODUCT",
            details=BondIdentityDetails(bond_identity_kind="LISTING", issuer_id="issuer"),
            **common,
        )
    if asset_type == "fund":
        return InstrumentIdentity(
            asset_type="fund",
            identity_level="PRODUCT",
            details=FundIdentityDetails(
                fund_identity_kind="LISTING",
                fund_id="fund",
                share_class_id="share-class",
                official_benchmark_id="benchmark",
            ),
            **common,
        )
    if asset_type == "futures":
        return InstrumentIdentity(
            asset_type="futures",
            identity_level="CONTRACT",
            details=FuturesIdentityDetails(
                product_code="FUT",
                contract_month="2609",
                expiry_at="2026-09-18T07:15:00+00:00",
                contract_multiplier="300",
                trading_calendar_id="FIXTURE",
            ),
            **common,
        )
    if asset_type == "option":
        return InstrumentIdentity(
            asset_type="option",
            identity_level="CONTRACT",
            details=OptionIdentityDetails(
                option_contract_id="option-fixture",
                exchange="FIXTURE",
                underlying_instrument_id="underlying",
                underlying_contract_id="underlying",
                expiry_at=datetime(2026, 12, 18, tzinfo=timezone.utc),
                last_trade_at=datetime(2026, 12, 18, tzinfo=timezone.utc),
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
            **common,
        )
    if asset_type == "fx":
        return InstrumentIdentity(
            asset_type="fx",
            identity_level="PRODUCT",
            details=FxIdentityDetails(
                base_currency="EUR",
                quote_currency="USD",
                settlement_type="SPOT",
                settlement_currency="USD",
                calendar_id="FX",
                price_convention="EUR_PER_USD",
            ),
            **common,
        )
    return InstrumentIdentity(
        asset_type="crypto",
        identity_level="PRODUCT",
        details=CryptoProductIdentityDetails(
            base_asset_id="btc",
            quote_asset_id="usd",
            market_type="SPOT",
            linear_or_inverse="NOT_APPLICABLE",
        ),
        **common,
    )


def _option_chain_fields(cutoff: datetime) -> dict[str, object]:
    policy: dict[str, float | int | str] = {
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
    records: list[dict[str, float | str]] = []
    for expiry_index, expiry_at in enumerate(
        (datetime(2026, 12, 18, tzinfo=timezone.utc), datetime(2027, 3, 18, tzinfo=timezone.utc))
    ):
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
    return {
        "chain_quality_policy": policy,
        "underlying_quote_at": cutoff.isoformat(),
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
        "chain": records,
    }


def _raw(asset_type: str) -> RawAssetSnapshot:
    requirements = {
        "bond": ["price", "official_valuation", "curve", "cashflows"],
        "fund": ["official_nav", "benchmark"],
        "futures": ["price", "contract_calendar"],
        "option": ["price", "option_chain", "contract_terms"],
        "fx": ["price", "calendar", "price_convention"],
        "crypto": ["price", "venue"],
    }
    asset_fields = {
        "bond": {
            "bond": {
                "maturity_date": "2030-01-01",
                "cashflows": [{"date": "2030-01-01", "amount": 100}],
                "curve": "CNY_GOVT",
                "benchmark": "CGBI",
            }
        },
        "fund": {
            "fund": {
                "fund_type": "ETF",
                "official_nav": 101.0,
                "benchmark": "SP500",
                "fee_schedule": "fixture",
                "holdings_as_of": "2026-07-31",
            }
        },
        "futures": {"futures": {"contract_calendar": "FIXTURE", "contract_terms": "fixture"}},
        "option": {
            "option": {
                "contract_terms": "fixture",
                "underlying_price": 100.0,
                "underlying_kind": "SPOT",
                "risk_free_rate": 0.05,
                "dividend_yield": 0.0,
                "implied_volatility": 0.20,
                **_option_chain_fields(datetime(2026, 8, 1, tzinfo=timezone.utc)),
            }
        },
        "fx": {"fx": {"completed_bar": True, "price_convention": "EUR_PER_USD"}},
        "crypto": {"crypto": {"venue_verified": True, "depth_1pct": 1000000}},
    }
    snapshot = {"price": 102.0}
    if asset_type == "bond":
        snapshot.update({"official_valuation": 102.0, "bid": 101.9, "ask": 102.1})
    if asset_type in {"futures", "option", "fx"}:
        snapshot.update({"bid": 101.9, "ask": 102.1})
    if asset_type == "option":
        snapshot.update(
            {
                "price": 5.90,
                "bid": 5.80,
                "ask": 6.00,
                "quote_at": datetime(2026, 8, 1, tzinfo=timezone.utc).isoformat(),
            }
        )
    if asset_type == "crypto":
        snapshot.update({"bid": 101.9, "ask": 102.1})
    return RawAssetSnapshot(
        identity=_identity(asset_type),
        cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        raw_schema_version="fixture-v1",
        raw_fields={"snapshot": snapshot, **asset_fields[asset_type]},
        history_rows=[
            {"date": "2026-07-31", "close": 100.0},
            {"date": "2026-08-01", "close": 102.0},
        ],
        source_manifest={
            "license_status": "APPROVED",
            "capabilities": requirements[asset_type],
        },
        license_tags=["APPROVED"],
        content_hash=hashlib.sha256(asset_type.encode("utf-8")).hexdigest(),
    )


@pytest.mark.parametrize(
    ("asset_type", "expected_outcomes"),
    [
        (
            "bond",
            {
                "bond.executable_total_return",
                "bond.valuation_total_return",
                "bond.credit_event",
            },
        ),
        (
            "fund",
            {"fund.etf_market_return", "fund.dealing_event"},
        ),
        (
            "futures",
            {
                "futures.contract_pnl",
                "futures.roll_aware_pnl",
                "futures.close_avoided_loss",
            },
        ),
        (
            "option",
            {
                "option.underlying_direction",
                "option.iv_direction",
                "option.exact_contract_net_profit",
                "option.close_avoided_loss",
            },
        ),
        (
            "fx",
            {"fx.direction_pnl", "fx.action_utility", "fx.risk_path"},
        ),
        (
            "crypto",
            {"crypto.spot_pnl", "crypto.benchmark_excess", "crypto.risk_path"},
        ),
    ],
)
def test_plugin_uses_asset_specific_heads_and_outcomes(
    asset_type: str, expected_outcomes: set[str]
) -> None:
    """A scorecard cannot flatten bonds, funds and derivatives into one price return."""
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get(asset_type)  # type: ignore[arg-type]
    raw = _raw(asset_type)
    quality = plugin.assess_quality(raw)
    eligible = plugin.promote_snapshot(raw, quality)

    assert eligible is not None
    candidate = plugin.make_decision(
        plugin.compute_features(eligible),
        quality,
        position_context="UNKNOWN",
        horizon_code="standard",
        snapshot=raw,
    )
    outcomes = plugin.score_outcome(
        decision=candidate,
        horizon_code="standard",
        as_of=raw.cutoff_at,
        snapshot=raw,
    )

    assert {outcome.outcome_kind for outcome in outcomes} == expected_outcomes
    assert len({outcome.outcome_kind for outcome in outcomes}) == len(outcomes)
    head_hashes = {head.head_spec_hash for head in candidate.prediction_heads}
    assert {outcome.head_spec_hash for outcome in outcomes}.issubset(head_hashes)
    assert sum(head.primary_for_promotion for head in candidate.prediction_heads) == 1


@pytest.mark.parametrize(
    ("asset_type", "container", "field", "reason_code"),
    [
        ("bond", "bond", "cashflows", "BOND.CASHFLOWS_MISSING"),
        ("fund", "fund", "official_nav", "FUND.OFFICIAL_NAV_MISSING"),
        ("futures", "snapshot", "bid", "FUTURES.BID_ASK_MISSING"),
        ("option", "option", "chain", "OPTION.CHAIN_INCOMPLETE"),
        ("fx", "snapshot", "ask", "FX.BID_ASK_MISSING"),
        ("crypto", "crypto", "depth_1pct", "CRYPTO.DEPTH_INSUFFICIENT"),
    ],
)
def test_plugin_preserves_raw_missing_values_then_returns_an_asset_specific_rejection(
    asset_type: str, container: str, field: str, reason_code: str
) -> None:
    """Missing domain fields may not silently become zero or a generic momentum signal."""
    raw = _raw(asset_type)
    raw.raw_fields[container].pop(field)

    quality = DEFAULT_ASSET_RESEARCH_REGISTRY.get(asset_type).assess_quality(raw)  # type: ignore[arg-type]

    assert quality.status == "REJECTED"
    assert reason_code in quality.reason_codes


@pytest.mark.parametrize(
    ("asset_type", "domain_fields", "feature_name", "expected_direction"),
    [
        (
            "bond",
            {"bond": {"yield_change_bps": 300}},
            "yield_change_bps",
            "SHORT",
        ),
        (
            "fund",
            {"fund": {"official_nav_return_20": 0.02, "benchmark_return_20": 0.10}},
            "excess_return_20",
            "SHORT",
        ),
        (
            "futures",
            {"futures": {"basis_change": -0.20}},
            "basis_change",
            "SHORT",
        ),
        (
            "option",
            {
                "option": {
                    "underlying_return_20": 0.06,
                    "implied_volatility": 0.50,
                }
            },
            "contract_edge",
            "LONG",
        ),
        (
            "fx",
            {"fx": {"valuation_gap": -0.20}},
            "valuation_gap",
            "SHORT",
        ),
        (
            "crypto",
            {"crypto": {"funding_rate": 0.02}},
            "funding_rate",
            "SHORT",
        ),
    ],
)
def test_plugin_domain_features_can_override_the_same_price_momentum(
    asset_type: str,
    domain_fields: dict[str, dict[str, float]],
    feature_name: str,
    expected_direction: str,
) -> None:
    """A common two-point price history must not flatten six domain policies."""
    raw = _raw(asset_type)
    for section, fields in domain_fields.items():
        raw.raw_fields[section].update(fields)
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get(asset_type)  # type: ignore[arg-type]
    quality = plugin.assess_quality(raw)
    eligible = plugin.promote_snapshot(raw, quality)

    assert eligible is not None
    features = plugin.compute_features(eligible)
    candidate = plugin.make_decision(
        features,
        quality,
        position_context="UNKNOWN",
        horizon_code="standard",
        snapshot=raw,
    )

    assert features.feature_version == f"{asset_type}-domain-features-v2"
    assert features.values[feature_name] is not None
    assert features.values["domain_signal_count"]
    assert candidate.normalized_direction == expected_direction
    expected_model_revision = "v3" if asset_type == "option" else "v2"
    assert candidate.prediction_heads[0].probability_model_version.endswith(
        f"domain-shadow-rule-{expected_model_revision}"
    )


def test_session_horizon_refuses_weekday_inference_then_uses_the_frozen_calendar() -> None:
    """A futures maturity exists only when its own source calendar covers it."""
    raw = _raw("futures")
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("futures")
    quality = plugin.assess_quality(raw)
    eligible = plugin.promote_snapshot(raw, quality)
    assert eligible is not None
    candidate = plugin.make_decision(
        plugin.compute_features(eligible),
        quality,
        position_context="UNKNOWN",
        horizon_code="standard",
        snapshot=raw,
    )

    unavailable = plugin.score_outcome(
        decision=candidate,
        horizon_code="standard",
        as_of=raw.cutoff_at,
        snapshot=raw,
    )
    assert all(outcome.maturity_at is None for outcome in unavailable)
    assert all("COMMON.CALENDAR_UNAVAILABLE" in outcome.reason_codes for outcome in unavailable)

    closes = [
        (raw.cutoff_at + timedelta(days=index + 1, hours=16)).isoformat() for index in range(20)
    ]
    raw.raw_fields["calendar"] = {"calendar_id": "FIXTURE", "sessions": closes}
    resolved = plugin.score_outcome(
        decision=candidate,
        horizon_code="standard",
        as_of=raw.cutoff_at,
        snapshot=raw,
    )

    assert all(outcome.maturity_reason == "HORIZON_REACHED" for outcome in resolved)
    assert {outcome.maturity_at for outcome in resolved} == {datetime.fromisoformat(closes[-1])}


def test_crypto_calendar_day_horizon_needs_no_exchange_weekday_calendar() -> None:
    raw = _raw("crypto")
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("crypto")
    quality = plugin.assess_quality(raw)
    eligible = plugin.promote_snapshot(raw, quality)
    assert eligible is not None
    candidate = plugin.make_decision(
        plugin.compute_features(eligible),
        quality,
        position_context="UNKNOWN",
        horizon_code="standard",
        snapshot=raw,
    )

    outcomes = plugin.score_outcome(
        decision=candidate,
        horizon_code="standard",
        as_of=raw.cutoff_at,
        snapshot=raw,
    )

    assert {outcome.maturity_at for outcome in outcomes} == {raw.cutoff_at + timedelta(days=20)}
    assert all(outcome.metrics["calendar_source"] == "UTC_CONTINUOUS" for outcome in outcomes)


def test_asset_level_fx_reference_stays_research_only_after_promotion() -> None:
    """A venue-free pair is researchable, but cannot become a product action."""
    raw = _raw("fx").model_copy(
        update={
            "identity": InstrumentIdentity(
                asset_type="fx",
                identity_level="ASSET",
                canonical_id="fx:reference:EUR/USD",
                display_symbol="EUR/USD",
                name="EUR/USD reference pair",
                venue=None,
                currency="USD",
                timezone="UTC",
                identifier_type="CURRENCY_PAIR",
                identifier_value="EUR/USD",
                product_type="REFERENCE_PAIR",
                metadata_version="fixture-v1",
                details=FxIdentityDetails(
                    base_currency="EUR",
                    quote_currency="USD",
                    settlement_type="SPOT",
                    calendar_id="FX",
                    price_convention="EUR_PER_USD",
                ),
            )
        }
    )
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("fx")
    quality = plugin.assess_quality(raw)
    eligible = plugin.promote_snapshot(raw, quality)

    assert eligible is not None
    candidate = plugin.make_decision(
        plugin.compute_features(eligible),
        quality,
        position_context="FLAT",
        horizon_code="standard",
        snapshot=raw,
    )
    published = apply_publication_gate(
        candidate,
        promoted=True,
        region_restricted=False,
        short_open_allowed=True,
    )

    assert candidate.actionability == "RESEARCH_ONLY"
    assert candidate.prediction_heads == []
    assert candidate.primary_head_code is None
    assert candidate.reason_codes == ["FX.REFERENCE_ONLY"]
    assert (
        plugin.score_outcome(
            decision=candidate,
            horizon_code="standard",
            as_of=raw.cutoff_at,
            snapshot=raw,
        )
        == []
    )
    assert published.actionability == "RESEARCH_ONLY"
    assert published.recommendation == "HOLD"
    assert published.trade_intent == "NONE"
    assert published.reason_codes == ["FX.REFERENCE_ONLY"]


def test_futures_product_stays_research_only_until_exact_contract_is_frozen() -> None:
    """A futures product lacks the immutable contract terms needed for a signal."""
    raw = _raw("futures").model_copy(
        update={
            "identity": InstrumentIdentity(
                asset_type="futures",
                identity_level="PRODUCT",
                canonical_id="futures:product:IF",
                display_symbol="IF",
                name="Index futures product",
                venue="FIXTURE",
                currency="USD",
                timezone="UTC",
                identifier_type="PRODUCT_CODE",
                identifier_value="IF",
                product_type="INDEX_FUTURES",
                metadata_version="fixture-v1",
                details=FuturesIdentityDetails(
                    product_code="IF",
                    trading_calendar_id="FIXTURE",
                ),
            )
        }
    )
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("futures")
    quality = plugin.assess_quality(raw)
    eligible = plugin.promote_snapshot(raw, quality)

    assert eligible is not None
    candidate = plugin.make_decision(
        plugin.compute_features(eligible),
        quality,
        position_context="FLAT",
        horizon_code="standard",
        snapshot=raw,
    )
    published = apply_publication_gate(
        candidate,
        promoted=True,
        region_restricted=False,
        short_open_allowed=True,
    )

    assert candidate.actionability == "RESEARCH_ONLY"
    assert candidate.prediction_heads == []
    assert candidate.primary_head_code is None
    assert candidate.reason_codes == ["FUTURES.PRODUCT_LEVEL_RESEARCH_ONLY"]
    assert (
        plugin.score_outcome(
            decision=candidate,
            horizon_code="standard",
            as_of=raw.cutoff_at,
            snapshot=raw,
        )
        == []
    )
    assert published.actionability == "RESEARCH_ONLY"
    assert published.recommendation == "HOLD"
    assert published.trade_intent == "NONE"
    assert published.reason_codes == ["FUTURES.PRODUCT_LEVEL_RESEARCH_ONLY"]


def test_confirmed_perpetual_bond_is_degraded_research_only_not_an_action() -> None:
    """An issuer-confirmed perpetual has no maturity-based executable model."""
    raw = _raw("bond")
    raw.raw_fields["bond"].update({"is_perpetual": True, "maturity_date": None})
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("bond")
    quality = plugin.assess_quality(raw)
    eligible = plugin.promote_snapshot(raw, quality)

    assert quality.status == "DEGRADED"
    assert quality.reason_codes == ["BOND.PERPETUAL_MODEL_REQUIRED"]
    assert eligible is not None
    candidate = plugin.make_decision(
        plugin.compute_features(eligible),
        quality,
        position_context="FLAT",
        horizon_code="standard",
        snapshot=raw,
    )
    published = apply_publication_gate(
        candidate,
        promoted=True,
        region_restricted=False,
        short_open_allowed=True,
    )

    assert candidate.quality_status == "DEGRADED"
    assert candidate.actionability == "RESEARCH_ONLY"
    assert candidate.prediction_heads == []
    assert candidate.primary_head_code is None
    assert candidate.reason_codes == ["BOND.PERPETUAL_MODEL_REQUIRED"]
    assert (
        plugin.score_outcome(
            decision=candidate,
            horizon_code="standard",
            as_of=raw.cutoff_at,
            snapshot=raw,
        )
        == []
    )
    assert published.quality_status == "DEGRADED"
    assert published.actionability == "RESEARCH_ONLY"
    assert published.recommendation == "HOLD"
    assert published.trade_intent == "NONE"
    assert published.reason_codes == ["BOND.PERPETUAL_MODEL_REQUIRED"]


@pytest.mark.parametrize(
    ("asset_type", "container", "updates", "reason_code"),
    [
        ("bond", "bond", {"evidence_coverage_low": True}, "COMMON.EVIDENCE_COVERAGE_LOW"),
        ("fund", "fund", {"management_evidence_available": False}, "FUND.MANAGEMENT_EVIDENCE_LOW"),
        (
            "futures",
            "futures",
            {"term_structure_complete": False},
            "FUTURES.TERM_STRUCTURE_INCOMPLETE",
        ),
        (
            "option",
            "option",
            {"surface_coverage_complete": False},
            "OPTION.SURFACE_COVERAGE_INSUFFICIENT",
        ),
        ("fx", "fx", {"macro_available": False}, "FX.MACRO_MISSING"),
        ("crypto", "crypto", {"onchain_provider_supported": False}, "CRYPTO.ONCHAIN_UNSUPPORTED"),
    ],
)
def test_secondary_evidence_gap_is_degraded_research_only(
    asset_type: str,
    container: str,
    updates: dict[str, object],
    reason_code: str,
) -> None:
    """Incomplete secondary evidence can remain visible but never actionable."""
    raw = _raw(asset_type)
    raw.raw_fields[container].update(updates)
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get(asset_type)  # type: ignore[arg-type]
    quality = plugin.assess_quality(raw)
    eligible = plugin.promote_snapshot(raw, quality)

    assert quality.status == "DEGRADED"
    assert quality.reason_codes == [reason_code]
    assert eligible is not None
    candidate = plugin.make_decision(
        plugin.compute_features(eligible),
        quality,
        position_context="FLAT",
        horizon_code="standard",
        snapshot=raw,
    )
    published = apply_publication_gate(
        candidate,
        promoted=True,
        region_restricted=False,
        short_open_allowed=True,
    )

    assert candidate.actionability == "RESEARCH_ONLY"
    assert candidate.prediction_heads == []
    assert candidate.primary_head_code is None
    assert candidate.reason_codes == [reason_code]
    assert (
        plugin.score_outcome(
            decision=candidate,
            horizon_code="standard",
            as_of=raw.cutoff_at,
            snapshot=raw,
        )
        == []
    )
    assert published.actionability == "RESEARCH_ONLY"
    assert published.recommendation == "HOLD"
    assert published.trade_intent == "NONE"
    assert published.reason_codes == [reason_code]


def test_fx_reference_quote_is_degraded_research_only_not_an_executable_price() -> None:
    """Reference FX can inform a report but cannot replace a venue bid/ask."""
    raw = _raw("fx")
    raw.raw_fields["snapshot"].pop("bid")
    raw.raw_fields["snapshot"].pop("ask")
    raw.source_manifest["quote_kind"] = "REFERENCE"
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("fx")
    quality = plugin.assess_quality(raw)
    eligible = plugin.promote_snapshot(raw, quality)

    assert quality.status == "DEGRADED"
    assert quality.reason_codes == ["FX.REFERENCE_ONLY"]
    assert eligible is not None
    candidate = plugin.make_decision(
        plugin.compute_features(eligible),
        quality,
        position_context="FLAT",
        horizon_code="standard",
        snapshot=raw,
    )
    published = apply_publication_gate(
        candidate,
        promoted=True,
        region_restricted=False,
        short_open_allowed=True,
    )

    assert candidate.actionability == "RESEARCH_ONLY"
    assert candidate.reason_codes == ["FX.REFERENCE_ONLY"]
    assert published.actionability == "RESEARCH_ONLY"
    assert published.recommendation == "HOLD"
    assert published.trade_intent == "NONE"


def test_official_bond_valuation_without_bid_ask_is_degraded_research_only() -> None:
    """A valuation is useful evidence but not an executable bond quote."""
    raw = _raw("bond")
    raw.raw_fields["snapshot"].pop("bid")
    raw.raw_fields["snapshot"].pop("ask")
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("bond")
    quality = plugin.assess_quality(raw)
    eligible = plugin.promote_snapshot(raw, quality)

    assert quality.status == "DEGRADED"
    assert quality.reason_codes == ["BOND.VALUATION_NOT_EXECUTABLE"]
    assert eligible is not None
    candidate = plugin.make_decision(
        plugin.compute_features(eligible),
        quality,
        position_context="FLAT",
        horizon_code="standard",
        snapshot=raw,
    )
    published = apply_publication_gate(
        candidate,
        promoted=True,
        region_restricted=False,
        short_open_allowed=True,
    )

    assert candidate.actionability == "RESEARCH_ONLY"
    assert published.actionability == "RESEARCH_ONLY"
    assert published.recommendation == "HOLD"
    assert published.trade_intent == "NONE"


@pytest.mark.parametrize(
    ("asset_type", "container", "updates", "reason_code"),
    [
        ("bond", "bond", {"specialized_model_required": True}, "BOND.SPECIALIZED_MODEL_REQUIRED"),
        (
            "fund",
            "fund",
            {"fund_type": "LEVERAGED"},
            "FUND.SPECIALIZED_MODEL_REQUIRED",
        ),
    ],
)
def test_specialized_asset_route_cannot_become_an_action_after_promotion(
    asset_type: str,
    container: str,
    updates: dict[str, object],
    reason_code: str,
) -> None:
    """A generic model may not act on an asset requiring a dedicated model."""
    raw = _raw(asset_type)
    raw.raw_fields[container].update(updates)
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get(asset_type)  # type: ignore[arg-type]
    quality = plugin.assess_quality(raw)
    eligible = plugin.promote_snapshot(raw, quality)

    assert quality.status == "ELIGIBLE"
    assert eligible is not None
    candidate = plugin.make_decision(
        plugin.compute_features(eligible),
        quality,
        position_context="FLAT",
        horizon_code="standard",
        snapshot=raw,
    )
    published = apply_publication_gate(
        candidate,
        promoted=True,
        region_restricted=False,
        short_open_allowed=True,
    )

    assert candidate.actionability == "RESEARCH_ONLY"
    assert candidate.prediction_heads == []
    assert candidate.primary_head_code is None
    assert candidate.reason_codes == [reason_code]
    assert published.actionability == "RESEARCH_ONLY"
    assert published.recommendation == "HOLD"
    assert published.trade_intent == "NONE"
    assert published.reason_codes == [reason_code]
