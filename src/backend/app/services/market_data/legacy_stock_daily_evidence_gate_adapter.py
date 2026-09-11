"""Concrete, default-off evidence gate for a legacy daily-bar import.

The legacy warehouse does not carry trustworthy per-row upstream provenance.
This adapter therefore records it as a *mixed legacy warehouse* source and
requires an explicit, operator-supplied approval object for every target.  It
does not register a source policy, construct a provider, call the network, or
make the table readable by a product route.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.market_data.access import MarketDataSourceAuthorization
from app.services.market_data.fetch_lease import MarketDataFetchLeaseHandle
from app.services.market_data.legacy_stock_daily_import import (
    LEGACY_STOCK_DAILY_PROVENANCE_CLASS,
    LEGACY_STOCK_DAILY_PROVIDER_ID,
    LEGACY_STOCK_DAILY_ROUTE_ID,
    LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
    FrozenLegacyStockDailyCalendar,
    FrozenLegacyStockDailyIdentity,
    LegacyStockDailyCanonicalWritePermit,
    LegacyStockDailyImportAttestation,
    LegacyStockDailyImportBatch,
    LegacyStockDailyImportError,
    LegacyStockDailyImportScope,
    LegacyStockDailyReadScopeReceipt,
    LegacyStockDailySourceBatchReceipt,
)
from app.services.market_data.legacy_stock_daily_source_repository import (
    LegacyStockDailySourceRepository,
)
from app.services.market_data.publication import MarketDataDeferredPublicationIntent
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.store import (
    DeferredProviderFetch,
    MarketDataStore,
    MarketDataStoreError,
)

UTC = timezone.utc
_GATE_VERSION = "legacy-stock-daily-evidence-gate-v1"
_READ_AUTHORIZATION_VERSION = "legacy-stock-daily-read-authorization-v1"
_SOURCE_BATCH_RECEIPT_VERSION = "legacy-stock-daily-source-batch-receipt-v1"
_DEFERRED_INTENT_VERSION = "legacy-stock-daily-deferred-intent-v1"
_PROMOTION_EVIDENCE_VERSION = "legacy-stock-daily-promotion-evidence-v1"
_MAX_TARGETS = 64


class LegacyStockDailyEvidenceGateAdapterError(LegacyStockDailyImportError):
    """Stable gate rejection before a legacy candidate becomes visible."""


@dataclass(frozen=True, slots=True)
class LegacyStockDailySourceProvenance:
    """A reviewed description of the warehouse's mixed, non-AkShare lineage.

    ``known_possible_upstreams`` records sources observed in the historical
    writer path.  It is intentionally not a per-row attribution claim.  In
    particular, putting ``akshare`` in this tuple does not turn any row into
    an AkShare proof.
    """

    source_revision: str
    approval_reference: str
    known_possible_upstreams: tuple[str, ...]
    source_registry_id: str = LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID
    provider_id: str = LEGACY_STOCK_DAILY_PROVIDER_ID
    route_id: str = LEGACY_STOCK_DAILY_ROUTE_ID
    provenance_class: str = LEGACY_STOCK_DAILY_PROVENANCE_CLASS

    def __post_init__(self) -> None:
        for field_name in (
            "source_revision",
            "approval_reference",
            "source_registry_id",
            "provider_id",
            "route_id",
            "provenance_class",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > 255:
                raise ValueError(f"{field_name} must be non-blank text")
            object.__setattr__(self, field_name, value.strip())
        upstreams = tuple(self.known_possible_upstreams)
        if not upstreams or len(upstreams) != len(set(upstreams)):
            raise ValueError("known_possible_upstreams must be a unique non-empty tuple")
        if any(not isinstance(value, str) or not value.strip() for value in upstreams):
            raise ValueError("known_possible_upstreams must contain non-blank text")
        object.__setattr__(
            self, "known_possible_upstreams", tuple(sorted(value.strip() for value in upstreams))
        )
        if (
            self.source_registry_id != LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID
            or self.provider_id != LEGACY_STOCK_DAILY_PROVIDER_ID
            or self.route_id != LEGACY_STOCK_DAILY_ROUTE_ID
            or self.provenance_class != LEGACY_STOCK_DAILY_PROVENANCE_CLASS
        ):
            raise ValueError("legacy source provenance must retain the mixed-warehouse identity")

    @property
    def manifest_sha256(self) -> str:
        """Return a stable digest for source lineage stored in every receipt."""
        return _sha256(self.as_receipt_provenance())

    def as_receipt_provenance(self) -> Mapping[str, object]:
        """Return an explicit non-provider-attribution provenance envelope."""
        return MappingProxyType(
            {
                "approval_reference": self.approval_reference,
                "known_possible_upstreams": list(self.known_possible_upstreams),
                "per_row_provider_attribution": "unavailable",
                "provenance_class": self.provenance_class,
                "provider_id": self.provider_id,
                "route_id": self.route_id,
                "source_registry_id": self.source_registry_id,
                "source_revision": self.source_revision,
            }
        )


@dataclass(frozen=True, slots=True)
class LegacyStockDailyCanonicalTarget:
    """One exact canonical series and its currently approved write evidence."""

    context: ResolvedMarketDataQueryContext
    source_authorization: MarketDataSourceAuthorization
    fetch_lease: MarketDataFetchLeaseHandle

    def __post_init__(self) -> None:
        if not isinstance(self.context, ResolvedMarketDataQueryContext):
            raise TypeError("context must be a ResolvedMarketDataQueryContext")
        if type(self.source_authorization) is not MarketDataSourceAuthorization:
            raise TypeError("source_authorization must be a MarketDataSourceAuthorization")
        if not isinstance(self.fetch_lease, MarketDataFetchLeaseHandle):
            raise TypeError("fetch_lease must be a MarketDataFetchLeaseHandle")


@dataclass(frozen=True, slots=True)
class _ReadApproval:
    receipt: LegacyStockDailyReadScopeReceipt
    calendar: FrozenLegacyStockDailyCalendar
    targets_by_canonical_id: Mapping[str, LegacyStockDailyCanonicalTarget]


@dataclass(frozen=True, slots=True)
class _SourceBatchApproval:
    receipt: LegacyStockDailySourceBatchReceipt
    import_scope: LegacyStockDailyImportScope
    targets_by_canonical_id: Mapping[str, LegacyStockDailyCanonicalTarget]


@dataclass(frozen=True, slots=True)
class _PermitApproval:
    permit: LegacyStockDailyCanonicalWritePermit
    target: LegacyStockDailyCanonicalTarget
    source_batch_receipt: LegacyStockDailySourceBatchReceipt
    import_scope: LegacyStockDailyImportScope


class LegacyStockDailyEvidenceGateAdapter:
    """Issue local-only import evidence from an explicit reviewed target set.

    There is deliberately no module singleton or environment-driven factory.
    Constructing this type requires an injected source repository, canonical
    Store, source provenance approval, target contexts, current authorizations,
    and durable lease handles.  The application therefore has no default
    capability to import ``STOCK_ZH_A_HIST``.
    """

    def __init__(
        self,
        *,
        source_repository: LegacyStockDailySourceRepository,
        store: MarketDataStore,
        source_provenance: LegacyStockDailySourceProvenance,
        targets: Sequence[LegacyStockDailyCanonicalTarget],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(source_repository, LegacyStockDailySourceRepository):
            raise TypeError("source_repository must be a LegacyStockDailySourceRepository")
        if not isinstance(store, MarketDataStore):
            raise TypeError("store must be a MarketDataStore")
        store_db = getattr(store, "_db", None)
        if not isinstance(store_db, AsyncSession) or not source_repository._owns_isolated_session(
            store_db
        ):
            raise ValueError("store must use the source repository's injected isolated session")
        if not isinstance(source_provenance, LegacyStockDailySourceProvenance):
            raise TypeError("source_provenance must be a LegacyStockDailySourceProvenance")
        if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes, bytearray)):
            raise TypeError("targets must be a sequence of LegacyStockDailyCanonicalTarget")
        frozen_targets = tuple(targets)
        if not frozen_targets or len(frozen_targets) > _MAX_TARGETS:
            raise ValueError("targets must contain between one and 64 items")
        if any(
            not isinstance(target, LegacyStockDailyCanonicalTarget) for target in frozen_targets
        ):
            raise TypeError("targets must contain LegacyStockDailyCanonicalTarget values")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        self._source_repository = source_repository
        self._store = store
        self._source_provenance = source_provenance
        self._targets_by_canonical_id = _targets_by_canonical_id(frozen_targets)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._read_approvals: dict[str, _ReadApproval] = {}
        self._source_batch_approvals: dict[str, _SourceBatchApproval] = {}
        self._permit_approvals: dict[tuple[str, str], _PermitApproval] = {}

    @property
    def source_provenance(self) -> LegacyStockDailySourceProvenance:
        """Expose the immutable mixed-warehouse label for receipt projection only."""
        return self._source_provenance

    async def authorize_legacy_read(
        self,
        *,
        table_name: str,
        attestation: LegacyStockDailyImportAttestation,
        calendar: FrozenLegacyStockDailyCalendar,
        frozen_identities: Mapping[str, FrozenLegacyStockDailyIdentity],
    ) -> LegacyStockDailyReadScopeReceipt:
        """Verify an approved local fixture scope before the reader can select rows."""
        try:
            _assert_read_scope_inputs(
                table_name=table_name,
                attestation=attestation,
                calendar=calendar,
                frozen_identities=frozen_identities,
                source_provenance=self._source_provenance,
                targets_by_canonical_id=self._targets_by_canonical_id,
            )
            await self._assert_current_target_authorizations(
                targets=self._targets_by_canonical_id.values()
            )
            schema = await self._source_repository.inspect_projection_schema()
            receipt_id = _read_authorization_receipt_id(
                source_provenance=self._source_provenance,
                schema_sha256=schema.schema_sha256,
                calendar=calendar,
                targets_by_canonical_id=self._targets_by_canonical_id,
            )
            receipt = LegacyStockDailyReadScopeReceipt(
                source_registry_id=self._source_provenance.source_registry_id,
                provider_id=self._source_provenance.provider_id,
                route_id=self._source_provenance.route_id,
                authorization_receipt_id=receipt_id,
                source_schema_sha256=schema.schema_sha256,
            )
        except LegacyStockDailyImportError:
            raise
        except (MarketDataStoreError, TypeError, ValueError) as exc:
            raise LegacyStockDailyEvidenceGateAdapterError(
                "LEGACY_STOCK_DAILY_SOURCE_PRECHECK_UNVERIFIED"
            ) from exc
        self._read_approvals[receipt.authorization_receipt_id] = _ReadApproval(
            receipt=receipt,
            calendar=calendar,
            targets_by_canonical_id=self._targets_by_canonical_id,
        )
        return receipt

    async def certify_source_batch(
        self,
        *,
        batch: LegacyStockDailyImportBatch,
        attestation: LegacyStockDailyImportAttestation,
        import_scope: LegacyStockDailyImportScope,
    ) -> LegacyStockDailySourceBatchReceipt:
        """Seal raw-batch and derivation hashes after the fixed source read."""
        try:
            if not isinstance(batch, LegacyStockDailyImportBatch):
                raise TypeError("batch must be a LegacyStockDailyImportBatch")
            if not isinstance(import_scope, LegacyStockDailyImportScope):
                raise TypeError("import_scope must be a LegacyStockDailyImportScope")
            if import_scope != batch.import_scope or import_scope.attestation != attestation:
                raise ValueError("batch import scope is not the current read scope")
            read_approval = self._read_approvals.get(
                import_scope.read_scope_receipt.authorization_receipt_id
            )
            if read_approval is None or read_approval.receipt != import_scope.read_scope_receipt:
                raise ValueError("read scope receipt was not issued by this gate")
            if read_approval.calendar != batch.calendar:
                raise ValueError("batch calendar changed after source authorization")
            if frozenset(bar.canonical_id for bar in batch.bars) != frozenset(
                read_approval.targets_by_canonical_id
            ):
                raise ValueError("source batch targets differ from the approved read scope")
            extracted_at = _as_utc(self._clock(), field_name="source extraction timestamp")
            receipt_id = _source_batch_receipt_id(
                source_provenance=self._source_provenance,
                batch=batch,
                import_scope=import_scope,
                extracted_at=extracted_at,
            )
            receipt = LegacyStockDailySourceBatchReceipt(
                source_batch_sha256=batch.content_sha256,
                source_registry_id=self._source_provenance.source_registry_id,
                provider_id=self._source_provenance.provider_id,
                route_id=self._source_provenance.route_id,
                authorization_receipt_id=import_scope.read_scope_receipt.authorization_receipt_id,
                source_receipt_id=receipt_id,
                source_schema_sha256=import_scope.source_schema_sha256,
                import_scope_sha256=import_scope.import_scope_sha256,
                extracted_at=extracted_at,
            )
        except LegacyStockDailyImportError:
            raise
        except (TypeError, ValueError) as exc:
            raise LegacyStockDailyEvidenceGateAdapterError(
                "LEGACY_STOCK_DAILY_SOURCE_BATCH_UNVERIFIED"
            ) from exc
        self._source_batch_approvals[receipt.source_receipt_id] = _SourceBatchApproval(
            receipt=receipt,
            import_scope=import_scope,
            targets_by_canonical_id=read_approval.targets_by_canonical_id,
        )
        return receipt

    async def authorize_canonical_writes(
        self,
        *,
        batch: LegacyStockDailyImportBatch,
        attestation: LegacyStockDailyImportAttestation,
        import_scope: LegacyStockDailyImportScope,
        source_batch_receipt: LegacyStockDailySourceBatchReceipt,
    ) -> Mapping[str, LegacyStockDailyCanonicalWritePermit]:
        """Recheck every source grant and issue one lease-bound permit per target."""
        try:
            if not isinstance(batch, LegacyStockDailyImportBatch):
                raise TypeError("batch must be a LegacyStockDailyImportBatch")
            if not isinstance(import_scope, LegacyStockDailyImportScope):
                raise TypeError("import_scope must be a LegacyStockDailyImportScope")
            if not isinstance(source_batch_receipt, LegacyStockDailySourceBatchReceipt):
                raise TypeError("source_batch_receipt must be a LegacyStockDailySourceBatchReceipt")
            source_approval = self._source_batch_approvals.get(
                source_batch_receipt.source_receipt_id
            )
            if (
                source_approval is None
                or source_approval.receipt != source_batch_receipt
                or source_approval.import_scope != import_scope
                or batch.import_scope != import_scope
                or import_scope.attestation != attestation
                or source_batch_receipt.source_batch_sha256 != batch.content_sha256
            ):
                raise ValueError("source batch receipt was not issued for this write")
            targets = source_approval.targets_by_canonical_id
            if frozenset(bar.canonical_id for bar in batch.bars) != frozenset(targets):
                raise ValueError("source batch targets differ from write targets")
            await self._assert_current_target_authorizations(targets=targets.values())
            permits: dict[str, LegacyStockDailyCanonicalWritePermit] = {}
            for canonical_id, target in sorted(targets.items()):
                permit = LegacyStockDailyCanonicalWritePermit(
                    canonical_id=canonical_id,
                    source_registry_id=self._source_provenance.source_registry_id,
                    provider_id=self._source_provenance.provider_id,
                    route_id=self._source_provenance.route_id,
                    read_authorization_receipt_id=(source_batch_receipt.authorization_receipt_id),
                    source_batch_sha256=source_batch_receipt.source_batch_sha256,
                    import_scope_sha256=import_scope.import_scope_sha256,
                    source_receipt_id=source_batch_receipt.source_receipt_id,
                    write_authorization_descriptor_sha256=(
                        target.source_authorization.descriptor_hash
                    ),
                    resolved_context_sha256=_resolved_context_sha256(target.context),
                    fetch_lease_key_sha256=target.fetch_lease.lease_key_sha256,
                    fetch_lease_fence_token=target.fetch_lease.fence_token,
                )
                permits[canonical_id] = permit
                self._permit_approvals[(canonical_id, permit.source_receipt_id)] = _PermitApproval(
                    permit=permit,
                    target=target,
                    source_batch_receipt=source_batch_receipt,
                    import_scope=import_scope,
                )
        except LegacyStockDailyImportError:
            raise
        except (MarketDataStoreError, TypeError, ValueError) as exc:
            raise LegacyStockDailyEvidenceGateAdapterError(
                "LEGACY_STOCK_DAILY_CANONICAL_WRITE_AUTHORIZATION_UNVERIFIED"
            ) from exc
        return MappingProxyType(permits)

    def target_for_permit(
        self,
        permit: LegacyStockDailyCanonicalWritePermit,
    ) -> LegacyStockDailyCanonicalTarget:
        """Return the gate-owned target only for an exact issued permit."""
        approval = self._permit_approval(permit)
        return approval.target

    def _owns_store(self, store: MarketDataStore) -> bool:
        """Bind a private writer to this gate's one isolated Store instance."""
        return store is self._store

    def deferred_intent_for_permit(
        self,
        permit: LegacyStockDailyCanonicalWritePermit,
    ) -> MarketDataDeferredPublicationIntent:
        """Build the durable deferred binding for one target before staging facts."""
        approval = self._permit_approval(permit)
        payload = {
            "canonical_id": permit.canonical_id,
            "contract_version": _DEFERRED_INTENT_VERSION,
            "fetch_lease_fence_token": permit.fetch_lease_fence_token,
            "fetch_lease_key_sha256": permit.fetch_lease_key_sha256,
            "import_scope_sha256": approval.import_scope.import_scope_sha256,
            "resolved_context_sha256": permit.resolved_context_sha256,
            "source_batch_sha256": permit.source_batch_sha256,
            "source_receipt_id": permit.source_receipt_id,
            "write_authorization_descriptor_sha256": permit.write_authorization_descriptor_sha256,
        }
        return MarketDataDeferredPublicationIntent(
            workflow_kind="legacy_stock_daily_import",
            intent_sha256=_sha256(payload),
        )

    async def assert_promotion_allowed(
        self,
        permit: LegacyStockDailyCanonicalWritePermit,
    ) -> None:
        """Revalidate the exact source grant inside Store's promotion transaction."""
        approval = self._permit_approval(permit)
        target = approval.target
        try:
            await self._store.ensure_source_authorization_before_provider_io(
                target.context,
                target.source_authorization,
                provider_id=self._source_provenance.provider_id,
                checked_at=_as_utc(self._clock(), field_name="promotion authorization timestamp"),
            )
        except (MarketDataStoreError, TypeError, ValueError) as exc:
            raise LegacyStockDailyEvidenceGateAdapterError(
                "LEGACY_STOCK_DAILY_PROMOTION_AUTHORIZATION_UNVERIFIED"
            ) from exc

    def promotion_evidence_sha256(
        self,
        *,
        permit: LegacyStockDailyCanonicalWritePermit,
        staged: DeferredProviderFetch,
        staged_revision_ids: Sequence[str],
    ) -> str:
        """Hash the reviewed staged handle and evidence before guarded promotion."""
        approval = self._permit_approval(permit)
        if not isinstance(staged, DeferredProviderFetch):
            raise TypeError("staged must be a DeferredProviderFetch")
        revisions = tuple(sorted(staged_revision_ids))
        if not revisions or revisions != tuple(sorted(staged.observation_revision_ids)):
            raise LegacyStockDailyEvidenceGateAdapterError(
                "LEGACY_STOCK_DAILY_STAGED_REVIEW_UNVERIFIED"
            )
        return _sha256(
            {
                "canonical_id": permit.canonical_id,
                "contract_version": _PROMOTION_EVIDENCE_VERSION,
                "import_scope_sha256": approval.import_scope.import_scope_sha256,
                "publication_id": staged.publication_id,
                "source_batch_sha256": approval.source_batch_receipt.source_batch_sha256,
                "source_receipt_id": permit.source_receipt_id,
                "source_snapshot_id": staged.source_snapshot_id,
                "staged_revision_ids": list(revisions),
                "write_authorization_descriptor_sha256": permit.write_authorization_descriptor_sha256,
            }
        )

    def _permit_approval(self, permit: LegacyStockDailyCanonicalWritePermit) -> _PermitApproval:
        if not isinstance(permit, LegacyStockDailyCanonicalWritePermit):
            raise TypeError("permit must be a LegacyStockDailyCanonicalWritePermit")
        approval = self._permit_approvals.get((permit.canonical_id, permit.source_receipt_id))
        if approval is None or approval.permit != permit:
            raise LegacyStockDailyEvidenceGateAdapterError(
                "LEGACY_STOCK_DAILY_CANONICAL_WRITE_AUTHORIZATION_UNVERIFIED"
            )
        return approval

    async def _assert_current_target_authorizations(
        self,
        *,
        targets: Sequence[LegacyStockDailyCanonicalTarget],
    ) -> None:
        checked_at = _as_utc(self._clock(), field_name="source authorization timestamp")
        for target in targets:
            _assert_target_source_binding(
                target=target,
                source_provenance=self._source_provenance,
            )
            await self._store.ensure_source_authorization_before_provider_io(
                target.context,
                target.source_authorization,
                provider_id=self._source_provenance.provider_id,
                checked_at=checked_at,
            )


