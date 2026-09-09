"""Offline behavioral contracts for the scheduled CFFEX settlement candidate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO

import pytest
from sqlalchemy import func, select

import app.services.market_data.cffex_settlement_collector as collector_module
from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry
from app.models.data_governance import DgDataset, DgProvider
from app.models.market_data_platform import MdObservationRevision, MdPublication, MdSourceSnapshot
from app.schemas.asset_research import FuturesIdentityDetails, InstrumentIdentity
from app.schemas.market_data_platform import MarketDataQueryRequest, ResolvedMarketDataQuery
from app.services.market_data.access import MarketDataSourceAuthorization
from app.services.market_data.catalog import DatasetStorageResolution
from app.services.market_data.cffex_settlement_collector import (
    AkShareCffexSettlementSource,
    CffexSettlementCollectionTarget,
    CffexSettlementCollector,
    CffexSettlementCollectorError,
    CffexSettlementCollectorPartialPublishError,
    CffexSettlementSourceBatch,
)
from app.services.market_data.coverage import QueryIdentity
from app.services.market_data.identity import ResolvedMarketDataIdentity
from app.services.market_data.publication import MarketDataPublicationError
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.store import MarketDataStore, MarketDataStoreError
from scripts.collect_iteration197_cffex_settlement import main as collector_command_main

UTC = timezone.utc
TRADING_DATE = date(2026, 9, 8)
SOURCE_RETRIEVED_AT = datetime(2026, 9, 8, 15, tzinfo=UTC)
LOCAL_RECEIVED_AT = datetime(2026, 9, 8, 16, tzinfo=UTC)
DATASET_ID = "dataset-cffex-settlement"
DATASET_CODE = "market.settlement"
PROVIDER_ID = "akshare"
SOURCE_POLICY_ID = "market-cffex-settlement-batch-v1"


class _FakeCffexSource:
    """Offline source seam that records exactly how often the collector calls it."""

    def __init__(self, rows: list[Mapping[str, object]]) -> None:
        self._rows = rows
        self.calls: list[date] = []

    async def fetch_batch(self, *, trading_date: date) -> CffexSettlementSourceBatch:
        self.calls.append(trading_date)
        return CffexSettlementSourceBatch(
            provider_id=PROVIDER_ID,
            source_revision="fixture-cffex-v1",
            retrieved_at=SOURCE_RETRIEVED_AT,
            raw_payload={
                "collector_request": {
                    "market": "CFFEX",
                    "trading_date": trading_date.isoformat(),
                },
                "source_route": {
                    "endpoint": "futures_hist_daily_cffex",
                    "call_kwargs": {"date": trading_date.strftime("%Y%m%d")},
                },
                "response_rows": self._rows,
            },
        )


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _daily_window() -> tuple[datetime, datetime]:
    start = datetime.combine(TRADING_DATE, datetime.min.time(), tzinfo=UTC)
    return start, start + timedelta(days=1)


def _identity(*, symbol: str, canonical_id: str) -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="futures",
        identity_level="CONTRACT",
        canonical_id=canonical_id,
        display_symbol=symbol,
        name=f"CFFEX {symbol}",
        venue="CFFEX",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="EXCHANGE_SYMBOL",
        identifier_value=symbol,
        product_type="INDEX_FUTURE",
        metadata_version="cffex-contract-v1",
        details=FuturesIdentityDetails(
            product_code=symbol[:-4],
            contract_month=symbol[-4:],
            underlying_id=f"underlying:{symbol[:-4]}",
            expiry_at=datetime(2026, 9, 18, tzinfo=UTC),
            contract_multiplier=Decimal("300"),
            trading_calendar_id="CFFEX",
        ),
    )


def _context(*, symbol: str, canonical_id: str) -> ResolvedMarketDataQueryContext:
    start, end = _daily_window()
    request = MarketDataQueryRequest.model_validate(
        {
            "identity": {"canonical_id": canonical_id},
            "family_id": "futures.settlement",
            "family_contract_version": "market-data-family-v1",
            "dataset_code": DATASET_CODE,
            "data_kind": "reference_series",
            "frequency": "1d",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "required_fields": ["settle", "previous_settle", "open_interest"],
            "adjustment": "unadjusted",
            "price_basis": "settle",
            "currency": "CNY",
            "unit": "contract",
            "source_policy_id": SOURCE_POLICY_ID,
            "purpose": "display",
        }
    )
    query = ResolvedMarketDataQuery.from_request(
        request,
        canonical_id=canonical_id,
        dataset_code=DATASET_CODE,
        instrument_metadata_version="cffex-contract-v1",
    )
    identity = _identity(symbol=symbol, canonical_id=canonical_id)
    resolved_identity = ResolvedMarketDataIdentity(
        instrument_id=f"instrument:{symbol}",
        canonical_id=canonical_id,
        asset_type="futures",
        metadata_version="cffex-contract-v1",
        venue="CFFEX",
        identity=identity,
        valid_from=datetime(2020, 1, 1, tzinfo=UTC),
        valid_to=None,
        known_at=datetime(2020, 1, 1, tzinfo=UTC),
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
            canonical_id=canonical_id,
            asset_type="futures",
            instrument_metadata_version="cffex-contract-v1",
            data_kind="reference_series",
            market="CFFEX",
            frequency="1d",
            source_policy_id=SOURCE_POLICY_ID,
            adjustment="unadjusted",
            price_basis="settle",
            currency="CNY",
            unit="contract",
        ),
    )


def _source_authorization(*, purpose: str = "display") -> MarketDataSourceAuthorization:
    values: dict[str, object] = {
        "source_registry_id": PROVIDER_ID,
        "registry_updated_at": LOCAL_RECEIVED_AT.isoformat(),
        "asset_type": "futures",
        "market": "CFFEX",
        "purpose": purpose,
        "license_status": "APPROVED",
        "allowed_uses": ("DISPLAY",),
        "jurisdictions": ("CFFEX",),
        "effective_from": datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        "effective_to": None,
        "retention_policy": "MARKET-DATA-V1",
        "retention_expires_at": None,
        "redistribution_policy": "NO_REDISTRIBUTION",
        "principal_scope": "principal-v1:cffex-offline-test",
        "tenant_scope": "default",
        "entitlement_revision": _sha("cffex-offline-entitlement"),
        "decision": "ALLOW",
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


def _target(symbol: str) -> CffexSettlementCollectionTarget:
    canonical_id = f"instrument:futures:CFFEX:{symbol}"
    return CffexSettlementCollectionTarget(
        context=_context(symbol=symbol, canonical_id=canonical_id),
        source_authorization=_source_authorization(),
    )


async def _seed_control_plane(db) -> None:
    db.add_all(
        [
            DgDataset(
                id=DATASET_ID,
                dataset_code=DATASET_CODE,
                display_name="CFFEX daily settlement",
                domain="market",
                canonical_schema={
                    "event_at": "timestamp",
                    "settle": "decimal",
                    "previous_settle": "decimal",
                    "open_interest": "decimal",
                },
                primary_key=["canonical_id", "event_at"],
            ),
            DgProvider(
                id="provider-akshare-cffex",
                provider_id=PROVIDER_ID,
                name="AkShare CFFEX",
                category="market",
                is_active=True,
            ),
            AssetDataSourceRegistry(
                source_id=PROVIDER_ID,
                asset_types=["futures"],
                jurisdictions=["CFFEX"],
                license_status="APPROVED",
                allowed_uses=["DISPLAY"],
                redistribution_policy="NO_REDISTRIBUTION",
                derived_data_policy="ALLOWED",
                retention_policy="market-data-v1",
                effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                effective_to=None,
                retention_expires_at=None,
                enabled=True,
                updated_at=LOCAL_RECEIVED_AT,
            ),
        ]
    )
    await db.commit()


def _row(
    symbol: str,
    *,
    settle: object = "3500.5",
    previous_settle: object = "3490.0",
    open_interest: object = "10000",
) -> dict[str, object]:
    return {
        "MARKET": "CFFEX",
        "SYMBOL": symbol,
        "TRADE_DATE": TRADING_DATE.isoformat(),
        "SETTLE_PRICE": settle,
        "PREV_SETTLE": previous_settle,
        "OPEN_INTEREST": open_interest,
    }


def _actual_akshare_row(symbol: str) -> dict[str, object]:
    """Represent the reviewed ``futures_hist_daily_cffex`` record shape."""
    return {
        "symbol": symbol,
        "date": TRADING_DATE.isoformat(),
        "settle": "3500.5",
        "pre_settle": "3490.0",
        "open_interest": "10000",
        "volume": "12000",
    }


async def _counts(db) -> tuple[int, int, int]:
    return (
        int(await db.scalar(select(func.count()).select_from(MdSourceSnapshot)) or 0),
        int(await db.scalar(select(func.count()).select_from(MdObservationRevision)) or 0),
        int(await db.scalar(select(func.count()).select_from(MdPublication)) or 0),
    )


def test_operator_command_is_network_inert_without_live_switch() -> None:
    """An ordinary local shell invocation cannot trigger provider I/O."""
    output = StringIO()

    exit_code = collector_command_main([], stream=output)

    assert exit_code == 0
    assert json.loads(output.getvalue()) == {
        "status": "NOT_RUN",
        "code": "CFFEX_SETTLEMENT_LIVE_CONFIRMATION_REQUIRED",
        "network_called": False,
        "database_written": False,
    }


@pytest.mark.asyncio
async def test_akshare_source_uses_the_cffex_specific_endpoint_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adapter's only source call is the reviewed CFFEX-specific route."""
    source_call_dates: list[str] = []

    class _Response:
        def to_dict(self, *, orient: str) -> list[dict[str, object]]:
            assert orient == "records"
            return [_actual_akshare_row("IF2609")]

    def fake_cffex_endpoint(*, date: str) -> _Response:
        source_call_dates.append(date)
        return _Response()

    monkeypatch.setattr(collector_module, "_resolve_akshare_callable", lambda: fake_cffex_endpoint)

    batch = await AkShareCffexSettlementSource().fetch_batch(trading_date=TRADING_DATE)

    assert source_call_dates == ["20260908"]
    assert batch.raw_payload["source_route"] == {
        "endpoint": "futures_hist_daily_cffex",
        "call_kwargs": {"date": "20260908"},
    }
    assert batch.raw_payload["response_rows"] == [_actual_akshare_row("IF2609")]


