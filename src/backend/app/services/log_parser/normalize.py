"""Pure normalisation helpers used across the log parser stack."""

from __future__ import annotations

import math
from typing import Any


def safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert a value to ``float``.

    Returns ``default`` if conversion fails or the result is NaN / Infinity.
    """
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (ValueError, TypeError):
        return default


def normalize_dt_text(value: Any) -> str:
    """Strip whitespace and coerce ``None`` to an empty string."""
    return str(value or "").strip()


def normalize_date_text(value: Any) -> str:
    """Reduce a datetime-ish text value to its date portion."""
    text = normalize_dt_text(value)
    if " " in text:
        return text.split(" ")[0]
    if "T" in text:
        return text.split("T")[0]
    return text


def is_truthy(value: Any) -> bool:
    """Lenient truth check for log fields written as strings."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def extract_indicator_values(row: dict[str, Any]) -> dict[str, float]:
    """Pull numeric indicator columns out of a data-log row.

    Reserved field names (datetime, event, OHLCV, etc.) and per-asset
    suffixes (``*_open``, ``*_close``, ...) are ignored so the caller gets a
    clean ``{indicator_name: float}`` map.
    """
    ignored = {
        "log_time",
        "datetime",
        "strategy_name",
        "data_name",
        "event_type",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "openinterest",
    }
    ignored_suffixes = (
        "_open",
        "_high",
        "_low",
        "_close",
        "_volume",
        "_openinterest",
        "_datetime",
    )
    values: dict[str, float] = {}
    for key, value in row.items():
        if key in ignored:
            continue
        if key.endswith(ignored_suffixes):
            continue
        if isinstance(value, (int, float, str)):
            numeric_value = safe_float(value, default=math.nan)
            if not math.isnan(numeric_value):
                values[key] = numeric_value
    return values
