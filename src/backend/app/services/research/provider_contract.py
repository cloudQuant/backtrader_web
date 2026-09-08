"""Immutable wire-request metadata shared by trusted provider adapters.

The payload is intentionally retained as bytes: callers that preflight a
request must be able to prove that the adapter later sent those exact bytes,
rather than an independently re-serialized approximation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from app.services.research.redaction import redact_sensitive_payload

_MAX_PREPARED_PAYLOAD_BYTES = 1_048_576
_MAX_OUTPUT_TOKENS = 131_072
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class PreparedProviderRequest:
    """A bounded immutable request body and the pinned route it belongs to."""

    payload: bytes
    provider_id: str
    model_id: str
    endpoint_hash: str
    max_output_tokens: int

    def __post_init__(self) -> None:
        try:
            if (
                type(self.payload) is not bytes
                or not 0 < len(self.payload) <= _MAX_PREPARED_PAYLOAD_BYTES
            ):
                raise ValueError
            _identity(self.provider_id, 128)
            _identity(self.model_id, 256)
            if (
                type(self.endpoint_hash) is not str
                or _SHA256_HEX.fullmatch(self.endpoint_hash) is None
            ):
                raise ValueError
            if (
                type(self.max_output_tokens) is not int
                or not 0 < self.max_output_tokens <= _MAX_OUTPUT_TOKENS
            ):
                raise ValueError
        except Exception:
            raise ValueError("LLM_PREPARED_REQUEST_INVALID") from None

    @property
    def body_hash(self) -> str:
        """Return the SHA-256 identity of the exact outbound body."""

        return sha256(self.payload).hexdigest()


def _identity(value: object, maximum: int) -> None:
    if (
        type(value) is not str
        or not value.strip()
        or len(value.encode("utf-8")) > maximum
        or "\x00" in value
        or redact_sensitive_payload(value) != value
    ):
        raise ValueError
