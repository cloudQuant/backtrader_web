"""Regression tests for market-history freshness gating."""

from __future__ import annotations

from datetime import date

from app.services.market_instrument import MarketInstrumentService


def test_history_refresh_rejects_legacy_rows_for_a_current_request():
    assert MarketInstrumentService._history_requires_refresh(
        asset_type="stock",
        rows=[{"date": "2024-12-31", "close": 10.0}],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 22),
    )


def test_history_refresh_accepts_a_valid_historical_request_range():
    assert not MarketInstrumentService._history_requires_refresh(
        asset_type="stock",
        rows=[{"date": "2024-12-30", "close": 10.0}, {"date": "2024-12-31", "close": 10.1}],
        start_date=date(2024, 12, 1),
        end_date=date(2024, 12, 31),
    )
