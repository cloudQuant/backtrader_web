"""FX outcome scoring must preserve reciprocal quote-side execution semantics."""

from decimal import Decimal

import pytest

from app.schemas.asset_research import FxIdentityDetails, InstrumentIdentity
from app.services.asset_research.outcomes import AssetOutcomeEvaluator


def _identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="fx",
        identity_level="PRODUCT",
        canonical_id="fx:fixture:eur-usd:spot",
        display_symbol="EUR/USD",
        name="Fixture EUR/USD",
        venue="FIXTURE",
        currency="USD",
        timezone="UTC",
        identifier_type="PAIR",
        identifier_value="EUR/USD",
        product_type="SPOT",
        metadata_version="fixture-v1",
        details=FxIdentityDetails(
            base_currency="EUR",
            quote_currency="USD",
            settlement_type="SPOT",
            settlement_currency="USD",
            calendar_id="FX_FIXTURE",
            price_convention="EUR_PER_USD",
        ),
    )


def test_fx_outcome_evaluator_normalizes_reciprocal_source_quotes_before_scoring_long_base() -> None:
    result = AssetOutcomeEvaluator._score_fx_execution(
        direction="LONG",
        outcome_kind="fx.direction_pnl",
        probabilities={"LONG": 0.7, "SHORT": 0.2, "NEUTRAL": 0.1},
        entry_fields={"snapshot": {"bid": 0.9090, "ask": 0.9092}},
        observed_fields={"snapshot": {"bid": 0.9010, "ask": 0.9012}},
        identity=_identity(),
        cost_snapshot={"total_cost_rate": 0.001},
        primary_for_promotion=True,
    )

    assert result.status == "SCORED"
    assert result.entry_price == Decimal("1") / Decimal("0.9090")
    assert result.entry_price_basis == "inverse_bid"
    assert result.exit_price == Decimal("1") / Decimal("0.9012")
    assert result.exit_price_basis == "inverse_ask"
    assert float(result.gross_return or 0) == pytest.approx(0.9090 / 0.9012 - 1)
    assert float(result.net_return or 0) == pytest.approx(0.9090 / 0.9012 - 1 - 0.001)


def test_fx_outcome_evaluator_refuses_to_turn_a_missing_cost_snapshot_into_zero_cost() -> None:
    result = AssetOutcomeEvaluator._score_fx_execution(
        direction="LONG",
        outcome_kind="fx.direction_pnl",
        probabilities={"LONG": 0.7, "SHORT": 0.2, "NEUTRAL": 0.1},
        entry_fields={"snapshot": {"bid": 0.9090, "ask": 0.9092}},
        observed_fields={"snapshot": {"bid": 0.9010, "ask": 0.9012}},
        identity=_identity(),
        cost_snapshot={},
        primary_for_promotion=True,
    )

    assert result.status == "UNSCORABLE"
    assert result.reason_codes == ["COMMON.OUTCOME_COST_SNAPSHOT_MISSING"]
