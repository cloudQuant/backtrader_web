"""Exchange-calendar contracts for signal generation and outcome scoring."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.services.stock_signal.calendar import TradingCalendar


@pytest.mark.asyncio
async def test_calendar_uses_explicit_exchange_dates_not_weekday_inference() -> None:
    calendar = TradingCalendar(
        fetcher=lambda: SimpleNamespace(
            to_dict=lambda orient: [
                {"trade_date": "2026-07-30"},
                {"trade_date": "2026-08-03"},
            ]
        )
    )

    assert await calendar.is_trading_day(date(2026, 7, 30)) is True
    assert await calendar.is_trading_day(date(2026, 7, 31)) is False
    assert await calendar.next_trading_day(date(2026, 7, 30)) == date(2026, 8, 3)


@pytest.mark.asyncio
async def test_calendar_rejects_an_empty_provider_response() -> None:
    calendar = TradingCalendar(fetcher=lambda: SimpleNamespace(to_dict=lambda orient: []))

    with pytest.raises(RuntimeError, match="trading_calendar_empty"):
        await calendar.is_trading_day(date(2026, 7, 30))
