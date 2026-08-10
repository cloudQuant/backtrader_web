"""Safety-critical publication rules for multi-asset research decisions."""

import pytest

from app.schemas.asset_research import CryptoResearchDetails, ResearchDecision
from app.services.asset_research.decision import apply_publication_gate


def _candidate(
    *,
    asset_type: str = "futures",
    direction: str = "LONG",
    position_context: str = "FLAT",
) -> ResearchDecision:
    return ResearchDecision(
        asset_type=asset_type,
        market_view={
            "LONG": "BULLISH",
            "SHORT": "BEARISH",
            "NEUTRAL": "NEUTRAL",
            "INDETERMINATE": "INDETERMINATE",
        }[direction],
        normalized_direction=direction,
        position_context=position_context,
        horizon_code="standard",
        quality_status="ELIGIBLE",
        reason_codes=[],
    )


def test_unpromoted_candidate_is_never_exposed_as_directional_advice() -> None:
    """A valid shadow signal is retained internally but published as research-only."""
    candidate = _candidate()

    published = apply_publication_gate(candidate, promoted=False, region_restricted=False)

    assert candidate.normalized_direction == "LONG"
    assert published.market_view == "INDETERMINATE"
    assert published.normalized_direction == "INDETERMINATE"
    assert published.recommendation == "HOLD"
    assert published.trade_intent == "NONE"
    assert published.actionability == "RESEARCH_ONLY"
    assert published.execution_disabled is True
    assert "COMMON.MODEL_NOT_PROMOTED" in published.reason_codes


def test_rejected_candidate_is_always_publicly_avoided() -> None:
    """Quality rejection must clear a candidate direction before any UI can render it."""
    candidate = _candidate(direction="SHORT").model_copy(update={"quality_status": "REJECTED"})

    published = apply_publication_gate(candidate, promoted=True, region_restricted=False)

    assert published.market_view == "INDETERMINATE"
    assert published.normalized_direction == "INDETERMINATE"
    assert published.recommendation == "AVOID"
    assert published.trade_intent == "NONE"
    assert published.actionability == "INSUFFICIENT_DATA"
    assert published.confidence is None
    assert published.prediction_heads == []
    assert "COMMON.INSUFFICIENT_DATA" in published.reason_codes


def test_option_naked_short_is_blocked_before_any_publication_path() -> None:
    """Options v1 cannot publish a short-open research action."""
    candidate = _candidate(asset_type="option", direction="SHORT")

    published = apply_publication_gate(candidate, promoted=True, region_restricted=False)

    assert published.recommendation == "AVOID"
    assert published.normalized_direction == "INDETERMINATE"
    assert published.trade_intent == "NONE"
    assert published.actionability == "INSUFFICIENT_DATA"
    assert "OPTION.NAKED_SHORT_BLOCKED" in published.reason_codes


def test_unpromoted_option_close_signal_is_not_exposed_before_promotion() -> None:
    """An option-specific safety rule must not bypass the shadow publication gate."""
    candidate = _candidate(asset_type="option", direction="NEUTRAL", position_context="LONG")

    published = apply_publication_gate(candidate, promoted=False, region_restricted=False)

    assert published.normalized_direction == "INDETERMINATE"
    assert published.recommendation == "HOLD"
    assert published.trade_intent == "NONE"
    assert published.actionability == "RESEARCH_ONLY"


def test_promoted_option_close_requires_a_verified_exact_position_context() -> None:
    """A bare LONG label is never sufficient to publish SELL+CLOSE for an option."""
    candidate = _candidate(asset_type="option", direction="NEUTRAL", position_context="LONG")

    rejected = apply_publication_gate(candidate, promoted=True, region_restricted=False)
    authorized = apply_publication_gate(
        candidate,
        promoted=True,
        region_restricted=False,
        option_close_context_authorized=True,
    )

    assert rejected.normalized_direction == "INDETERMINATE"
    assert rejected.recommendation == "AVOID"
    assert rejected.trade_intent == "NONE"
    assert rejected.reason_codes[-1] == "OPTION.ACTION_TUPLE_BLOCKED"
    assert authorized.recommendation == "SELL"
    assert authorized.trade_intent == "CLOSE"


