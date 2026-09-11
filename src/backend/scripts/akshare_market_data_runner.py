"""Isolated JSON runner for the reviewed AkShare market-data subset.

The FastAPI process resolves the route, endpoint and keyword arguments before
spawning this script.  This runner accepts only that one envelope, performs the
endpoint call in its own POSIX session, and returns JSON-safe source rows.  It
does not import application modules, inspect the database, or select routes.
"""

from __future__ import annotations

import importlib
import json
import math
import os
import re
import sys
from collections.abc import Mapping, Sequence
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "akshare-market-data-v1"
_MAX_RESPONSE_ROWS = 50_000
_MAX_REQUEST_BYTES = 512 * 1024
_MAX_CALL_KWARGS = 32
_MAX_CAPTURED_PROVIDER_OUTPUT_BYTES = 4 * 1024
_SITE_PACKAGES_ENVIRONMENT_KEY = "AKSHARE_RUNNER_SITE_PACKAGES"
_ALLOWED_ENDPOINTS = frozenset(
    {
        "stock_zh_a_hist",
        "futures_zh_daily_sina",
        "bond_zh_hs_daily",
        "fund_etf_hist_em",
        "fund_etf_fund_info_em",
        "option_cffex_hs300_daily_sina",
        "option_cffex_sz50_daily_sina",
        "option_cffex_zz1000_daily_sina",
        "forex_hist_em",
    }
)


class _BoundedTextCapture:
    """Absorb provider progress output without contaminating the JSON protocol."""

    def __init__(self, maximum_bytes: int) -> None:
        self._maximum_bytes = maximum_bytes
        self._retained_bytes = 0

    def write(self, value: str) -> int:
        if not isinstance(value, str):
            return 0
        remaining = self._maximum_bytes - self._retained_bytes
        if remaining > 0:
            self._retained_bytes += min(len(value.encode("utf-8", errors="replace")), remaining)
        return len(value)

    def flush(self) -> None:
        return None


