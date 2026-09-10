"""Strict legacy K-line request parsing and local-read projection.

The legacy response is a compatibility shape only.  This module deliberately
accepts a typed ``MarketDataQueryExecution`` from the governed v2 path and
never imports a provider, resolves a database identity, or reads a legacy
table.  It therefore cannot turn a projection failure into an online fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo

from app.services.market_data.coverage import CoverageStatus
from app.services.market_data.dataset_contracts import (
    KLINE_LEGACY_CONTRACT_VERSION,
    KLINE_LEGACY_FAMILY_ID,
)
from app.services.market_data.field_quality import (
    FieldQualityValueError,
    is_usable_field_value,
    normalize_numeric_field_value,
)
from app.services.market_data.legacy_kline_identity import matches_legacy_kline_display_token
from app.services.market_data.query_service import MarketDataQueryExecution

UTC = timezone.utc
SHANGHAI = ZoneInfo("Asia/Shanghai")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PERIOD_TO_FREQUENCY = {"daily": "1d", "weekly": "1w", "monthly": "1mo"}
_REQUIRED_FIELDS = ("open", "high", "low", "close", "volume", "change_pct")
_MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991
_TWO_DECIMAL_PLACES = Decimal("0.01")


class LegacyKlineInputError(ValueError):
    """A legacy K-line query string cannot form a bounded reviewed request."""

    code = "KLINE_REQUEST_INVALID"


class LegacyKlineBridgeError(ValueError):
    """The governed query result cannot safely form the legacy response."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class LegacyKlineRequest:
    """A validated legacy selector with its exact normalized v2 time window."""

    symbol: str
    period: str
    frequency: str
    start: datetime
    end: datetime


def parse_legacy_kline_request(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    period: str,
) -> LegacyKlineRequest:
    """Validate a legacy date range and translate it into a Shanghai UTC window.

    The public legacy dates remain inclusive.  The v2 request uses the explicit
    half-open UTC interval derived from the corresponding Shanghai calendar
    period.  Weekly and monthly selectors must already name a complete
    Shanghai calendar period; the bridge rejects a partial period instead of
    silently expanding a caller's requested interval.
    """
    if not isinstance(symbol, str) or not symbol or symbol != symbol.strip():
        raise LegacyKlineInputError(LegacyKlineInputError.code)
    if not isinstance(period, str):
        raise LegacyKlineInputError(LegacyKlineInputError.code)
    frequency = _PERIOD_TO_FREQUENCY.get(period)
    if frequency is None:
        raise LegacyKlineInputError(LegacyKlineInputError.code)
    requested_start = _parse_iso_date(start_date)
    requested_end = _parse_iso_date(end_date)
    if requested_start > requested_end:
        raise LegacyKlineInputError(LegacyKlineInputError.code)

    # ISO labels at Python's supported calendar endpoints are syntactically
    # valid, but some cannot form the reviewed half-open Shanghai-to-UTC
    # window (for example 9999-12-31 plus one day or 0001-01-01 minus UTC
    # offset).  They remain client selector failures, never handler 500s.
    try:
        if period == "daily":
            normalized_start, normalized_end = requested_start, requested_end
            if (normalized_end - normalized_start).days + 1 > 366:
                raise LegacyKlineInputError(LegacyKlineInputError.code)
        elif period == "weekly":
            if requested_start.weekday() != 0 or requested_end.weekday() != 6:
                raise LegacyKlineInputError(LegacyKlineInputError.code)
            normalized_start, normalized_end = requested_start, requested_end
            if ((normalized_end - normalized_start).days + 1) // 7 > 260:
                raise LegacyKlineInputError(LegacyKlineInputError.code)
        else:
            if requested_start.day != 1 or requested_end != _last_day_of_month(requested_end):
                raise LegacyKlineInputError(LegacyKlineInputError.code)
            normalized_start, normalized_end = requested_start, requested_end
            month_count = (normalized_end.year - normalized_start.year) * 12 + (
                normalized_end.month - normalized_start.month
            ) + 1
            if month_count > 120:
                raise LegacyKlineInputError(LegacyKlineInputError.code)

        return LegacyKlineRequest(
            symbol=symbol,
            period=period,
            frequency=frequency,
            start=_shanghai_midnight(normalized_start),
            end=_shanghai_midnight(_next_day_or_month(normalized_end, period)),
        )
    except LegacyKlineInputError:
        raise
    except (OverflowError, ValueError) as exc:
        raise LegacyKlineInputError(LegacyKlineInputError.code) from exc


