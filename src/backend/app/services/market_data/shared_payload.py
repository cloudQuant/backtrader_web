"""Narrow descriptor for content-addressed raw provider-response segments."""

from __future__ import annotations

from dataclasses import dataclass


def _require_segment_text(value: object, *, field_name: str) -> str:
    """Validate a bounded descriptor value without importing provider DTOs."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > 128:
        raise ValueError(f"{field_name} is too long")
    return normalized


@dataclass(frozen=True, slots=True)
class SharedSourcePayloadSegment:
    """Describe one raw-response segment that Store may content-address.

    The descriptor carries no caller-supplied payload, digest, or byte count.
    ``MarketDataStore`` extracts the named segment from the complete raw
    receipt and computes its immutable evidence identity itself.
    """

    segment_key: str
    payload_format: str
    payload_role: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "segment_key",
            _require_segment_text(self.segment_key, field_name="shared payload segment key"),
        )
        object.__setattr__(
            self,
            "payload_format",
            _require_segment_text(self.payload_format, field_name="shared payload format"),
        )
        object.__setattr__(
            self,
            "payload_role",
            _require_segment_text(self.payload_role, field_name="shared payload role"),
        )