def _canonical_json(payload: Mapping[str, Any]) -> str:
    """Return one deterministic strict-JSON envelope."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def _emit(payload: Mapping[str, Any]) -> int:
    """Write exactly one protocol document to stdout."""
    sys.stdout.write(_canonical_json(payload))
    sys.stdout.flush()
    return 0


def _error(
    request_id: object,
    code: str,
    detail: str,
    *,
    request: Mapping[str, Any] | None = None,
    execution: Mapping[str, Any] | None = None,
    source_revision: str | None = None,
) -> int:
    """Return a bounded error receipt, echoing a verified parent envelope.

    A source failure is still an untrusted child response.  Once the parent
    envelope has passed runner validation, retain all immutable echoes so the
    parent can authenticate the error before surfacing its stable code.
    """
    payload: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id if isinstance(request_id, str) else None,
        "error": {"code": code, "detail": detail[:512]},
    }
    if request is not None and execution is not None and source_revision is not None:
        payload.update(
            {
                "request": dict(request),
                "execution": dict(execution),
                "source_revision": source_revision,
            }
        )
    return _emit(payload)


def _strict_json_loads(raw: bytes) -> object:
    """Reject NaN and Infinity instead of accepting nonstandard JSON values."""

    def reject_constant(_: str) -> object:
        raise ValueError("non-finite JSON token")

    return json.loads(raw.decode("utf-8"), parse_constant=reject_constant)


def _has_isolated_no_site_startup() -> bool:
    """Require parent command ``-I -S`` before dynamic provider import."""
    return bool(sys.flags.isolated) and bool(sys.flags.no_site)


def _configured_site_packages() -> Path:
    """Append only the operator-selected absolute package directory."""
    configured = os.environ.get(_SITE_PACKAGES_ENVIRONMENT_KEY, "").strip()
    if not configured or "\x00" in configured:
        raise ValueError("AKSHARE_RUNNER_SITE_PACKAGES_INVALID")
    candidate = Path(configured)
    if not candidate.is_absolute():
        raise ValueError("AKSHARE_RUNNER_SITE_PACKAGES_INVALID")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("AKSHARE_RUNNER_SITE_PACKAGES_INVALID") from exc
    if not resolved.is_dir():
        raise ValueError("AKSHARE_RUNNER_SITE_PACKAGES_INVALID")
    resolved_text = str(resolved)
    if resolved_text not in sys.path:
        # ``-S`` intentionally skipped global site processing. Appending one
        # reviewed directory does not evaluate .pth/sitecustomize hooks.
        sys.path.append(resolved_text)
    return resolved


def _require_text(value: object, *, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise ValueError("AKSHARE_RUNNER_INVALID_REQUEST")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError("AKSHARE_RUNNER_INVALID_REQUEST")
    return normalized


def _request_id(value: object) -> str:
    request_id = _require_text(value, maximum=128)
    if len(request_id) < 32 or re.fullmatch(r"[A-Za-z0-9_-]+", request_id) is None:
        raise ValueError("AKSHARE_RUNNER_INVALID_REQUEST")
    return request_id


def _execution(envelope: Mapping[str, Any]) -> tuple[Mapping[str, Any], str, dict[str, Any], str]:
    """Validate the pre-parsed execution object without route selection here."""
    execution = envelope.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("AKSHARE_RUNNER_INVALID_REQUEST")
    route = execution.get("route")
    if not isinstance(route, Mapping):
        raise ValueError("AKSHARE_RUNNER_INVALID_REQUEST")
    endpoint = _require_text(execution.get("endpoint"))
    if endpoint not in _ALLOWED_ENDPOINTS:
        raise ValueError("AKSHARE_ROUTE_UNSUPPORTED")
    source_revision = _require_text(execution.get("source_revision"), maximum=512)
    call_kwargs = execution.get("call_kwargs")
    if not isinstance(call_kwargs, Mapping) or len(call_kwargs) > _MAX_CALL_KWARGS:
        raise ValueError("AKSHARE_RUNNER_INVALID_REQUEST")
    normalized_kwargs: dict[str, Any] = {}
    for key, value in call_kwargs.items():
        normalized_key = _require_text(key)
        if normalized_key in normalized_kwargs:
            raise ValueError("AKSHARE_RUNNER_INVALID_REQUEST")
        normalized_kwargs[normalized_key] = value
    try:
        _canonical_json({"call_kwargs": normalized_kwargs, "route": dict(route)})
    except (TypeError, ValueError) as exc:
        raise ValueError("AKSHARE_RUNNER_INVALID_REQUEST") from exc
    return dict(execution), endpoint, normalized_kwargs, source_revision


def _json_safe(value: Any) -> Any:
    """Convert common dataframe scalar types to strict JSON values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe(item_method())
        except (TypeError, ValueError):
            pass
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return str(isoformat())
        except (TypeError, ValueError):
            pass
    return str(value)


def _coerce_response_rows(response: object) -> list[dict[str, Any]]:
    """Convert only bounded dataframe-like or sequence responses to JSON rows."""
    if response is None:
        return []
    try:
        response_length = len(response)  # type: ignore[arg-type]
    except TypeError:
        response_length = None
    if response_length is not None and response_length > _MAX_RESPONSE_ROWS:
        raise ValueError("AKSHARE_RESPONSE_TOO_LARGE")
    to_dict = getattr(response, "to_dict", None)
    if callable(to_dict):
        try:
            rows = to_dict(orient="records")
        except (TypeError, ValueError) as exc:
            raise ValueError("AKSHARE_RESPONSE_INVALID") from exc
    elif isinstance(response, Sequence) and not isinstance(response, (str, bytes, bytearray)):
        rows = response
    else:
        raise ValueError("AKSHARE_RESPONSE_INVALID")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("AKSHARE_RESPONSE_INVALID")
    if len(rows) > _MAX_RESPONSE_ROWS:
        raise ValueError("AKSHARE_RESPONSE_TOO_LARGE")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("AKSHARE_RESPONSE_INVALID")
        normalized_row = {str(key): _json_safe(value) for key, value in row.items()}
        try:
            _canonical_json(normalized_row)
        except (TypeError, ValueError) as exc:
            raise ValueError("AKSHARE_RESPONSE_INVALID") from exc
        normalized.append(normalized_row)
    return normalized