def _assert_read_scope_inputs(
    *,
    table_name: str,
    attestation: LegacyStockDailyImportAttestation,
    calendar: FrozenLegacyStockDailyCalendar,
    frozen_identities: Mapping[str, FrozenLegacyStockDailyIdentity],
    source_provenance: LegacyStockDailySourceProvenance,
    targets_by_canonical_id: Mapping[str, LegacyStockDailyCanonicalTarget],
) -> None:
    if table_name != "STOCK_ZH_A_HIST":
        raise ValueError("legacy table is unsupported")
    if not isinstance(attestation, LegacyStockDailyImportAttestation):
        raise TypeError("attestation must be a LegacyStockDailyImportAttestation")
    if (
        attestation.source_id != source_provenance.source_registry_id
        or attestation.source_revision != source_provenance.source_revision
    ):
        raise ValueError("attestation does not bind the approved mixed warehouse")
    if not isinstance(calendar, FrozenLegacyStockDailyCalendar):
        raise TypeError("calendar must be a FrozenLegacyStockDailyCalendar")
    if not isinstance(frozen_identities, Mapping):
        raise TypeError("frozen_identities must be a mapping")
    identities = tuple(frozen_identities.values())
    if len(identities) != len(targets_by_canonical_id):
        raise ValueError("frozen identities do not exactly cover the approved targets")
    seen_symbols: set[str] = set()
    seen_canonical_ids: set[str] = set()
    for provider_symbol, identity in frozen_identities.items():
        if not isinstance(provider_symbol, str) or not isinstance(
            identity, FrozenLegacyStockDailyIdentity
        ):
            raise TypeError("frozen identities are invalid")
        target = targets_by_canonical_id.get(identity.canonical_id)
        if target is None:
            raise ValueError("frozen identity is not an approved target")
        context_identity = target.context.identity
        if (
            provider_symbol != identity.provider_symbol
            or identity.provider_symbol != context_identity.identity.display_symbol
            or identity.canonical_id != target.context.query.canonical_id
            or identity.canonical_id != context_identity.canonical_id
            or identity.instrument_metadata_version != context_identity.metadata_version
            or identity.market != context_identity.venue
            or identity.market != calendar.calendar_code
        ):
            raise ValueError("frozen identity does not match the approved target context")
        if provider_symbol in seen_symbols or identity.canonical_id in seen_canonical_ids:
            raise ValueError("frozen identities are ambiguous")
        seen_symbols.add(provider_symbol)
        seen_canonical_ids.add(identity.canonical_id)
    if seen_canonical_ids != set(targets_by_canonical_id):
        raise ValueError("approved target is missing a frozen identity")


