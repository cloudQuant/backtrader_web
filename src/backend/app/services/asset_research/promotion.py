"""Fail-closed T2 evidence checks for publishing asset-research directions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from hmac import compare_digest

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_research import AssetModelRegistry, AssetModelStatusEvent
from app.schemas.asset_research import PromotionEvidenceMetrics, PromotionScope
from app.services.asset_research.data import canonical_json_hash


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive DATETIME reads and aware production reads."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def promotion_scope_from_registry_record(record: AssetModelRegistry) -> PromotionScope | None:
    """Rebuild the normalized promotion scope from one registry projection.

    ``quote_or_settlement_asset`` predates a dedicated registry column and is
    intentionally stored in ``scope_parameters_json``.  It is removed before
    validating the remaining plugin parameters so the canonical scope has one
    unambiguous representation.
    """
    if not isinstance(record.scope_parameters_json, Mapping):
        return None

    scope_parameters = dict(record.scope_parameters_json)
    quote_or_settlement_asset = scope_parameters.pop("quote_or_settlement_asset", None)
    if quote_or_settlement_asset is not None and not isinstance(quote_or_settlement_asset, str):
        return None

    try:
        return PromotionScope(
            scope_type=record.promotion_scope_type,
            asset_type=record.asset_type,
            instrument_class=record.instrument_class,
            canonical_id=record.canonical_id_scope,
            venue=record.venue_scope,
            product_type=record.product_type_scope,
            quote_or_settlement_asset=quote_or_settlement_asset,
            signal_head=record.signal_head,
            horizon_code=record.horizon_code,
            scope_parameters=scope_parameters,
        )
    except (TypeError, ValidationError):
        return None


def verified_promotion_scope(record: AssetModelRegistry) -> PromotionScope | None:
    """Return a scope only when its registry projection reproduces its key."""
    scope = promotion_scope_from_registry_record(record)
    stored_key = record.promotion_scope_key
    if scope is None or not isinstance(stored_key, str):
        return None
    if not compare_digest(scope.scope_key(), stored_key):
        return None
    return scope


def has_complete_t2_metrics(
    record: AssetModelRegistry, *, approved_at: datetime | None = None
) -> bool:
    """Return whether a projected registry row carries all required T2 evidence.

    A row's ``PROMOTED`` label is a projection, not evidence.  The projection is
    deliberately insufficient unless its frozen metrics can be parsed and meet
    the documented statistical, utility and forward-validation gates.
    """
    try:
        metrics = PromotionEvidenceMetrics.model_validate(record.metrics_json)
    except ValidationError:
        return False

    if metrics.head_spec_hash != record.head_spec_hash:
        return False
    effective_approved_at = approved_at if approved_at is not None else record.approved_at
    if effective_approved_at is None:
        return False
    if _as_utc(record.training_cutoff_at) > _as_utc(effective_approved_at):
        return False
    if metrics.sample_count < 200 or metrics.unique_evaluation_days < 60:
        return False
    if metrics.evaluation_artifact_hash == "0" * 64:
        return False
    if metrics.model_card_hash == "0" * 64:
        return False
    if metrics.drift_report_hash == "0" * 64:
        return False
    if metrics.market_regime_count < 3:
        return False
    if not all(
        (
            metrics.walk_forward_train_before_test,
            metrics.overlap_purged,
            metrics.embargo_applied,
            metrics.vintage_data_enforced,
            metrics.block_length_covers_max_overlap,
            metrics.reliability_reviewed,
            metrics.tail_risk_approved,
            metrics.maximum_drawdown_approved,
            metrics.coverage_approved,
            metrics.data_failure_rate_approved,
            metrics.multiple_comparisons_controlled,
        )
    ):
        return False
    if metrics.brier_skill_score <= 0:
        return False
    if metrics.mean_net_utility <= 0 or metrics.delta_net_utility_ci_lower < 0:
        return False
    minimum_shadow_days = 90 if record.asset_type == "crypto" else 60
    if metrics.forward_shadow_days < minimum_shadow_days:
        return False
    if record.promotion_scope_type == "POOLED" and (
        metrics.max_instrument_share is None
        or metrics.max_instrument_share > 0.40
        or metrics.cross_instrument_extrapolation_reviewed is not True
    ):
        return False
    if (
        record.asset_type == "futures"
        and record.promotion_scope_type == "INSTRUMENT_SPECIFIC"
        and (
            metrics.futures_contract_month_count is None or metrics.futures_contract_month_count < 3
        )
    ):
        return False
    if (
        record.asset_type == "option"
        and record.promotion_scope_type == "INSTRUMENT_SPECIFIC"
        and (
            metrics.option_expiry_count is None
            or metrics.option_expiry_count < 2
            or metrics.option_strike_count is None
            or metrics.option_strike_count < 2
        )
    ):
        return False
    return True


def has_required_model_approvals(record: AssetModelRegistry) -> bool:
    """Return whether the immutable registry evidence names every required approver."""
    required = {"model_quality", "product", "compliance", "data_license", "security"}
    approvals = record.approval_set_json or {}
    if not record.evidence_uri or not record.evidence_content_hash:
        return False
    if not isinstance(approvals, Mapping):
        return False
    for name in required:
        value = approvals.get(name)
        if value is True:
            continue
        if isinstance(value, Mapping) and value.get("approved") is True:
            continue
        return False
    return True


async def has_matching_promotion_event(
    db: AsyncSession, *, record: AssetModelRegistry, as_of_at: datetime
) -> bool:
    """Require a pre-cutoff immutable ``SHADOW -> PROMOTED`` evidence event."""
    if record.approved_at is None:
        return False

    events = list(
        (
            await db.execute(
                select(AssetModelStatusEvent).where(
                    AssetModelStatusEvent.model_registry_id == record.id,
                    AssetModelStatusEvent.from_status == "SHADOW",
                    AssetModelStatusEvent.to_status == "PROMOTED",
                    AssetModelStatusEvent.evidence_uri == record.evidence_uri,
                    AssetModelStatusEvent.evidence_content_hash == record.evidence_content_hash,
                )
            )
        ).scalars()
    )
    expected_metrics_hash = canonical_json_hash(record.metrics_json)
    approved_at = _as_utc(record.approved_at)
    cutoff_at = _as_utc(as_of_at)
    return any(
        bool(event.reason_codes_json)
        and approved_at <= _as_utc(event.created_at) <= cutoff_at
        and canonical_json_hash(event.metrics_snapshot_json) == expected_metrics_hash
        for event in events
    )
