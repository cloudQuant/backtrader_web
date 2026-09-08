"""Isolated JSON-line runner for the approved OpenBB market-data subset.

Run this script only from a dedicated environment containing the approved
OpenBB extension set.  The web process invokes it through
``OPENBB_MARKET_DATA_RUNNER`` and never imports OpenBB itself.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

PROTOCOL_VERSION = "openbb-market-data-v1"
_ALLOWED_ASSET_TYPES = {"stock", "fund", "futures", "fx", "crypto"}
_YFINANCE_INTERVAL_BY_FREQUENCY = {
    "1d": "1d",
    "1w": "1W",
    "1mo": "1M",
}
_MAX_RAW_PAYLOAD_BYTES = 4 * 1024 * 1024


def _emit(payload: Mapping[str, Any]) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=_json_default))
    sys.stdout.flush()
    return 0


def _json_default(value: object) -> str | float:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _json_safe(value: object) -> object:
    """Preserve a bounded OpenBB record representation before normalization."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("OPENBB_RAW_PAYLOAD_INVALID")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("OPENBB_RAW_PAYLOAD_INVALID")
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("OPENBB_RAW_PAYLOAD_INVALID")
            normalized[key] = _json_safe(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        return _json_safe(item())
    raise ValueError("OPENBB_RAW_PAYLOAD_INVALID")


def _canonical_json(value: object) -> str:
    """Serialize raw runner evidence once for its source receipt hash."""
    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _raw_payload(rows: list[dict[str, Any]]) -> tuple[dict[str, object], str]:
    """Return the pre-normalization source-record evidence and its verified hash."""
    payload = {
        "format": "openbb-records-pre-normalization-v1",
        "records": _json_safe(rows),
    }
    encoded = _canonical_json(payload).encode("utf-8")
    if len(encoded) > _MAX_RAW_PAYLOAD_BYTES:
        raise ValueError("OPENBB_RAW_PAYLOAD_TOO_LARGE")
    return payload, hashlib.sha256(encoded).hexdigest()


def _error(request_id: object, code: str, detail: str) -> int:
    return _emit(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "error": {"code": code, "detail": detail[:2048]},
        }
    )


