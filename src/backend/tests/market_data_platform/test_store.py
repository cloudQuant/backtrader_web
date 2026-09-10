"""Focused behavioral contracts for normalized Iteration 197 local storage."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry
from app.models.data_governance import DgDataset, DgProvider
from app.models.market_data_platform import (
    CALENDAR_SOURCE_GOVERNANCE_STATE_VERIFIED,
    MdCalendarEvent,
    MdCalendarSnapshot,
    MdDataSeries,
    MdObservationRevision,
    MdPublication,
    MdSourcePayload,
    MdSourceSnapshot,
    MdSourceSnapshotPayloadRef,
)
from app.schemas.asset_research import InstrumentIdentity, StockIdentityDetails
from app.schemas.market_data_platform import MarketDataQueryRequest, ResolvedMarketDataQuery
from app.services.market_data import store as store_module
from app.services.market_data.access import MarketDataSourceAuthorization
from app.services.market_data.catalog import DatasetStorageResolution
from app.services.market_data.coverage import (
    CalendarStatus,
    ObservationQuality,
    QueryIdentity,
    TimeWindow,
)
from app.services.market_data.fetch_lease import (
    MarketDataFetchLeaseError,
    MarketDataFetchLeaseManager,
)
from app.services.market_data.field_quality import FIELD_QUALITY_POLICY_VERSION
from app.services.market_data.identity import ResolvedMarketDataIdentity
from app.services.market_data.providers import (
    MarketDataProviderRequest,
    ProviderFetchResult,
    ProviderMarketObservation,
    SharedSourcePayloadSegment,
)
from app.services.market_data.publication import (
    PUBLICATION_CALENDAR_SNAPSHOT,
    MarketDataPublicationError,
    MarketDataPublicationManager,
    MarketDataVisibilityAnchor,
)
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.store import (
    UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
    MarketDataStore,
    MarketDataStoreError,
)

UTC = timezone.utc
DATASET_ID = "dataset-market-stock"
DATASET_CODE = "market.stock_daily"
CANONICAL_ID = "instrument:stock:CN-SSE:600000"
METADATA_VERSION = "stock-v1"
PROVIDER_ID = "akshare:stock"


def _at(hour: int, *, day: int = 8) -> datetime:
    return datetime(2026, 9, day, hour, tzinfo=UTC)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="stock",
        identity_level="ASSET",
        canonical_id=CANONICAL_ID,
        display_symbol="600000",
        name="浦发银行",
        venue="CN-SSE",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="EXCHANGE_SYMBOL",
        identifier_value="600000",
        product_type="EQUITY",
        metadata_version=METADATA_VERSION,
        details=StockIdentityDetails(exchange_symbol="600000.SH"),
    )


def _context(
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    required_fields: tuple[str, ...] = ("close",),
    purpose: str = "display",
    consistency: str = "display",
    mode: str = "local_first",
    knowledge_cutoff: datetime | None = None,
    family_id: str | None = None,
    family_contract_version: str | None = None,
) -> ResolvedMarketDataQueryContext:
    start_at = start or _at(9)
    end_at = end or _at(16)
    request = MarketDataQueryRequest.model_validate(
        {
            "identity": {"canonical_id": CANONICAL_ID},
            "dataset_code": DATASET_CODE,
            "data_kind": "bars",
            "frequency": "1d",
            "start": start_at.isoformat(),
            "end": end_at.isoformat(),
            "required_fields": list(required_fields),
            "adjustment": "qfq",
            "price_basis": "close",
            "currency": "CNY",
            "unit": "share",
            "source_policy_id": "market-default-v1",
            "family_id": family_id,
            "family_contract_version": family_contract_version,
            "purpose": purpose,
            "consistency": consistency,
            "mode": mode,
            "knowledge_cutoff": (
                knowledge_cutoff.isoformat() if knowledge_cutoff is not None else None
            ),
        }
    )
    query = ResolvedMarketDataQuery.from_request(
        request,
        canonical_id=CANONICAL_ID,
        dataset_code=DATASET_CODE,
        instrument_metadata_version=METADATA_VERSION,
    )
    identity = _identity()
    resolved_identity = ResolvedMarketDataIdentity(
        instrument_id="instrument-stock-v1",
        canonical_id=CANONICAL_ID,
        asset_type="stock",
        metadata_version=METADATA_VERSION,
        venue="CN-SSE",
        identity=identity,
        valid_from=_at(0, day=1),
        valid_to=None,
        known_at=_at(0, day=1),
    )
    return ResolvedMarketDataQueryContext(
        query=query,
        identity=resolved_identity,
        storage=DatasetStorageResolution(
            dataset_id=DATASET_ID,
            dataset_code=DATASET_CODE,
            storage_id="canonical-market-data",
            engine="postgresql",
            database_name="market_data",
            physical_table="md_observation_revisions",
            write_mode="canonical_read_write",
        ),
        coverage_identity=QueryIdentity(
            dataset_code=DATASET_CODE,
            canonical_id=CANONICAL_ID,
            asset_type="stock",
            instrument_metadata_version=METADATA_VERSION,
            data_kind="bars",
            market="CN-SSE",
            frequency="1d",
            source_policy_id="market-default-v1",
            adjustment="qfq",
            price_basis="close",
            currency="CNY",
            unit="share",
            family_id=query.family_id,
            family_contract_version=query.family_contract_version,
        ),
    )


async def _seed_dataset_and_provider(
    db,
    *,
    provider_id: str = PROVIDER_ID,
    active: bool = True,
) -> None:
    db.add_all(
        [
            DgDataset(
                id=DATASET_ID,
                dataset_code=DATASET_CODE,
                display_name="A 股日线",
                domain="market",
                canonical_schema={"event_at": "timestamp", "close": "decimal"},
                primary_key=["canonical_id", "event_at"],
            ),
            DgProvider(
                id="provider-akshare-stock",
                provider_id=provider_id,
                name="AkShare stock",
                category="market",
                is_active=active,
            ),
        ]
    )
    await db.commit()


async def _seed_source_registry(
    db,
    *,
    source_id: str = PROVIDER_ID,
    license_status: str = "APPROVED",
    updated_at: datetime | None = None,
    allowed_uses: tuple[str, ...] = ("DISPLAY",),
) -> None:
    """Seed the live registry contract used to validate a frozen receipt grant."""
    db.add(
        AssetDataSourceRegistry(
            source_id=source_id,
            asset_types=["stock"],
            jurisdictions=["CN"],
            license_status=license_status,
            allowed_uses=list(allowed_uses),
            redistribution_policy="NO_REDISTRIBUTION",
            derived_data_policy="ALLOWED",
            retention_policy="market-data-v1",
            effective_from=datetime(2020, 1, 1, tzinfo=UTC),
            effective_to=None,
            retention_expires_at=None,
            enabled=True,
            updated_at=updated_at or _at(0),
        )
    )
    await db.commit()


def _source_authorization(
    *,
    source_registry_id: str = PROVIDER_ID,
    license_status: str = "APPROVED",
    decision: str = "ALLOW",
    asset_type: str = "stock",
    allowed_uses: tuple[str, ...] = ("DISPLAY",),
    purpose: str = "display",
) -> MarketDataSourceAuthorization:
    """Build exact source evidence in the canonical authorizer representation."""
    values: dict[str, object] = {
        "source_registry_id": source_registry_id,
        "registry_updated_at": _at(0).isoformat(),
        "asset_type": asset_type,
        "market": "CN-SSE",
        "purpose": purpose,
        "license_status": license_status,
        "allowed_uses": allowed_uses,
        "jurisdictions": ("CN",),
        "effective_from": datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        "effective_to": None,
        "retention_policy": "MARKET-DATA-V1",
        "retention_expires_at": None,
        "redistribution_policy": "NO_REDISTRIBUTION",
        "principal_scope": "principal-v1:test-receipt",
        "tenant_scope": "default",
        "entitlement_revision": _sha("test-entitlement"),
        "decision": decision,
    }
    descriptor_hash = hashlib.sha256(
        json.dumps(
            {"version": "market-data-source-authorization-v1", **values},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return MarketDataSourceAuthorization(descriptor_hash=descriptor_hash, **values)  # type: ignore[arg-type]


def _calendar_source_governance(
    *,
    manifest_hash: str,
    source_registry_id: str = PROVIDER_ID,
) -> dict[str, object]:
    """Build the importer-owned descriptor shape expected by the calendar reader."""
    values: dict[str, object] = {
        "version": "market-data-calendar-source-governance-v1",
        "source_registry_id": source_registry_id,
        "registry_updated_at": _at(0).isoformat(),
        "license_status": "APPROVED",
        "asset_types": ["STOCK"],
        "jurisdictions": ["CN"],
        "allowed_uses": ["DISPLAY"],
        "effective_from": datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        "effective_to": None,
        "retention_policy": "MARKET-DATA-V1",
        "retention_expires_at": None,
        "redistribution_policy": "NO_REDISTRIBUTION",
        "approval_reference": "CAB-197-CALENDAR-TEST",
        "evidence_uri": "file:///approved/calendars/CN-SSE-2026-09.json",
        "evidence_content_hash": _sha("calendar-source-evidence"),
        "calendar_manifest_hash": manifest_hash,
        "decision": "ALLOW",
    }
    descriptor_hash = _sha(
        json.dumps(values, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )
    return {**values, "descriptor_hash": descriptor_hash}


def _result(
    *,
    observations: tuple[ProviderMarketObservation, ...],
    retrieved_at: datetime,
    provider_id: str = PROVIDER_ID,
    source_revision: str = "v1",
    request_provider: str = "akshare",
    raw_payload: dict[str, object] | None = None,
    shared_source_payload_segment: SharedSourcePayloadSegment | None = None,
    request: MarketDataProviderRequest | None = None,
    context: ResolvedMarketDataQueryContext | None = None,
) -> ProviderFetchResult:
    context = context or _context()
    return ProviderFetchResult(
        provider_id=provider_id,
        source_revision=source_revision,
        retrieved_at=retrieved_at,
        observations=observations,
        raw_payload=raw_payload
        or {"records": [{"event_at": item.event_at.isoformat()} for item in observations]},
        request=request
        or MarketDataProviderRequest(
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
            provider=request_provider,
            adjustment=context.query.adjustment,
            price_basis=context.query.price_basis,
            currency=context.query.currency,
            unit=context.query.unit,
            source_policy_id=context.query.source_policy_id,
            family_id=context.query.family_id,
            family_contract_version=context.query.family_contract_version,
        ),
        shared_source_payload_segment=shared_source_payload_segment,
    )


def _observation(
    *,
    event_at: datetime,
    available_at: datetime,
    fields: dict[str, object],
) -> ProviderMarketObservation:
    return ProviderMarketObservation(
        event_at=event_at,
        available_at=available_at,
        fields=fields,
    )


def _legacy_v1_revision_key(
    context: ResolvedMarketDataQueryContext,
    revision: MdObservationRevision,
    *,
    fields_sha256: str,
    quality: ObservationQuality,
) -> str:
    """Build a historically valid v1 identity for fixtures that predate source-time sealing."""
    return store_module._observation_revision_identity_sha256(
        contract_version=store_module._OBSERVATION_REVISION_CONTRACT_V1,
        series_semantic_key_sha256=MarketDataStore.series_identity(context).semantic_key_sha256,
        source_snapshot_id=revision.source_snapshot_id,
        event_at=store_module._stored_utc(
            revision.event_time,
            field_name="legacy revision event_time",
        ),
        available_at=store_module._stored_utc(
            revision.available_at,
            field_name="legacy revision available_at",
        ),
        fields_sha256=fields_sha256,
        quality=quality,
        revision_number=revision.revision_number,
        source_available_at=None,
    )


@pytest.mark.asyncio
async def test_series_identity_reuses_one_series_across_windows_and_projection_fields() -> None:
    """Windows and required-field projection do not fork the canonical economic series."""
    first_context = _context(required_fields=("close",))
    second_context = _context(
        start=_at(9, day=9),
        end=_at(16, day=9),
        required_fields=("close", "volume"),
    )

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db)
        first = await store.get_or_create_series(first_context)
        second = await store.get_or_create_series(second_context)
        await db.commit()

        count = await db.scalar(select(func.count()).select_from(MdDataSeries))

    assert first.id == second.id
    assert count == 1
    assert "start" not in first.semantic_identity_json
    assert "end" not in first.semantic_identity_json
    assert "required_fields" not in first.semantic_identity_json
    assert first.semantic_identity_json["instrument_metadata_version"] == METADATA_VERSION


def test_series_identity_binds_the_private_kline_family_contract_pair() -> None:
    """A full-OHLCV legacy series never shares storage identity with stock.realtime."""
    kline_context = _context(
        required_fields=("open", "high", "low", "close", "volume", "change_pct"),
        family_id="stock.kline_legacy",
        family_contract_version="market-data-kline-v1",
    )
    realtime_context = _context(
        family_id="stock.realtime",
        family_contract_version="market-data-family-v1",
    )

    kline_identity = MarketDataStore.series_identity(kline_context)
    realtime_identity = MarketDataStore.series_identity(realtime_context)

    assert kline_identity.semantic_key_sha256 != realtime_identity.semantic_key_sha256
    assert kline_identity.semantic_identity["family_id"] == "stock.kline_legacy"
    assert kline_identity.semantic_identity["family_contract_version"] == "market-data-kline-v1"
    assert realtime_identity.semantic_identity["family_id"] == "stock.realtime"
    assert realtime_identity.semantic_identity["family_contract_version"] == "market-data-family-v1"


@pytest.mark.asyncio
async def test_store_appends_source_provenance_and_normalized_revisions() -> None:
    """Each fetch retains its raw receipt while same-event revisions remain append-only."""
    context = _context()
    event_at = _at(10)
    failed_event_at = _at(11)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db)
        first = await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(14),
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(12),
                        fields={"close": Decimal("10.50")},
                    ),
                    _observation(
                        event_at=failed_event_at,
                        available_at=_at(12),
                        fields={"open": Decimal("10.00")},
                    ),
                ),
                raw_payload={"records": [{"close": Decimal("10.50")}]},
            ),
            received_at=_at(14),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()

        second = await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(16),
                source_revision="v2",
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(15),
                        fields={"close": Decimal("11.00")},
                    ),
                ),
            ),
            received_at=_at(16),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()

        snapshots = list(
            (await db.execute(select(MdSourceSnapshot).order_by(MdSourceSnapshot.retrieved_at)))
            .scalars()
            .all()
        )
        revisions = list(
            (
                await db.execute(
                    select(MdObservationRevision)
                    .where(MdObservationRevision.event_time == event_at)
                    .order_by(MdObservationRevision.revision_number)
                )
            )
            .scalars()
            .all()
        )
        failed_revision = await db.scalar(
            select(MdObservationRevision).where(MdObservationRevision.event_time == failed_event_at)
        )

    assert first.series_id == second.series_id
    assert first.passing_observation_count == 1
    assert first.failed_observation_count == 1
    assert len(snapshots) == 2
    assert snapshots[0].payload_manifest_json["raw_payload"]["records"][0]["close"] == "10.50"
    expected_fields_hash = _sha(
        json.dumps({"close": "10.50"}, separators=(",", ":"), sort_keys=True)
    )
    assert revisions[0].fields_sha256 == expected_fields_hash
    assert [item.revision_number for item in revisions] == [1, 2]
    assert revisions[0].source_snapshot_id == first.source_snapshot_id
    assert revisions[1].source_snapshot_id == second.source_snapshot_id
    assert failed_revision is not None
    assert failed_revision.quality_status == "failed"
    assert failed_revision.quality_details_json["missing_required_fields"] == ["close"]
    assert revisions[0].quality_policy_version == FIELD_QUALITY_POLICY_VERSION


@pytest.mark.asyncio
async def test_store_persists_separate_provider_request_and_source_authorization_evidence() -> None:
    """One receipt retains public-query, provider-call, and registry evidence separately."""
    context = _context()
    result = _result(
        retrieved_at=_at(12),
        observations=(
            _observation(
                event_at=_at(10),
                available_at=_at(11),
                fields={"close": "10.00"},
            ),
        ),
    )
    authorization = _source_authorization()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        await _seed_source_registry(db)
        persisted = await MarketDataStore(db).persist_provider_result(
            context,
            result,
            received_at=_at(12),
            source_authorization=authorization,
        )
        snapshot = await db.get(MdSourceSnapshot, persisted.source_snapshot_id)

    assert snapshot is not None
    assert snapshot.request_fingerprint_sha256 == context.query.query_fingerprint
    assert snapshot.query_fingerprint_sha256 == context.query.query_fingerprint
    assert snapshot.provider_request_id == result.request.request_id
    assert (
        snapshot.provider_request_fingerprint_sha256
        == result.request.provider_request_fingerprint_sha256
    )
    assert snapshot.source_authorization_state == "VERIFIED"
    assert snapshot.source_authorization_descriptor_sha256 == authorization.descriptor_hash
    assert snapshot.request_json["provider_request"] == result.request.dto_payload
    assert snapshot.provenance_json["source_authorization"] == authorization.as_provenance()


@pytest.mark.asyncio
async def test_store_persists_research_cache_fill_with_research_source_authorization() -> None:
    """A current cache receipt remains distinguishable from an Iteration 196 PIT read."""
    context = _context(purpose="research_cache_fill")
    result = _result(
        retrieved_at=_at(12),
        observations=(
            _observation(
                event_at=_at(10),
                available_at=_at(11),
                fields={"close": "10.00"},
            ),
        ),
        context=context,
    )
    authorization = _source_authorization(
        purpose="research_cache_fill",
        allowed_uses=("RESEARCH_ONLY",),
    )

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        await _seed_source_registry(db, allowed_uses=("RESEARCH_ONLY",))
        persisted = await MarketDataStore(db).persist_provider_result(
            context,
            result,
            received_at=_at(12),
            source_authorization=authorization,
        )
        snapshot = await db.get(MdSourceSnapshot, persisted.source_snapshot_id)

    assert snapshot is not None
    assert snapshot.provenance_json["source_authorization"]["purpose"] == "research_cache_fill"
    assert snapshot.provenance_json["source_authorization"]["allowed_uses"] == ["RESEARCH_ONLY"]


@pytest.mark.asyncio
async def test_store_allows_a_cache_fill_receipt_for_strict_research_only() -> None:
    """A persisted cache fill satisfies research reread but never a backtest read."""
    cache_fill_context = _context(purpose="research_cache_fill")
    strict_research_context = _context(
        purpose="research",
        consistency="strict",
        knowledge_cutoff=_at(13),
    )
    strict_backtest_context = _context(
        purpose="backtest",
        consistency="strict",
        knowledge_cutoff=_at(13),
    )
    result = _result(
        retrieved_at=_at(12),
        observations=(
            _observation(
                event_at=_at(10),
                available_at=_at(11),
                fields={"close": "10.00"},
            ),
        ),
        context=cache_fill_context,
    )
    authorization = _source_authorization(
        purpose="research_cache_fill",
        allowed_uses=("RESEARCH_ONLY",),
    )

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        await _seed_source_registry(db, allowed_uses=("RESEARCH_ONLY",))
        store = MarketDataStore(db, clock=lambda: _at(12))
        await store.persist_provider_result(
            cache_fill_context,
            result,
            received_at=_at(12),
            source_authorization=authorization,
        )
        strict_research_rows = await store.read_observation_revisions(
            strict_research_context,
            knowledge_cutoff=_at(13),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        strict_backtest_rows = await store.read_observation_revisions(
            strict_backtest_context,
            knowledge_cutoff=_at(13),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )

    assert len(strict_research_rows) == 1
    assert strict_research_rows[0].fields == {"close": "10.00"}
    assert strict_backtest_rows == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("authorization", "expected_code"),
    [
        (
            _source_authorization(source_registry_id="openbb:yfinance"),
            "SOURCE_AUTHORIZATION_PROVIDER_MISMATCH",
        ),
        (_source_authorization(decision="DENY"), "SOURCE_AUTHORIZATION_DENIED"),
        (_source_authorization(asset_type="bond"), "SOURCE_AUTHORIZATION_CONTEXT_MISMATCH"),
        (
            _source_authorization(allowed_uses=("DISPLAY", "RESEARCH")),
            "SOURCE_AUTHORIZATION_REGISTRY_STALE",
        ),
        (
            replace(_source_authorization(), license_status="PUBLIC"),
            "SOURCE_AUTHORIZATION_DESCRIPTOR_MISMATCH",
        ),
    ],
)
async def test_store_rejects_untrusted_or_non_allow_source_authorization(
    authorization: MarketDataSourceAuthorization,
    expected_code: str,
) -> None:
    """Mismatched or stale authorization fields cannot bypass the registry recheck."""
    context = _context()
    result = _result(
        retrieved_at=_at(12),
        observations=(
            _observation(
                event_at=_at(10),
                available_at=_at(11),
                fields={"close": "10.00"},
            ),
        ),
    )

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        await _seed_source_registry(db)
        with pytest.raises(MarketDataStoreError) as rejected:
            await MarketDataStore(db).persist_provider_result(
                context,
                result,
                received_at=_at(12),
                source_authorization=authorization,
            )
        count = await db.scalar(select(func.count()).select_from(MdSourceSnapshot))

    assert rejected.value.code == expected_code
    assert count == 0


@pytest.mark.asyncio
async def test_store_requires_a_grant_or_explicitly_tags_compatibility_writes() -> None:
    """No-grant direct writes cannot silently create facts usable by a v2 read."""
    context = _context()
    result = _result(
        retrieved_at=_at(12),
        observations=(
            _observation(
                event_at=_at(10),
                available_at=_at(11),
                fields={"close": "10.00"},
            ),
        ),
    )

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(12))
        with pytest.raises(MarketDataStoreError) as missing_grant:
            await store.persist_provider_result(context, result, received_at=_at(12))
        await db.rollback()

        with pytest.raises(MarketDataStoreError) as conflicting_mode:
            await store.persist_provider_result(
                context,
                result,
                received_at=_at(12),
                source_authorization=_source_authorization(),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        await db.rollback()

        with pytest.raises(MarketDataStoreError) as undeclared_compatibility_mode:
            await store.persist_provider_result(
                context,
                result,
                received_at=_at(12),
                unverified_compatibility_reason="ad_hoc_import",
            )
        await db.rollback()

        persisted = await store.persist_provider_result(
            context,
            result,
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        snapshot = await db.get(MdSourceSnapshot, persisted.source_snapshot_id)
        assert snapshot is not None
        persisted_state = snapshot.source_authorization_state
        persisted_descriptor = snapshot.source_authorization_descriptor_sha256
        persisted_provenance = snapshot.provenance_json["unverified_compatibility"]
        direct_rows = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(13),
        )
        v2_rows = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(13),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        await db.execute(
            update(MdSourceSnapshot)
            .where(MdSourceSnapshot.id == persisted.source_snapshot_id)
            .values(
                source_authorization_state=None,
                source_authorization_descriptor_sha256=None,
            )
        )
        await db.commit()
        legacy_v2_rows = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(13),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )

    assert missing_grant.value.code == "SOURCE_AUTHORIZATION_REQUIRED"
    assert conflicting_mode.value.code == "SOURCE_AUTHORIZATION_MODE_CONFLICT"
    assert undeclared_compatibility_mode.value.code == "SOURCE_AUTHORIZATION_REQUIRED"
    assert persisted_state == "UNVERIFIED_COMPATIBILITY"
    assert persisted_descriptor is None
    assert persisted_provenance == {
        "version": "market-data-unverified-source-write-v1",
        "reason": UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        "decision": "UNVERIFIED",
    }
    assert len(direct_rows) == 1
    assert v2_rows == ()
    assert legacy_v2_rows == ()


@pytest.mark.asyncio
async def test_store_rechecks_frozen_authorization_against_current_source_registry() -> None:
    """A registry change after provider collection blocks receipt persistence."""
    context = _context()
    result = _result(
        retrieved_at=_at(12),
        observations=(
            _observation(
                event_at=_at(10),
                available_at=_at(11),
                fields={"close": "10.00"},
            ),
        ),
    )

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        await _seed_source_registry(db, license_status="UNKNOWN")
        with pytest.raises(MarketDataStoreError) as rejected:
            await MarketDataStore(db).persist_provider_result(
                context,
                result,
                received_at=_at(12),
                source_authorization=_source_authorization(),
            )
        count = await db.scalar(select(func.count()).select_from(MdSourceSnapshot))

    assert rejected.value.code == "SOURCE_AUTHORIZATION_REGISTRY_STALE"
    assert count == 0


@pytest.mark.asyncio
async def test_store_filters_local_reads_by_currently_authorized_source_registry_ids() -> None:
    """A sealed local fact is not returned when its source is no longer allowed."""
    context = _context()
    event_at = _at(10)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        await _seed_source_registry(db)
        await _seed_source_registry(db, source_id="openbb:yfinance")
        db.add(
            DgProvider(
                id="provider-openbb-yfinance",
                provider_id="openbb:yfinance",
                name="OpenBB yfinance",
                category="market",
                is_active=True,
            )
        )
        await db.commit()
        store = MarketDataStore(db, clock=lambda: _at(14))
        await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(12),
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(11),
                        fields={"close": "10.00"},
                    ),
                ),
            ),
            received_at=_at(12),
            source_authorization=_source_authorization(),
        )
        await store.persist_provider_result(
            context,
            _result(
                provider_id="openbb:yfinance",
                request_provider="openbb",
                source_revision="v2",
                retrieved_at=_at(14),
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(13),
                        fields={"close": "11.00"},
                    ),
                ),
            ),
            received_at=_at(14),
            source_authorization=_source_authorization(source_registry_id="openbb:yfinance"),
        )
        allowed = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(15),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        denied = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(15),
            allowed_source_registry_ids=frozenset(),
        )

    assert len(allowed) == 1
    assert allowed[0].fields == {"close": "10.00"}
    assert denied == ()


@pytest.mark.asyncio
async def test_store_v2_read_excludes_a_forged_verified_authorization_receipt() -> None:
    """State and source ID alone cannot make a raw/internal row a v2 fact."""
    context = _context()
    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        await _seed_source_registry(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        persisted = await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(12),
                observations=(
                    _observation(
                        event_at=_at(10),
                        available_at=_at(11),
                        fields={"close": "10.00"},
                    ),
                ),
            ),
            received_at=_at(12),
            source_authorization=_source_authorization(),
        )
        snapshot = await db.get(MdSourceSnapshot, persisted.source_snapshot_id)
        assert snapshot is not None
        forged_provenance = dict(snapshot.provenance_json)
        forged_authorization = dict(forged_provenance["source_authorization"])
        forged_authorization["market"] = "US-NYSE"
        forged_provenance["source_authorization"] = forged_authorization
        await db.execute(
            update(MdSourceSnapshot)
            .where(MdSourceSnapshot.id == persisted.source_snapshot_id)
            .values(provenance_json=forged_provenance)
            .execution_options(synchronize_session=False)
        )
        await db.commit()

        unrestricted = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(15),
        )
        current_authorized = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(15),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )

    assert len(unrestricted) == 1
    assert current_authorized == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("placeholder", ("--", "N/A"))
async def test_store_marks_akshare_bar_placeholders_failed_under_the_typed_policy(
    placeholder: str,
) -> None:
    """AkShare bar text sentinels can persist as evidence but cannot become PASS facts."""
    context = _context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        persisted = await MarketDataStore(db).persist_provider_result(
            context,
            _result(
                retrieved_at=_at(12),
                observations=(
                    _observation(
                        event_at=_at(10),
                        available_at=_at(11),
                        fields={"close": placeholder},
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        revision = await db.scalar(select(MdObservationRevision))

    assert persisted.passing_observation_count == 0
    assert persisted.failed_observation_count == 1
    assert revision is not None
    assert revision.quality_status == "failed"
    assert revision.quality_policy_version == FIELD_QUALITY_POLICY_VERSION
    assert revision.quality_details_json["missing_required_fields"] == ["close"]
    assert revision.fields_json == {"close": None}


@pytest.mark.asyncio
async def test_store_rechecks_a_legacy_pass_placeholder_without_rewriting_it() -> None:
    """A later legacy PASS row cannot hide an older usable fact at read time."""
    context = _context()
    event_at = _at(10)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(12),
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(11),
                        fields={"close": "10.00"},
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(14),
                source_revision="legacy-v1",
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(13),
                        fields={"close": "11.00"},
                    ),
                ),
            ),
            received_at=_at(14),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        legacy = await db.scalar(
            select(MdObservationRevision)
            .where(MdObservationRevision.revision_number == 2)
            .order_by(MdObservationRevision.id)
        )
        assert legacy is not None
        legacy_fields = {"close": "--"}
        legacy_fields_sha256 = _sha(
            json.dumps(legacy_fields, separators=(",", ":"), sort_keys=True)
        )
        await db.execute(
            update(MdObservationRevision)
            .where(MdObservationRevision.id == legacy.id)
            .values(
                fields_json=legacy_fields,
                fields_sha256=legacy_fields_sha256,
                quality_status="pass",
                quality_policy_version="required-fields-v1",
                revision_key_sha256=_legacy_v1_revision_key(
                    context,
                    legacy,
                    fields_sha256=legacy_fields_sha256,
                    quality=ObservationQuality.PASS,
                ),
            )
        )
        await db.commit()

        selected = await store.read_observation_revisions(context, knowledge_cutoff=_at(15))

    assert len(selected) == 1
    assert selected[0].revision_number == 1
    assert selected[0].fields == {"close": "10.00"}


@pytest.mark.asyncio
async def test_store_excludes_a_legacy_pass_placeholder_from_response_rows_but_keeps_diagnostics() -> (
    None
):
    """The current field policy controls product reads without rewriting history."""
    context = _context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        # Publication visibility is sampled after commit rather than copied
        # from a provider's receipt time, so this PIT test fixes that clock.
        store = MarketDataStore(db, clock=lambda: _at(12))
        await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(12),
                observations=(
                    _observation(
                        event_at=_at(10),
                        available_at=_at(11),
                        fields={"close": "10.00"},
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        legacy = await db.scalar(select(MdObservationRevision))
        assert legacy is not None
        legacy_fields = {"close": "--"}
        legacy_fields_sha256 = _sha(
            json.dumps(legacy_fields, separators=(",", ":"), sort_keys=True)
        )
        await db.execute(
            update(MdObservationRevision)
            .where(MdObservationRevision.id == legacy.id)
            .values(
                fields_json=legacy_fields,
                fields_sha256=legacy_fields_sha256,
                quality_status="pass",
                quality_policy_version="required-fields-v1",
                revision_key_sha256=_legacy_v1_revision_key(
                    context,
                    legacy,
                    fields_sha256=legacy_fields_sha256,
                    quality=ObservationQuality.PASS,
                ),
            )
        )
        await db.commit()

        response_rows = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(15),
        )
        diagnostic_rows = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(15),
            include_unusable_for_coverage=True,
        )

    assert response_rows == ()
    assert len(diagnostic_rows) == 1
    assert diagnostic_rows[0].quality is ObservationQuality.PASS
    assert diagnostic_rows[0].fields == {"close": "--"}


@pytest.mark.asyncio
async def test_store_applies_the_same_placeholder_fallback_to_openbb_without_network() -> None:
    """The provider-neutral store rejects an OpenBB text sentinel without an adapter call."""
    context = _context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db, provider_id="openbb:yfinance")
        persisted = await MarketDataStore(db).persist_provider_result(
            context,
            _result(
                provider_id="openbb:yfinance",
                request_provider="openbb",
                retrieved_at=_at(12),
                observations=(
                    _observation(
                        event_at=_at(10),
                        available_at=_at(11),
                        fields={"close": "--"},
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        revision = await db.scalar(select(MdObservationRevision))

    assert persisted.passing_observation_count == 0
    assert persisted.failed_observation_count == 1
    assert revision is not None
    assert revision.quality_status == "failed"
    assert revision.fields_json == {"close": None}


@pytest.mark.asyncio
async def test_local_read_uses_availability_and_commit_time_for_point_in_time_selection() -> None:
    """A later correction cannot leak into a cutoff before it was locally committed."""
    context = _context()
    event_at = _at(10)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        # The requested historical cutoffs need a deterministic trusted
        # publication clock. A real clock later than the artificial replay
        # window correctly makes these receipts invisible.
        store = MarketDataStore(db, clock=lambda: _at(12))
        await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(12),
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(11),
                        fields={"close": "10.00"},
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(16),
                source_revision="v2",
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(15),
                        fields={"close": "11.00"},
                    ),
                ),
            ),
            received_at=_at(16),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()

        early = await store.read_observations(context, knowledge_cutoff=_at(13))
        late = await store.read_observations(context, knowledge_cutoff=_at(17))

    assert len(early) == 1
    assert early[0].fields["close"] == "10.00"
    assert len(late) == 1
    assert late[0].fields["close"] == "11.00"


@pytest.mark.asyncio
async def test_local_read_keeps_an_older_complete_revision_visible_after_a_narrower_revision() -> (
    None
):
    """A field projection must not hide an already cached, broader local fact."""
    broad_context = _context(required_fields=("close", "volume"))
    narrow_context = _context(required_fields=("close",))
    event_at = _at(10)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        await store.persist_provider_result(
            broad_context,
            _result(
                retrieved_at=_at(12),
                context=broad_context,
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(11),
                        fields={"close": "10.00", "volume": 1000},
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        await store.persist_provider_result(
            narrow_context,
            _result(
                retrieved_at=_at(14),
                source_revision="narrow-v2",
                context=narrow_context,
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(13),
                        fields={"close": "10.25"},
                    ),
                ),
            ),
            received_at=_at(14),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()

        broad_rows = await store.read_observation_revisions(
            broad_context,
            knowledge_cutoff=_at(15),
        )
        narrow_rows = await store.read_observation_revisions(
            narrow_context,
            knowledge_cutoff=_at(15),
        )

    assert len(broad_rows) == 1
    assert broad_rows[0].revision_number == 1
    assert broad_rows[0].fields == {"close": "10.00", "volume": 1000}
    assert len(narrow_rows) == 1
    assert narrow_rows[0].revision_number == 2
    assert narrow_rows[0].fields == {"close": "10.25"}


@pytest.mark.asyncio
async def test_store_rejects_unregistered_out_of_window_and_duplicate_provider_events() -> None:
    """Invalid provider input fails before it can create an evidence receipt."""
    context = _context()
    valid_observation = _observation(
        event_at=_at(10),
        available_at=_at(11),
        fields={"close": "10.00"},
    )

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db)
        with pytest.raises(MarketDataStoreError) as unregistered:
            await store.persist_provider_result(
                context,
                _result(
                    provider_id="unregistered:stock",
                    retrieved_at=_at(12),
                    observations=(valid_observation,),
                ),
                received_at=_at(12),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        with pytest.raises(MarketDataStoreError) as out_of_window:
            await store.persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(17),
                    observations=(
                        _observation(
                            event_at=context.query.end,
                            available_at=_at(16),
                            fields={"close": "10.00"},
                        ),
                    ),
                ),
                received_at=_at(17),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        with pytest.raises(MarketDataStoreError) as duplicate:
            await store.persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(13),
                    observations=(valid_observation, valid_observation),
                ),
                received_at=_at(13),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        count = await db.scalar(select(func.count()).select_from(MdSourceSnapshot))

    assert unregistered.value.code == "PROVIDER_UNREGISTERED"
    assert out_of_window.value.code == "PROVIDER_EVENT_OUT_OF_WINDOW"
    assert duplicate.value.code == "DUPLICATE_PROVIDER_EVENT"
    assert count == 0


@pytest.mark.asyncio
async def test_store_bounds_inline_raw_payload_before_writing_source_evidence(monkeypatch) -> None:
    """An adapter cannot exhaust the canonical store with an arbitrarily large raw receipt."""
    context = _context()
    monkeypatch.setattr(store_module, "MAX_SOURCE_PAYLOAD_BYTES", 32)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        with pytest.raises(MarketDataStoreError) as too_large:
            await MarketDataStore(db).persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(12),
                    observations=(
                        _observation(
                            event_at=_at(10),
                            available_at=_at(11),
                            fields={"close": "10.00"},
                        ),
                    ),
                    raw_payload={"payload": "x" * 128},
                ),
                received_at=_at(12),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        count = await db.scalar(select(func.count()).select_from(MdSourceSnapshot))

    assert too_large.value.code == "PROVIDER_PAYLOAD_TOO_LARGE"
    assert count == 0


@pytest.mark.asyncio
async def test_store_content_addresses_one_source_batch_for_multiple_source_receipts() -> None:
    """Target receipts retain full hashes while their wide batch is stored once."""
    context = _context()
    raw_payload = {
        "collector": {"batch_id": "wide-batch-1", "target_scope": "stock"},
        "source_batch": {
            "capture": {"provider": "akshare", "captured_at": _at(12).isoformat()},
            "response_rows": [{"symbol": "600000", "close": "10.00"}],
        },
    }
    segment = SharedSourcePayloadSegment(
        segment_key="source_batch",
        payload_format="canonical-json-utf8-v1",
        payload_role="source_batch",
    )

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db)
        first = await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(12),
                observations=(
                    _observation(event_at=_at(10), available_at=_at(11), fields={"close": "10.00"}),
                ),
                raw_payload=raw_payload,
                shared_source_payload_segment=segment,
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        second = await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(13),
                source_revision="v2",
                observations=(
                    _observation(event_at=_at(10), available_at=_at(11), fields={"close": "10.10"}),
                ),
                raw_payload=raw_payload,
                shared_source_payload_segment=segment,
            ),
            received_at=_at(13),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        payloads = list((await db.execute(select(MdSourcePayload))).scalars())
        refs = list((await db.execute(select(MdSourceSnapshotPayloadRef))).scalars())
        snapshots = list(
            (
                await db.execute(select(MdSourceSnapshot).order_by(MdSourceSnapshot.retrieved_at))
            ).scalars()
        )
        publication_count = int(
            await db.scalar(select(func.count()).select_from(MdPublication)) or 0
        )

    assert len(payloads) == 1
    assert len(refs) == 2
    assert {item.source_snapshot_id for item in refs} == {
        first.source_snapshot_id,
        second.source_snapshot_id,
    }
    assert {item.payload_role for item in refs} == {"source_batch"}
    refs_by_snapshot_id = {item.source_snapshot_id: item for item in refs}
    shared_payload = payloads[0]
    canonical_source_batch = json.dumps(
        raw_payload["source_batch"],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert bytes(shared_payload.canonical_payload_bytes) == canonical_source_batch
    assert shared_payload.payload_bytes == len(canonical_source_batch)
    assert shared_payload.content_sha256 == hashlib.sha256(canonical_source_batch).hexdigest()
    assert publication_count == 2
    for snapshot in snapshots:
        manifest = snapshot.payload_manifest_json
        assert manifest["format"] == "content-addressed-source-batch-v1"
        assert "raw_payload" not in manifest
        assert manifest["receipt_payload"] == {"collector": raw_payload["collector"]}
        assert manifest["shared_source_payload"] == {
            "content_sha256": shared_payload.content_sha256,
            "payload_format": "canonical-json-utf8-v1",
            "payload_bytes": len(canonical_source_batch),
            "payload_role": "source_batch",
        }
        ref = refs_by_snapshot_id[snapshot.id]
        assert ref.content_sha256 == manifest["shared_source_payload"]["content_sha256"]
        assert ref.payload_role == manifest["shared_source_payload"]["payload_role"]
        reconstructed = dict(manifest["receipt_payload"])
        reconstructed["source_batch"] = json.loads(canonical_source_batch.decode("utf-8"))
        assert (
            snapshot.payload_sha256
            == hashlib.sha256(
                json.dumps(
                    reconstructed,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
        )


@pytest.mark.asyncio
async def test_store_never_reuses_a_shared_payload_for_different_canonical_bytes() -> None:
    """Content addressing shares only exactly identical normalized source batches."""
    context = _context()
    segment = SharedSourcePayloadSegment(
        segment_key="source_batch",
        payload_format="canonical-json-utf8-v1",
        payload_role="source_batch",
    )
    first_payload = {
        "collector": {"batch_id": "wide-batch-a"},
        "source_batch": {"response_rows": [{"symbol": "600000", "close": "10.00"}]},
    }
    second_payload = {
        "collector": {"batch_id": "wide-batch-b"},
        "source_batch": {"response_rows": [{"symbol": "600000", "close": "10.01"}]},
    }

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db)
        await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(12),
                observations=(
                    _observation(event_at=_at(10), available_at=_at(11), fields={"close": "10.00"}),
                ),
                raw_payload=first_payload,
                shared_source_payload_segment=segment,
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(13),
                source_revision="v2",
                observations=(
                    _observation(event_at=_at(10), available_at=_at(11), fields={"close": "10.01"}),
                ),
                raw_payload=second_payload,
                shared_source_payload_segment=segment,
            ),
            received_at=_at(13),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        payloads = list((await db.execute(select(MdSourcePayload))).scalars())
        refs = list((await db.execute(select(MdSourceSnapshotPayloadRef))).scalars())

    assert len(payloads) == 2
    assert len(refs) == 2
    assert {payload.content_sha256 for payload in payloads} == {
        hashlib.sha256(
            json.dumps(
                payload["source_batch"], ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
        ).hexdigest()
        for payload in (first_payload, second_payload)
    }


@pytest.mark.asyncio
async def test_store_rejects_invalid_shared_payload_segment_before_writing_evidence() -> None:
    """A caller cannot select arbitrary receipt sections for content addressing."""
    context = _context()
    invalid_segment = SharedSourcePayloadSegment(
        segment_key="records",
        payload_format="canonical-json-utf8-v1",
        payload_role="source_batch",
    )

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        with pytest.raises(MarketDataStoreError) as rejected:
            await MarketDataStore(db).persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(12),
                    observations=(
                        _observation(
                            event_at=_at(10),
                            available_at=_at(11),
                            fields={"close": "10.00"},
                        ),
                    ),
                    raw_payload={"records": [{"close": "10.00"}], "source_batch": {}},
                    shared_source_payload_segment=invalid_segment,
                ),
                received_at=_at(12),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        counts = (
            int(await db.scalar(select(func.count()).select_from(MdSourcePayload)) or 0),
            int(await db.scalar(select(func.count()).select_from(MdSourceSnapshotPayloadRef)) or 0),
            int(await db.scalar(select(func.count()).select_from(MdSourceSnapshot)) or 0),
        )

    assert rejected.value.code == "SHARED_SOURCE_PAYLOAD_SEGMENT_INVALID"
    assert counts == (0, 0, 0)


@pytest.mark.asyncio
async def test_store_rejects_corrupted_existing_shared_payload_before_new_receipt() -> None:
    """Natural-key reuse cannot conceal a tampered immutable payload row."""
    context = _context()
    raw_payload = {"collector": {"batch_id": "tamper-check"}, "source_batch": {"rows": []}}
    segment = SharedSourcePayloadSegment(
        segment_key="source_batch",
        payload_format="canonical-json-utf8-v1",
        payload_role="source_batch",
    )
    observation = _observation(event_at=_at(10), available_at=_at(11), fields={"close": "10.00"})

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db)
        await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(12),
                observations=(observation,),
                raw_payload=raw_payload,
                shared_source_payload_segment=segment,
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        payload = await db.scalar(select(MdSourcePayload))
        assert payload is not None
        await db.execute(
            update(MdSourcePayload)
            .where(MdSourcePayload.content_sha256 == payload.content_sha256)
            .values(canonical_payload_bytes=b'{"tampered":true}')
        )
        await db.commit()
        with pytest.raises(MarketDataStoreError) as rejected:
            await store.persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(13),
                    source_revision="v2",
                    observations=(observation,),
                    raw_payload=raw_payload,
                    shared_source_payload_segment=segment,
                ),
                received_at=_at(13),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        await db.rollback()
        snapshot_count = int(
            await db.scalar(select(func.count()).select_from(MdSourceSnapshot)) or 0
        )

    assert rejected.value.code == "SHARED_SOURCE_PAYLOAD_INTEGRITY_CONFLICT"
    assert snapshot_count == 1


@pytest.mark.asyncio
async def test_store_revalidates_shared_payload_after_another_session_tampers() -> None:
    """A long-lived store session cannot reuse an identity-mapped stale blob."""
    context = _context()
    raw_payload = {"collector": {"batch_id": "cross-session-tamper"}, "source_batch": {"rows": []}}
    segment = SharedSourcePayloadSegment(
        segment_key="source_batch",
        payload_format="canonical-json-utf8-v1",
        payload_role="source_batch",
    )
    observation = _observation(event_at=_at(10), available_at=_at(11), fields={"close": "10.00"})

    async with async_session_maker() as stale_db:
        await _seed_dataset_and_provider(stale_db)
        store = MarketDataStore(stale_db)
        await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(12),
                observations=(observation,),
                raw_payload=raw_payload,
                shared_source_payload_segment=segment,
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        payload = await stale_db.scalar(select(MdSourcePayload))
        assert payload is not None
        await stale_db.commit()

        async with async_session_maker() as tamper_db:
            await tamper_db.execute(
                update(MdSourcePayload)
                .where(MdSourcePayload.content_sha256 == payload.content_sha256)
                .values(canonical_payload_bytes=b'{"tampered":true}')
            )
            await tamper_db.commit()

        with pytest.raises(MarketDataStoreError) as rejected:
            await store.persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(13),
                    source_revision="v2",
                    observations=(observation,),
                    raw_payload=raw_payload,
                    shared_source_payload_segment=segment,
                ),
                received_at=_at(13),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        await stale_db.rollback()
        snapshot_count = int(
            await stale_db.scalar(select(func.count()).select_from(MdSourceSnapshot)) or 0
        )

    assert rejected.value.code == "SHARED_SOURCE_PAYLOAD_INTEGRITY_CONFLICT"
    assert snapshot_count == 1


@pytest.mark.asyncio
async def test_store_rejects_a_receipt_bound_to_another_query_before_writing() -> None:
    """Direct store callers cannot persist a valid receipt for a nearby series/window."""
    context = _context()
    observation = _observation(
        event_at=_at(10),
        available_at=_at(11),
        fields={"close": "10.00"},
    )
    base_result = _result(retrieved_at=_at(12), observations=(observation,))
    mismatched_request = replace(base_result.request, canonical_id="instrument:stock:CN-SSE:600001")

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        with pytest.raises(MarketDataStoreError) as mismatch:
            await MarketDataStore(db).persist_provider_result(
                context,
                replace(base_result, request=mismatched_request),
                received_at=_at(12),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        count = await db.scalar(select(func.count()).select_from(MdSourceSnapshot))

    assert mismatch.value.code == "PROVIDER_REQUEST_MISMATCH"
    assert count == 0


@pytest.mark.asyncio
async def test_store_uses_local_receipt_time_not_provider_claim_for_pit_visibility() -> None:
    """An old provider timestamp cannot backdate when this platform learned the fact."""
    context = _context()
    observation = _observation(
        event_at=_at(10),
        available_at=_at(10),
        fields={"close": "10.00"},
    )

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        persisted = await store.persist_provider_result(
            context,
            _result(retrieved_at=_at(10), observations=(observation,)),
            received_at=_at(14),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        before_receipt = await store.read_observations(context, knowledge_cutoff=_at(13))
        at_business_receipt = await store.read_observations(context, knowledge_cutoff=_at(14))
        # The visibility receipt is deliberately later than ``received_at``:
        # transaction A must commit before transaction B publishes it.
        after_receipt = await store.read_observations(
            context,
            knowledge_cutoff=_at(14).replace(microsecond=1),
        )
        snapshot = await db.get(MdSourceSnapshot, persisted.source_snapshot_id)

    assert before_receipt == ()
    assert at_business_receipt == ()
    assert len(after_receipt) == 1
    assert persisted.received_at == _at(14).replace(microsecond=1)
    assert snapshot is not None
    assert store_module._stored_utc(
        snapshot.retrieved_at, field_name="snapshot retrieved_at"
    ) == _at(14)
    assert store_module._stored_utc(
        snapshot.source_observed_at, field_name="snapshot observed_at"
    ) == _at(10)
    assert snapshot.provenance_json["provider_retrieved_at"] == _at(10).isoformat()


@pytest.mark.asyncio
async def test_store_local_revision_exposes_validated_provider_availability_separately() -> None:
    """A local read preserves upstream availability without replacing its PIT receipt time."""
    context = _context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(12))
        await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(11),
                observations=(
                    _observation(
                        event_at=_at(10),
                        available_at=_at(11),
                        fields={"close": "10.00"},
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()

        rows = await store.read_observation_revisions(context, knowledge_cutoff=_at(13))

    assert len(rows) == 1
    assert rows[0].source_available_at == _at(11)
    assert rows[0].available_at == _at(12)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_available_at",
    (
        None,
        "not-a-timestamp",
        "2026-09-08T11:00:00",
        _at(10).isoformat(),
        _at(13).isoformat(),
    ),
    ids=(
        "missing",
        "malformed",
        "timezone-free",
        "sealed-but-earlier",
        "after-local-availability",
    ),
)
async def test_store_fails_closed_when_persisted_provider_availability_is_invalid(
    provider_available_at: str | None,
) -> None:
    """Tampered or incomplete upstream availability evidence cannot contribute local coverage."""
    context = _context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(12))
        persisted = await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(11),
                observations=(
                    _observation(
                        event_at=_at(10),
                        available_at=_at(11),
                        fields={"close": "10.00"},
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        revision = await db.get(MdObservationRevision, persisted.observation_revision_ids[0])
        assert revision is not None
        forged_provenance = dict(revision.provenance_json)
        if provider_available_at is None:
            forged_provenance.pop("provider_available_at")
        else:
            forged_provenance["provider_available_at"] = provider_available_at
        await db.execute(
            update(MdObservationRevision)
            .where(MdObservationRevision.id == revision.id)
            .values(provenance_json=forged_provenance)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        db.expire_all()

        with pytest.raises(MarketDataStoreError) as rejected:
            await store.read_observation_revisions(context, knowledge_cutoff=_at(13))

    assert rejected.value.code == "LOCAL_OBSERVATION_INTEGRITY"


@pytest.mark.asyncio
async def test_store_fails_closed_when_sealed_provider_availability_follows_local_receipt() -> None:
    """A valid v2 identity cannot make upstream availability later than the local receipt."""
    context = _context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(12))
        persisted = await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(11),
                observations=(
                    _observation(
                        event_at=_at(10),
                        available_at=_at(11),
                        fields={"close": "10.00"},
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        revision = await db.get(MdObservationRevision, persisted.observation_revision_ids[0])
        assert revision is not None
        forged_source_available_at = _at(13)
        forged_provenance = dict(revision.provenance_json)
        forged_provenance["provider_available_at"] = forged_source_available_at.isoformat()
        sealed_forged_revision_key = store_module._observation_revision_identity_sha256(
            contract_version=store_module._OBSERVATION_REVISION_CONTRACT_V2,
            series_semantic_key_sha256=MarketDataStore.series_identity(context).semantic_key_sha256,
            source_snapshot_id=revision.source_snapshot_id,
            event_at=store_module._stored_utc(
                revision.event_time,
                field_name="sealed forged revision event_time",
            ),
            available_at=store_module._stored_utc(
                revision.available_at,
                field_name="sealed forged revision available_at",
            ),
            fields_sha256=revision.fields_sha256,
            quality=ObservationQuality(revision.quality_status),
            revision_number=revision.revision_number,
            source_available_at=forged_source_available_at,
        )
        await db.execute(
            update(MdObservationRevision)
            .where(MdObservationRevision.id == revision.id)
            .values(
                revision_key_sha256=sealed_forged_revision_key,
                provenance_json=forged_provenance,
            )
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        db.expire_all()

        with pytest.raises(MarketDataStoreError) as rejected:
            await store.read_observation_revisions(context, knowledge_cutoff=_at(14))

    assert rejected.value.code == "LOCAL_OBSERVATION_INTEGRITY"


@pytest.mark.asyncio
async def test_store_leaves_unsealed_v1_provider_availability_unavailable() -> None:
    """Historical v1 identity rows remain readable but cannot claim source timing proof."""
    context = _context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(12))
        persisted = await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(11),
                observations=(
                    _observation(
                        event_at=_at(10),
                        available_at=_at(11),
                        fields={"close": "10.00"},
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        revision = await db.get(MdObservationRevision, persisted.observation_revision_ids[0])
        assert revision is not None
        legacy_revision_key = _legacy_v1_revision_key(
            context,
            revision,
            fields_sha256=revision.fields_sha256,
            quality=ObservationQuality(revision.quality_status),
        )
        legacy_provenance = dict(revision.provenance_json)
        legacy_provenance["provider_available_at"] = _at(11).isoformat()
        await db.execute(
            update(MdObservationRevision)
            .where(MdObservationRevision.id == revision.id)
            .values(
                revision_key_sha256=legacy_revision_key,
                provenance_json=legacy_provenance,
            )
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        db.expire_all()

        rows = await store.read_observation_revisions(context, knowledge_cutoff=_at(13))

    assert len(rows) == 1
    assert rows[0].source_available_at is None
    assert rows[0].available_at == _at(12)


@pytest.mark.asyncio
async def test_store_uses_visibility_sequence_to_exclude_later_receipts_at_or_before_cutoff() -> (
    None
):
    """A frozen sequence excludes later seals even under a future time cutoff."""
    context = _context()
    event_at = _at(10)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        first = await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(14),
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(14),
                        fields={"close": "10.00"},
                    ),
                ),
            ),
            received_at=_at(14),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        # A historical request may name a future availability cutoff.  Freeze
        # its sequence now, before a later receipt is sealed at the old
        # representable timestamp.
        future_anchor = await store.resolve_visibility_anchor(knowledge_cutoff=_at(15))
        second = await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(14),
                source_revision="same-visible-at-v2",
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(14),
                        fields={"close": "11.00"},
                    ),
                ),
            ),
            received_at=_at(14),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        assert first.received_at == second.received_at
        first_anchor = MarketDataVisibilityAnchor(
            visible_at=first.received_at,
            max_visibility_sequence=1,
        )
        second_anchor = MarketDataVisibilityAnchor(
            visible_at=second.received_at,
            max_visibility_sequence=2,
        )
        at_first = await store.read_observation_revisions(
            context,
            knowledge_cutoff=first.received_at,
            visibility_anchor=first_anchor,
        )
        at_second = await store.read_observation_revisions(
            context,
            knowledge_cutoff=second.received_at,
            visibility_anchor=second_anchor,
        )
        at_future_anchor = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(15),
            visibility_anchor=future_anchor,
        )

    assert [
        (row.revision_number, row.fields["close"], row.visibility_sequence) for row in at_first
    ] == [(1, "10.00", 1)]
    assert [
        (row.revision_number, row.fields["close"], row.visibility_sequence) for row in at_second
    ] == [(2, "11.00", 2)]
    assert future_anchor == MarketDataVisibilityAnchor(
        visible_at=_at(15),
        max_visibility_sequence=1,
    )
    assert [
        (row.revision_number, row.fields["close"], row.visibility_sequence)
        for row in at_future_anchor
    ] == [(1, "10.00", 1)]


@pytest.mark.asyncio
async def test_store_fails_closed_on_series_hash_identity_collision() -> None:
    """A SHA collision or corruption can never silently merge economic series."""
    context = _context()
    identity = MarketDataStore.series_identity(context)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        db.add(
            MdDataSeries(
                id="tampered-series",
                dataset_id=DATASET_ID,
                canonical_id=CANONICAL_ID,
                data_kind="bars",
                frequency="1d",
                semantic_key_sha256=identity.semantic_key_sha256,
                semantic_identity_json={"tampered": True},
            )
        )
        await db.commit()

        with pytest.raises(MarketDataStoreError) as collision:
            await MarketDataStore(db).get_series(context)

    assert collision.value.code == "SERIES_SEMANTIC_COLLISION"


@pytest.mark.asyncio
async def test_calendar_reader_returns_typed_unknown_then_explicit_versioned_sessions() -> None:
    """Calendar coverage is known only from a persisted version and explicit window evidence."""
    context = _context()
    window = TimeWindow(start_at=_at(9), end_at=_at(16))

    async with async_session_maker() as db:
        store = MarketDataStore(db)
        unknown = await store.read_calendar(calendar_code="CN-SSE", window=window)

        snapshot_hash = _sha("calendar-cn-sse-2026-09")
        source_governance = _calendar_source_governance(manifest_hash=snapshot_hash)
        snapshot = MdCalendarSnapshot(
            id="calendar-cn-sse-2026-09",
            calendar_code="CN-SSE",
            calendar_version="2026.09",
            timezone_name="Asia/Shanghai",
            source_registry_id=PROVIDER_ID,
            source_governance_state=CALENDAR_SOURCE_GOVERNANCE_STATE_VERIFIED,
            source_governance_descriptor_sha256=str(source_governance["descriptor_hash"]),
            snapshot_sha256=snapshot_hash,
            definition_json={
                "manifest_hash": snapshot_hash,
                "source_governance": source_governance,
                "coverage_start_at": _at(9).isoformat(),
                "coverage_end_at": _at(16).isoformat(),
            },
            effective_from=date(2026, 9, 8),
            effective_to=date(2026, 9, 8),
        )
        db.add_all(
            [
                snapshot,
                MdCalendarEvent(
                    id="calendar-cn-sse-session-am",
                    calendar_snapshot_id=snapshot.id,
                    trading_date=date(2026, 9, 8),
                    event_type="session",
                    session_code="am",
                    is_trading_day=True,
                    event_start=_at(10),
                    event_end=_at(11),
                    event_payload_json={
                        "coverage": {"data_kind": "bars", "frequency": "1d"},
                        "open": "09:30",
                        "close": "11:30",
                    },
                    event_sha256=_sha("calendar-cn-sse-session-am"),
                ),
                MdCalendarEvent(
                    id="calendar-cn-sse-session-pm",
                    calendar_snapshot_id=snapshot.id,
                    trading_date=date(2026, 9, 8),
                    event_type="session",
                    session_code="pm",
                    is_trading_day=True,
                    event_start=_at(14),
                    event_end=_at(15),
                    event_payload_json={
                        "coverage": {"data_kind": "bars", "frequency": "1d"},
                        "open": "13:00",
                        "close": "15:00",
                    },
                    event_sha256=_sha("calendar-cn-sse-session-pm"),
                ),
                MdPublication(
                    entity_type=PUBLICATION_CALENDAR_SNAPSHOT,
                    entity_id=snapshot.id,
                    entity_sha256=snapshot.snapshot_sha256,
                    published_at=_at(8),
                    visibility_sequence=1,
                    created_at=_at(8),
                ),
            ]
        )
        await db.commit()

        known = await store.read_calendar_for_context(context)

    assert unknown.status is CalendarStatus.UNKNOWN
    assert unknown.reason == "CALENDAR_VERSION_NOT_FOUND"
    assert known.status is CalendarStatus.KNOWN
    assert known.calendar_version == "2026.09"
    assert [key.event_at.hour for key in known.event_keys] == [10, 14]


@pytest.mark.asyncio
async def test_stale_fetch_lease_owner_cannot_commit_or_publish_provider_facts() -> None:
    """A post-expiry owner rolls back staged facts before any visibility receipt exists."""
    context = _context()
    lease_key = _sha("stale-owner-provider-write")

    async with async_session_maker() as stale_db, async_session_maker() as current_db:
        await _seed_dataset_and_provider(stale_db)
        stale_leases = MarketDataFetchLeaseManager(
            stale_db,
            clock=lambda: _at(14),
            lease_ttl=timedelta(minutes=1),
        )
        stale_handle = await stale_leases.acquire(lease_key)
        assert stale_handle is not None

        current_leases = MarketDataFetchLeaseManager(
            current_db,
            clock=lambda: _at(15),
            lease_ttl=timedelta(minutes=1),
        )
        current_handle = await current_leases.acquire(lease_key)
        assert current_handle is not None

        stale_store = MarketDataStore(stale_db, clock=lambda: _at(15))
        with pytest.raises(MarketDataStoreError) as rejected:
            await stale_store.persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(14),
                    observations=(
                        _observation(
                            event_at=_at(10),
                            available_at=_at(14),
                            fields={"close": "10.00"},
                        ),
                    ),
                ),
                received_at=_at(15),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
                fetch_lease=stale_handle,
            )
        source_count = await stale_db.scalar(select(func.count()).select_from(MdSourceSnapshot))
        publication_count = await stale_db.scalar(select(func.count()).select_from(MdPublication))

    assert rejected.value.code == "FETCH_LEASE_FENCE_LOST"
    assert source_count == 0
    assert publication_count == 0


@pytest.mark.asyncio
async def test_store_closes_read_transaction_before_provider_io() -> None:
    """A real SQLAlchemy request session cannot carry local reads into an adapter."""
    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db)

        await db.scalar(select(DgProvider).where(DgProvider.provider_id == PROVIDER_ID))
        assert db.in_transaction()

        await store.close_transaction_before_provider_io()

        assert not db.in_transaction()


@pytest.mark.asyncio
async def test_fetch_lease_takeover_before_publication_keeps_committed_facts_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A handoff after fact commit cannot turn the old owner's receipt visible."""
    context = _context()
    lease_key = _sha("stale-owner-before-publication")

    async with async_session_maker() as stale_db, async_session_maker() as current_db:
        await _seed_dataset_and_provider(stale_db)
        stale_leases = MarketDataFetchLeaseManager(
            stale_db,
            clock=lambda: _at(14),
            lease_ttl=timedelta(minutes=1),
        )
        stale_handle = await stale_leases.acquire(lease_key)
        assert stale_handle is not None

        current_leases = MarketDataFetchLeaseManager(
            current_db,
            clock=lambda: _at(15),
            lease_ttl=timedelta(minutes=1),
        )
        stale_store = MarketDataStore(stale_db, clock=lambda: _at(14))
        original_publish = stale_store._publications.publish_staged
        current_handle = None

        async def take_over_before_publish(*args: object, **kwargs: object) -> datetime:
            nonlocal current_handle
            current_handle = await current_leases.acquire(lease_key)
            assert current_handle is not None
            return await original_publish(*args, **kwargs)

        monkeypatch.setattr(stale_store._publications, "publish_staged", take_over_before_publish)

        with pytest.raises(MarketDataStoreError) as rejected:
            await stale_store.persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(14),
                    observations=(
                        _observation(
                            event_at=_at(10),
                            available_at=_at(14),
                            fields={"close": "10.00"},
                        ),
                    ),
                ),
                received_at=_at(14),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
                fetch_lease=stale_handle,
            )

        # The pre-publish guard failure rolls its own publication transaction
        # back; the caller session is clean before it reads the hidden receipt.
        assert not stale_db.in_transaction()
        publication = await stale_db.scalar(select(MdPublication))
        source_count = await stale_db.scalar(select(func.count()).select_from(MdSourceSnapshot))

    assert rejected.value.code == "FETCH_LEASE_FENCE_LOST"
    assert current_handle is not None
    assert source_count == 1
    assert publication is not None
    assert publication.published_at is None
    assert publication.visibility_sequence is None