@pytest.mark.asyncio
async def test_maps_one_cffex_batch_once_publishes_then_reads_locally() -> None:
    """One explicit date maps legacy fields and later rereads no source request."""
    source = _FakeCffexSource([_row("IF2609")])
    target = _target("IF2609")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        collector = CffexSettlementCollector(
            store=store, source=source, clock=lambda: LOCAL_RECEIVED_AT
        )
        report = await collector.collect(trading_date=TRADING_DATE, targets=(target,))

        rows = await store.read_observation_revisions(
            target.context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        snapshot = await db.get(MdSourceSnapshot, report.persisted_fetches[0].source_snapshot_id)

    assert source.calls == [TRADING_DATE]
    assert report.published_target_count == 1
    assert report.source_row_count == 1
    assert report.quarantined_symbols == ()
    assert len(rows) == 1
    assert dict(rows[0].fields) == {
        "settle": "3500.5",
        "previous_settle": "3490.0",
        "open_interest": "10000",
    }
    assert rows[0].available_at == LOCAL_RECEIVED_AT
    assert snapshot is not None
    assert snapshot.source_observed_at is not None
    assert snapshot.source_observed_at.replace(tzinfo=UTC) == SOURCE_RETRIEVED_AT
    assert snapshot.provenance_json["provider_retrieved_at"] == SOURCE_RETRIEVED_AT.isoformat()
    assert snapshot.payload_manifest_json["raw_payload"]["source_batch"]["collector_request"] == {
        "market": "CFFEX",
        "trading_date": TRADING_DATE.isoformat(),
    }


@pytest.mark.asyncio
async def test_actual_akshare_rows_without_market_map_pre_settle() -> None:
    """The reviewed lower-case CFFEX response needs no duplicated market column."""
    source = _FakeCffexSource([_actual_akshare_row("IF2609")])
    target = _target("IF2609")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        await CffexSettlementCollector(
            store=store,
            source=source,
            clock=lambda: LOCAL_RECEIVED_AT,
        ).collect(trading_date=TRADING_DATE, targets=(target,))
        rows = await store.read_observation_revisions(
            target.context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )

    assert source.calls == [TRADING_DATE]
    assert len(rows) == 1
    assert dict(rows[0].fields) == {
        "settle": "3500.5",
        "previous_settle": "3490.0",
        "open_interest": "10000",
    }


@pytest.mark.asyncio
async def test_one_snapshot_maps_multiple_frozen_contracts_and_quarantines_unknown() -> None:
    """A broad response has one source call and cannot publish an unmapped contract."""
    source = _FakeCffexSource([_row("IF2609"), _row("IH2609"), _row("IM2609")])
    targets = (_target("IF2609"), _target("IH2609"))

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        report = await CffexSettlementCollector(
            store=store,
            source=source,
            clock=lambda: LOCAL_RECEIVED_AT,
        ).collect(trading_date=TRADING_DATE, targets=targets)
        snapshots = list((await db.execute(select(MdSourceSnapshot))).scalars())

    assert source.calls == [TRADING_DATE]
    assert report.published_target_count == 2
    assert report.quarantined_symbols == ("IM2609",)
    assert len(snapshots) == 2
    source_batch_hashes = {
        snapshot.payload_manifest_json["raw_payload"]["collector"]["source_batch_sha256"]
        for snapshot in snapshots
    }
    assert source_batch_hashes == {report.source_batch_sha256}
    assert {snapshot.provenance_json["provider_retrieved_at"] for snapshot in snapshots} == {
        SOURCE_RETRIEVED_AT.isoformat()
    }


@pytest.mark.asyncio
async def test_later_target_write_reports_the_exact_published_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sequential Store publications never masquerade as an atomic batch result."""
    source = _FakeCffexSource([_actual_akshare_row("IF2609"), _actual_akshare_row("IH2609")])
    targets = (_target("IF2609"), _target("IH2609"))

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        original_persist = store.persist_provider_result
        persist_attempts = 0

        async def interrupt_second_target(*args: object, **kwargs: object):
            nonlocal persist_attempts
            persist_attempts += 1
            if persist_attempts == 2:
                raise MarketDataStoreError("OBSERVATION_WRITE_FAILED")
            return await original_persist(*args, **kwargs)

        monkeypatch.setattr(store, "persist_provider_result", interrupt_second_target)
        with pytest.raises(CffexSettlementCollectorPartialPublishError) as partial:
            await CffexSettlementCollector(
                store=store,
                source=source,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=targets)

        prefix_rows = await store.read_observation_revisions(
            targets[0].context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        counts = await _counts(db)

    assert source.calls == [TRADING_DATE]
    assert persist_attempts == 2
    assert partial.value.code == "CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED"
    assert len(partial.value.persisted_fetches) == 1
    assert len(prefix_rows) == 1
    assert counts == (1, 1, 1)


@pytest.mark.asyncio
async def test_duplicate_or_missing_metric_rejects_whole_batch_before_source_receipt() -> None:
    """A corrupted source response never writes a partial canonical receipt."""
    target = _target("IF2609")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        duplicate_source = _FakeCffexSource([_row("IF2609"), _row("IF2609")])
        duplicate_collector = CffexSettlementCollector(
            store=MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT),
            source=duplicate_source,
            clock=lambda: LOCAL_RECEIVED_AT,
        )
        with pytest.raises(CffexSettlementCollectorError, match="CFFEX_SETTLEMENT_ROW_DUPLICATE"):
            await duplicate_collector.collect(trading_date=TRADING_DATE, targets=(target,))
        duplicate_counts = await _counts(db)

        missing_row = _row("IF2609")
        del missing_row["PREV_SETTLE"]
        missing_source = _FakeCffexSource([missing_row])
        missing_collector = CffexSettlementCollector(
            store=MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT),
            source=missing_source,
            clock=lambda: LOCAL_RECEIVED_AT,
        )
        with pytest.raises(
            CffexSettlementCollectorError,
            match="CFFEX_SETTLEMENT_ROW_REQUIRED_FIELD_MISSING",
        ):
            await missing_collector.collect(trading_date=TRADING_DATE, targets=(target,))
        missing_counts = await _counts(db)

    assert duplicate_source.calls == [TRADING_DATE]
    assert missing_source.calls == [TRADING_DATE]
    assert duplicate_counts == (0, 0, 0)
    assert missing_counts == (0, 0, 0)


@pytest.mark.asyncio
async def test_supplied_non_cffex_market_rejects_before_any_source_receipt() -> None:
    """An optional row market cannot silently widen the CFFEX-scoped source route."""
    non_cffex_row = _actual_akshare_row("IF2609")
    non_cffex_row["market"] = "SHFE"
    source = _FakeCffexSource([non_cffex_row])
    target = _target("IF2609")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        collector = CffexSettlementCollector(
            store=MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT),
            source=source,
            clock=lambda: LOCAL_RECEIVED_AT,
        )
        with pytest.raises(
            CffexSettlementCollectorError, match="CFFEX_SETTLEMENT_ROW_MARKET_INVALID"
        ):
            await collector.collect(trading_date=TRADING_DATE, targets=(target,))
        counts = await _counts(db)

    assert source.calls == [TRADING_DATE]
    assert counts == (0, 0, 0)


@pytest.mark.asyncio
async def test_unbound_family_never_reaches_the_cffex_source() -> None:
    """The scheduled candidate keeps the same explicit family identity as its receipt."""
    target = _target("IF2609")
    unbound_query = target.context.query.model_copy(
        update={"family_id": None, "family_contract_version": None}
    )
    unbound_target = CffexSettlementCollectionTarget(
        context=replace(target.context, query=unbound_query),
        source_authorization=target.source_authorization,
    )
    source = _FakeCffexSource([_actual_akshare_row("IF2609")])

    async with async_session_maker() as db:
        collector = CffexSettlementCollector(
            store=MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT),
            source=source,
            clock=lambda: LOCAL_RECEIVED_AT,
        )
        with pytest.raises(
            CffexSettlementCollectorError, match="CFFEX_SETTLEMENT_TARGET_CONTRACT_INVALID"
        ):
            await collector.collect(trading_date=TRADING_DATE, targets=(unbound_target,))

    assert source.calls == []


@pytest.mark.asyncio
async def test_source_authorization_purpose_must_match_before_provider_io() -> None:
    """A research grant cannot fetch into a frozen display query's receipt."""
    target = _target("IF2609")
    mismatched_target = CffexSettlementCollectionTarget(
        context=target.context,
        source_authorization=_source_authorization(purpose="research"),
    )
    source = _FakeCffexSource([_actual_akshare_row("IF2609")])

    async with async_session_maker() as db:
        collector = CffexSettlementCollector(
            store=MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT),
            source=source,
            clock=lambda: LOCAL_RECEIVED_AT,
        )
        with pytest.raises(
            CffexSettlementCollectorError,
            match="CFFEX_SETTLEMENT_TARGET_AUTHORIZATION_CONTEXT_MISMATCH",
        ):
            await collector.collect(trading_date=TRADING_DATE, targets=(mismatched_target,))

    assert source.calls == []


@pytest.mark.asyncio
async def test_pending_publication_stays_invisible_until_a_later_local_read() -> None:
    """The collector never exposes staged data when publication does not seal it."""
    source = _FakeCffexSource([_row("IF2609")])
    target = _target("IF2609")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)

        async def interrupt_publication(*_args: object, **_kwargs: object) -> datetime:
            raise MarketDataPublicationError("PUBLICATION_TEST_INTERRUPTED")

        store._publications.publish_staged = interrupt_publication  # type: ignore[method-assign]
        with pytest.raises(MarketDataStoreError, match="OBSERVATION_PUBLICATION_FAILED"):
            await CffexSettlementCollector(
                store=store,
                source=source,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=(target,))

        invisible_rows = await store.read_observation_revisions(
            target.context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        pending_publications = await db.scalar(
            select(func.count())
            .select_from(MdPublication)
            .where(MdPublication.published_at.is_(None))
        )

    assert source.calls == [TRADING_DATE]
    assert invisible_rows == ()
    assert pending_publications == 1
