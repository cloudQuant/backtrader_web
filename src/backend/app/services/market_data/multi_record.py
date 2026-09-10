"""Pure, fail-closed foundations for record-keyed B2 market-data facts.

The current public market-data query path intentionally remains limited to
single-record products.  This module supplies only deterministic building
blocks for a future local-only B2 path: server-derived semantic record keys and
explicit slice/report completeness decisions.  It does not register a family,
call a provider, read a database, or infer domain rules from observed rows.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType

RECORD_IDENTITY_CONTRACT_VERSION = "market-data-semantic-record-key-v1"
"""Version of the durable semantic record-key canonicalization contract."""

COMPLETENESS_SELECTOR_CONTRACT_VERSION = "market-data-b2-completeness-selector-v1"
"""Version of selector digests used to bind completeness evidence."""

SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON = (
    '{"record_identity_contract_version":"market-data-semantic-record-key-v1","scope":"singleton"}'
)
"""Fixed canonical payload for every legacy/single-record observation row."""

SINGLE_RECORD_SEMANTIC_KEY_SHA256 = (
    "98220d1065fb50740a858df25f884573e8c6aea554b05a3268ed4d1fd621d08e"
)
"""SHA-256 for :data:`SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON`."""

_MAX_TEXT_LENGTH = 255
_MAX_DIMENSION_DEPTH = 8
_MAX_DIMENSION_ITEMS = 128
_MAX_SEQUENCE_ITEMS = 128
_MAX_CANONICAL_JSON_BYTES = 16 * 1024
_MAX_SELECTOR_MANIFEST_BYTES = 4 * 1024 * 1024
_MAX_EXPECTED_RECORD_KEYS = 50_000
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_UTC = timezone.utc


def _canonical_json(value: object) -> str:
    """Encode one already-normalized JSON value in the single canonical form."""
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(encoded.encode("utf-8")) > _MAX_CANONICAL_JSON_BYTES:
        raise ValueError("canonical JSON exceeds the maximum permitted size")
    return encoded


def _canonical_selector_manifest_json(value: object) -> str:
    """Encode a bounded completeness manifest without the record-key size limit.

    A single semantic key stays deliberately small (16 KiB), while a declared
    option/report manifest may contain every accepted record in one Store
    batch. The 4 MiB cap covers 50,000 SHA-256 entries plus selector metadata
    and keeps a caller from turning an internal local read into an unbounded
    memory allocation.
    """
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(encoded.encode("utf-8")) > _MAX_SELECTOR_MANIFEST_BYTES:
        raise ValueError("selector manifest exceeds the maximum permitted size")
    return encoded


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_text(value: object, *, field_name: str, maximum: int = _MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} exceeds {maximum} characters")
    return normalized


def _require_sha256(value: object, *, field_name: str) -> str:
    normalized = _require_text(value, field_name=field_name, maximum=64)
    if _SHA256_PATTERN.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be a lowercase 64-character SHA-256 digest")
    return normalized


def _require_aware_utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(_UTC)


def _normalize_dimension_name(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} keys must be strings")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} keys must be non-empty strings")
    if len(normalized) > _MAX_TEXT_LENGTH:
        raise ValueError(f"{field_name} keys exceed {_MAX_TEXT_LENGTH} characters")
    return normalized


def _normalize_json_value(value: object, *, field_name: str, depth: int) -> object:
    """Freeze a bounded JSON-safe value without applying domain-specific coercion."""
    if depth > _MAX_DIMENSION_DEPTH:
        raise ValueError(f"{field_name} exceeds maximum nesting depth")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} contains an empty string")
        if len(normalized) > _MAX_TEXT_LENGTH:
            raise ValueError(f"{field_name} string exceeds {_MAX_TEXT_LENGTH} characters")
        return normalized
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must contain finite numbers")
        return value
    if isinstance(value, Mapping):
        return _normalize_mapping(value, field_name=field_name, depth=depth + 1)
    if isinstance(value, (list, tuple)):
        if not value:
            raise ValueError(f"{field_name} cannot contain an empty sequence")
        if len(value) > _MAX_SEQUENCE_ITEMS:
            raise ValueError(f"{field_name} contains too many sequence items")
        return tuple(
            _normalize_json_value(item, field_name=f"{field_name}[{index}]", depth=depth + 1)
            for index, item in enumerate(value)
        )
    raise TypeError(f"{field_name} contains unsupported JSON value type")


def _normalize_mapping(
    value: object,
    *,
    field_name: str,
    depth: int = 0,
    allow_empty: bool = False,
) -> Mapping[str, object]:
    """Freeze an object with sorted, non-empty string keys."""
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    if len(value) > _MAX_DIMENSION_ITEMS:
        raise ValueError(f"{field_name} contains too many items")

    normalized: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        key = _normalize_dimension_name(raw_key, field_name=field_name)
        if key in normalized:
            raise ValueError(f"{field_name} contains duplicate normalized key {key!r}")
        normalized[key] = _normalize_json_value(
            raw_value,
            field_name=f"{field_name}.{key}",
            depth=depth,
        )

    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} must be non-empty")
    return MappingProxyType(dict(sorted(normalized.items())))


def _json_compatible(value: object) -> object:
    """Convert frozen normalized values into values accepted by ``json.dumps``."""
    if isinstance(value, Mapping):
        return {key: _json_compatible(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_compatible(item) for item in value]
    return value


def _canonical_json_values_equal(left: object, right: object) -> bool:
    """Compare normalized JSON values with the same type-sensitive encoding as keys.

    Python equality is unsafe for a semantic record key because ``True == 1``
    and ``-0.0 == 0.0`` even though the canonical JSON bytes, and therefore the
    record-key digest, are different. Both callers pass values produced by the
    structural normalizer above, so this conversion is deliberately narrow.
    """
    return _canonical_json(_json_compatible(left)) == _canonical_json(_json_compatible(right))


@dataclass(frozen=True, slots=True)
class SemanticRecordKey:
    """One server-normalized, hash-addressable business-record identity."""

    canonical_json: str
    sha256: str
    dimensions: Mapping[str, object]
    is_singleton: bool

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_json, str) or not self.canonical_json:
            raise ValueError("canonical_json must be a non-empty string")
        if _sha256(self.canonical_json) != _require_sha256(self.sha256, field_name="sha256"):
            raise ValueError("sha256 must match canonical_json")
        if not isinstance(self.is_singleton, bool):
            raise TypeError("is_singleton must be a bool")
        normalized_dimensions = _normalize_mapping(
            self.dimensions,
            field_name="dimensions",
            allow_empty=self.is_singleton,
        )
        try:
            payload = json.loads(self.canonical_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("canonical_json must be a JSON object") from exc
        if not isinstance(payload, dict) or _canonical_json(payload) != self.canonical_json:
            raise ValueError("canonical_json must be a canonical JSON object")

        if self.is_singleton:
            if normalized_dimensions:
                raise ValueError("singleton semantic record keys cannot have dimensions")
            expected_payload = {
                "record_identity_contract_version": RECORD_IDENTITY_CONTRACT_VERSION,
                "scope": "singleton",
            }
            if payload != expected_payload:
                raise ValueError(
                    "singleton semantic record key payload is not the fixed server value"
                )
        else:
            expected_fields = {
                "record_identity_contract_version",
                "family_id",
                "family_contract_version",
                "dimensions",
            }
            if set(payload) != expected_fields:
                raise ValueError("non-singleton semantic record key payload has invalid fields")
            if payload["record_identity_contract_version"] != RECORD_IDENTITY_CONTRACT_VERSION:
                raise ValueError("semantic record key contract version is unsupported")
            family_id = _require_text(payload["family_id"], field_name="family_id")
            family_contract_version = _require_text(
                payload["family_contract_version"],
                field_name="family_contract_version",
            )
            if (
                payload["family_id"] != family_id
                or payload["family_contract_version"] != family_contract_version
            ):
                raise ValueError("semantic record key family values must already be normalized")
            payload_dimensions = _normalize_mapping(
                payload["dimensions"],
                field_name="canonical_json.dimensions",
            )
            if not _canonical_json_values_equal(payload_dimensions, normalized_dimensions):
                raise ValueError("canonical_json dimensions must match dimensions")
        object.__setattr__(self, "dimensions", normalized_dimensions)


def _semantic_record_key(
    *,
    canonical_json: str,
    dimensions: Mapping[str, object],
    is_singleton: bool,
) -> SemanticRecordKey:
    return SemanticRecordKey(
        canonical_json=canonical_json,
        sha256=_sha256(canonical_json),
        dimensions=dimensions,
        is_singleton=is_singleton,
    )


_SINGLE_RECORD_SEMANTIC_KEY = _semantic_record_key(
    canonical_json=SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON,
    dimensions=MappingProxyType({}),
    is_singleton=True,
)


def single_record_semantic_key() -> SemanticRecordKey:
    """Return the one identity allowed for every single-record observation."""
    return _SINGLE_RECORD_SEMANTIC_KEY


def normalize_semantic_record_key(
    *,
    family_id: str,
    family_contract_version: str,
    dimensions: Mapping[str, object],
) -> SemanticRecordKey:
    """Issue a B2 key from server-controlled family and dimension values.

    The function deliberately preserves JSON scalar types and values after only
    structural normalization.  Product-specific transformations such as strike
    rounding, contract aliasing, or case folding belong to a reviewed family
    adapter before it reaches this generic foundation.
    """
    normalized_family_id = _require_text(family_id, field_name="family_id")
    normalized_family_contract_version = _require_text(
        family_contract_version,
        field_name="family_contract_version",
    )
    normalized_dimensions = _normalize_mapping(dimensions, field_name="dimensions")
    canonical_json = _canonical_json(
        {
            "record_identity_contract_version": RECORD_IDENTITY_CONTRACT_VERSION,
            "family_id": normalized_family_id,
            "family_contract_version": normalized_family_contract_version,
            "dimensions": _json_compatible(normalized_dimensions),
        }
    )
    return _semantic_record_key(
        canonical_json=canonical_json,
        dimensions=normalized_dimensions,
        is_singleton=False,
    )


def normalize_record_dimensions(dimensions: Mapping[str, object]) -> Mapping[str, object]:
    """Deep-freeze one provider-owned dimension object before Store identity binding."""
    normalized = _normalize_mapping(dimensions, field_name="record_dimensions")
    # Reject an overlarge provider DTO before it reaches a source receipt or
    # Store transaction. The later complete semantic-key construction applies
    # the same bounded canonicalizer to the family/version envelope.
    _canonical_json(_json_compatible(normalized))
    return normalized


def _normalize_expected_record_key_sha256s(
    value: Iterable[str] | None,
) -> frozenset[str] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError("expected_record_key_sha256s must be an iterable of SHA-256 digests")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if index >= _MAX_EXPECTED_RECORD_KEYS:
            raise ValueError(
                f"expected_record_key_sha256s exceeds {_MAX_EXPECTED_RECORD_KEYS} entries"
            )
        digest = _require_sha256(item, field_name=f"expected_record_key_sha256s[{index}]")
        if digest in seen:
            raise ValueError("expected_record_key_sha256s contains duplicate digest")
        seen.add(digest)
        normalized.append(digest)
    return frozenset(normalized)


def _selector_digest(
    *,
    selector_kind: str,
    family_id: str,
    family_contract_version: str,
    selector_dimensions: Mapping[str, object],
    expected_record_key_sha256s: frozenset[str] | None,
) -> str:
    return _sha256(
        _canonical_selector_manifest_json(
            {
                "completeness_selector_contract_version": COMPLETENESS_SELECTOR_CONTRACT_VERSION,
                "selector_kind": selector_kind,
                "family_id": family_id,
                "family_contract_version": family_contract_version,
                "selector_dimensions": _json_compatible(selector_dimensions),
                "expected_record_key_sha256s": (
                    sorted(expected_record_key_sha256s)
                    if expected_record_key_sha256s is not None
                    else None
                ),
            }
        )
    )


@dataclass(frozen=True, slots=True)
class B2SliceSelector:
    """A frozen option-like slice and its approved expected record-key manifest."""

    family_id: str
    family_contract_version: str
    selector_dimensions: Mapping[str, object]
    expected_record_key_sha256s: Iterable[str] | None
    selector_digest: str = field(init=False)

    def __post_init__(self) -> None:
        family_id = _require_text(self.family_id, field_name="family_id")
        family_contract_version = _require_text(
            self.family_contract_version,
            field_name="family_contract_version",
        )
        selector_dimensions = _normalize_mapping(
            self.selector_dimensions,
            field_name="selector_dimensions",
        )
        expected = _normalize_expected_record_key_sha256s(self.expected_record_key_sha256s)
        object.__setattr__(self, "family_id", family_id)
        object.__setattr__(self, "family_contract_version", family_contract_version)
        object.__setattr__(self, "selector_dimensions", selector_dimensions)
        object.__setattr__(self, "expected_record_key_sha256s", expected)
        object.__setattr__(
            self,
            "selector_digest",
            _selector_digest(
                selector_kind="slice",
                family_id=family_id,
                family_contract_version=family_contract_version,
                selector_dimensions=selector_dimensions,
                expected_record_key_sha256s=expected,
            ),
        )


@dataclass(frozen=True, slots=True)
class B2ReportSelector:
    """A frozen inventory/CME-like report and its expected record-key manifest."""

    family_id: str
    family_contract_version: str
    selector_dimensions: Mapping[str, object]
    expected_record_key_sha256s: Iterable[str] | None
    selector_digest: str = field(init=False)

    def __post_init__(self) -> None:
        family_id = _require_text(self.family_id, field_name="family_id")
        family_contract_version = _require_text(
            self.family_contract_version,
            field_name="family_contract_version",
        )
        selector_dimensions = _normalize_mapping(
            self.selector_dimensions,
            field_name="selector_dimensions",
        )
        expected = _normalize_expected_record_key_sha256s(self.expected_record_key_sha256s)
        object.__setattr__(self, "family_id", family_id)
        object.__setattr__(self, "family_contract_version", family_contract_version)
        object.__setattr__(self, "selector_dimensions", selector_dimensions)
        object.__setattr__(self, "expected_record_key_sha256s", expected)
        object.__setattr__(
            self,
            "selector_digest",
            _selector_digest(
                selector_kind="report",
                family_id=family_id,
                family_contract_version=family_contract_version,
                selector_dimensions=selector_dimensions,
                expected_record_key_sha256s=expected,
            ),
        )


@dataclass(frozen=True, slots=True)
class ZeroRecordCertificate:
    """Evidence that one selector/event pair was explicitly declared to have no rows.

    This pure object does not itself make a certificate durable or authorize a
    response. A future provider integration must bind ``evidence_sha256`` to
    an immutable receipt and visibility anchor before any local reader accepts
    it. The current B2 local reader deliberately accepts no zero certificate.
    """

    selector_digest: str
    event_at: datetime
    evidence_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "selector_digest",
            _require_sha256(self.selector_digest, field_name="selector_digest"),
        )
        object.__setattr__(
            self,
            "event_at",
            _require_aware_utc(self.event_at, field_name="zero-record certificate event_at"),
        )
        object.__setattr__(
            self,
            "evidence_sha256",
            _require_sha256(self.evidence_sha256, field_name="evidence_sha256"),
        )


class CompletenessStatus(str, Enum):
    """Whether a selector's observations meet its explicit manifest."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class CompletenessResult:
    """A deterministic completeness decision with all fail-closed reasons."""

    selector_digest: str
    status: CompletenessStatus
    reason_codes: tuple[str, ...]
    expected_record_key_sha256s: frozenset[str] | None
    observed_record_key_sha256s: frozenset[str]
    missing_record_key_sha256s: frozenset[str]
    duplicate_record_key_sha256s: frozenset[str]
    unexpected_record_key_sha256s: frozenset[str]
    zero_record_certificate_used: bool

    @property
    def is_complete(self) -> bool:
        """Return the boolean form used by local readers and coverage callers."""
        return self.status is CompletenessStatus.COMPLETE