def project_legacy_kline_execution(
    execution: MarketDataQueryExecution,
    *,
    request: LegacyKlineRequest,
) -> dict[str, Any]:
    """Project only an exact, complete, unpaginated local v2 reread.

    ``execution`` must be the caller's final ``local_only`` reread.  Its first
    local-first execution may have filled and persisted a gap, but provider
    output must never be sent to a legacy caller directly.
    """
    if not isinstance(execution, MarketDataQueryExecution):
        raise TypeError("execution must be a MarketDataQueryExecution")
    if not isinstance(request, LegacyKlineRequest):
        raise TypeError("request must be a LegacyKlineRequest")
    query = execution.context.query
    if (
        query.family_id != KLINE_LEGACY_FAMILY_ID
        or query.family_contract_version != KLINE_LEGACY_CONTRACT_VERSION
        or query.dataset_code != "market.bars"
        or query.data_kind != "bars"
        or query.frequency != request.frequency
        or query.adjustment != "qfq"
        or query.price_basis != "close"
        or query.currency != "CNY"
        or query.unit != "share"
        or query.source_policy_id != "market-default-v1"
        or query.consistency != "display"
        or query.purpose != "display"
        or query.knowledge_cutoff is not None
        or frozenset(query.required_fields) != frozenset(_REQUIRED_FIELDS)
        or query.start != request.start
        or query.end != request.end
        or query.mode != "local_only"
        or query.cursor is not None
        or query.page_size != 2000
        or execution.context.identity.canonical_id != query.canonical_id
        or not matches_legacy_kline_display_token(
            execution.context.identity.identity,
            token=request.symbol,
        )
        or execution.context.coverage_identity.canonical_id != query.canonical_id
        or execution.context.coverage_identity.dataset_code != query.dataset_code
        or execution.context.coverage_identity.data_kind != query.data_kind
        or execution.context.coverage_identity.frequency != query.frequency
        or execution.context.coverage_identity.source_policy_id != query.source_policy_id
        or execution.context.coverage_identity.adjustment != query.adjustment
        or execution.context.coverage_identity.price_basis != query.price_basis
        or execution.context.coverage_identity.currency != query.currency
        or execution.context.coverage_identity.unit != query.unit
        or execution.context.coverage_identity.family_id != query.family_id
        or execution.context.coverage_identity.family_contract_version
        != query.family_contract_version
    ):
        raise LegacyKlineBridgeError("KLINE_QUERY_CONTRACT_INVALID")
    if execution.coverage.status is not CoverageStatus.COMPLETE:
        raise LegacyKlineBridgeError("KLINE_COVERAGE_INCOMPLETE")
    if execution.next_cursor is not None:
        raise LegacyKlineBridgeError("KLINE_CURSOR_UNEXPECTED")

    coverage = execution.coverage
    if (
        coverage.expected_event_keys != coverage.accepted_event_keys
        or coverage.missing_event_keys
        or coverage.gaps
    ):
        raise LegacyKlineBridgeError("KLINE_COVERAGE_EVENT_INTEGRITY")
    expected_event_times = tuple(_as_utc(event.event_at) for event in coverage.expected_event_keys)
    if (
        expected_event_times != tuple(sorted(expected_event_times))
        or len(expected_event_times) != len(set(expected_event_times))
        or any(not (query.start <= event_at < query.end) for event_at in expected_event_times)
    ):
        raise LegacyKlineBridgeError("KLINE_COVERAGE_EVENT_INTEGRITY")
    actual_event_times = tuple(_as_utc(item.event_at) for item in execution.observations)
    if len(actual_event_times) != len(set(actual_event_times)):
        raise LegacyKlineBridgeError("KLINE_RESPONSE_EVENT_DUPLICATE")
    if tuple(sorted(actual_event_times)) != expected_event_times:
        raise LegacyKlineBridgeError("KLINE_RESPONSE_EVENT_MISMATCH")

    observations_by_event = {
        _as_utc(item.event_at): item for item in execution.observations
    }
    dates: list[str] = []
    ohlc: list[list[float]] = []
    volumes: list[int] = []
    records: list[dict[str, object]] = []
    seen_buckets: set[date] = set()
    for event_at in expected_event_times:
        item = observations_by_event[event_at]
        local_date = event_at.astimezone(SHANGHAI).date()
        bucket = _period_bucket(local_date, period=request.period)
        if bucket in seen_buckets:
            raise LegacyKlineBridgeError("KLINE_PERIOD_CARDINALITY_INVALID")
        seen_buckets.add(bucket)
        rendered_date = local_date.isoformat()
        rendered_open = _two_decimal_number(item.fields.get("open"), field_name="open")
        rendered_high = _two_decimal_number(item.fields.get("high"), field_name="high")
        rendered_low = _two_decimal_number(item.fields.get("low"), field_name="low")
        rendered_close = _two_decimal_number(item.fields.get("close"), field_name="close")
        rendered_volume = _safe_integer(item.fields.get("volume"), field_name="volume")
        rendered_change = _two_decimal_number(
            item.fields.get("change_pct"),
            field_name="change_pct",
        )
        dates.append(rendered_date)
        ohlc.append([rendered_open, rendered_close, rendered_low, rendered_high])
        volumes.append(rendered_volume)
        records.append(
            {
                "date": rendered_date,
                "open": rendered_open,
                "high": rendered_high,
                "low": rendered_low,
                "close": rendered_close,
                "volume": rendered_volume,
                # This is a percent point (for example 1.23 means +1.23%),
                # never a fractional return.
                "change": rendered_change,
            }
        )
    if not (len(dates) == len(ohlc) == len(volumes) == len(records)):
        raise LegacyKlineBridgeError("KLINE_PROJECTION_ALIGNMENT_INVALID")
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise LegacyKlineBridgeError("KLINE_DATE_INTEGRITY")
    return {
        "symbol": request.symbol,
        "count": len(records),
        "kline": {"dates": dates, "ohlc": ohlc, "volumes": volumes},
        "records": records,
    }