@pytest.mark.parametrize(
    ("position_context", "direction", "recommendation", "trade_intent", "actionability"),
    [
        ("FLAT", "LONG", "BUY", "OPEN", "ACTIONABLE"),
        ("FLAT", "SHORT", "SELL", "OPEN", "ACTIONABLE"),
        ("FLAT", "NEUTRAL", "HOLD", "NONE", "ACTIONABLE"),
        ("LONG", "LONG", "HOLD", "KEEP", "ACTIONABLE"),
        ("LONG", "SHORT", "SELL", "CLOSE", "ACTIONABLE"),
        ("LONG", "NEUTRAL", "HOLD", "KEEP", "ACTIONABLE"),
        ("SHORT", "LONG", "BUY", "CLOSE", "ACTIONABLE"),
        ("SHORT", "SHORT", "HOLD", "KEEP", "ACTIONABLE"),
        ("SHORT", "NEUTRAL", "HOLD", "KEEP", "ACTIONABLE"),
        ("UNKNOWN", "LONG", "BUY", "NONE", "ACTIONABLE"),
        ("UNKNOWN", "SHORT", "SELL", "NONE", "ACTIONABLE"),
        ("UNKNOWN", "NEUTRAL", "HOLD", "NONE", "ACTIONABLE"),
        ("FLAT", "INDETERMINATE", "AVOID", "NONE", "INSUFFICIENT_DATA"),
    ],
)
def test_futures_publication_uses_the_single_action_truth_table(
    position_context: str,
    direction: str,
    recommendation: str,
    trade_intent: str,
    actionability: str,
) -> None:
    """Linear products derive public actions only from the shared state table."""
    published = apply_publication_gate(
        _candidate(
            asset_type="futures",
            direction=direction,
            position_context=position_context,
        ),
        promoted=True,
        region_restricted=False,
        short_open_allowed=True,
    )

    assert published.recommendation == recommendation
    assert published.trade_intent == trade_intent
    assert published.actionability == actionability


def test_linear_short_view_keeps_a_sell_research_label_without_short_open_capability() -> None:
    """A linear product can keep its bearish view while its open intent remains disabled."""
    published = apply_publication_gate(
        _candidate(asset_type="futures", direction="SHORT", position_context="FLAT"),
        promoted=True,
        region_restricted=False,
        short_open_allowed=False,
    )

    assert published.normalized_direction == "SHORT"
    assert published.recommendation == "SELL"
    assert published.trade_intent == "NONE"
    assert published.actionability == "ACTIONABLE"


@pytest.mark.parametrize("asset_type", ["bond", "fund", "crypto"])
def test_long_only_or_unclassified_assets_never_turn_a_flat_short_view_into_a_short_open_signal(
    asset_type: str,
) -> None:
    """A generic capability flag must not convert an unsafe product into a naked short."""
    published = apply_publication_gate(
        _candidate(asset_type=asset_type, direction="SHORT", position_context="FLAT"),
        promoted=True,
        region_restricted=False,
        short_open_allowed=True,
    )

    assert published.normalized_direction == "INDETERMINATE"
    assert published.recommendation == "HOLD"
    assert published.trade_intent == "NONE"
    assert published.actionability == "RESEARCH_ONLY"
    assert "COMMON.SHORT_OPEN_UNSUPPORTED" in published.reason_codes


@pytest.mark.parametrize("asset_type", ["bond", "fund"])
def test_long_only_assets_translate_a_short_view_to_close_only_for_a_verified_long_context(
    asset_type: str,
) -> None:
    """For long-only products, SELL means reducing an existing long rather than opening short."""
    published = apply_publication_gate(
        _candidate(asset_type=asset_type, direction="SHORT", position_context="LONG"),
        promoted=True,
        region_restricted=False,
        short_open_allowed=True,
    )

    assert published.normalized_direction == "SHORT"
    assert published.recommendation == "SELL"
    assert published.trade_intent == "CLOSE"
    assert published.actionability == "ACTIONABLE"


def test_crypto_short_open_requires_a_frozen_derivative_product_type() -> None:
    """A configured perpetual can express a short only after its product type is frozen."""
    candidate = _candidate(asset_type="crypto", direction="SHORT", position_context="FLAT").model_copy(
        update={"asset_details": CryptoResearchDetails(product_type="PERPETUAL")}
    )

    published = apply_publication_gate(
        candidate,
        promoted=True,
        region_restricted=False,
        short_open_allowed=True,
    )

    assert published.normalized_direction == "SHORT"
    assert published.recommendation == "SELL"
    assert published.trade_intent == "OPEN"
    assert published.actionability == "ACTIONABLE"


def test_fx_region_restriction_keeps_its_asset_specific_reason_code() -> None:
    """The API taxonomy promised by the FX plan must survive the common gate."""
    published = apply_publication_gate(
        _candidate(asset_type="fx"), promoted=True, region_restricted=True
    )

    assert published.actionability == "REGION_RESTRICTED"
    assert published.reason_codes[-1] == "FX.REGION_RESTRICTED"
