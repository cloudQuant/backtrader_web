"""Internal local-only reads for Iteration 197 B2 multi-record facts.

This module intentionally has no public route registration, provider adapter,
lease manager, source-policy resolver, or dependency on ``MarketDataQueryService``.
It can replay only already-persisted facts through the Store's frozen visibility
anchor and refuses to render a partial slice/report as market data.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.services.market_data.coverage import ObservationQuality
from app.services.market_data.field_quality import is_usable_field_value
from app.services.market_data.multi_record import (
    B2ReportSelector,
    B2SliceSelector,
    CompletenessResult,
    CompletenessStatus,
    ReportCompletenessPlanner,
    SemanticRecordKey,
    SliceCompletenessPlanner,
    ZeroRecordCertificate,
    _canonical_json_values_equal,
)
from app.services.market_data.multi_record_evidence import DurableB2CompletenessEvidence
from app.services.market_data.publication import MarketDataVisibilityAnchor
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.store import LocalObservationRevision, MarketDataStore

UTC = timezone.utc
_CURSOR_VERSION = 2
_CURSOR_KIND = "market-data-b2-local-cursor-v2"
_CURSOR_HMAC_BYTES = hashlib.sha256().digest_size
_MAX_CURSOR_TOKEN_LENGTH = 2048
_MAX_CURSOR_PAYLOAD_BYTES = 1500
_DEFAULT_CURSOR_TTL = timedelta(minutes=15)
_MAX_PAGE_SIZE = 2000
_B2_SLICE_FAMILY_IDS = frozenset({"option.derivative", "option.risk_surface"})
_B2_REPORT_FAMILY_IDS = frozenset({"futures.inventory", "crypto.cme_position"})
_BASE64URL_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)


class MultiRecordLocalQueryServiceError(ValueError):
    """Stable fail-closed error raised by the internal B2 local reader."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _MultiRecordReadStore(Protocol):
    """The only Store capability available to this local-only service."""

    async def resolve_visibility_anchor(
        self,
        *,
        knowledge_cutoff: datetime,
    ) -> MarketDataVisibilityAnchor: ...

    async def read_b2_completeness_evidence(
        self,
        context: ResolvedMarketDataQueryContext,
        *,
        selector: B2SliceSelector | B2ReportSelector,
        event_at: datetime,
        knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor,
        allowed_source_registry_ids: frozenset[str],
    ) -> DurableB2CompletenessEvidence | None: ...

    async def read_observation_revisions(
        self,
        context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor,
        include_unusable_for_coverage: bool = False,
        allowed_source_registry_ids: frozenset[str] | None = None,
        exact_event_at: datetime | None = None,
        exact_source_snapshot_id: str | None = None,
    ) -> tuple[LocalObservationRevision, ...]: ...