def _targets_by_canonical_id(
    targets: Sequence[LegacyStockDailyCanonicalTarget],
) -> Mapping[str, LegacyStockDailyCanonicalTarget]:
    by_canonical_id: dict[str, LegacyStockDailyCanonicalTarget] = {}
    symbols: set[str] = set()
    for target in targets:
        context = target.context
        canonical_id = context.query.canonical_id
        provider_symbol = context.identity.identity.display_symbol
        if canonical_id in by_canonical_id or provider_symbol in symbols:
            raise ValueError("legacy import targets must have unique canonical IDs and symbols")
        by_canonical_id[canonical_id] = target
        symbols.add(provider_symbol)
    return MappingProxyType(by_canonical_id)


def _assert_target_source_binding(
    *,
    target: LegacyStockDailyCanonicalTarget,
    source_provenance: LegacyStockDailySourceProvenance,
) -> None:
    context = target.context
    authorization = target.source_authorization
    if (
        context.identity.asset_type != "stock"
        or context.identity.venue not in {"CN-SSE", "CN-SZSE"}
        or context.query.data_kind != "bars"
        or context.query.frequency != "1d"
        or context.query.adjustment != "qfq"
        or frozenset(context.query.required_fields)
        != frozenset({"open", "high", "low", "close", "volume", "change_pct"})
        or authorization.source_registry_id != source_provenance.source_registry_id
        or authorization.asset_type != "stock"
        or authorization.market != context.identity.venue
        or authorization.purpose != context.query.purpose
        or authorization.decision != "ALLOW"
    ):
        raise ValueError("legacy import target source binding is invalid")