@pytest.mark.asyncio
async def test_stale_fenced_pending_receipt_stays_hidden_while_recovery_and_current_owner_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generic recovery skips old fenced evidence without starving safe receipts."""
    context = _context()
    lease_key = _sha("stale-fenced-pending-recovery")

    async with async_session_maker() as stale_db, async_session_maker() as current_db:
        await _seed_dataset_and_provider(stale_db)
        stale_handle = await MarketDataFetchLeaseManager(
            stale_db,
            clock=lambda: _at(14),
            lease_ttl=timedelta(minutes=1),
        ).acquire(lease_key)
        assert stale_handle is not None

        stale_store = MarketDataStore(stale_db, clock=lambda: _at(14))

        async def interrupt_publication(*_args: object, **_kwargs: object) -> datetime:
            raise MarketDataPublicationError("PUBLICATION_TEST_INTERRUPTED")

        monkeypatch.setattr(stale_store._publications, "publish_staged", interrupt_publication)
        with pytest.raises(MarketDataStoreError) as stale_interrupted:
            await stale_store.persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(14),
                    observations=(
                        _observation(
                            event_at=_at(10),
                            available_at=_at(14),
                            fields={"close": "10.00"},
                        ),
                    ),
                ),
                received_at=_at(14),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
                fetch_lease=stale_handle,
            )
        stale_snapshot = await stale_db.scalar(select(MdSourceSnapshot))
        stale_receipt = await stale_db.scalar(select(MdPublication))
        assert stale_snapshot is not None
        assert stale_receipt is not None
        stale_snapshot_id = stale_snapshot.id
        stale_binding_key = stale_snapshot.fetch_lease_key_sha256
        stale_binding_fence = stale_snapshot.fetch_lease_fence_token
        stale_receipt_id = stale_receipt.id
        stale_receipt_entity_id = stale_receipt.entity_id
        await stale_db.rollback()

        current_handle = await MarketDataFetchLeaseManager(
            current_db,
            clock=lambda: _at(15),
            lease_ttl=timedelta(minutes=1),
        ).acquire(lease_key)
        assert current_handle is not None
        assert current_handle.fence_token == stale_handle.fence_token + 1

        async def forged_noop_guard() -> None:
            return None

        # A public caller cannot bypass the real database-owner predicate by
        # presenting the old generation plus an arbitrary callback. The
        # publication manager performs its own conditional fence renewal in
        # this transaction before it considers the receipt binding.
        with pytest.raises(MarketDataFetchLeaseError) as direct_guard_rejected:
            await MarketDataPublicationManager(
                stale_db,
                clock=lambda: _at(15),
                fetch_lease_clock=lambda: _at(15),
            ).publish_staged(
                (stale_receipt_id,),
                fetch_lease=replace(stale_handle, owner_token="forged-owner-token"),
                pre_publish_guard=forged_noop_guard,
            )

        # Leave a separate non-fenced source receipt pending. Recovery must
        # publish it even though the older fenced receipt is permanently
        # excluded until an owner-coordinated retry can prove its fence.
        ordinary_store = MarketDataStore(current_db, clock=lambda: _at(15))
        monkeypatch.setattr(ordinary_store._publications, "publish_staged", interrupt_publication)
        with pytest.raises(MarketDataStoreError) as ordinary_interrupted:
            await ordinary_store.persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(15),
                    source_revision="ordinary-pending-v2",
                    observations=(
                        _observation(
                            event_at=_at(10),
                            available_at=_at(15),
                            fields={"close": "11.00"},
                        ),
                    ),
                ),
                received_at=_at(15),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        ordinary_snapshot = await current_db.scalar(
            select(MdSourceSnapshot).where(MdSourceSnapshot.fetch_lease_key_sha256.is_(None))
        )
        assert ordinary_snapshot is not None
        ordinary_receipt = await current_db.scalar(
            select(MdPublication).where(MdPublication.entity_id == ordinary_snapshot.id)
        )
        assert ordinary_receipt is not None
        ordinary_receipt_id = ordinary_receipt.id
        await current_db.rollback()

        recovered_ids = await MarketDataPublicationManager(
            stale_db,
            clock=lambda: _at(15),
        ).recover_pending()
        stale_receipt_after_recovery = await stale_db.scalar(
            select(MdPublication)
            .where(MdPublication.id == stale_receipt_id)
            .execution_options(populate_existing=True)
        )
        assert stale_receipt_after_recovery is not None
        stale_receipt_visible_after_recovery = stale_receipt_after_recovery.published_at
        stale_receipt_sequence_after_recovery = stale_receipt_after_recovery.visibility_sequence

        current_store = MarketDataStore(current_db, clock=lambda: _at(15))
        current_persisted = await current_store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(15),
                source_revision="current-owner-v3",
                observations=(
                    _observation(
                        event_at=_at(10),
                        available_at=_at(15),
                        fields={"close": "12.00"},
                    ),
                ),
            ),
            received_at=_at(15),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            fetch_lease=current_handle,
        )
        current_snapshot = await current_db.get(
            MdSourceSnapshot,
            current_persisted.source_snapshot_id,
        )
        current_receipt = await current_db.scalar(
            select(MdPublication).where(
                MdPublication.entity_id == current_persisted.source_snapshot_id
            )
        )
        assert current_snapshot is not None
        assert current_receipt is not None
        current_binding_key = current_snapshot.fetch_lease_key_sha256
        current_binding_fence = current_snapshot.fetch_lease_fence_token
        current_receipt_visible = current_receipt.published_at
        current_receipt_sequence = current_receipt.visibility_sequence

    assert stale_interrupted.value.code == "OBSERVATION_PUBLICATION_FAILED"
    assert ordinary_interrupted.value.code == "OBSERVATION_PUBLICATION_FAILED"
    assert direct_guard_rejected.value.code == "FETCH_LEASE_FENCE_LOST"
    assert stale_binding_key == lease_key
    assert stale_binding_fence == stale_handle.fence_token
    assert stale_snapshot_id == stale_receipt_entity_id
    assert stale_receipt_visible_after_recovery is None
    assert stale_receipt_sequence_after_recovery is None
    assert ordinary_receipt_id in recovered_ids
    assert stale_receipt_id not in recovered_ids
    assert current_binding_key == lease_key
    assert current_binding_fence == current_handle.fence_token
    assert current_receipt_visible is not None
    assert current_receipt_sequence is not None


@pytest.mark.asyncio
async def test_store_persists_normally_when_no_fetch_lease_is_supplied() -> None:
    """Existing controlled import paths remain unchanged when no lease is requested."""
    context = _context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        persisted = await MarketDataStore(db, clock=lambda: _at(14)).persist_provider_result(
            context,
            _result(
                retrieved_at=_at(14),
                observations=(
                    _observation(
                        event_at=_at(10),
                        available_at=_at(14),
                        fields={"close": "10.00"},
                    ),
                ),
            ),
            received_at=_at(14),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        source_count = await db.scalar(select(func.count()).select_from(MdSourceSnapshot))
        publication_count = await db.scalar(select(func.count()).select_from(MdPublication))

    assert persisted.observation_revision_ids
    assert source_count == 1
    assert publication_count == 1
