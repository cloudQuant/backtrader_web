"""Narrow redaction helpers for untrusted multi-asset research payloads.

Provider payloads, legacy report rows and error text are untrusted at their
respective boundaries.  These helpers intentionally retain the surrounding
field shape for auditability while replacing credential-bearing values before
they can enter a snapshot, report, export or public API response.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED_VALUE = "[REDACTED]"

_SENSITIVE_KEY_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "access_key",
        "secret_key",
        "client_secret",
        "private_key",
        "password",
        "passwd",
        "authorization",
        "access_token",
        "refresh_token",
        "auth_token",
        "cookie",
        "set_cookie",
        "credentials",
    }
)
_SENSITIVE_TEXT = re.compile(
    r"(?ix)"
    r"(?:\b(?:api[_ -]?key|access[_ -]?key|secret[_ -]?key|client[_ -]?secret|"
    r"private[_ -]?key|password|passwd|authorization|access[_ -]?token|"
    r"refresh[_ -]?token|auth[_ -]?token|cookie)\b\s*(?:=|:)\s*)"
    r"(?:bearer\s+)?[^\s,;]+"
    r"|(?:\bbearer\s+)[A-Za-z0-9._~+/=-]+"
)


def redact_sensitive_data(value: Any) -> Any:
    """Return a recursively redacted copy of an untrusted JSON-like value.

    Keys are retained with a fixed marker so an audit can tell a provider sent
    an impermissible field without retaining its value.  Plain strings also
    have common ``key=value`` and ``Bearer`` credential forms removed because
    warnings and legacy report markdown do not always preserve a JSON key.
    """
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for raw_key, nested_value in value.items():
            key = str(raw_key)
            if _is_sensitive_key(key):
                redacted[key] = REDACTED_VALUE
            else:
                redacted[key] = redact_sensitive_data(nested_value)
        return redacted
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, bytes):
        return REDACTED_VALUE
    if isinstance(value, str):
        return _SENSITIVE_TEXT.sub(REDACTED_VALUE, value)
    return value


def _is_sensitive_key(value: str) -> bool:
    """Recognize credential field names without treating crypto token data as a secret."""
    normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return normalized in _SENSITIVE_KEY_NAMES