def _read_authorization_receipt_id(
    *,
    source_provenance: LegacyStockDailySourceProvenance,
    schema_sha256: str,
    calendar: FrozenLegacyStockDailyCalendar,
    targets_by_canonical_id: Mapping[str, LegacyStockDailyCanonicalTarget],
) -> str:
    payload = {
        "calendar": {
            "calendar_snapshot_id": calendar.calendar_snapshot_id,
            "calendar_version": calendar.calendar_version,
            "coverage_window": {
                "end_at": calendar.coverage_window.end_at.isoformat(),
                "start_at": calendar.coverage_window.start_at.isoformat(),
            },
            "event_key_by_trading_date": [
                {
                    "event_at": key.event_at.isoformat(),
                    "trading_date": trading_date.isoformat(),
                }
                for trading_date, key in sorted(calendar.event_key_by_trading_date.items())
            ],
        },
        "contract_version": _READ_AUTHORIZATION_VERSION,
        "schema_sha256": schema_sha256,
        "source_provenance_sha256": source_provenance.manifest_sha256,
        "targets": [
            {
                "authorization_descriptor_sha256": target.source_authorization.descriptor_hash,
                "canonical_id": canonical_id,
                "fetch_lease_fence_token": target.fetch_lease.fence_token,
                "fetch_lease_key_sha256": target.fetch_lease.lease_key_sha256,
                "query_fingerprint": target.context.query.query_fingerprint,
            }
            for canonical_id, target in sorted(targets_by_canonical_id.items())
        ],
    }
    return f"legacy-stock-daily-read:{_sha256(payload)}"


