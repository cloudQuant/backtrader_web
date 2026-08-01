"""Deterministic OHLCV feature extraction for point-in-time signals."""

from __future__ import annotations

import math
import statistics
from datetime import date
from typing import Any

from app.services.stock_signal.types import SignalFeatures

FEATURE_VERSION = "ohlcv-v1"


def _number(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _return(closes: list[float], periods: int) -> float | None:
    if len(closes) <= periods or closes[-(periods + 1)] <= 0:
        return None
    return closes[-1] / closes[-(periods + 1)] - 1


def _ma_gap(closes: list[float], periods: int) -> float | None:
    if len(closes) < periods or closes[-1] <= 0:
        return None
    average = _mean(closes[-periods:])
    return closes[-1] / average - 1 if average and average > 0 else None


def _rsi(closes: list[float], periods: int = 14) -> float | None:
    if len(closes) <= periods:
        return None
    changes = [closes[index] - closes[index - 1] for index in range(len(closes) - periods, len(closes))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = _mean(gains) or 0.0
    avg_loss = _mean(losses) or 0.0
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _atr_ratio(rows: list[dict[str, Any]], closes: list[float], periods: int = 14) -> float | None:
    if len(rows) <= periods or len(closes) <= periods or closes[-1] <= 0:
        return None
    ranges: list[float] = []
    start = len(rows) - periods
    for index in range(start, len(rows)):
        high = _number(rows[index].get("high"))
        low = _number(rows[index].get("low"))
        previous_close = _number(rows[index - 1].get("close")) if index else None
        if high is None or low is None or previous_close is None:
            return None
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    average = _mean(ranges)
    return average / closes[-1] if average is not None else None


def _volatility(closes: list[float], periods: int = 20) -> float | None:
    if len(closes) <= periods:
        return None
    returns = [
        closes[index] / closes[index - 1] - 1
        for index in range(len(closes) - periods, len(closes))
        if closes[index - 1] > 0
    ]
    if len(returns) != periods:
        return None
    return statistics.pstdev(returns)


def _volume_zscore(rows: list[dict[str, Any]], periods: int = 20) -> float | None:
    volumes = [_number(row.get("volume")) for row in rows[-periods:]]
    if len(volumes) != periods or any(value is None or value < 0 for value in volumes):
        return None
    known = [value for value in volumes if value is not None]
    deviation = statistics.pstdev(known)
    if deviation == 0:
        return 0.0
    return (known[-1] - statistics.mean(known)) / deviation


def _range_position(closes: list[float], periods: int = 20) -> float | None:
    if len(closes) < periods:
        return None
    window = closes[-periods:]
    lowest, highest = min(window), max(window)
    if highest == lowest:
        return 0.5
    return (window[-1] - lowest) / (highest - lowest)


def calculate_features(rows: list[dict[str, Any]]) -> SignalFeatures:
    """Calculate transparent price features without silently imputing missing values."""
    normalized_rows = sorted(
        [row for row in rows if isinstance(row, dict) and _parse_date(row.get("date")) is not None],
        key=lambda row: str(row.get("date")),
    )
    closes = [_number(row.get("close")) for row in normalized_rows]
    reasons: list[str] = []
    if any(value is None or value <= 0 for value in closes):
        reasons.append("invalid_close_price")
    valid_closes = [value for value in closes if value is not None and value > 0]
    if len(valid_closes) != len(normalized_rows):
        valid_closes = []
    if len(normalized_rows) < 60:
        reasons.append("insufficient_history_bars")

    latest_close = valid_closes[-1] if valid_closes else None
    latest_open = _number(normalized_rows[-1].get("open")) if normalized_rows else None
    if latest_open is not None and latest_open <= 0:
        latest_open = None
        reasons.append("invalid_latest_open")
    latest_date = _parse_date(normalized_rows[-1].get("date")) if normalized_rows else None

    if not valid_closes:
        return SignalFeatures(
            as_of_date=latest_date,
            latest_close=None,
            latest_open=latest_open,
            return_1=None,
            return_5=None,
            return_20=None,
            return_60=None,
            ma5_gap=None,
            ma20_gap=None,
            rsi14=None,
            atr14_ratio=None,
            volatility20=None,
            volume_zscore20=None,
            range_position20=None,
            bar_count=len(normalized_rows),
            reasons=tuple(sorted(set(reasons))),
        )

    atr = _atr_ratio(normalized_rows, valid_closes)
    if atr is None:
        reasons.append("missing_ohlc_for_atr")
    volume_zscore = _volume_zscore(normalized_rows)
    if volume_zscore is None:
        reasons.append("missing_volume_for_zscore")
    return SignalFeatures(
        as_of_date=latest_date,
        latest_close=latest_close,
        latest_open=latest_open,
        return_1=_return(valid_closes, 1),
        return_5=_return(valid_closes, 5),
        return_20=_return(valid_closes, 20),
        return_60=_return(valid_closes, 60),
        ma5_gap=_ma_gap(valid_closes, 5),
        ma20_gap=_ma_gap(valid_closes, 20),
        rsi14=_rsi(valid_closes),
        atr14_ratio=atr,
        volatility20=_volatility(valid_closes),
        volume_zscore20=volume_zscore,
        range_position20=_range_position(valid_closes),
        bar_count=len(normalized_rows),
        reasons=tuple(sorted(set(reasons))),
    )
