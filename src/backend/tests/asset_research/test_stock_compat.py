"""Regression contracts for the old-stock read-only compatibility adapter."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.db.database import async_session_maker
from app.models.stock_signal import StockSignalPrediction
from app.services.asset_research.stock_compat import StockResearchCompatibilityAdapter
from app.services.stock_signal.service import StockSignalService


def _legacy_prediction(*, key: str, action: str) -> StockSignalPrediction:
    record = StockSignalPrediction(
        prediction_key=key,
        owner_scope="system",
        source="nightly_sse50",
        universe_code="SSE50",
        symbol="600000.SH",
        symbol_name="浦发银行",
        market_type="A股",
        as_of_date=date(2026, 7, 30),
        as_of_at=datetime(2026, 7, 30, 15, 0, tzinfo=timezone.utc),
        available_at=datetime(2026, 7, 30, 19, 0, tzinfo=timezone.utc),
        next_trading_date=date(2026, 7, 31),
        signal_action=action,
        confidence_score=0.75,
        risk_score=0.3,
        eligibility_status="eligible",
        quality_reasons_json=[],
        data_freshness_json={},
        feature_version="ohlcv-v1",
        decision_policy_version="baseline-v1",
        model_version="deterministic-shadow-v1",
        feature_snapshot_json={},
        policy_snapshot_json={},
        source_snapshot_hash="a" * 64,
        outcome_status="scored" if action == "BUY" else "pending",
    )
    if action == "BUY":
        record.horizon_20d_return = 0.05
        record.buy_is_correct_20d = True
    return record


@pytest.mark.asyncio
async def test_stock_compatibility_adapter_preserves_legacy_facts_without_promoting_them() -> None:
    async with async_session_maker() as db:
        db.add_all(
            [
                _legacy_prediction(key="legacy-buy", action="BUY"),
                _legacy_prediction(key="legacy-watch", action="WATCH"),
            ]
        )
        await db.commit()

        response = await StockResearchCompatibilityAdapter(
            StockSignalService(db)
        ).get_visible_history(
            user_id="any-user",
            symbol="600000.SH",
        )

    mapped = {item.decision.legacy_signal_action: item for item in response.items}
    buy = mapped["BUY"]
    watch = mapped["WATCH"]
    assert response.compatibility_version == "stock-signal-v1-to-asset-research-v1"
    assert buy.decision.recommendation == "BUY"
    assert buy.decision.execution_disabled is True
    assert buy.outcome.legacy_20d_action_correct is True
    assert watch.decision.recommendation == "HOLD"
    assert watch.outcome.legacy_20d_action_correct is None
    assert buy.legacy_identity.identity_status == "LEGACY_UNRESOLVED"
    assert "LEGACY_STOCK_SOURCE_MANIFEST_UNAVAILABLE" in buy.semantic_loss_reason_codes


@pytest.mark.asyncio
async def test_stock_compatibility_reconcile_reports_zero_defects_for_mapped_records() -> None:
    async with async_session_maker() as db:
        db.add_all(
            [
                _legacy_prediction(key="reconcile-buy", action="BUY"),
                _legacy_prediction(key="reconcile-watch", action="WATCH"),
            ]
        )
        await db.commit()

        summary = await StockResearchCompatibilityAdapter(StockSignalService(db)).reconcile_system()

    assert summary.mapping_version == "stock-signal-v1-to-asset-research-v1"
    assert summary.defect_count == 0
    assert summary.has_unsupported_defect is False
