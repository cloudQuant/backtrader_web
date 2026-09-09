"""Shared typed field-quality rules for provider receipts and local reuse.

The policy is deliberately pure: it has no provider client, database, or
clock dependency.  Writers use it to normalize new provider facts, while
readers and coverage planning use the same predicates to re-evaluate immutable
legacy revisions under the current quality standard.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

FIELD_QUALITY_POLICY_VERSION = "typed-field-quality-v2"

# These are the normalized numeric metrics emitted by the reviewed AkShare,
# OpenBB, and offline snapshot adapters. A future textual observation field
# must be declared outside this set rather than inheriting numeric permissiveness.
KNOWN_NUMERIC_FIELDS = frozenset(
    {
        "amount",
        "amplitude",
        "ask",
        "ask_size",
        "bid",
        "bid_size",
        "change",
        "change_pct",
        "close",
        "coupon",
        "cumulative_nav",
        "daily_growth_rate",
        "days_to_expiry",
        "delta",
        "delivery_quantity",
        "float_market_cap",
        "gamma",
        "high",
        "implied_volatility",
        "inventory_quantity",
        "iopv",
        "last",
        "low",
        "long_position",
        "market_cap",
        "moneyness",
        "nav",
        "net_position",
        "open",
        "open_interest",
        "pb",
        "pe",
        "price",
        "previous_close",
        "previous_settle",
        "rank",
        "rate",
        "receipt_quantity",
        "settle",
        "short_position",
        "strike",
        "theta",
        "turnover",
        "turnover_rate",
        "vega",
        "volume",
        "yield_to_maturity",
    }
)
KNOWN_DATE_FIELDS = frozenset({"as_of", "expiry", "maturity_date", "report_date"})
KNOWN_DATETIME_FIELDS = frozenset({"update_time"})
_UNAVAILABLE_TEXT = frozenset({"--", "n/a"})
_UTC = timezone.utc


class FieldQualityValueError(ValueError):
    """A schema-declared typed field cannot be represented safely."""

    def __init__(self, field_name: str) -> None:
        self.field_name = field_name
        super().__init__(f"invalid typed field value: {field_name}")


def normalize_numeric_field_value(
    value: object,
    *,
    field_name: str,
) -> int | float | str | None:
    """Return a finite, JSON-safe value for one known numeric field.

    Finite decimals and numeric strings become their exact decimal string form
    to avoid a lossy float conversion. ``None`` continues to mean an absent
    field so callers can preserve existing required-field-missing semantics.
    """
    normalized_field_name = _require_known_numeric_field(field_name)
    if value is None:
        return None
    if isinstance(value, bool):
        raise FieldQualityValueError(normalized_field_name)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        raise FieldQualityValueError(normalized_field_name)
    if isinstance(value, Decimal):
        return _decimal_as_json_number(value, field_name=normalized_field_name)
    if isinstance(value, str):
        normalized_value = value.strip()
        if not normalized_value or normalized_value.casefold() in _UNAVAILABLE_TEXT:
            raise FieldQualityValueError(normalized_field_name)
        try:
            decimal_value = Decimal(normalized_value)
        except (InvalidOperation, ValueError) as exc:
            raise FieldQualityValueError(normalized_field_name) from exc
        return _decimal_as_json_number(decimal_value, field_name=normalized_field_name)
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            scalar_value = item_method()
        except (TypeError, ValueError) as exc:
            raise FieldQualityValueError(normalized_field_name) from exc
        if scalar_value is value:
            raise FieldQualityValueError(normalized_field_name)
        return normalize_numeric_field_value(scalar_value, field_name=normalized_field_name)
    raise FieldQualityValueError(normalized_field_name)


def normalize_date_field_value(value: object, *, field_name: str) -> str | None:
    """Return an ISO date for one known date field without local-time inference."""
    normalized_field_name = _require_known_date_field(field_name)
    if value is None:
        return None
    if isinstance(value, datetime):
        raise FieldQualityValueError(normalized_field_name)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        normalized_value = value.strip()
        if not normalized_value or normalized_value.casefold() in _UNAVAILABLE_TEXT:
            raise FieldQualityValueError(normalized_field_name)
        try:
            return date.fromisoformat(normalized_value).isoformat()
        except ValueError as exc:
            raise FieldQualityValueError(normalized_field_name) from exc
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            scalar_value = item_method()
        except (TypeError, ValueError) as exc:
            raise FieldQualityValueError(normalized_field_name) from exc
        if scalar_value is value:
            raise FieldQualityValueError(normalized_field_name)
        return normalize_date_field_value(scalar_value, field_name=normalized_field_name)
    raise FieldQualityValueError(normalized_field_name)


def normalize_datetime_field_value(value: object, *, field_name: str) -> str | None:
    """Return a timezone-aware ISO instant for one known datetime field.

    A timezone-free source string has no stable market-time meaning at this
    shared boundary, so it remains unavailable until an adapter supplies an
    explicit source-timezone conversion. The returned UTC form is portable in
    JSON and deterministic across provider and local-read paths.
    """
    normalized_field_name = _require_known_datetime_field(field_name)
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized_value = value.strip()
        if not normalized_value or normalized_value.casefold() in _UNAVAILABLE_TEXT:
            raise FieldQualityValueError(normalized_field_name)
        try:
            parsed = datetime.fromisoformat(normalized_value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise FieldQualityValueError(normalized_field_name) from exc
    else:
        item_method = getattr(value, "item", None)
        if callable(item_method):
            try:
                scalar_value = item_method()
            except (TypeError, ValueError) as exc:
                raise FieldQualityValueError(normalized_field_name) from exc
            if scalar_value is value:
                raise FieldQualityValueError(normalized_field_name)
            return normalize_datetime_field_value(scalar_value, field_name=normalized_field_name)
        raise FieldQualityValueError(normalized_field_name)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FieldQualityValueError(normalized_field_name)
    return parsed.astimezone(_UTC).isoformat()


def normalize_provider_fields(fields: Mapping[str, object]) -> dict[str, object]:
    """Normalize known metric fields before new provider revisions are persisted.

    Invalid known numeric values become ``None`` in normalized evidence. Their
    raw provider receipt remains separately persisted, and the common
    usability predicate marks the revision failed. Unknown fields are retained
    for existing JSON-safe persistence validation and can never turn a required
    placeholder into a usable value.
    """
    normalized: dict[str, object] = {}
    for field_name, value in fields.items():
        if isinstance(field_name, str) and field_name.strip() in KNOWN_NUMERIC_FIELDS:
            try:
                normalized[field_name] = normalize_numeric_field_value(
                    value,
                    field_name=field_name,
                )
            except FieldQualityValueError:
                normalized[field_name] = None
        elif isinstance(field_name, str) and field_name.strip() in KNOWN_DATE_FIELDS:
            try:
                normalized[field_name] = normalize_date_field_value(
                    value,
                    field_name=field_name,
                )
            except FieldQualityValueError:
                normalized[field_name] = None
        elif isinstance(field_name, str) and field_name.strip() in KNOWN_DATETIME_FIELDS:
            try:
                normalized[field_name] = normalize_datetime_field_value(
                    value,
                    field_name=field_name,
                )
            except FieldQualityValueError:
                normalized[field_name] = None
        else:
            normalized[field_name] = value
    return normalized


def is_usable_field_value(field_name: str, value: object) -> bool:
    """Return whether a current or immutable legacy field can satisfy a query."""
    if not isinstance(field_name, str) or not field_name.strip():
        return False
    normalized_field_name = field_name.strip()
    if normalized_field_name in KNOWN_NUMERIC_FIELDS:
        try:
            return (
                normalize_numeric_field_value(value, field_name=normalized_field_name) is not None
            )
        except FieldQualityValueError:
            return False
    if normalized_field_name in KNOWN_DATE_FIELDS:
        try:
            return normalize_date_field_value(value, field_name=normalized_field_name) is not None
        except FieldQualityValueError:
            return False
    if normalized_field_name in KNOWN_DATETIME_FIELDS:
        try:
            return (
                normalize_datetime_field_value(value, field_name=normalized_field_name) is not None
            )
        except FieldQualityValueError:
            return False
    return _is_usable_unknown_field_value(value)


def _decimal_as_json_number(value: Decimal, *, field_name: str) -> str:
    """Preserve a finite decimal exactly in JSON's portable string representation."""
    if not value.is_finite():
        raise FieldQualityValueError(field_name)
    return format(value, "f")


