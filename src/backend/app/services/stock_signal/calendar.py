"""Trading-calendar access that refuses to infer exchange sessions from weekdays."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date
from typing import Any


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


class TradingCalendar:
    """Cached A-share trading dates backed by an explicit provider."""

    def __init__(self, fetcher: Callable[[], Any] | None = None) -> None:
        self._fetcher = fetcher or self._fetch_dates
        self._dates: set[date] | None = None

    @staticmethod
    def _fetch_dates() -> Any:
        import akshare as ak

        return ak.tool_trade_date_hist_sina()

    async def refresh(self) -> set[date]:
        """Refresh the calendar or raise a clear error without a weekday fallback."""
        frame = await asyncio.to_thread(self._fetcher)
        try:
            rows = frame.to_dict(orient="records")
        except (AttributeError, TypeError, ValueError) as exc:
            raise RuntimeError("trading_calendar_unavailable") from exc
        dates = {
            parsed
            for row in rows
            if isinstance(row, dict)
            for parsed in [_parse_date(row.get("trade_date") or row.get("日期") or row.get("date"))]
            if parsed is not None
        }
        if not dates:
            raise RuntimeError("trading_calendar_empty")
        self._dates = dates
        return dates

    async def _ensure_dates(self) -> set[date]:
        return self._dates if self._dates is not None else await self.refresh()

    async def is_trading_day(self, value: date) -> bool:
        return value in await self._ensure_dates()

    async def next_trading_day(self, value: date) -> date | None:
        dates = await self._ensure_dates()
        return min((item for item in dates if item > value), default=None)