def _as_utc_text(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("OpenBB row has no usable event timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _route(obb: Any, asset_type: str) -> Callable[..., Any]:
    if asset_type == "stock":
        return obb.equity.price.historical
    if asset_type == "fund":
        return obb.etf.historical
    if asset_type == "futures":
        return obb.derivatives.futures.historical
    if asset_type == "fx":
        return obb.currency.price.historical
    if asset_type == "crypto":
        return obb.crypto.price.historical
    raise ValueError(f"unsupported OpenBB asset type: {asset_type}")


def _records(result: Any) -> list[dict[str, Any]]:
    if hasattr(result, "to_df"):
        # OpenBB's OBBject.to_df() defaults to ``index="date"``.  Converting
        # that DataFrame with ``orient="records"`` drops its index and leaves
        # the child protocol without an event timestamp.  Requesting an
        # index-free frame retains the ``date`` column as a source field.
        dataframe = result.to_df(index=None)
        return [dict(item) for item in dataframe.to_dict(orient="records")]
    if hasattr(result, "results") and isinstance(result.results, list):
        return [dict(item) for item in result.results if isinstance(item, Mapping)]
    if isinstance(result, list):
        return [dict(item) for item in result if isinstance(item, Mapping)]
    raise ValueError("OpenBB response has no record representation")


def _normalize_records(
    rows: list[dict[str, Any]],
    *,
    start_at: datetime,
    end_at: datetime,
) -> list[dict[str, Any]]:
    """Normalize and enforce the parent's exact half-open response window."""
    normalized: list[dict[str, Any]] = []
    timestamp_fields = ("event_at", "date", "datetime", "timestamp")
    for row in rows:
        event_value = next(
            (row.get(key) for key in timestamp_fields if row.get(key) is not None), None
        )
        event_at = datetime.fromisoformat(_as_utc_text(event_value))
        if not start_at <= event_at < end_at:
            continue
        fields = {key: value for key, value in row.items() if key not in timestamp_fields}
        if fields:
            normalized.append({"event_at": event_at.isoformat(), "fields": fields})
    return normalized


def _request_timestamp(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _yfinance_historical_arguments(request: Mapping[str, Any]) -> dict[str, object]:
    """Translate one UTC day-aligned half-open window to yfinance arguments."""
    frequency = request.get("frequency")
    if frequency not in _YFINANCE_INTERVAL_BY_FREQUENCY:
        raise ValueError("OPENBB_FREQUENCY_UNSUPPORTED")
    start_at = _request_timestamp(request.get("start_at"), field_name="start_at")
    end_at = _request_timestamp(request.get("end_at"), field_name="end_at")
    if start_at >= end_at:
        raise ValueError("OPENBB_WINDOW_INVALID")
    if any(
        value != 0
        for value in (
            start_at.hour,
            start_at.minute,
            start_at.second,
            start_at.microsecond,
            end_at.hour,
            end_at.minute,
            end_at.second,
            end_at.microsecond,
        )
    ):
        raise ValueError("OPENBB_WINDOW_ALIGNMENT_UNSUPPORTED")
    return {
        "symbol": request["provider_symbol"],
        "start_date": start_at.date().isoformat(),
        "end_date": (end_at - timedelta(microseconds=1)).date().isoformat(),
        "interval": _YFINANCE_INTERVAL_BY_FREQUENCY[frequency],
        "provider": request["provider"],
    }


def _provider_error_code(exc: Exception) -> str:
    """Translate common provider failures into bounded operational outcomes.

    The parent FastAPI process receives only this stable code through the JSON
    protocol.  A temporary provider rate limit must remain distinguishable
    from a malformed response or unsupported route, so the query service can
    retain local data and try a later approved route.
    """
    detail = str(exc).casefold()
    if any(token in detail for token in ("rate limit", "too many requests", "http 429", "429")):
        return "OPENBB_RATE_LIMITED"
    if any(token in detail for token in ("unauthorized", "forbidden", "authentication", "api key")):
        return "OPENBB_AUTH_REQUIRED"
    if any(token in detail for token in ("no results", "empty data", "[empty]")):
        return "OPENBB_EMPTY_RESPONSE"
    return "OPENBB_ROUTE_FAILED"


def main() -> int:
    try:
        envelope = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        return _error(None, "OPENBB_RUNNER_INVALID_REQUEST", str(exc))
    if not isinstance(envelope, Mapping):
        return _error(None, "OPENBB_RUNNER_INVALID_REQUEST", "request envelope must be an object")
    request_id = envelope.get("request_id")
    if envelope.get("protocol_version") != PROTOCOL_VERSION or not isinstance(request_id, str):
        return _error(
            request_id, "OPENBB_RUNNER_INVALID_REQUEST", "protocol or request ID is invalid"
        )
    request = envelope.get("request")
    if not isinstance(request, Mapping):
        return _error(request_id, "OPENBB_RUNNER_INVALID_REQUEST", "request body must be an object")

    asset_type = request.get("asset_type")
    provider = request.get("provider")
    if asset_type not in _ALLOWED_ASSET_TYPES:
        return _error(request_id, "OPENBB_UNSUPPORTED", "asset type is not approved for the runner")
    allowed_providers = {
        item.strip()
        for item in os.getenv("OPENBB_ALLOWED_PROVIDERS", "yfinance").split(",")
        if item.strip()
    }
    if not isinstance(provider, str) or provider not in allowed_providers:
        return _error(request_id, "OPENBB_UNSUPPORTED", "provider is not approved for the runner")
    if request.get("data_kind") != "bars":
        return _error(request_id, "OPENBB_UNSUPPORTED", "only bars are approved for this runner")
    # The current runner does not perform corporate-action adjustment, price
    # basis conversion, currency conversion, or unit conversion.  Refuse every
    # declared semantic axis instead of returning a provider-default series
    # under a caller's stronger label.
    if any(
        request.get(field_name) is not None
        for field_name in ("adjustment", "price_basis", "currency", "unit")
    ):
        return _error(
            request_id,
            "OPENBB_SEMANTICS_UNSUPPORTED",
            "runner only supports undeclared provider-native price semantics",
        )

    try:
        from openbb import obb  # type: ignore[import-not-found]
    except ImportError as exc:
        return _error(request_id, "OPENBB_RUNNER_UNAVAILABLE", str(exc))

    try:
        if provider != "yfinance":
            return _error(request_id, "OPENBB_UNSUPPORTED", "provider window semantics are not approved")
        call_arguments = _yfinance_historical_arguments(request)
        result = _route(obb, str(asset_type))(**call_arguments)
        raw_payload, raw_payload_sha256 = _raw_payload(_records(result))
        source_rows = raw_payload["records"]
        if not isinstance(source_rows, list) or any(
            not isinstance(row, dict) for row in source_rows
        ):
            raise ValueError("OPENBB_RAW_PAYLOAD_INVALID")
        records = _normalize_records(
            source_rows,
            start_at=_request_timestamp(request.get("start_at"), field_name="start_at"),
            end_at=_request_timestamp(request.get("end_at"), field_name="end_at"),
        )
    except ValueError as exc:
        code = str(exc)
        if code.startswith("OPENBB_"):
            return _error(request_id, code, "request cannot be represented by this provider")
        return _error(request_id, "OPENBB_RUNNER_INVALID_REQUEST", "invalid provider request")
    except Exception as exc:  # Runner boundary: serialise provider exceptions, never trace to web.
        return _error(request_id, _provider_error_code(exc), str(exc))

    source_revision = f"openbb-raw-sha256:{raw_payload_sha256}"
    return _emit(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "provider_id": f"openbb:{provider}",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "source_revision": source_revision,
            "records": records,
            "raw_payload": raw_payload,
            "raw_payload_sha256": raw_payload_sha256,
            "warnings": [],
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