def _require_known_numeric_field(field_name: str) -> str:
    """Reject accidental use of the numeric normalizer for undeclared fields."""
    if not isinstance(field_name, str):
        raise FieldQualityValueError("<invalid>")
    normalized = field_name.strip()
    if normalized not in KNOWN_NUMERIC_FIELDS:
        raise FieldQualityValueError(normalized or "<invalid>")
    return normalized


def _require_known_date_field(field_name: str) -> str:
    """Reject accidental use of the date normalizer for undeclared fields."""
    if not isinstance(field_name, str):
        raise FieldQualityValueError("<invalid>")
    normalized = field_name.strip()
    if normalized not in KNOWN_DATE_FIELDS:
        raise FieldQualityValueError(normalized or "<invalid>")
    return normalized


def _require_known_datetime_field(field_name: str) -> str:
    """Reject accidental use of the datetime normalizer for undeclared fields."""
    if not isinstance(field_name, str):
        raise FieldQualityValueError("<invalid>")
    normalized = field_name.strip()
    if normalized not in KNOWN_DATETIME_FIELDS:
        raise FieldQualityValueError(normalized or "<invalid>")
    return normalized


def _is_usable_unknown_field_value(value: object) -> bool:
    """Apply conservative scalar usability rules to a non-numeric field name."""
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        normalized = value.strip()
        return bool(normalized) and normalized.casefold() not in _UNAVAILABLE_TEXT
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Decimal):
        return value.is_finite()
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            scalar_value = item_method()
        except (TypeError, ValueError):
            return False
        if scalar_value is value:
            return False
        return _is_usable_unknown_field_value(scalar_value)
    return False


__all__ = [
    "FIELD_QUALITY_POLICY_VERSION",
    "KNOWN_DATE_FIELDS",
    "KNOWN_DATETIME_FIELDS",
    "KNOWN_NUMERIC_FIELDS",
    "FieldQualityValueError",
    "is_usable_field_value",
    "normalize_date_field_value",
    "normalize_datetime_field_value",
    "normalize_numeric_field_value",
    "normalize_provider_fields",
]