def _parse_iso_date(value: object) -> date:
    if not isinstance(value, str) or not _DATE_PATTERN.fullmatch(value):
        raise LegacyKlineInputError(LegacyKlineInputError.code)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LegacyKlineInputError(LegacyKlineInputError.code) from exc


def _last_day_of_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1) - timedelta(days=1)
    return date(value.year, value.month + 1, 1) - timedelta(days=1)


def _next_day_or_month(value: date, period: str) -> date:
    if period == "monthly":
        if value.month == 12:
            return date(value.year + 1, 1, 1)
        return date(value.year, value.month + 1, 1)
    return value + timedelta(days=1)


def _shanghai_midnight(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=SHANGHAI).astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise LegacyKlineBridgeError("KLINE_EVENT_TIME_INVALID")
    return value.astimezone(UTC)


def _period_bucket(value: date, *, period: str) -> date:
    if period == "daily":
        return value
    if period == "weekly":
        return value - timedelta(days=value.weekday())
    if period == "monthly":
        return value.replace(day=1)
    raise LegacyKlineBridgeError("KLINE_PERIOD_INVALID")


def _two_decimal_number(value: object, *, field_name: str) -> float:
    decimal_value = _finite_decimal(value, field_name=field_name)
    try:
        rounded = decimal_value.quantize(_TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)
        rendered = float(rounded)
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise LegacyKlineBridgeError("KLINE_FIELD_QUALITY_INVALID") from exc
    if not isfinite(rendered):
        raise LegacyKlineBridgeError("KLINE_FIELD_QUALITY_INVALID")
    # The compatibility response uses JSON numbers. Do not emit a finite
    # binary float which silently loses the reviewed two-decimal value.
    if Decimal(str(rendered)) != rounded:
        raise LegacyKlineBridgeError("KLINE_FIELD_QUALITY_INVALID")
    if rendered == 0:
        return 0.0
    return rendered


def _safe_integer(value: object, *, field_name: str) -> int:
    decimal_value = _finite_decimal(value, field_name=field_name)
    if decimal_value != decimal_value.to_integral_value():
        raise LegacyKlineBridgeError("KLINE_VOLUME_INVALID")
    rendered = int(decimal_value)
    if rendered < 0 or rendered > _MAX_SAFE_JSON_INTEGER:
        raise LegacyKlineBridgeError("KLINE_VOLUME_INVALID")
    return rendered


def _finite_decimal(value: object, *, field_name: str) -> Decimal:
    if not is_usable_field_value(field_name, value):
        raise LegacyKlineBridgeError("KLINE_FIELD_QUALITY_INVALID")
    try:
        normalized = normalize_numeric_field_value(value, field_name=field_name)
        if normalized is None:
            raise LegacyKlineBridgeError("KLINE_FIELD_QUALITY_INVALID")
        decimal_value = Decimal(str(normalized))
    except (FieldQualityValueError, InvalidOperation, ValueError) as exc:
        raise LegacyKlineBridgeError("KLINE_FIELD_QUALITY_INVALID") from exc
    if not decimal_value.is_finite():
        raise LegacyKlineBridgeError("KLINE_FIELD_QUALITY_INVALID")
    return decimal_value


__all__ = [
    "LegacyKlineBridgeError",
    "LegacyKlineInputError",
    "LegacyKlineRequest",
    "parse_legacy_kline_request",
    "project_legacy_kline_execution",
]