def _source_revision(endpoint: str) -> str:
    """Bind the returned receipt to the installed AkShare distribution version."""
    try:
        version = metadata.version("akshare")
    except metadata.PackageNotFoundError:
        version = "unknown"
    return f"akshare-{version}:{endpoint}"


def main() -> int:
    """Read exactly one parent-built execution envelope and emit one receipt."""
    if not _has_isolated_no_site_startup():
        return _error(None, "AKSHARE_RUNNER_ISOLATION_UNAVAILABLE", "runner requires -I -S")
    raw = sys.stdin.buffer.read(_MAX_REQUEST_BYTES + 1)
    if len(raw) > _MAX_REQUEST_BYTES:
        return _error(None, "AKSHARE_RUNNER_REQUEST_TOO_LARGE", "request exceeds runner limit")
    try:
        envelope = _strict_json_loads(raw)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return _error(None, "AKSHARE_RUNNER_INVALID_REQUEST", "request is not valid strict JSON")
    if not isinstance(envelope, Mapping):
        return _error(None, "AKSHARE_RUNNER_INVALID_REQUEST", "request envelope must be an object")
    request_id: object = envelope.get("request_id")
    request: Mapping[str, Any] | None = None
    execution: Mapping[str, Any] | None = None
    parent_source_revision: str | None = None
    try:
        if envelope.get("protocol_version") != PROTOCOL_VERSION:
            raise ValueError("AKSHARE_RUNNER_PROTOCOL_MISMATCH")
        parsed_request_id = _request_id(request_id)
        request = envelope.get("request")
        if not isinstance(request, Mapping) or request.get("request_id") != parsed_request_id:
            raise ValueError("AKSHARE_RUNNER_INVALID_REQUEST")
        if request.get("provider") != "akshare":
            raise ValueError("AKSHARE_PROVIDER_MISMATCH")
        execution, endpoint, call_kwargs, parent_source_revision = _execution(envelope)
        _configured_site_packages()
        if _source_revision(endpoint) != parent_source_revision:
            raise ValueError("AKSHARE_RUNNER_SOURCE_REVISION_MISMATCH")
    except ValueError as exc:
        return _error(
            request_id,
            str(exc),
            "runner request validation failed",
            request=request,
            execution=execution,
            source_revision=parent_source_revision,
        )

    try:
        akshare = importlib.import_module("akshare")
        source_callable = getattr(akshare, endpoint, None)
        if not callable(source_callable):
            raise ValueError("AKSHARE_ROUTE_UNAVAILABLE")
        captured_output = _BoundedTextCapture(_MAX_CAPTURED_PROVIDER_OUTPUT_BYTES)
        with redirect_stdout(captured_output), redirect_stderr(captured_output):
            response = source_callable(**call_kwargs)
        response_rows = _coerce_response_rows(response)
    except ValueError as exc:
        return _error(
            request_id,
            str(exc),
            "provider result is invalid",
            request=request,
            execution=execution,
            source_revision=parent_source_revision,
        )
    except ImportError:
        return _error(
            request_id,
            "AKSHARE_RUNNER_UNAVAILABLE",
            "AkShare import is unavailable",
            request=request,
            execution=execution,
            source_revision=parent_source_revision,
        )
    except Exception:
        return _error(
            request_id,
            "AKSHARE_FETCH_FAILED",
            "provider request failed",
            request=request,
            execution=execution,
            source_revision=parent_source_revision,
        )

    return _emit(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": parsed_request_id,
            "request": dict(request),
            "execution": execution,
            "source_revision": parent_source_revision,
            "response_rows": response_rows,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
