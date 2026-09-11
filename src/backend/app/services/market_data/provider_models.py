"""Provider-neutral market-data request and result contracts.

These DTOs are deliberately independent from OpenBB transport and runtime
activation so AkShare and future providers retain the same validated boundary.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Protocol

from app.services.market_data.multi_record import normalize_record_dimensions
from app.services.market_data.shared_payload import SharedSourcePayloadSegment


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _require_text(value: str, *, field_name: str, maximum: int = 2048) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} is too long")
    return normalized


def _require_request_id(value: object) -> str:
    """Validate the opaque CSPRNG correlation token accepted from internal code."""
    if not isinstance(value, str):
        raise ValueError("request_id must be a string")
    normalized = value.strip()
    if (
        len(normalized) < 32
        or len(normalized) > 128
        or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            for character in normalized
        )
    ):
        raise ValueError("request_id must be an opaque base64url token")
    return normalized


def _require_sha256(value: object, *, field_name: str) -> str:
    """Validate a canonical SHA-256 hex digest without accepting a prefix."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return normalized


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True, slots=True)
class MarketDataProviderRequest:
    """The bounded, provider-neutral request sent to one market-data adapter.

    ``request_id`` is generated once for each authorized fetch attempt with
    the operating-system CSPRNG.  It intentionally differs from the public
    query fingerprint, which describes business semantics rather than a
    specific provider call.
    """

    query_fingerprint: str
    canonical_id: str
    asset_type: str
    provider_symbol: str
    market: str
    data_kind: str
    frequency: str
    start_at: datetime
    end_at: datetime
    required_fields: frozenset[str]
    provider: str
    adjustment: str | None = None
    price_basis: str | None = None
    currency: str | None = None
    unit: str | None = None
    source_policy_id: str | None = None
    route_id: str | None = None
    # The resolved query product and the server-owned endpoint remain in the
    # echoed DTO so an isolated runner cannot substitute a same-shaped route.
    family_id: str | None = None
    family_contract_version: str | None = None
    provider_endpoint: str | None = None
    # These frozen master-data facts let an adapter defend a product-specific
    # source route even when it is invoked outside the policy selector.
    product_type: str | None = None
    fund_identity_kind: str | None = None
    # This is the reviewed, server-owned source-policy descriptor.  It is
    # deliberately separate from the authenticated caller's dynamic access
    # grant below, so a receipt can prove both what route policy allowed and
    # which current principal/source decision authorized the attempt.
    policy_descriptor_hash: str | None = None
    access_grant_descriptor_hash: str | None = None
    request_id: str = field(default_factory=lambda: secrets.token_urlsafe(32))

    def __post_init__(self) -> None:
        for field_name in (
            "query_fingerprint",
            "canonical_id",
            "asset_type",
            "provider_symbol",
            "market",
            "data_kind",
            "frequency",
            "provider",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "adjustment",
            "price_basis",
            "currency",
            "unit",
            "source_policy_id",
            "route_id",
            "family_id",
            "family_contract_version",
            "provider_endpoint",
            "product_type",
            "fund_identity_kind",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _require_text(value, field_name=field_name, maximum=256),
                )
        if (self.family_id is None) != (self.family_contract_version is None):
            raise ValueError("family_id and family_contract_version must be specified together")
        object.__setattr__(self, "request_id", _require_request_id(self.request_id))
        if self.policy_descriptor_hash is not None:
            object.__setattr__(
                self,
                "policy_descriptor_hash",
                _require_sha256(
                    self.policy_descriptor_hash,
                    field_name="policy_descriptor_hash",
                ),
            )
        if self.access_grant_descriptor_hash is not None:
            object.__setattr__(
                self,
                "access_grant_descriptor_hash",
                _require_sha256(
                    self.access_grant_descriptor_hash,
                    field_name="access_grant_descriptor_hash",
                ),
            )
        if len(self.query_fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in self.query_fingerprint.lower()
        ):
            raise ValueError("query_fingerprint must be a SHA-256 hex digest")
        start_at = _as_utc(self.start_at, field_name="start_at")
        end_at = _as_utc(self.end_at, field_name="end_at")
        if start_at >= end_at:
            raise ValueError("provider request requires a half-open [start_at, end_at) interval")
        if not isinstance(self.required_fields, frozenset) or not self.required_fields:
            raise ValueError("required_fields must be a non-empty frozenset")
        for field_name in self.required_fields:
            _require_text(field_name, field_name="required field", maximum=256)
        object.__setattr__(self, "start_at", start_at)
        object.__setattr__(self, "end_at", end_at)

    @property
    def dto_payload(self) -> dict[str, Any]:
        """Return the exact outbound DTO that a provider receipt must echo."""
        return {
            "request_id": self.request_id,
            "query_fingerprint": self.query_fingerprint,
            "canonical_id": self.canonical_id,
            "asset_type": self.asset_type,
            "provider_symbol": self.provider_symbol,
            "market": self.market,
            "data_kind": self.data_kind,
            "frequency": self.frequency,
            "start_at": self.start_at.isoformat(),
            "end_at": self.end_at.isoformat(),
            "required_fields": sorted(self.required_fields),
            "provider": self.provider,
            "adjustment": self.adjustment,
            "price_basis": self.price_basis,
            "currency": self.currency,
            "unit": self.unit,
            "source_policy_id": self.source_policy_id,
            "route_id": self.route_id,
            "family_id": self.family_id,
            "family_contract_version": self.family_contract_version,
            "provider_endpoint": self.provider_endpoint,
            "product_type": self.product_type,
            "fund_identity_kind": self.fund_identity_kind,
            "policy_descriptor_hash": self.policy_descriptor_hash,
            "access_grant_descriptor_hash": self.access_grant_descriptor_hash,
        }

    @property
    def provider_request_fingerprint_sha256(self) -> str:
        """Hash the complete outbound DTO independently from query identity."""
        return hashlib.sha256(_canonical_json(self.dto_payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderMarketObservation:
    """One normalized observation returned by a provider adapter."""

    event_at: datetime
    available_at: datetime
    fields: Mapping[str, Any]
    # This is deliberately dimensions only: the Store, rather than a provider
    # adapter or external caller, derives the canonical semantic key and its
    # digest after it binds the exact family contract.
    record_dimensions: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        event_at = _as_utc(self.event_at, field_name="event_at")
        available_at = _as_utc(self.available_at, field_name="available_at")
        if not isinstance(self.fields, Mapping):
            raise TypeError("fields must be a mapping")
        normalized_fields: dict[str, Any] = {}
        for field_name, value in self.fields.items():
            normalized_field_name = _require_text(field_name, field_name="field", maximum=256)
            if normalized_field_name in normalized_fields:
                raise ValueError("provider observation contains duplicate normalized field names")
            normalized_fields[normalized_field_name] = value
        if not normalized_fields:
            raise ValueError("provider observation fields must not be empty")
        normalized_dimensions: Mapping[str, object] | None = None
        if self.record_dimensions is not None:
            if not isinstance(self.record_dimensions, Mapping):
                raise TypeError("record_dimensions must be a mapping or None")
            # Record dimensions become part of the durable server-derived
            # identity later in Store. Unlike ordinary field payloads, they
            # must not retain nested caller-owned dict/list references between
            # DTO construction and persistence.
            normalized_dimensions = normalize_record_dimensions(self.record_dimensions)
        object.__setattr__(self, "event_at", event_at)
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(self, "fields", MappingProxyType(normalized_fields))
        object.__setattr__(
            self,
            "record_dimensions",
            normalized_dimensions,
        )


@dataclass(frozen=True, slots=True)
class ProviderFetchResult:
    """Source-provenanced provider response ready for validation and persistence."""

    provider_id: str
    source_revision: str
    retrieved_at: datetime
    observations: tuple[ProviderMarketObservation, ...]
    raw_payload: Mapping[str, Any]
    request: MarketDataProviderRequest
    warnings: tuple[str, ...] = ()
    shared_source_payload_segment: SharedSourcePayloadSegment | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "provider_id", _require_text(self.provider_id, field_name="provider_id")
        )
        object.__setattr__(
            self,
            "source_revision",
            _require_text(self.source_revision, field_name="source_revision"),
        )
        object.__setattr__(
            self, "retrieved_at", _as_utc(self.retrieved_at, field_name="retrieved_at")
        )
        observations = tuple(self.observations)
        if any(not isinstance(item, ProviderMarketObservation) for item in observations):
            raise TypeError("observations must contain ProviderMarketObservation values")
        if not isinstance(self.raw_payload, Mapping):
            raise TypeError("raw_payload must be a mapping")
        if not isinstance(self.request, MarketDataProviderRequest):
            raise TypeError("request must be the original MarketDataProviderRequest")
        if self.shared_source_payload_segment is not None and not isinstance(
            self.shared_source_payload_segment, SharedSourcePayloadSegment
        ):
            raise TypeError(
                "shared_source_payload_segment must be SharedSourcePayloadSegment or None"
            )
        warnings = tuple(_require_text(item, field_name="warning") for item in self.warnings)
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "raw_payload", MappingProxyType(dict(self.raw_payload)))
        object.__setattr__(self, "warnings", warnings)

    @property
    def raw_payload_hash(self) -> str:
        """Return a deterministic integrity hash for the persisted source payload."""
        # ``__post_init__`` freezes the top-level receipt mapping so callers
        # cannot replace its evidence envelope after provider validation.
        # ``json.dumps`` does not know how to serialize ``mappingproxy``
        # directly, however.  Hash a plain snapshot of that immutable mapping
        # so the public provenance helper remains usable for every validated
        # AkShare/OpenBB result and preserves the same canonical JSON bytes.
        return hashlib.sha256(_canonical_json(dict(self.raw_payload)).encode("utf-8")).hexdigest()


class MarketDataProvider(Protocol):
    """A narrow adapter boundary for AkShare, OpenBB, or approved future sources."""

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        """Fetch an exact bounded request without writing storage directly."""
