"""Canonical serialization and content identity for trusted research records."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
from typing import Any


def canonical_json(payload: Any) -> str:
    """Return a deterministic JSON representation for a research payload.

    Research identities must not change merely because a client used another
    object-key ordering, a UTC spelling, or an equivalent decimal spelling.
    List order remains significant because it can describe an ordered search
    space or a portfolio construction rule.
    """

    normalized = normalize_payload(payload)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def content_hash(payload: Any) -> str:
    """Return the SHA-256 identity of a canonical research payload."""

    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def normalize_payload(payload: Any) -> Any:
    """Normalize JSON-compatible values without discarding semantic fields."""

    if payload is None or isinstance(payload, (str, bool)):
        return payload
    if isinstance(payload, Enum):
        return normalize_payload(payload.value)
    if isinstance(payload, datetime):
        return _normalize_datetime(payload)
    if isinstance(payload, date):
        return payload.isoformat()
    if isinstance(payload, Decimal):
        return _normalize_decimal(payload)
    if isinstance(payload, int):
        return payload
    if isinstance(payload, float):
        if not math.isfinite(payload):
            raise ValueError("CANONICAL_NUMBER_NOT_FINITE")
        return _normalize_decimal(Decimal(str(payload)))
    if isinstance(payload, dict):
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            if not isinstance(key, str):
                raise TypeError("CANONICAL_OBJECT_KEY_NOT_STRING")
            normalized[key] = normalize_payload(value)
        return normalized
    if isinstance(payload, (list, tuple)):
        return [normalize_payload(item) for item in payload]
    if hasattr(payload, "model_dump"):
        return normalize_payload(payload.model_dump(mode="python"))
    if hasattr(payload, "dict"):
        return normalize_payload(payload.dict())
    raise TypeError(f"CANONICAL_VALUE_UNSUPPORTED:{type(payload).__name__}")


def _normalize_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("CANONICAL_DATETIME_TIMEZONE_REQUIRED")
    utc_value = value.astimezone(timezone.utc)
    rendered = utc_value.isoformat(timespec="microseconds")
    if rendered.endswith(".000000+00:00"):
        rendered = rendered.replace(".000000+00:00", "Z")
    else:
        rendered = rendered.replace("+00:00", "Z")
    return rendered


def _normalize_decimal(value: Decimal) -> int | float:
    try:
        normalized = value.normalize()
    except InvalidOperation as exc:
        raise ValueError("CANONICAL_NUMBER_INVALID") from exc
    if not normalized.is_finite():
        raise ValueError("CANONICAL_NUMBER_NOT_FINITE")
    if normalized == normalized.to_integral_value():
        return int(normalized)
    return float(normalized)
