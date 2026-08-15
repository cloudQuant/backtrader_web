"""Data freshness and eligibility gates for stock signals."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.services.stock_signal.types import DataQualityAssessment, SignalFeatures


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _financial_report_date(snapshot: dict[str, Any]) -> date | None:
    financials = snapshot.get("financials") or {}
    records = [
        record
        for record in [*(financials.get("annual") or []), *(financials.get("quarterly") or [])]
        if isinstance(record, dict)
    ]
    dates = [_parse_date(record.get("report_date")) for record in records]
    return max((item for item in dates if item is not None), default=None)


def _latest_news_date(snapshot: dict[str, Any]) -> date | None:
    items = (snapshot.get("news") or {}).get("items") or []
    dates = [_parse_date(item.get("published_at")) for item in items if isinstance(item, dict)]
    return max((item for item in dates if item is not None), default=None)


class DataQualityGate:
    """Reject stale prices and degrade missing non-price evidence explicitly."""

    def __init__(
        self,
        *,
        min_history_bars: int = 60,
        max_financial_age_days: int = 210,
        max_news_age_days: int = 7,
    ) -> None:
        self.min_history_bars = min_history_bars
        self.max_financial_age_days = max_financial_age_days
        self.max_news_age_days = max_news_age_days

    def assess(
        self,
        *,
        snapshot: dict[str, Any],
        features: SignalFeatures,
        as_of_date: date,
    ) -> DataQualityAssessment:
        rejected: list[str] = []
        degraded: list[str] = []
        if features.as_of_date != as_of_date:
            rejected.append("stale_or_missing_market_close")
        if features.bar_count < self.min_history_bars:
            rejected.append("insufficient_history_bars")
        if features.latest_close is None or features.latest_close <= 0:
            rejected.append("invalid_latest_close")
        if features.latest_open is None or features.latest_open <= 0:
            rejected.append("invalid_latest_open")
        for reason in features.reasons:
            if reason in {"invalid_close_price", "invalid_latest_open"}:
                rejected.append(reason)
            elif reason in {"missing_ohlc_for_atr", "missing_volume_for_zscore"}:
                degraded.append(reason)

        financial_date = _financial_report_date(snapshot)
        if financial_date is None:
            degraded.append("financials_unavailable")
        elif (as_of_date - financial_date).days > self.max_financial_age_days:
            degraded.append("financials_stale")

        news_items = (snapshot.get("news") or {}).get("items") or []
        news_date = _latest_news_date(snapshot)
        if not news_items:
            degraded.append("news_unavailable")
        elif news_date is None:
            degraded.append("news_timestamp_unavailable")
        elif (as_of_date - news_date).days > self.max_news_age_days:
            degraded.append("news_stale")

        freshness = {
            "market_as_of_date": features.as_of_date.isoformat() if features.as_of_date else None,
            "financial_report_date": financial_date.isoformat() if financial_date else None,
            "news_latest_date": news_date.isoformat() if news_date else None,
        }
        if rejected:
            return DataQualityAssessment(
                "rejected", tuple(sorted(set(rejected + degraded))), freshness
            )
        if degraded:
            return DataQualityAssessment("degraded", tuple(sorted(set(degraded))), freshness)
        return DataQualityAssessment("eligible", (), freshness)
