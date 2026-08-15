"""Deterministic publication gates for research-only multi-asset decisions."""

from __future__ import annotations

from app.schemas.asset_research import CryptoResearchDetails, ResearchDecision

_IDENTITY_SCOPE_RESEARCH_ONLY_REASONS = frozenset(
    {
        "BOND.ASSET_LEVEL_RESEARCH_ONLY",
        "BOND.PERPETUAL_MODEL_REQUIRED",
        "BOND.SPECIALIZED_MODEL_REQUIRED",
        "FUND.SPECIALIZED_MODEL_REQUIRED",
        "FUTURES.PRODUCT_LEVEL_RESEARCH_ONLY",
        "FX.REFERENCE_ONLY",
        "CRYPTO.ASSET_LEVEL_RESEARCH_ONLY",
    }
)


def _with_reason(decision: ResearchDecision, reason_code: str) -> list[str]:
    return list(dict.fromkeys([*decision.reason_codes, reason_code]))


def _safe_avoid(
    decision: ResearchDecision,
    *,
    actionability: str,
    reason_code: str,
) -> ResearchDecision:
    return decision.model_copy(
        update={
            "market_view": "INDETERMINATE",
            "normalized_direction": "INDETERMINATE",
            "recommendation": "AVOID",
            "actionability": actionability,
            "trade_intent": "NONE",
            "confidence": None,
            "prediction_heads": [],
            "primary_head_code": None,
            "reason_codes": _with_reason(decision, reason_code),
            "execution_disabled": True,
        }
    )


def _research_only(
    decision: ResearchDecision, *, reason_code: str | None = "COMMON.MODEL_NOT_PROMOTED"
) -> ResearchDecision:
    """Clear public actionability while preserving an identity-scope reason."""
    reason_codes = (
        _with_reason(decision, reason_code)
        if reason_code is not None
        else list(decision.reason_codes)
    )
    return decision.model_copy(
        update={
            "market_view": "INDETERMINATE",
            "normalized_direction": "INDETERMINATE",
            "recommendation": "HOLD",
            "actionability": "RESEARCH_ONLY",
            "trade_intent": "NONE",
            "confidence": None,
            "prediction_heads": [],
            "primary_head_code": None,
            "reason_codes": reason_codes,
            "execution_disabled": True,
        }
    )


def _truth_table(decision: ResearchDecision, *, short_open_allowed: bool) -> ResearchDecision:
    direction = decision.normalized_direction
    position = decision.position_context
    recommendation = "HOLD"
    intent = "NONE"

    if direction == "INDETERMINATE":
        return _safe_avoid(
            decision,
            actionability="INSUFFICIENT_DATA",
            reason_code="COMMON.RISK_NOT_MEASURABLE",
        )
    if position == "FLAT":
        if direction == "LONG":
            recommendation, intent = "BUY", "OPEN"
        elif direction == "SHORT":
            recommendation, intent = "SELL", "OPEN" if short_open_allowed else "NONE"
    elif position == "LONG":
        if direction == "SHORT":
            recommendation, intent = "SELL", "CLOSE"
        else:
            recommendation, intent = "HOLD", "KEEP"
    elif position == "SHORT":
        if direction == "LONG":
            recommendation, intent = "BUY", "CLOSE"
        else:
            recommendation, intent = "HOLD", "KEEP"
    elif position == "UNKNOWN":
        if direction == "LONG":
            recommendation = "BUY"
        elif direction == "SHORT":
            recommendation = "SELL"

    return decision.model_copy(
        update={
            "recommendation": recommendation,
            "actionability": "ACTIONABLE",
            "trade_intent": intent,
            "execution_disabled": True,
        }
    )


def _apply_option_guard(
    decision: ResearchDecision, *, close_context_authorized: bool
) -> ResearchDecision | None:
    """Return a safe decision if an option v1 invariant disallows the candidate."""
    if decision.asset_type != "option":
        return None
    if decision.normalized_direction == "SHORT" or decision.position_context == "SHORT":
        return _safe_avoid(
            decision,
            actionability="INSUFFICIENT_DATA",
            reason_code="OPTION.NAKED_SHORT_BLOCKED",
        )
    if decision.position_context == "LONG" and decision.normalized_direction == "NEUTRAL":
        if not close_context_authorized:
            return _safe_avoid(
                decision,
                actionability="INSUFFICIENT_DATA",
                reason_code="OPTION.ACTION_TUPLE_BLOCKED",
            )
        return decision.model_copy(
            update={
                "recommendation": "SELL",
                "actionability": "ACTIONABLE",
                "trade_intent": "CLOSE",
                "execution_disabled": True,
            }
        )
    return None


def _flat_short_is_unsupported_by_product(candidate: ResearchDecision) -> bool:
    """Return whether a flat/unknown short is invalid for the frozen product.

    The server-owned ``short_open_allowed`` capability determines whether a
    supported linear product receives ``OPEN`` or ``NONE``. It cannot make a
    bond, fund, bare crypto asset, or spot pair shortable. Those product types
    must fail closed even if a future caller accidentally supplies the generic
    capability flag.
    """
    if candidate.asset_type in {"bond", "fund"}:
        return True
    if candidate.asset_type != "crypto":
        return False
    details = candidate.asset_details
    return not (
        isinstance(details, CryptoResearchDetails)
        and details.product_type in {"PERPETUAL", "DELIVERY_FUTURE"}
    )


def apply_publication_gate(
    candidate: ResearchDecision,
    *,
    promoted: bool,
    region_restricted: bool,
    short_open_allowed: bool = False,
    option_close_context_authorized: bool = False,
) -> ResearchDecision:
    """Publish only an eligible, promoted and compliance-safe research decision.

    This function is deliberately pure so it is shared by interactive runs,
    retries and schedules.  It never grants execution capability.
    """
    if region_restricted:
        region_reason = {
            "crypto": "CRYPTO.REGION_RESTRICTED",
            "fx": "FX.REGION_RESTRICTED",
        }.get(candidate.asset_type, "COMMON.REGION_RESTRICTED")
        return _safe_avoid(
            candidate,
            actionability="REGION_RESTRICTED",
            reason_code=region_reason,
        )
    if candidate.quality_status == "REJECTED":
        return _safe_avoid(
            candidate,
            actionability="INSUFFICIENT_DATA",
            reason_code="COMMON.INSUFFICIENT_DATA",
        )
    if candidate.quality_status == "DEGRADED":
        return _research_only(candidate, reason_code=None)
    if candidate.actionability == "RESEARCH_ONLY" and any(
        reason in _IDENTITY_SCOPE_RESEARCH_ONLY_REASONS for reason in candidate.reason_codes
    ):
        return _research_only(candidate, reason_code=None)
    if not promoted:
        return _research_only(candidate)
    option_guard = _apply_option_guard(
        candidate,
        close_context_authorized=option_close_context_authorized,
    )
    if option_guard is not None:
        return option_guard
    if (
        candidate.normalized_direction == "SHORT"
        and candidate.position_context in {"FLAT", "UNKNOWN"}
        and _flat_short_is_unsupported_by_product(candidate)
    ):
        # A bearish view can be recorded for research, but an unsupported
        # product must never turn a generic capability flag into a naked sell
        # recommendation. A real long holding may still be reduced/closed by
        # the common truth table below.
        return _research_only(candidate, reason_code="COMMON.SHORT_OPEN_UNSUPPORTED")
    return _truth_table(candidate, short_open_allowed=short_open_allowed)