def _source_batch_receipt_id(
    *,
    source_provenance: LegacyStockDailySourceProvenance,
    batch: LegacyStockDailyImportBatch,
    import_scope: LegacyStockDailyImportScope,
    extracted_at: datetime,
) -> str:
    payload = {
        "contract_version": _SOURCE_BATCH_RECEIPT_VERSION,
        "extracted_at": extracted_at.isoformat(),
        "import_scope_sha256": import_scope.import_scope_sha256,
        "source_batch_sha256": batch.content_sha256,
        "source_provenance_sha256": source_provenance.manifest_sha256,
    }
    return f"legacy-stock-daily-batch:{_sha256(payload)}"


def _resolved_context_sha256(context: ResolvedMarketDataQueryContext) -> str:
    identity = context.coverage_identity
    payload = {
        "canonical_id": context.query.canonical_id,
        "coverage_identity": {
            "adjustment": identity.adjustment,
            "asset_type": identity.asset_type,
            "canonical_id": identity.canonical_id,
            "currency": identity.currency,
            "data_kind": identity.data_kind,
            "dataset_code": identity.dataset_code,
            "family_contract_version": identity.family_contract_version,
            "family_id": identity.family_id,
            "frequency": identity.frequency,
            "instrument_metadata_version": identity.instrument_metadata_version,
            "market": identity.market,
            "price_basis": identity.price_basis,
            "source_policy_id": identity.source_policy_id,
            "unit": identity.unit,
        },
        "identity_metadata_version": context.identity.metadata_version,
        "instrument_id": context.identity.instrument_id,
        "query_fingerprint": context.query.query_fingerprint,
        "storage_dataset_id": context.storage.dataset_id,
    }
    return _sha256(payload)


def _sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            _plain_json(payload),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _plain_json(value: object) -> object:
    """Copy immutable receipt mappings into JSON-native containers for hashing."""
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    if isinstance(value, list):
        return [_plain_json(item) for item in value]
    return value


def _as_utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