@dataclass(frozen=True, slots=True)
class MultiRecordLocalAccessBinding:
    """Internal access coordinates signed into B2 pagination tokens.

    The raw principal/tenant text remains outside the token. The deterministic
    digest also includes the current allowed source set, so a continuation
    cannot silently reuse a page across a changed entitlement decision. This
    internal DTO does not authorize a principal: any future public wrapper
    must derive this set from a validated ``MarketDataAccessGrant`` and bind
    its policy/grant descriptors before constructing this object.
    """

    principal_scope: str
    tenant_scope: str
    entitlement_revision: str
    # This local reader never has the generic QueryService's offline-import
    # seam.  A current, nonempty registry allow-list is mandatory so a caller
    # cannot turn ``None`` into an unfiltered read of compatibility receipts.
    allowed_source_registry_ids: frozenset[str]
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        principal_scope = _require_text(
            self.principal_scope,
            field_name="access principal_scope",
            maximum=256,
        )
        tenant_scope = _require_text(
            self.tenant_scope,
            field_name="access tenant_scope",
            maximum=256,
        )
        entitlement_revision = _require_text(
            self.entitlement_revision,
            field_name="access entitlement_revision",
            maximum=256,
        )
        allowed = _normalize_allowed_source_registry_ids(self.allowed_source_registry_ids)
        object.__setattr__(self, "principal_scope", principal_scope)
        object.__setattr__(self, "tenant_scope", tenant_scope)
        object.__setattr__(self, "entitlement_revision", entitlement_revision)
        object.__setattr__(self, "allowed_source_registry_ids", allowed)
        object.__setattr__(
            self,
            "digest",
            _sha256(
                _canonical_json(
                    {
                        "contract_version": "market-data-b2-local-access-v1",
                        "principal_scope": principal_scope,
                        "tenant_scope": tenant_scope,
                        "entitlement_revision": entitlement_revision,
                        "allowed_source_registry_ids": sorted(allowed),
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class MultiRecordLocalReadRequest:
    """A server-constructed, one-event local-only B2 read lookup request.

    ``selector`` narrows the durable receipt lookup but does not declare
    completeness.  Execution must replace it with the selector reconstructed
    from a published B2 receipt before selecting any observation revision.
    """

    context: ResolvedMarketDataQueryContext
    selector: B2SliceSelector | B2ReportSelector
    event_at: datetime
    knowledge_cutoff: datetime
    access_binding: MultiRecordLocalAccessBinding
    page_size: int = 500
    cursor: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.context, ResolvedMarketDataQueryContext):
            raise TypeError("context must be a ResolvedMarketDataQueryContext")
        if not isinstance(self.selector, (B2SliceSelector, B2ReportSelector)):
            raise TypeError("selector must be a B2SliceSelector or B2ReportSelector")
        if not isinstance(self.access_binding, MultiRecordLocalAccessBinding):
            raise TypeError("access_binding must be a MultiRecordLocalAccessBinding")
        event_at = _require_aware_utc(self.event_at, field_name="event_at")
        knowledge_cutoff = _require_aware_utc(
            self.knowledge_cutoff,
            field_name="knowledge_cutoff",
        )
        if isinstance(self.page_size, bool) or not isinstance(self.page_size, int):
            raise TypeError("page_size must be an integer")
        if not 1 <= self.page_size <= _MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {_MAX_PAGE_SIZE}")
        if self.cursor is not None:
            _require_text(self.cursor, field_name="cursor", maximum=_MAX_CURSOR_TOKEN_LENGTH)
        object.__setattr__(self, "event_at", event_at)
        object.__setattr__(self, "knowledge_cutoff", knowledge_cutoff)


@dataclass(frozen=True, slots=True)
class MultiRecordLocalQueryExecution:
    """One local-only B2 page plus the completeness evidence that permits it."""

    context: ResolvedMarketDataQueryContext
    event_at: datetime
    knowledge_cutoff: datetime
    visibility_anchor: MarketDataVisibilityAnchor
    selector_digest: str
    completeness: CompletenessResult
    observations: tuple[LocalObservationRevision, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class _Cursor:
    """Validated B2 continuation state, never built from unsigned input."""

    query_fingerprint: str
    series_semantic_key_sha256: str
    family_id: str
    family_contract_version: str
    selector_kind: str
    selector_digest: str
    event_at: datetime
    knowledge_cutoff: datetime
    visibility_anchor: MarketDataVisibilityAnchor
    access_binding_digest: str
    receipt_id: str
    receipt_sha256: str
    source_snapshot_id: str
    last_event_at: datetime
    last_semantic_record_key_sha256: str
    last_revision_number: int
    last_revision_id: str
    issued_at: datetime
    expires_at: datetime


class MultiRecordLocalQueryService:
    """Replay an exact B2 slice/report from local evidence only."""

    def __init__(
        self,
        store: _MultiRecordReadStore,
        *,
        cursor_signing_key: str | bytes,
        clock: Callable[[], datetime] | None = None,
        cursor_ttl: timedelta = _DEFAULT_CURSOR_TTL,
    ) -> None:
        if not all(
            hasattr(store, method)
            for method in (
                "resolve_visibility_anchor",
                "read_b2_completeness_evidence",
                "read_observation_revisions",
            )
        ):
            raise TypeError("store must expose only the required local read methods")
        if not isinstance(cursor_ttl, timedelta) or not timedelta(0) < cursor_ttl <= timedelta(
            days=1
        ):
            raise ValueError("cursor_ttl must be greater than zero and no more than one day")
        self._store = store
        self._cursor_signing_key = _coerce_cursor_signing_key(cursor_signing_key)
        self._clock = clock or _utc_now
        self._cursor_ttl = cursor_ttl

    async def execute(
        self,
        request: MultiRecordLocalReadRequest,
    ) -> MultiRecordLocalQueryExecution:
        """Read, prove completeness, and page a frozen B2 local snapshot."""
        if not isinstance(request, MultiRecordLocalReadRequest):
            raise TypeError("request must be a MultiRecordLocalReadRequest")
        _validate_request_contract(request)
        series_semantic_key_sha256 = MarketDataStore.series_identity(
            request.context
        ).semantic_key_sha256
        now = _require_aware_utc(self._clock(), field_name="cursor clock")
        cursor = (
            _decode_cursor(
                request.cursor,
                signing_key=self._cursor_signing_key,
                now=now,
                expected_request=request,
                series_semantic_key_sha256=series_semantic_key_sha256,
            )
            if request.cursor is not None
            else None
        )
        visibility_anchor = (
            cursor.visibility_anchor
            if cursor is not None
            else await self._store.resolve_visibility_anchor(
                knowledge_cutoff=request.knowledge_cutoff
            )
        )
        evidence = await self._store.read_b2_completeness_evidence(
            request.context,
            selector=request.selector,
            event_at=request.event_at,
            knowledge_cutoff=request.knowledge_cutoff,
            visibility_anchor=visibility_anchor,
            allowed_source_registry_ids=request.access_binding.allowed_source_registry_ids,
        )
        if evidence is None:
            return MultiRecordLocalQueryExecution(
                context=request.context,
                event_at=request.event_at,
                knowledge_cutoff=request.knowledge_cutoff,
                visibility_anchor=visibility_anchor,
                selector_digest=request.selector.selector_digest,
                completeness=_durable_evidence_missing_completeness(request.selector),
                observations=(),
                next_cursor=None,
            )
        _assert_durable_evidence_matches_request(evidence, request=request)
        if cursor is not None:
            _assert_cursor_matches_evidence(cursor, evidence=evidence)
        revisions = await self._store.read_observation_revisions(
            request.context,
            knowledge_cutoff=request.knowledge_cutoff,
            visibility_anchor=visibility_anchor,
            allowed_source_registry_ids=request.access_binding.allowed_source_registry_ids,
            exact_event_at=request.event_at,
            exact_source_snapshot_id=evidence.source_snapshot_id,
        )
        matching = _matching_selector_revisions(
            revisions,
            context=request.context,
            event_at=request.event_at,
            selector=evidence.selector,
        )
        completeness = _plan_completeness(
            selector=evidence.selector,
            observations=matching,
            zero_record_certificate=evidence.zero_record_certificate,
            event_at=evidence.event_at,
        )
        if not completeness.is_complete:
            return MultiRecordLocalQueryExecution(
                context=request.context,
                event_at=request.event_at,
                knowledge_cutoff=request.knowledge_cutoff,
                visibility_anchor=visibility_anchor,
                selector_digest=evidence.selector.selector_digest,
                completeness=completeness,
                observations=(),
                next_cursor=None,
            )

        records = tuple(sorted(matching, key=_record_sort_key))
        issued_at = cursor.issued_at if cursor is not None else now
        expires_at = cursor.expires_at if cursor is not None else now + self._cursor_ttl
        page, next_cursor = _paginate_records(
            records,
            cursor=cursor,
            request=request,
            evidence=evidence,
            series_semantic_key_sha256=series_semantic_key_sha256,
            visibility_anchor=visibility_anchor,
            issued_at=issued_at,
            expires_at=expires_at,
            signing_key=self._cursor_signing_key,
        )
        return MultiRecordLocalQueryExecution(
            context=request.context,
            event_at=request.event_at,
            knowledge_cutoff=request.knowledge_cutoff,
            visibility_anchor=visibility_anchor,
            selector_digest=evidence.selector.selector_digest,
            completeness=completeness,
            observations=page,
            next_cursor=next_cursor,
        )


def _validate_request_contract(request: MultiRecordLocalReadRequest) -> None:
    """Refuse anything that could turn this internal reader into an online path."""
    query = request.context.query
    if query.mode != "local_only":
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_MODE_REQUIRED")
    if query.consistency != "strict":
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_STRICT_CONSISTENCY_REQUIRED")
    if query.knowledge_cutoff != request.knowledge_cutoff:
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_CUTOFF_MISMATCH")
    if query.cursor is not None:
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_CONTEXT_CURSOR_FORBIDDEN")
    if not query.start <= request.event_at < query.end:
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_EVENT_OUT_OF_WINDOW")
    if (
        query.family_id != request.selector.family_id
        or query.family_contract_version != request.selector.family_contract_version
    ):
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_SELECTOR_CONTEXT_MISMATCH")
    if isinstance(request.selector, B2SliceSelector):
        if request.selector.family_id not in _B2_SLICE_FAMILY_IDS:
            raise MultiRecordLocalQueryServiceError("B2_LOCAL_SELECTOR_FAMILY_UNSUPPORTED")
    elif request.selector.family_id not in _B2_REPORT_FAMILY_IDS:
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_SELECTOR_FAMILY_UNSUPPORTED")


def _matching_selector_revisions(
    revisions: tuple[LocalObservationRevision, ...],
    *,
    context: ResolvedMarketDataQueryContext,
    event_at: datetime,
    selector: B2SliceSelector | B2ReportSelector,
) -> tuple[LocalObservationRevision, ...]:
    """Validate record identities and select only the durable slice/report."""
    selected: list[LocalObservationRevision] = []
    for revision in revisions:
        if revision.event_at != event_at:
            continue
        dimensions = _validated_record_dimensions(
            revision,
            family_id=selector.family_id,
            family_contract_version=selector.family_contract_version,
        )
        if not _dimensions_match_selector(dimensions, selector.selector_dimensions):
            continue
        if not _revision_is_usable_for_request(revision, context):
            continue
        selected.append(revision)
    return tuple(selected)


def _validated_record_dimensions(
    revision: LocalObservationRevision,
    *,
    family_id: str,
    family_contract_version: str,
) -> Mapping[str, object]:
    """Revalidate a Store result before it informs B2 completeness evidence."""
    try:
        payload = json.loads(revision.semantic_record_key)
        if not isinstance(payload, Mapping):
            raise ValueError("semantic record key payload is not an object")
        dimensions = payload.get("dimensions")
        record_key = SemanticRecordKey(
            canonical_json=revision.semantic_record_key,
            sha256=revision.semantic_record_key_sha256,
            dimensions=dimensions,
            is_singleton=False,
        )
        if (
            payload.get("family_id") != family_id
            or payload.get("family_contract_version") != family_contract_version
        ):
            raise ValueError("semantic record key family does not match request")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_RECORD_INTEGRITY") from exc
    return record_key.dimensions


def _dimensions_match_selector(
    dimensions: Mapping[str, object],
    selector_dimensions: Mapping[str, object],
) -> bool:
    return all(
        key in dimensions and _json_value_matches(dimensions[key], value)
        for key, value in selector_dimensions.items()
    )


def _json_value_matches(left: object, right: object) -> bool:
    """Match the exact canonical JSON representation used by semantic keys."""
    return _canonical_json_values_equal(left, right)


def _revision_is_usable_for_request(
    revision: LocalObservationRevision,
    context: ResolvedMarketDataQueryContext,
) -> bool:
    return revision.quality is ObservationQuality.PASS and all(
        is_usable_field_value(field_name, revision.fields.get(field_name))
        for field_name in context.query.required_fields
    )


def _plan_completeness(
    *,
    selector: B2SliceSelector | B2ReportSelector,
    observations: tuple[LocalObservationRevision, ...],
    zero_record_certificate: ZeroRecordCertificate | None,
    event_at: datetime,
) -> CompletenessResult:
    """Use only a durable manifest and its optional durable zero certificate."""
    record_key_sha256s = tuple(item.semantic_record_key_sha256 for item in observations)
    if isinstance(selector, B2SliceSelector):
        return SliceCompletenessPlanner().plan(
            selector=selector,
            observed_record_key_sha256s=record_key_sha256s,
            zero_record_certificate=zero_record_certificate,
            event_at=event_at,
        )
    return ReportCompletenessPlanner().plan(
        selector=selector,
        observed_record_key_sha256s=record_key_sha256s,
        zero_record_certificate=zero_record_certificate,
        event_at=event_at,
    )


def _durable_evidence_missing_completeness(
    selector: B2SliceSelector | B2ReportSelector,
) -> CompletenessResult:
    """Return the non-renderable result for a selector without a stored receipt."""
    expected = selector.expected_record_key_sha256s
    return CompletenessResult(
        selector_digest=selector.selector_digest,
        status=CompletenessStatus.INCOMPLETE,
        reason_codes=("DURABLE_SELECTOR_EVIDENCE_MISSING",),
        expected_record_key_sha256s=expected,
        observed_record_key_sha256s=frozenset(),
        missing_record_key_sha256s=expected or frozenset(),
        duplicate_record_key_sha256s=frozenset(),
        unexpected_record_key_sha256s=frozenset(),
        zero_record_certificate_used=False,
    )


def _assert_durable_evidence_matches_request(
    evidence: DurableB2CompletenessEvidence,
    *,
    request: MultiRecordLocalReadRequest,
) -> None:
    """Ensure a Store result cannot swap the request's selector or event scope."""
    if (
        not isinstance(evidence, DurableB2CompletenessEvidence)
        or evidence.event_at != request.event_at
        or type(evidence.selector) is not type(request.selector)
        or evidence.selector.family_id != request.selector.family_id
        or evidence.selector.family_contract_version != request.selector.family_contract_version
        or evidence.selector.selector_digest != request.selector.selector_digest
    ):
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_DURABLE_EVIDENCE_MISMATCH")


def _paginate_records(
    records: tuple[LocalObservationRevision, ...],
    *,
    cursor: _Cursor | None,
    request: MultiRecordLocalReadRequest,
    evidence: DurableB2CompletenessEvidence,
    series_semantic_key_sha256: str,
    visibility_anchor: MarketDataVisibilityAnchor,
    issued_at: datetime,
    expires_at: datetime,
    signing_key: bytes,
) -> tuple[tuple[LocalObservationRevision, ...], str | None]:
    start_index = 0
    if cursor is not None:
        _assert_cursor_matches_request(
            cursor,
            request=request,
            series_semantic_key_sha256=series_semantic_key_sha256,
            visibility_anchor=visibility_anchor,
        )
        _assert_cursor_matches_evidence(cursor, evidence=evidence)
        last_key = (
            cursor.last_event_at,
            cursor.last_semantic_record_key_sha256,
            cursor.last_revision_number,
            cursor.last_revision_id,
        )
        for index, item in enumerate(records):
            if _cursor_record_key(item) == last_key:
                start_index = index + 1
                break
        else:
            raise MultiRecordLocalQueryServiceError("B2_LOCAL_CURSOR_NOT_FOUND")
    page = records[start_index : start_index + request.page_size]
    if not page or start_index + len(page) >= len(records):
        return page, None
    return page, _encode_cursor(
        record=page[-1],
        request=request,
        evidence=evidence,
        series_semantic_key_sha256=series_semantic_key_sha256,
        visibility_anchor=visibility_anchor,
        issued_at=issued_at,
        expires_at=expires_at,
        signing_key=signing_key,
    )


def _record_sort_key(revision: LocalObservationRevision) -> tuple[datetime, str, int, str]:
    return (
        revision.event_at,
        revision.semantic_record_key,
        revision.revision_number,
        revision.revision_id,
    )


def _cursor_record_key(revision: LocalObservationRevision) -> tuple[datetime, str, int, str]:
    return (
        revision.event_at,
        revision.semantic_record_key_sha256,
        revision.revision_number,
        revision.revision_id,
    )


def _selector_kind(selector: B2SliceSelector | B2ReportSelector) -> str:
    return "slice" if isinstance(selector, B2SliceSelector) else "report"


def _encode_cursor(
    *,
    record: LocalObservationRevision,
    request: MultiRecordLocalReadRequest,
    evidence: DurableB2CompletenessEvidence,
    series_semantic_key_sha256: str,
    visibility_anchor: MarketDataVisibilityAnchor,
    issued_at: datetime,
    expires_at: datetime,
    signing_key: bytes,
) -> str:
    issued_at = _require_aware_utc(issued_at, field_name="cursor issued_at")
    expires_at = _require_aware_utc(expires_at, field_name="cursor expires_at")
    if expires_at <= issued_at:
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_CURSOR_EXPIRY_INVALID")
    payload = _canonical_json(
        {
            "version": _CURSOR_VERSION,
            "kind": _CURSOR_KIND,
            "query_fingerprint": request.context.query.query_fingerprint,
            "series_semantic_key_sha256": series_semantic_key_sha256,
            "family_id": request.selector.family_id,
            "family_contract_version": request.selector.family_contract_version,
            "selector_kind": _selector_kind(request.selector),
            "selector_digest": request.selector.selector_digest,
            "event_at": request.event_at.isoformat(),
            "knowledge_cutoff": request.knowledge_cutoff.isoformat(),
            "visibility_anchor": _anchor_payload(visibility_anchor),
            "access_binding_digest": request.access_binding.digest,
            "receipt_id": evidence.receipt_id,
            "receipt_sha256": evidence.receipt_sha256,
            "source_snapshot_id": evidence.source_snapshot_id,
            "last": {
                "event_at": record.event_at.isoformat(),
                "semantic_record_key_sha256": record.semantic_record_key_sha256,
                "revision_number": record.revision_number,
                "revision_id": record.revision_id,
            },
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
    ).encode("utf-8")
    signature = hmac.new(signing_key, payload, hashlib.sha256).digest()
    token = f"{_base64url_encode(payload)}.{_base64url_encode(signature)}"
    if len(token) > _MAX_CURSOR_TOKEN_LENGTH:
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_CURSOR_PAYLOAD_TOO_LARGE")
    return token


def _decode_cursor(
    token: str,
    *,
    signing_key: bytes,
    now: datetime,
    expected_request: MultiRecordLocalReadRequest,
    series_semantic_key_sha256: str,
) -> _Cursor:
    try:
        encoded_payload, encoded_signature = _split_cursor_token(token)
        payload_bytes = _base64url_decode(encoded_payload)
        signature = _base64url_decode(encoded_signature)
        if len(payload_bytes) > _MAX_CURSOR_PAYLOAD_BYTES or len(signature) != _CURSOR_HMAC_BYTES:
            raise ValueError("invalid cursor segment length")
        expected_signature = hmac.new(signing_key, payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_signature, signature):
            raise MultiRecordLocalQueryServiceError("B2_LOCAL_CURSOR_SIGNATURE_INVALID")
        payload = json.loads(payload_bytes.decode("utf-8"))
    except MultiRecordLocalQueryServiceError:
        raise
    except (
        UnicodeEncodeError,
        UnicodeDecodeError,
        ValueError,
        binascii.Error,
        json.JSONDecodeError,
    ) as exc:
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_CURSOR_INVALID") from exc
    if not isinstance(payload, Mapping) or set(payload) != {
        "version",
        "kind",
        "query_fingerprint",
        "series_semantic_key_sha256",
        "family_id",
        "family_contract_version",
        "selector_kind",
        "selector_digest",
        "event_at",
        "knowledge_cutoff",
        "visibility_anchor",
        "access_binding_digest",
        "receipt_id",
        "receipt_sha256",
        "source_snapshot_id",
        "last",
        "issued_at",
        "expires_at",
    }:
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_CURSOR_INVALID")
    if payload.get("version") != _CURSOR_VERSION or payload.get("kind") != _CURSOR_KIND:
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_CURSOR_VERSION_UNSUPPORTED")
    try:
        last = _require_mapping(payload.get("last"), field_name="cursor last")
        if set(last) != {
            "event_at",
            "semantic_record_key_sha256",
            "revision_number",
            "revision_id",
        }:
            raise ValueError("cursor last has invalid fields")
        cursor = _Cursor(
            query_fingerprint=_require_sha256(
                payload.get("query_fingerprint"),
                field_name="cursor query_fingerprint",
            ),
            series_semantic_key_sha256=_require_sha256(
                payload.get("series_semantic_key_sha256"),
                field_name="cursor series_semantic_key_sha256",
            ),
            family_id=_require_text(payload.get("family_id"), field_name="cursor family_id"),
            family_contract_version=_require_text(
                payload.get("family_contract_version"),
                field_name="cursor family_contract_version",
            ),
            selector_kind=_require_text(
                payload.get("selector_kind"),
                field_name="cursor selector_kind",
            ),
            selector_digest=_require_sha256(
                payload.get("selector_digest"),
                field_name="cursor selector_digest",
            ),
            event_at=_parse_datetime(payload.get("event_at"), field_name="cursor event_at"),
            knowledge_cutoff=_parse_datetime(
                payload.get("knowledge_cutoff"),
                field_name="cursor knowledge_cutoff",
            ),
            visibility_anchor=_decode_anchor(payload.get("visibility_anchor")),
            access_binding_digest=_require_sha256(
                payload.get("access_binding_digest"),
                field_name="cursor access_binding_digest",
            ),
            receipt_id=_require_text(
                payload.get("receipt_id"),
                field_name="cursor receipt_id",
                maximum=36,
            ),
            receipt_sha256=_require_sha256(
                payload.get("receipt_sha256"),
                field_name="cursor receipt_sha256",
            ),
            source_snapshot_id=_require_text(
                payload.get("source_snapshot_id"),
                field_name="cursor source_snapshot_id",
                maximum=36,
            ),
            last_event_at=_parse_datetime(last.get("event_at"), field_name="cursor last.event_at"),
            last_semantic_record_key_sha256=_require_sha256(
                last.get("semantic_record_key_sha256"),
                field_name="cursor last.semantic_record_key_sha256",
            ),
            last_revision_number=_require_positive_int(
                last.get("revision_number"),
                field_name="cursor last.revision_number",
            ),
            last_revision_id=_require_text(
                last.get("revision_id"),
                field_name="cursor last.revision_id",
            ),
            issued_at=_parse_datetime(payload.get("issued_at"), field_name="cursor issued_at"),
            expires_at=_parse_datetime(payload.get("expires_at"), field_name="cursor expires_at"),
        )
    except (TypeError, ValueError) as exc:
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_CURSOR_INVALID") from exc
    if cursor.expires_at <= cursor.issued_at:
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_CURSOR_EXPIRY_INVALID")
    if _require_aware_utc(now, field_name="cursor clock") >= cursor.expires_at:
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_CURSOR_EXPIRED")
    _assert_cursor_matches_request(
        cursor,
        request=expected_request,
        series_semantic_key_sha256=series_semantic_key_sha256,
        visibility_anchor=cursor.visibility_anchor,
    )
    return cursor


def _assert_cursor_matches_request(
    cursor: _Cursor,
    *,
    request: MultiRecordLocalReadRequest,
    series_semantic_key_sha256: str,
    visibility_anchor: MarketDataVisibilityAnchor,
) -> None:
    if (
        cursor.query_fingerprint != request.context.query.query_fingerprint
        or cursor.series_semantic_key_sha256 != series_semantic_key_sha256
        or cursor.family_id != request.selector.family_id
        or cursor.family_contract_version != request.selector.family_contract_version
        or cursor.selector_kind != _selector_kind(request.selector)
        or cursor.selector_digest != request.selector.selector_digest
        or cursor.event_at != request.event_at
        or cursor.knowledge_cutoff != request.knowledge_cutoff
        or cursor.visibility_anchor != visibility_anchor
        or cursor.access_binding_digest != request.access_binding.digest
    ):
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_CURSOR_MISMATCH")


def _assert_cursor_matches_evidence(
    cursor: _Cursor,
    *,
    evidence: DurableB2CompletenessEvidence,
) -> None:
    """Bind every continuation to the exact durable receipt/source pair."""
    if (
        cursor.receipt_id != evidence.receipt_id
        or cursor.receipt_sha256 != evidence.receipt_sha256
        or cursor.source_snapshot_id != evidence.source_snapshot_id
    ):
        raise MultiRecordLocalQueryServiceError("B2_LOCAL_CURSOR_EVIDENCE_MISMATCH")


def _anchor_payload(anchor: MarketDataVisibilityAnchor) -> dict[str, object]:
    if not isinstance(anchor, MarketDataVisibilityAnchor):
        raise TypeError("visibility_anchor must be a MarketDataVisibilityAnchor")
    return {
        "visible_at": _require_aware_utc(
            anchor.visible_at, field_name="visibility anchor"
        ).isoformat(),
        "max_visibility_sequence": _require_positive_or_zero_int(
            anchor.max_visibility_sequence,
            field_name="visibility anchor max_visibility_sequence",
        ),
    }


def _decode_anchor(value: object) -> MarketDataVisibilityAnchor:
    mapping = _require_mapping(value, field_name="cursor visibility_anchor")
    if set(mapping) != {"visible_at", "max_visibility_sequence"}:
        raise ValueError("cursor visibility_anchor has invalid fields")
    return MarketDataVisibilityAnchor(
        visible_at=_parse_datetime(
            mapping.get("visible_at"), field_name="cursor visibility_anchor"
        ),
        max_visibility_sequence=_require_positive_or_zero_int(
            mapping.get("max_visibility_sequence"),
            field_name="cursor visibility_anchor max_visibility_sequence",
        ),
    )


def _split_cursor_token(token: object) -> tuple[str, str]:
    if not isinstance(token, str) or len(token) > _MAX_CURSOR_TOKEN_LENGTH:
        raise ValueError("cursor token is invalid")
    parts = token.split(".")
    if len(parts) != 2 or not all(parts):
        raise ValueError("cursor token must contain two segments")
    if any(any(character not in _BASE64URL_CHARACTERS for character in part) for part in parts):
        raise ValueError("cursor token is not base64url")
    return parts[0], parts[1]


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))


def _coerce_cursor_signing_key(value: str | bytes) -> bytes:
    if isinstance(value, str):
        encoded = value.encode("utf-8")
    elif isinstance(value, bytes):
        encoded = value
    else:
        raise TypeError("cursor_signing_key must be a string or bytes")
    if len(encoded) < 32:
        raise ValueError("cursor_signing_key must contain at least 32 bytes")
    return encoded


def _normalize_allowed_source_registry_ids(value: object) -> frozenset[str]:
    """Require an explicit current registry grant for every B2 local read."""
    if not isinstance(value, frozenset):
        raise TypeError("allowed_source_registry_ids must be a frozenset")
    normalized = frozenset(
        _require_text(item, field_name="allowed source registry id", maximum=128) for item in value
    )
    if not normalized:
        raise ValueError("allowed_source_registry_ids must be non-empty")
    return normalized


def _require_mapping(value: object, *, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise TypeError(f"{field_name} keys must be strings")
    return value


def _require_text(value: object, *, field_name: str, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{field_name} must be a non-empty string no longer than {maximum}")
    return normalized


def _require_sha256(value: object, *, field_name: str) -> str:
    normalized = _require_text(value, field_name=field_name, maximum=64)
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return normalized


def _require_positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _require_positive_or_zero_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _require_aware_utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _parse_datetime(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    return _require_aware_utc(parsed, field_name=field_name)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "MultiRecordLocalAccessBinding",
    "MultiRecordLocalQueryExecution",
    "MultiRecordLocalQueryService",
    "MultiRecordLocalQueryServiceError",
    "MultiRecordLocalReadRequest",
]
