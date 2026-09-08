"""Recursive redaction for untrusted research inputs and ordinary read models."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = frozenset(
    {
        "apikey",
        "authorization",
        "credential",
        "password",
        "privatekey",
        "secret",
        "token",
    }
)
_SECRET_TEXT = re.compile(
    r"(?:\b(?:api[_-]?key|token|secret|password)\s*[=:]|\bsk-[A-Za-z0-9_-]{8,}|\bBearer\s+\S+)",
    re.IGNORECASE,
)


def redact_sensitive_payload(payload: Any) -> Any:
    """Return a structurally equivalent payload with sensitive values removed.

    This helper deliberately preserves ordinary fields so callers can retain a
    useful audit summary, but it treats all nested secret-bearing keys and URL
    credentials/query parameters as untrusted and non-exportable.
    """

    if isinstance(payload, Mapping):
        return {
            str(key): REDACTED if _is_sensitive_key(str(key)) else redact_sensitive_payload(value)
            for key, value in payload.items()
        }
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [redact_sensitive_payload(value) for value in payload]
    if isinstance(payload, str):
        return _redact_string(payload)
    return payload


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _redact_string(value: str) -> str:
    if _SECRET_TEXT.search(value):
        return REDACTED
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return value

    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    netloc = (
        f"{REDACTED}@{hostname}{port}" if (parsed.username or parsed.password) else parsed.netloc
    )
    query = [
        (key, REDACTED if _is_sensitive_key(key) else item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(query), parsed.fragment))