def _normalize_observed_record_key_sha256s(
    value: Iterable[str],
) -> tuple[frozenset[str], frozenset[str]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError("observed_record_key_sha256s must be an iterable of SHA-256 digests")

    observed: set[str] = set()
    duplicates: set[str] = set()
    for index, item in enumerate(value):
        digest = _require_sha256(item, field_name=f"observed_record_key_sha256s[{index}]")
        if digest in observed:
            duplicates.add(digest)
        observed.add(digest)
    return frozenset(observed), frozenset(duplicates)


def _plan_completeness(
    *,
    selector_digest: str,
    expected_record_key_sha256s: frozenset[str] | None,
    observed_record_key_sha256s: Iterable[str],
    zero_record_certificate: ZeroRecordCertificate | None,
    event_at: datetime | None,
) -> CompletenessResult:
    if zero_record_certificate is not None and not isinstance(
        zero_record_certificate,
        ZeroRecordCertificate,
    ):
        raise TypeError("zero_record_certificate must be a ZeroRecordCertificate")

    observed, duplicates = _normalize_observed_record_key_sha256s(observed_record_key_sha256s)
    missing: frozenset[str] = frozenset()
    unexpected: frozenset[str] = frozenset()
    reason_codes: list[str] = []
    zero_record_certificate_used = False

    if expected_record_key_sha256s is None:
        reason_codes.append("EXPECTED_RECORD_SET_UNDECLARED")
    else:
        missing = expected_record_key_sha256s - observed
        unexpected = observed - expected_record_key_sha256s
        if duplicates:
            reason_codes.append("DUPLICATE_RECORD_KEY")
        if missing:
            reason_codes.append("MISSING_RECORD_KEY")
        if unexpected:
            reason_codes.append("UNEXPECTED_RECORD_KEY")

        if not expected_record_key_sha256s and not observed:
            if zero_record_certificate is None:
                reason_codes.append("EMPTY_RESULT_UNDECLARED")
            elif zero_record_certificate.selector_digest != selector_digest:
                reason_codes.append("ZERO_RECORD_CERTIFICATE_SELECTOR_MISMATCH")
            elif event_at is None:
                reason_codes.append("ZERO_RECORD_CERTIFICATE_EVENT_UNBOUND")
            elif zero_record_certificate.event_at != _require_aware_utc(
                event_at,
                field_name="completeness event_at",
            ):
                reason_codes.append("ZERO_RECORD_CERTIFICATE_EVENT_MISMATCH")
            else:
                zero_record_certificate_used = True
        elif zero_record_certificate is not None:
            reason_codes.append("ZERO_RECORD_CERTIFICATE_NOT_ALLOWED")

    status = CompletenessStatus.COMPLETE if not reason_codes else CompletenessStatus.INCOMPLETE
    return CompletenessResult(
        selector_digest=selector_digest,
        status=status,
        reason_codes=tuple(reason_codes),
        expected_record_key_sha256s=expected_record_key_sha256s,
        observed_record_key_sha256s=observed,
        missing_record_key_sha256s=missing,
        duplicate_record_key_sha256s=duplicates,
        unexpected_record_key_sha256s=unexpected,
        zero_record_certificate_used=zero_record_certificate_used,
    )


class SliceCompletenessPlanner:
    """Evaluate only a declared option-like slice manifest; never infer one."""

    def plan(
        self,
        *,
        selector: B2SliceSelector,
        observed_record_key_sha256s: Iterable[str],
        zero_record_certificate: ZeroRecordCertificate | None = None,
        event_at: datetime | None = None,
    ) -> CompletenessResult:
        if not isinstance(selector, B2SliceSelector):
            raise TypeError("selector must be a B2SliceSelector")
        return _plan_completeness(
            selector_digest=selector.selector_digest,
            expected_record_key_sha256s=selector.expected_record_key_sha256s,
            observed_record_key_sha256s=observed_record_key_sha256s,
            zero_record_certificate=zero_record_certificate,
            event_at=event_at,
        )


class ReportCompletenessPlanner:
    """Evaluate only a declared inventory/CME report manifest; never infer one."""

    def plan(
        self,
        *,
        selector: B2ReportSelector,
        observed_record_key_sha256s: Iterable[str],
        zero_record_certificate: ZeroRecordCertificate | None = None,
        event_at: datetime | None = None,
    ) -> CompletenessResult:
        if not isinstance(selector, B2ReportSelector):
            raise TypeError("selector must be a B2ReportSelector")
        return _plan_completeness(
            selector_digest=selector.selector_digest,
            expected_record_key_sha256s=selector.expected_record_key_sha256s,
            observed_record_key_sha256s=observed_record_key_sha256s,
            zero_record_certificate=zero_record_certificate,
            event_at=event_at,
        )


__all__ = [
    "B2ReportSelector",
    "B2SliceSelector",
    "COMPLETENESS_SELECTOR_CONTRACT_VERSION",
    "CompletenessResult",
    "CompletenessStatus",
    "RECORD_IDENTITY_CONTRACT_VERSION",
    "ReportCompletenessPlanner",
    "SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON",
    "SINGLE_RECORD_SEMANTIC_KEY_SHA256",
    "SemanticRecordKey",
    "SliceCompletenessPlanner",
    "ZeroRecordCertificate",
    "normalize_semantic_record_key",
    "normalize_record_dimensions",
    "single_record_semantic_key",
]
