"""Private canonical writer for explicitly approved legacy daily-bar batches.

The writer has no source-fetch method and no application factory.  It receives
only a batch that the evidence gate already sealed, stages each target under a
durable release hold, rereads that hidden state, then promotes it through a
fresh fixture-isolation check.  Every receipt remains explicitly
``UNVERIFIED_COMPATIBILITY``; a failed review quarantines every still-hidden
target.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType

from app.services.market_data.coverage import EventKey, ObservationQuality
from app.services.market_data.legacy_stock_daily_evidence_gate_adapter import (
    LegacyStockDailyEvidenceGateAdapter,
)
from app.services.market_data.legacy_stock_daily_import import (
    FrozenLegacyStockDailyCalendar,
    LegacyStockDailyBar,
    LegacyStockDailyBarRevisionBinding,
    LegacyStockDailyCanonicalWrite,
    LegacyStockDailyCanonicalWritePermit,
    LegacyStockDailyImportAttestation,
    LegacyStockDailyImportBatch,
    LegacyStockDailyImportError,
    LegacyStockDailyLocalReread,
    LegacyStockDailyPublicationReceipt,
    LegacyStockDailySourceBar,
    LegacyStockDailySourceBatchReceipt,
)
from app.services.market_data.providers import (
    MarketDataProviderRequest,
    ProviderFetchResult,
    ProviderMarketObservation,
    SharedSourcePayloadSegment,
)
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.store import (
    UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
    DeferredProviderFetch,
    MarketDataStore,
    MarketDataStoreError,
    _DeferredLegacyImportCandidate,
    _LegacyStockDailyPersistedEvidence,
    _PromotedLegacyImportCandidate,
    _PromotedLegacyImportPublicationReceipt,
)

UTC = timezone.utc
_WRITER_VERSION = "legacy-stock-daily-canonical-writer-v1"
_SHARED_SOURCE_PAYLOAD_FORMAT = "canonical-json-utf8-v1"
_SHARED_SOURCE_PAYLOAD_ROLE = "source_batch"


class LegacyStockDailyCanonicalWriterAdapterError(LegacyStockDailyImportError):
    """Stable rejection emitted while a staged legacy candidate is reviewed."""


@dataclass(frozen=True, slots=True)
class _StagedTarget:
    """One opaque hidden receipt and the inspection that proved its contents."""

    permit: LegacyStockDailyCanonicalWritePermit
    staged: DeferredProviderFetch
    inspection: _DeferredLegacyImportCandidate


class LegacyStockDailyCanonicalWriterAdapter:
    """Stage, inspect, promote, and locally reread one approved import batch.

    This class is only composable with
    :class:`LegacyStockDailyEvidenceGateAdapter`; there is no default writer
    binding in the API, scheduler, or provider registry.
    """

    def __init__(
        self,
        *,
        store: MarketDataStore,
        evidence_gate: LegacyStockDailyEvidenceGateAdapter,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(store, MarketDataStore):
            raise TypeError("store must be a MarketDataStore")
        if not isinstance(evidence_gate, LegacyStockDailyEvidenceGateAdapter):
            raise TypeError("evidence_gate must be a LegacyStockDailyEvidenceGateAdapter")
        if not evidence_gate._owns_store(store):
            raise ValueError("writer must use the evidence gate's isolated Store instance")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        self._store = store
        self._evidence_gate = evidence_gate
        self._clock = clock or (lambda: datetime.now(UTC))
        # This process-local map is deliberately a fail-closed harness seam.
        # A restarted writer cannot reinterpret an unverified promoted receipt
        # as a product local read; it must reconstruct the isolated review.
        self._private_promoted_staged: dict[tuple[str, ...], Mapping[str, _StagedTarget]] = {}

    async def write_daily_bars(
        self,
        *,
        batch: LegacyStockDailyImportBatch,
        attestation: LegacyStockDailyImportAttestation,
        source_batch_receipt: LegacyStockDailySourceBatchReceipt,
        write_permits: Mapping[str, LegacyStockDailyCanonicalWritePermit],
    ) -> LegacyStockDailyCanonicalWrite:
        """Persist only staged facts until exact target evidence is reread.

        The Store necessarily commits each target's immutable facts separately.
        If a later staging/review/promotion step fails, all still-hidden
        receipts are quarantined.  A previously promoted receipt remains an
        auditable durable fact rather than being silently rewritten; callers
        receive a failure instead of an aggregate success claim.
        """
        staged_targets: list[_StagedTarget] = []
        pending_staged: DeferredProviderFetch | None = None
        try:
            _assert_write_inputs(
                batch=batch,
                attestation=attestation,
                source_batch_receipt=source_batch_receipt,
                write_permits=write_permits,
            )
            local_received_at = max(
                _as_utc(self._clock(), field_name="local receipt timestamp"),
                source_batch_receipt.extracted_at,
            )
            for canonical_id, permit in sorted(write_permits.items()):
                target = self._evidence_gate.target_for_permit(permit)
                bars = tuple(bar for bar in batch.bars if bar.canonical_id == canonical_id)
                _assert_target_bars(target.context, bars=bars, permit=permit)
                result = _provider_result_for_target(
                    batch=batch,
                    attestation=attestation,
                    source_batch_receipt=source_batch_receipt,
                    permit=permit,
                    context=target.context,
                    bars=bars,
                    source_provenance=self._evidence_gate.source_provenance.as_receipt_provenance(),
                )
                staged = await self._store.stage_provider_result_for_deferred_release(
                    target.context,
                    result,
                    received_at=local_received_at,
                    # The mixed legacy warehouse has no source authorization.
                    # Store records this fixture receipt as explicitly
                    # UNVERIFIED_COMPATIBILITY; it is never an AkShare claim.
                    unverified_compatibility_reason=target.unverified_compatibility_reason,
                    fetch_lease=target.fetch_lease,
                    deferred_intent=self._evidence_gate.deferred_intent_for_permit(permit),
                )
                pending_staged = staged
                inspection = await self._store._read_deferred_legacy_import_candidate(
                    target.context,
                    staged=staged,
                )
                # The private reread deliberately uses an ordinary read-only
                # Store transaction.  Promotion and quarantine each open a
                # fresh receipt-locking transaction, so release it before a
                # staged candidate can continue through either path.
                await self._store.close_transaction_before_provider_io()
                _assert_staged_projection(
                    batch=batch,
                    attestation=attestation,
                    bars=bars,
                    source_batch_receipt=source_batch_receipt,
                    permit=permit,
                    context=target.context,
                    source_provenance=self._evidence_gate.source_provenance.as_receipt_provenance(),
                    staged=staged,
                    inspection=inspection,
                    result=result,
                )
                staged_targets.append(
                    _StagedTarget(permit=permit, staged=staged, inspection=inspection)
                )
                pending_staged = None
        except LegacyStockDailyImportError:
            await self._quarantine_staged(staged_targets, pending_staged=pending_staged)
            raise
        except (MarketDataStoreError, TypeError, ValueError) as exc:
            await self._quarantine_staged(staged_targets, pending_staged=pending_staged)
            raise LegacyStockDailyCanonicalWriterAdapterError(
                "LEGACY_STOCK_DAILY_STAGED_REVIEW_UNVERIFIED"
            ) from exc

        promoted: list[_StagedTarget] = []
        try:
            for staged_target in staged_targets:
                target = self._evidence_gate.target_for_permit(staged_target.permit)

                async def pre_publish_guard(
                    permit: LegacyStockDailyCanonicalWritePermit = staged_target.permit,
                ) -> None:
                    await self._evidence_gate.assert_promotion_allowed(permit)

                promotion_evidence_sha256 = self._evidence_gate.promotion_evidence_sha256(
                    permit=staged_target.permit,
                    staged=staged_target.staged,
                    staged_revision_ids=tuple(
                        observation.revision_id
                        for observation in staged_target.inspection.observations
                    ),
                )
                await self._store.promote_deferred_provider_result(
                    staged_target.staged,
                    promotion_evidence_sha256=promotion_evidence_sha256,
                    pre_publish_guard=pre_publish_guard,
                    fetch_lease=target.fetch_lease,
                )
                promoted.append(staged_target)
        except LegacyStockDailyImportError:
            await self._quarantine_staged(
                candidate for candidate in staged_targets if candidate not in promoted
            )
            raise
        except (MarketDataStoreError, TypeError, ValueError) as exc:
            await self._quarantine_staged(
                candidate for candidate in staged_targets if candidate not in promoted
            )
            raise LegacyStockDailyCanonicalWriterAdapterError(
                "LEGACY_STOCK_DAILY_PROMOTION_UNVERIFIED"
            ) from exc

        try:
            publication_receipts = []
            for staged_target in staged_targets:
                publication_receipts.append(
                    await self._store._read_promoted_legacy_import_publication(
                        self._evidence_gate.target_for_permit(staged_target.permit).context,
                        staged=staged_target.staged,
                    )
                )
            canonical_write = _canonical_write(
                source_batch_receipt=source_batch_receipt,
                write_permits=write_permits,
                staged_targets=staged_targets,
                publication_receipts=tuple(publication_receipts),
                local_received_at=local_received_at,
            )
            self._private_promoted_staged[_canonical_write_key(canonical_write)] = MappingProxyType(
                {item.permit.canonical_id: item for item in staged_targets}
            )
            return canonical_write
        except (MarketDataStoreError, TypeError, ValueError) as exc:
            raise LegacyStockDailyCanonicalWriterAdapterError(
                "LEGACY_STOCK_DAILY_CANONICAL_WRITE_INVALID"
            ) from exc

    async def read_daily_bars_local_only(
        self,
        *,
        canonical_ids: frozenset[str],
        calendar: FrozenLegacyStockDailyCalendar,
        input_event_keys: tuple[EventKey, ...],
        canonical_write: LegacyStockDailyCanonicalWrite,
        knowledge_cutoff: datetime,
    ) -> LegacyStockDailyLocalReread:
        """Perform the harness-only post-promotion local reread required by the protocol.

        The lookup deliberately does not call the ordinary Store local reader:
        promoted mixed-warehouse snapshots remain unverified and therefore
        cannot become a product response.  It instead uses Store's private
        persisted-evidence reread bound to the exact staged handle retained by
        this isolated writer instance.
        """
        if not isinstance(calendar, FrozenLegacyStockDailyCalendar):
            raise TypeError("calendar must be a FrozenLegacyStockDailyCalendar")
        if not isinstance(canonical_write, LegacyStockDailyCanonicalWrite):
            raise TypeError("canonical_write must be a LegacyStockDailyCanonicalWrite")
        cutoff = _as_utc(knowledge_cutoff, field_name="knowledge_cutoff")
        if canonical_ids != frozenset(canonical_write.target_write_permits):
            raise LegacyStockDailyCanonicalWriterAdapterError(
                "LEGACY_STOCK_DAILY_LOCAL_REREAD_WRITE_MISMATCH"
            )
        staged_by_canonical_id = self._private_promoted_staged.get(
            _canonical_write_key(canonical_write)
        )
        if staged_by_canonical_id is None or frozenset(staged_by_canonical_id) != canonical_ids:
            raise LegacyStockDailyCanonicalWriterAdapterError(
                "LEGACY_STOCK_DAILY_LOCAL_REREAD_WRITE_MISMATCH"
            )
        visibility_anchor = await self._store.resolve_visibility_anchor(knowledge_cutoff=cutoff)
        bars: list[LegacyStockDailyBar] = []
        revision_ids: set[str] = set()
        source_snapshot_ids: set[str] = set()
        binding_by_key = {
            (binding.canonical_id, binding.event_at): binding
            for binding in canonical_write.bar_revision_bindings
        }
        publication_by_snapshot = {
            receipt.source_snapshot_id: receipt for receipt in canonical_write.publication_receipts
        }
        for canonical_id in sorted(canonical_ids):
            permit = canonical_write.target_write_permits[canonical_id]
            target = self._evidence_gate.target_for_permit(permit)
            staged_target = staged_by_canonical_id.get(canonical_id)
            if staged_target is None or staged_target.permit != permit:
                raise LegacyStockDailyCanonicalWriterAdapterError(
                    "LEGACY_STOCK_DAILY_LOCAL_REREAD_WRITE_MISMATCH"
                )
            snapshot_ids = {
                binding.source_snapshot_id
                for binding in canonical_write.bar_revision_bindings
                if binding.canonical_id == canonical_id
            }
            if len(snapshot_ids) != 1:
                raise LegacyStockDailyCanonicalWriterAdapterError(
                    "LEGACY_STOCK_DAILY_LOCAL_REREAD_WRITE_MISMATCH"
                )
            snapshot_id = next(iter(snapshot_ids))
            promoted = await self._store._read_promoted_legacy_import_candidate(
                target.context,
                staged=staged_target.staged,
            )
            _assert_promoted_private_reread(
                promoted=promoted,
                staged_target=staged_target,
                canonical_write=canonical_write,
                expected_snapshot_id=snapshot_id,
                expected_publication=publication_by_snapshot.get(snapshot_id),
            )
            for observation in promoted.observations:
                binding = binding_by_key.get((canonical_id, observation.event_at))
                if (
                    binding is None
                    or binding.observation_revision_id != observation.revision_id
                    or binding.source_snapshot_id != observation.source_snapshot_id
                    or observation.quality is not ObservationQuality.PASS
                    or observation.source_available_at is None
                    or observation.available_at != canonical_write.local_observation_available_at
                ):
                    raise LegacyStockDailyCanonicalWriterAdapterError(
                        "LEGACY_STOCK_DAILY_LOCAL_REREAD_WRITE_MISMATCH"
                    )
                bars.append(
                    LegacyStockDailyBar(
                        provider_symbol=target.context.identity.identity.display_symbol,
                        canonical_id=canonical_id,
                        market=target.context.identity.venue or "",
                        frequency="1d",
                        adjustment="qfq",
                        event_at=observation.event_at,
                        source_available_at=observation.source_available_at,
                        available_at=observation.available_at,
                        observation_revision_id=observation.revision_id,
                        source_snapshot_id=observation.source_snapshot_id,
                        fields=observation.fields,
                    )
                )
                revision_ids.add(observation.revision_id)
                source_snapshot_ids.add(observation.source_snapshot_id)
        expected_bindings = set(binding_by_key)
        if (
            {(bar.canonical_id, bar.event_at) for bar in bars} != expected_bindings
            or revision_ids != canonical_write.observation_revision_ids
            or source_snapshot_ids != canonical_write.source_snapshot_ids
            or tuple(sorted({EventKey(bar.event_at) for bar in bars})) != input_event_keys
        ):
            raise LegacyStockDailyCanonicalWriterAdapterError(
                "LEGACY_STOCK_DAILY_LOCAL_REREAD_MISMATCH"
            )
        reread_calendar = FrozenLegacyStockDailyCalendar(
            calendar_snapshot_id=calendar.calendar_snapshot_id,
            calendar_code=calendar.calendar_code,
            calendar_version=calendar.calendar_version,
            timezone_name=calendar.timezone_name,
            data_kind=calendar.data_kind,
            frequency=calendar.frequency,
            coverage_window=calendar.coverage_window,
            visibility_anchor=visibility_anchor,
            event_key_by_trading_date=dict(calendar.event_key_by_trading_date),
        )
        return LegacyStockDailyLocalReread(
            bars=tuple(sorted(bars, key=lambda item: (item.event_at, item.canonical_id))),
            calendar=reread_calendar,
            input_event_keys=input_event_keys,
            accepted_event_keys=input_event_keys,
            knowledge_cutoff=cutoff,
            visibility_anchor=visibility_anchor,
            mode="local_only",
            source_snapshot_ids=frozenset(source_snapshot_ids),
            observation_revision_ids=frozenset(revision_ids),
        )

    async def _quarantine_staged(
        self,
        staged_targets: Iterable[_StagedTarget],
        *,
        pending_staged: DeferredProviderFetch | None = None,
    ) -> None:
        """Keep failed candidates durable but invisible without masking the first error."""
        try:
            await self._store.close_transaction_before_provider_io()
        except MarketDataStoreError:
            # If the caller left a dirty transaction, this adapter cannot
            # safely discard it. The original rejection remains the useful
            # signal, and an active deferred hold is still non-visible.
            return
        staged_receipts = [item.staged for item in staged_targets]
        if pending_staged is not None:
            staged_receipts.append(pending_staged)
        for staged in staged_receipts:
            try:
                await self._store.quarantine_deferred_provider_result(
                    staged,
                    quarantine_code="LEGACY_STOCK_DAILY_STAGED_REVIEW_FAILED",
                )
            except (MarketDataStoreError, TypeError, ValueError):
                # The original failure remains more useful to the caller. A
                # failed quarantine still cannot expose a DEFERRED receipt.
                continue


def _assert_write_inputs(
    *,
    batch: LegacyStockDailyImportBatch,
    attestation: LegacyStockDailyImportAttestation,
    source_batch_receipt: LegacyStockDailySourceBatchReceipt,
    write_permits: Mapping[str, LegacyStockDailyCanonicalWritePermit],
) -> None:
    if not isinstance(batch, LegacyStockDailyImportBatch):
        raise TypeError("batch must be a LegacyStockDailyImportBatch")
    if not isinstance(attestation, LegacyStockDailyImportAttestation):
        raise TypeError("attestation must be a LegacyStockDailyImportAttestation")
    if not isinstance(source_batch_receipt, LegacyStockDailySourceBatchReceipt):
        raise TypeError("source_batch_receipt must be a LegacyStockDailySourceBatchReceipt")
    if not isinstance(write_permits, Mapping) or not write_permits:
        raise TypeError("write_permits must be a non-empty mapping")
    if (
        source_batch_receipt.source_batch_sha256 != batch.content_sha256
        or source_batch_receipt.import_scope_sha256 != batch.import_scope.import_scope_sha256
        or frozenset(write_permits) != frozenset(bar.canonical_id for bar in batch.bars)
    ):
        raise LegacyStockDailyCanonicalWriterAdapterError(
            "LEGACY_STOCK_DAILY_CANONICAL_WRITE_INVALID"
        )
    for canonical_id, permit in write_permits.items():
        if (
            not isinstance(canonical_id, str)
            or not isinstance(permit, LegacyStockDailyCanonicalWritePermit)
            or permit.canonical_id != canonical_id
            or permit.source_receipt_id != source_batch_receipt.source_receipt_id
            or permit.source_batch_sha256 != source_batch_receipt.source_batch_sha256
            or permit.import_scope_sha256 != batch.import_scope.import_scope_sha256
        ):
            raise LegacyStockDailyCanonicalWriterAdapterError(
                "LEGACY_STOCK_DAILY_CANONICAL_WRITE_INVALID"
            )


def _assert_target_bars(
    context: ResolvedMarketDataQueryContext,
    *,
    bars: Sequence[LegacyStockDailySourceBar],
    permit: LegacyStockDailyCanonicalWritePermit,
) -> None:
    if not bars or context.query.canonical_id != permit.canonical_id:
        raise LegacyStockDailyCanonicalWriterAdapterError(
            "LEGACY_STOCK_DAILY_CANONICAL_WRITE_INVALID"
        )
    if any(
        (
            bar.canonical_id != context.query.canonical_id
            or bar.provider_symbol != context.identity.identity.display_symbol
            or bar.market != context.identity.venue
            or not context.query.start <= bar.event_at < context.query.end
            or bar.source_available_at is None
        )
        for bar in bars
    ):
        raise LegacyStockDailyCanonicalWriterAdapterError(
            "LEGACY_STOCK_DAILY_CANONICAL_WRITE_INVALID"
        )


def _provider_result_for_target(
    *,
    batch: LegacyStockDailyImportBatch,
    attestation: LegacyStockDailyImportAttestation,
    source_batch_receipt: LegacyStockDailySourceBatchReceipt,
    permit: LegacyStockDailyCanonicalWritePermit,
    context: ResolvedMarketDataQueryContext,
    bars: Sequence[LegacyStockDailySourceBar],
    source_provenance: Mapping[str, object],
) -> ProviderFetchResult:
    request = MarketDataProviderRequest(
        query_fingerprint=context.query.query_fingerprint,
        canonical_id=context.query.canonical_id,
        asset_type=context.identity.asset_type,
        provider_symbol=context.identity.identity.display_symbol,
        market=context.identity.venue or "",
        data_kind=context.query.data_kind,
        frequency=context.query.frequency or "snapshot",
        start_at=context.query.start,
        end_at=context.query.end,
        required_fields=frozenset(context.query.required_fields),
        provider=source_batch_receipt.provider_id,
        adjustment=context.query.adjustment,
        price_basis=context.query.price_basis,
        currency=context.query.currency,
        unit=context.query.unit,
        source_policy_id=context.query.source_policy_id,
        route_id=source_batch_receipt.route_id,
        family_id=context.query.family_id,
        family_contract_version=context.query.family_contract_version,
        provider_endpoint=source_batch_receipt.route_id,
    )
    raw_payload = {
        "legacy_import": {
            "attestation": {
                "adjustment": attestation.adjustment,
                "schema_version": attestation.schema_version,
                "source_id": attestation.source_id,
                "source_revision": attestation.source_revision,
                "source_timezone": attestation.source_timezone,
            },
            "canonical_id": permit.canonical_id,
            "contract_version": _WRITER_VERSION,
            "import_scope_sha256": permit.import_scope_sha256,
            "per_row_provider_attribution": "unavailable",
            "source_batch_sha256": permit.source_batch_sha256,
            "source_provenance": _plain_json(source_provenance),
            "source_receipt": {
                "authorization_receipt_id": source_batch_receipt.authorization_receipt_id,
                "extracted_at": source_batch_receipt.extracted_at.isoformat(),
                "provider_id": source_batch_receipt.provider_id,
                "route_id": source_batch_receipt.route_id,
                "source_registry_id": source_batch_receipt.source_registry_id,
                "source_receipt_id": source_batch_receipt.source_receipt_id,
                "source_schema_sha256": source_batch_receipt.source_schema_sha256,
            },
            "write_permit": {
                "fetch_lease_fence_token": permit.fetch_lease_fence_token,
                "fetch_lease_key_sha256": permit.fetch_lease_key_sha256,
                "resolved_context_sha256": permit.resolved_context_sha256,
                "write_authorization_descriptor_sha256": (
                    permit.write_authorization_descriptor_sha256
                ),
            },
        },
        "source_batch": _plain_json(batch.raw_payload),
    }
    return ProviderFetchResult(
        provider_id=source_batch_receipt.provider_id,
        source_revision=attestation.source_revision,
        retrieved_at=source_batch_receipt.extracted_at,
        observations=tuple(
            ProviderMarketObservation(
                event_at=bar.event_at,
                available_at=bar.source_available_at,
                fields=dict(bar.fields),
            )
            for bar in bars
        ),
        raw_payload=raw_payload,
        request=request,
        warnings=(
            "LEGACY_STOCK_DAILY_OFFLINE_IMPORT",
            "LEGACY_STOCK_DAILY_MIXED_PROVENANCE",
            "LEGACY_STOCK_DAILY_PER_ROW_PROVIDER_ATTRIBUTION_UNAVAILABLE",
        ),
        shared_source_payload_segment=SharedSourcePayloadSegment(
            segment_key="source_batch",
            payload_format=_SHARED_SOURCE_PAYLOAD_FORMAT,
            payload_role=_SHARED_SOURCE_PAYLOAD_ROLE,
        ),
    )


def _assert_staged_projection(
    *,
    batch: LegacyStockDailyImportBatch,
    attestation: LegacyStockDailyImportAttestation,
    bars: Sequence[LegacyStockDailySourceBar],
    source_batch_receipt: LegacyStockDailySourceBatchReceipt,
    permit: LegacyStockDailyCanonicalWritePermit,
    context: ResolvedMarketDataQueryContext,
    source_provenance: Mapping[str, object],
    staged: DeferredProviderFetch,
    inspection: _DeferredLegacyImportCandidate,
    result: ProviderFetchResult,
) -> None:
    if inspection.staged != staged or len(inspection.observations) != len(bars):
        raise LegacyStockDailyCanonicalWriterAdapterError(
            "LEGACY_STOCK_DAILY_STAGED_REVIEW_UNVERIFIED"
        )
    _assert_persisted_legacy_import_evidence(
        evidence=inspection.evidence,
        batch=batch,
        attestation=attestation,
        source_batch_receipt=source_batch_receipt,
        permit=permit,
        context=context,
        source_provenance=source_provenance,
        result=result,
        expected_source_snapshot_id=staged.source_snapshot_id,
    )
    expected_by_event = {bar.event_at: bar for bar in bars}
    seen_events: set[datetime] = set()
    for observation in inspection.observations:
        expected = expected_by_event.get(observation.event_at)
        if (
            expected is None
            or observation.event_at in seen_events
            or observation.source_snapshot_id != staged.source_snapshot_id
            or observation.quality is not ObservationQuality.PASS
            or observation.fields != expected.fields
            or observation.source_available_at != source_batch_receipt.extracted_at
            or observation.available_at != staged.local_received_at
        ):
            raise LegacyStockDailyCanonicalWriterAdapterError(
                "LEGACY_STOCK_DAILY_STAGED_REVIEW_UNVERIFIED"
            )
        seen_events.add(observation.event_at)
    if seen_events != set(expected_by_event):
        raise LegacyStockDailyCanonicalWriterAdapterError(
            "LEGACY_STOCK_DAILY_STAGED_REVIEW_UNVERIFIED"
        )


def _assert_persisted_legacy_import_evidence(
    *,
    evidence: _LegacyStockDailyPersistedEvidence,
    batch: LegacyStockDailyImportBatch,
    attestation: LegacyStockDailyImportAttestation,
    source_batch_receipt: LegacyStockDailySourceBatchReceipt,
    permit: LegacyStockDailyCanonicalWritePermit,
    context: ResolvedMarketDataQueryContext,
    source_provenance: Mapping[str, object],
    result: ProviderFetchResult,
    expected_source_snapshot_id: str,
) -> None:
    """Compare Store-reread evidence with the issued fixture receipt/permit.

    The comparison deliberately begins with the private Store return.  The
    caller's batch and permit only provide expected values; they cannot replace
    the persisted request, receipt manifest, shared bytes, or source evidence.
    """
    expected_attestation = {
        "adjustment": attestation.adjustment,
        "schema_version": attestation.schema_version,
        "source_id": attestation.source_id,
        "source_revision": attestation.source_revision,
        "source_timezone": attestation.source_timezone,
    }
    expected_source_receipt = {
        "authorization_receipt_id": source_batch_receipt.authorization_receipt_id,
        "extracted_at": source_batch_receipt.extracted_at.isoformat(),
        "provider_id": source_batch_receipt.provider_id,
        "route_id": source_batch_receipt.route_id,
        "source_registry_id": source_batch_receipt.source_registry_id,
        "source_receipt_id": source_batch_receipt.source_receipt_id,
        "source_schema_sha256": source_batch_receipt.source_schema_sha256,
    }
    expected_permit = {
        "fetch_lease_fence_token": permit.fetch_lease_fence_token,
        "fetch_lease_key_sha256": permit.fetch_lease_key_sha256,
        "resolved_context_sha256": permit.resolved_context_sha256,
        "write_authorization_descriptor_sha256": permit.write_authorization_descriptor_sha256,
    }
    legacy_import = evidence.legacy_import
    if (
        evidence.source_snapshot_id != expected_source_snapshot_id
        or evidence.source_id != source_batch_receipt.provider_id
        or evidence.endpoint_version != attestation.source_revision
        or evidence.source_observed_at != source_batch_receipt.extracted_at
        or evidence.source_authorization_state != "UNVERIFIED_COMPATIBILITY"
        or evidence.unverified_compatibility
        != {
            "version": "market-data-unverified-source-write-v1",
            "reason": UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            "decision": "UNVERIFIED",
        }
        or _canonical_json_value(evidence.source_batch) != _canonical_json_value(batch.raw_payload)
        or _canonical_json_value(evidence.provider_request)
        != _canonical_json_value(result.request.dto_payload)
        or _canonical_json_value(evidence.resolved_query)
        != _canonical_json_value(context.query.semantic_payload())
        or set(evidence.receipt_payload) != {"legacy_import"}
        or set(legacy_import)
        != {
            "attestation",
            "canonical_id",
            "contract_version",
            "import_scope_sha256",
            "per_row_provider_attribution",
            "source_batch_sha256",
            "source_provenance",
            "source_receipt",
            "write_permit",
        }
        or legacy_import.get("canonical_id") != permit.canonical_id
        or legacy_import.get("contract_version") != _WRITER_VERSION
        or legacy_import.get("source_batch_sha256") != source_batch_receipt.source_batch_sha256
        or legacy_import.get("import_scope_sha256") != source_batch_receipt.import_scope_sha256
        or legacy_import.get("per_row_provider_attribution") != "unavailable"
        or _canonical_json_value(legacy_import.get("attestation"))
        != _canonical_json_value(expected_attestation)
        or _canonical_json_value(legacy_import.get("source_receipt"))
        != _canonical_json_value(expected_source_receipt)
        or _canonical_json_value(legacy_import.get("write_permit"))
        != _canonical_json_value(expected_permit)
        or _canonical_json_value(legacy_import.get("source_provenance"))
        != _canonical_json_value(source_provenance)
        or source_batch_receipt.source_schema_sha256 != batch.import_scope.source_schema_sha256
        or permit.import_scope_sha256 != batch.import_scope.import_scope_sha256
        or permit.resolved_context_sha256 != _resolved_context_sha256_for_writer(context)
        or evidence.fetch_lease_key_sha256 != permit.fetch_lease_key_sha256
        or evidence.fetch_lease_fence_token != permit.fetch_lease_fence_token
    ):
        raise LegacyStockDailyCanonicalWriterAdapterError(
            "LEGACY_STOCK_DAILY_STAGED_REVIEW_UNVERIFIED"
        )


def _assert_promoted_private_reread(
    *,
    promoted: _PromotedLegacyImportCandidate,
    staged_target: _StagedTarget,
    canonical_write: LegacyStockDailyCanonicalWrite,
    expected_snapshot_id: str,
    expected_publication: LegacyStockDailyPublicationReceipt | None,
) -> None:
    """Reject a post-promotion source/receipt mutation before local harness use."""
    if (
        promoted.staged != staged_target.staged
        or promoted.evidence != staged_target.inspection.evidence
        or promoted.observations != staged_target.inspection.observations
        or promoted.publication.source_snapshot_id != expected_snapshot_id
        or expected_publication is None
        or promoted.publication.publication_id != expected_publication.publication_id
        or promoted.publication.visible_at != expected_publication.visible_at
        or promoted.publication.visibility_sequence != expected_publication.visibility_sequence
        or promoted.publication.source_snapshot_id not in canonical_write.source_snapshot_ids
    ):
        raise LegacyStockDailyCanonicalWriterAdapterError(
            "LEGACY_STOCK_DAILY_LOCAL_REREAD_WRITE_MISMATCH"
        )


def _canonical_write_key(canonical_write: LegacyStockDailyCanonicalWrite) -> tuple[str, ...]:
    """Return an in-process key for an opaque isolated-writer staged handle."""
    payload = {
        "import_scope_sha256": canonical_write.import_scope_sha256,
        "observation_revision_ids": sorted(canonical_write.observation_revision_ids),
        "source_batch_sha256": canonical_write.source_batch_sha256,
        "source_receipt_id": canonical_write.source_receipt_id,
        "source_snapshot_ids": sorted(canonical_write.source_snapshot_ids),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()
    return (digest,)


def _canonical_json_value(value: object) -> str:
    """Hash-comparable JSON serialization for persisted-evidence comparisons."""
    return json.dumps(
        _plain_json(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _resolved_context_sha256_for_writer(context: ResolvedMarketDataQueryContext) -> str:
    """Match the gate's context seal without importing its private helper."""
    identity = context.coverage_identity
    return hashlib.sha256(
        _canonical_json_value(
            {
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
        ).encode("utf-8")
    ).hexdigest()


def _canonical_write(
    *,
    source_batch_receipt: LegacyStockDailySourceBatchReceipt,
    write_permits: Mapping[str, LegacyStockDailyCanonicalWritePermit],
    staged_targets: Sequence[_StagedTarget],
    publication_receipts: Sequence[_PromotedLegacyImportPublicationReceipt],
    local_received_at: datetime,
) -> LegacyStockDailyCanonicalWrite:
    if len(publication_receipts) != len(staged_targets):
        raise LegacyStockDailyCanonicalWriterAdapterError(
            "LEGACY_STOCK_DAILY_CANONICAL_WRITE_INVALID"
        )
    bindings: list[LegacyStockDailyBarRevisionBinding] = []
    revision_to_snapshot: dict[str, str] = {}
    canonical_receipts: list[LegacyStockDailyPublicationReceipt] = []
    for staged_target, publication in zip(staged_targets, publication_receipts, strict=True):
        if publication.source_snapshot_id != staged_target.staged.source_snapshot_id:
            raise LegacyStockDailyCanonicalWriterAdapterError(
                "LEGACY_STOCK_DAILY_CANONICAL_WRITE_INVALID"
            )
        canonical_receipts.append(
            LegacyStockDailyPublicationReceipt(
                publication_id=publication.publication_id,
                source_snapshot_id=publication.source_snapshot_id,
                visible_at=publication.visible_at,
                visibility_sequence=publication.visibility_sequence,
            )
        )
        for observation in staged_target.inspection.observations:
            bindings.append(
                LegacyStockDailyBarRevisionBinding(
                    canonical_id=staged_target.permit.canonical_id,
                    event_at=observation.event_at,
                    observation_revision_id=observation.revision_id,
                    source_snapshot_id=observation.source_snapshot_id,
                )
            )
            revision_to_snapshot[observation.revision_id] = observation.source_snapshot_id
    return LegacyStockDailyCanonicalWrite(
        source_snapshot_ids=frozenset(revision_to_snapshot.values()),
        observation_revision_ids=frozenset(revision_to_snapshot),
        observation_revision_source_snapshot_ids=revision_to_snapshot,
        bar_revision_bindings=tuple(
            sorted(bindings, key=lambda item: (item.event_at, item.canonical_id))
        ),
        target_write_permits=MappingProxyType(dict(write_permits)),
        source_batch_sha256=source_batch_receipt.source_batch_sha256,
        import_scope_sha256=source_batch_receipt.import_scope_sha256,
        source_receipt_id=source_batch_receipt.source_receipt_id,
        local_observation_available_at=local_received_at,
        published_at=max(item.visible_at for item in canonical_receipts),
        publication_receipts=tuple(canonical_receipts),
    )


def _plain_json(value: object) -> object:
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
