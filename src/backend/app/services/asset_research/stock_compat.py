"""Read-only semantic adapter for the existing stock-signal history.

The legacy stock tables remain authoritative during the expand/migrate phase.
This adapter makes their meaning visible beside multi-asset research without
copying rows into ``asset_signal_predictions`` or inventing a canonical master
identity, source manifest, position context, or outcome-head specification.
"""

from __future__ import annotations

from app.models.stock_signal import StockSignalPrediction
from app.schemas.asset_research import (
    StockResearchCompatibilityHistoryResponse,
    StockResearchCompatibilityItem,
)
from app.services.asset_research.stock_reconciliation import (
    ReconciliationSummary,
    reconcile_batch,
)
from app.services.stock_signal.service import StockSignalService


class StockResearchCompatibilityAdapter:
    """Map visible legacy stock facts into an explicitly lossy versioned view."""

    COMPATIBILITY_VERSION = "stock-signal-v1-to-asset-research-v1"
    _SEMANTIC_LOSS = (
        "LEGACY_STOCK_CANONICAL_ID_UNRESOLVED",
        "LEGACY_STOCK_SOURCE_MANIFEST_UNAVAILABLE",
        "LEGACY_STOCK_POSITION_CONTEXT_UNAVAILABLE",
        "LEGACY_STOCK_OUTCOME_HEAD_UNVERSIONED",
    )
    _DECISIONS = {
        "BUY": ("BUY", "BULLISH", "LONG"),
        "SELL": ("SELL", "BEARISH", "SHORT"),
        "WATCH": ("HOLD", "NEUTRAL", "NEUTRAL"),
    }
    _QUALITY = {
        "eligible": "ELIGIBLE",
        "degraded": "DEGRADED",
        "rejected": "REJECTED",
    }

    def __init__(self, stock_signals: StockSignalService) -> None:
        self._stock_signals = stock_signals

    async def get_visible_history(
        self,
        *,
        user_id: str,
        symbol: str,
        source: str | None = None,
        limit: int = 30,
        cursor: str | None = None,
    ) -> StockResearchCompatibilityHistoryResponse:
        """Read legacy facts in their original visibility scope and cursor order."""
        records, next_cursor = await self._stock_signals.get_visible_history(
            user_id=user_id,
            symbol=symbol,
            source=source,
            limit=limit,
            cursor=cursor,
        )
        return StockResearchCompatibilityHistoryResponse(
            compatibility_version=self.COMPATIBILITY_VERSION,
            items=[self.record_payload(record) for record in records],
            next_cursor=next_cursor,
        )

    async def reconcile_system(
        self,
        *,
        mapping_version: str | None = None,
        limit: int = 100,
    ) -> ReconciliationSummary:
        """Audit legacy system records against this versioned compatibility mapping."""
        records = await self._stock_signals.get_all_system_predictions(limit=limit)
        pairs: list[tuple[dict[str, object], dict[str, object]]] = []
        for record in records:
            mapped = self.record_payload(record).model_dump(mode="json")
            legacy = {
                "reference": str(record.id),
                "canonical_id": str(record.symbol).upper(),
                "cutoff_at": record.as_of_date.isoformat(),
                "recommendation": str(mapped["decision"]["recommendation"]),
                "narrative": None,
            }
            generic: dict[str, object] = {
                "canonical_id": str(mapped["legacy_identity"]["legacy_symbol"]).upper(),
                "cutoff_at": str(mapped["as_of_date"]),
                "recommendation": str(mapped["decision"]["recommendation"]),
                "narrative": None,
            }
            pairs.append((legacy, generic))
        return reconcile_batch(
            mapping_version=mapping_version or self.COMPATIBILITY_VERSION,
            pairs=pairs,
        )

    @classmethod
    def record_payload(cls, record: StockSignalPrediction) -> StockResearchCompatibilityItem:
        """Map one old record without promoting it to a generic prediction fact."""
        signal_action = str(record.signal_action)
        recommendation, market_view, direction = cls._DECISIONS.get(
            signal_action, ("HOLD", "INDETERMINATE", "INDETERMINATE")
        )
        is_correct = (
            record.buy_is_correct_20d
            if signal_action == "BUY"
            else record.sell_is_correct_20d
            if signal_action == "SELL"
            else None
        )
        return StockResearchCompatibilityItem(
            compatibility_version=cls.COMPATIBILITY_VERSION,
            legacy_prediction_id=record.id,
            legacy_identity={
                "asset_type": "stock",
                "legacy_symbol": record.symbol,
                "symbol_name": record.symbol_name,
                "market_type": record.market_type,
                "identity_status": "LEGACY_UNRESOLVED",
            },
            source=record.source,
            universe_code=record.universe_code,
            as_of_date=record.as_of_date,
            available_at=record.available_at,
            next_trading_date=record.next_trading_date,
            horizon_code="legacy-stock-20-trading-days-v1",
            decision={
                "legacy_signal_action": signal_action,
                "recommendation": recommendation,
                "market_view": market_view,
                "normalized_direction": direction,
                "confidence": record.confidence_score,
                "risk_score": record.risk_score,
                "expected_excess_return": record.expected_excess_return,
                "actionability": "RESEARCH_ONLY",
                "execution_disabled": True,
            },
            quality_status=cls._QUALITY.get(str(record.eligibility_status), "REJECTED"),
            quality_reason_codes=list(record.quality_reasons_json or []),
            model_versions={
                "feature_version": record.feature_version,
                "decision_policy_version": record.decision_policy_version,
                "model_version": record.model_version,
            },
            outcome={
                "legacy_outcome_status": str(record.outcome_status).upper(),
                "outcome_reason": record.outcome_reason,
                "entry_date": record.entry_date,
                "entry_price": record.entry_price,
                "horizon_1d_return": record.horizon_1d_return,
                "horizon_5d_return": record.horizon_5d_return,
                "horizon_20d_return": record.horizon_20d_return,
                "benchmark_20d_return": record.benchmark_20d_return,
                "excess_20d_return": record.excess_20d_return,
                "legacy_20d_action_correct": is_correct,
            },
            report_reference_id=record.report_id,
            semantic_loss_reason_codes=list(cls._SEMANTIC_LOSS),
        )
