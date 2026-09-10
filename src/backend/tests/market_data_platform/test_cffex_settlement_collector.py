"""Offline behavioral contracts for the scheduled CFFEX settlement candidate."""

from __future__ import annotations

import asyncio
import builtins
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
from types import MappingProxyType

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
    CffexSettlementCollectorFetchLeaseReleaseError,
    CffexSettlementCollectorPartialPublishCancelledError,
    CffexSettlementCollectorPartialPublishError,
    CffexSettlementSourceBatch,
    CffexSettlementSourceDescriptor,
    CffexSettlementSourceRegistration,
)
from app.services.market_data.coverage import QueryIdentity
from app.services.market_data.fetch_lease import MarketDataFetchLeaseError
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
TEST_SOURCE_DESCRIPTOR_ID = "fixture-cffex-settlement-source-v1"
TEST_SOURCE_ORIGIN = "https://fixtures.example"
TEST_SOURCE_CERTIFICATE_SHA256 = "a" * 64
_TEST_ACTIVE_SOURCE: object | None = None


class _FakeCffexSource:
    """Offline source seam that records exactly how often the collector calls it."""

    def __init__(
        self,
        rows: list[Mapping[str, object]],
        *,
        payload_mutator: Callable[[dict[str, object]], None] | None = None,
        source_revision: str = "fixture-cffex-v1",
    ) -> None:
        self._rows = rows
        self._payload_mutator = payload_mutator
        self._source_revision = source_revision
        self.calls: list[date] = []

    async def fetch_batch(self, *, trading_date: date) -> CffexSettlementSourceBatch:
        self.calls.append(trading_date)
        raw_payload: dict[str, object] = {
            "collector_request": {
                "market": "CFFEX",
                "trading_date": trading_date.isoformat(),
            },
            "source_route": {
                "endpoint": "futures_hist_daily_cffex",
                "origin": TEST_SOURCE_ORIGIN,
                "call_kwargs": {"date": trading_date.strftime("%Y%m%d")},
            },
            "transport_evidence": {
                "contract_version": "cffex-settlement-transport-evidence-v1",
                "scheme": "https",
                "origin": TEST_SOURCE_ORIGIN,
                "tls_verified": True,
                "certificate_policy": "pinned-peer-certificate-sha256-v1",
                "peer_certificate_sha256": TEST_SOURCE_CERTIFICATE_SHA256,
            },
            "response_rows": self._rows,
        }
        if self._payload_mutator is not None:
            self._payload_mutator(raw_payload)
        return CffexSettlementSourceBatch(
            provider_id=PROVIDER_ID,
            source_revision=self._source_revision,
            retrieved_at=SOURCE_RETRIEVED_AT,
            raw_payload=raw_payload,
        )


def _fixture_source_factory() -> object:
    if _TEST_ACTIVE_SOURCE is None:
        raise RuntimeError("test source is not configured")
    return _TEST_ACTIVE_SOURCE


@pytest.fixture(autouse=True)
def _install_reviewed_fixture_source(monkeypatch: pytest.MonkeyPatch):
    """Keep tests on the same static source-registration boundary as production."""
    global _TEST_ACTIVE_SOURCE
    _TEST_ACTIVE_SOURCE = None
    descriptor = CffexSettlementSourceDescriptor(
        descriptor_id=TEST_SOURCE_DESCRIPTOR_ID,
        provider_id=PROVIDER_ID,
        source_revision="fixture-cffex-v1",
        endpoint="futures_hist_daily_cffex",
        origin=TEST_SOURCE_ORIGIN,
        certificate_policy="pinned-peer-certificate-sha256-v1",
        peer_certificate_sha256=TEST_SOURCE_CERTIFICATE_SHA256,
    )
    monkeypatch.setattr(
        collector_module,
        "CFFEX_SETTLEMENT_REVIEWED_SOURCE_REGISTRY",
        MappingProxyType(
            {
                TEST_SOURCE_DESCRIPTOR_ID: CffexSettlementSourceRegistration(
                    descriptor=descriptor,
                    source_factory=_fixture_source_factory,
                )
            }
        ),
    )
    yield
    _TEST_ACTIVE_SOURCE = None


def _collector(
    *,
    store: MarketDataStore,
    source: object,
    clock: Callable[[], datetime],
) -> CffexSettlementCollector:
    global _TEST_ACTIVE_SOURCE
    _TEST_ACTIVE_SOURCE = source
    return CffexSettlementCollector(
        store=store,
        source_descriptor_id=TEST_SOURCE_DESCRIPTOR_ID,
        clock=clock,
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
            family_id="futures.settlement",
            family_contract_version="market-data-family-v1",
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
async def test_akshare_source_refuses_before_import_or_endpoint_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unauthenticated AkShare route cannot even resolve its import seam."""
    akshare_import_calls: list[str] = []
    resolver_calls: list[str] = []
    original_import = builtins.__import__

    def forbidden_akshare_import(module_name: str, *args: object, **kwargs: object) -> object:
        if module_name == "akshare" or module_name.startswith("akshare."):
            akshare_import_calls.append(module_name)
            raise AssertionError("AkShare import must remain unreachable")
        return original_import(module_name, *args, **kwargs)

    def forbidden_endpoint_resolver() -> object:
        resolver_calls.append("called")
        raise AssertionError("AkShare endpoint resolver must remain unreachable")

    monkeypatch.setattr(builtins, "__import__", forbidden_akshare_import)
    monkeypatch.setattr(
        collector_module,
        "_resolve_akshare_callable",
        forbidden_endpoint_resolver,
        raising=False,
    )

    with pytest.raises(CffexSettlementCollectorError) as rejected:
        await AkShareCffexSettlementSource().fetch_batch(trading_date=TRADING_DATE)

    assert rejected.value.code == "CFFEX_SETTLEMENT_SOURCE_TRANSPORT_UNAPPROVED"
    assert akshare_import_calls == []
    assert resolver_calls == []


def _transport_evidence(payload: dict[str, object]) -> dict[str, object]:
    evidence = payload["transport_evidence"]
    assert isinstance(evidence, dict)
    return evidence


def _source_route(payload: dict[str, object]) -> dict[str, object]:
    route = payload["source_route"]
    assert isinstance(route, dict)
    return route


def _remove_transport_evidence(payload: dict[str, object]) -> None:
    payload.pop("transport_evidence")


def _set_http_transport(payload: dict[str, object]) -> None:
    _transport_evidence(payload)["scheme"] = "http"


def _set_unverified_tls(payload: dict[str, object]) -> None:
    _transport_evidence(payload)["tls_verified"] = False


def _set_bad_certificate_digest(payload: dict[str, object]) -> None:
    _transport_evidence(payload)["peer_certificate_sha256"] = "A" * 64


def _set_mismatched_origin(payload: dict[str, object]) -> None:
    _source_route(payload)["origin"] = "https://other-fixture.example"


def _add_sensitive_transport_field(payload: dict[str, object]) -> None:
    _transport_evidence(payload)["authorization"] = "must-not-persist"


def _set_unreviewed_origin(payload: dict[str, object]) -> None:
    origin = "https://unreviewed.example"
    _source_route(payload)["origin"] = origin
    _transport_evidence(payload)["origin"] = origin


def _add_nested_row_token(payload: dict[str, object]) -> None:
    rows = payload["response_rows"]
    assert isinstance(rows, list)
    first_row = rows[0]
    assert isinstance(first_row, dict)
    first_row["metadata"] = {"access_token": "must-not-persist"}


def _add_nested_row_access_key(payload: dict[str, object]) -> None:
    rows = payload["response_rows"]
    assert isinstance(rows, list)
    first_row = rows[0]
    assert isinstance(first_row, dict)
    first_row["metadata"] = {"access_key": "must-not-persist"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload_mutator", "expected_code"),
    [
        (_remove_transport_evidence, "CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID"),
        (_set_http_transport, "CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID"),
        (_set_unverified_tls, "CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID"),
        (_set_bad_certificate_digest, "CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID"),
        (_set_mismatched_origin, "CFFEX_SETTLEMENT_SOURCE_DESCRIPTOR_MISMATCH"),
        (_set_unreviewed_origin, "CFFEX_SETTLEMENT_SOURCE_DESCRIPTOR_MISMATCH"),
        (_add_sensitive_transport_field, "CFFEX_SETTLEMENT_SOURCE_SENSITIVE_PAYLOAD_REJECTED"),
    ],
    ids=(
        "missing-evidence",
        "http-scheme",
        "tls-unverified",
        "invalid-certificate-digest",
        "route-origin-mismatch",
        "unreviewed-origin",
        "sensitive-extra-field",
    ),
)
async def test_invalid_transport_evidence_never_reaches_store(
    payload_mutator: Callable[[dict[str, object]], None],
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Future sources must produce minimal redacted HTTPS evidence before persistence."""
    source = _FakeCffexSource([_actual_akshare_row("IF2609")], payload_mutator=payload_mutator)
    target = _target("IF2609")
    persist_calls = 0

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)

        async def unexpected_persist(*args: object, **kwargs: object) -> object:
            nonlocal persist_calls
            persist_calls += 1
            raise AssertionError("invalid transport evidence must fail before Store persistence")

        monkeypatch.setattr(store, "persist_provider_result", unexpected_persist)
        with pytest.raises(CffexSettlementCollectorError) as rejected:
            await _collector(
                store=store,
                source=source,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=(target,))
        counts = await _counts(db)

    assert rejected.value.code == expected_code
    assert "must-not-persist" not in str(rejected.value)
    assert source.calls == [TRADING_DATE]
    assert persist_calls == 0
    assert counts == (0, 0, 0)


@pytest.mark.asyncio
async def test_empty_reviewed_source_registry_never_constructs_or_calls_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production-empty source registry fails before adapter construction or I/O."""
    source = _FakeCffexSource([_actual_akshare_row("IF2609")])
    target = _target("IF2609")
    persist_calls = 0
    monkeypatch.setattr(
        collector_module,
        "CFFEX_SETTLEMENT_REVIEWED_SOURCE_REGISTRY",
        MappingProxyType({}),
    )

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)

        async def unexpected_persist(*args: object, **kwargs: object) -> object:
            nonlocal persist_calls
            persist_calls += 1
            raise AssertionError("empty source registry must fail before Store persistence")

        monkeypatch.setattr(store, "persist_provider_result", unexpected_persist)
        with pytest.raises(CffexSettlementCollectorError) as rejected:
            await CffexSettlementCollector(
                store=store,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=(target,))
        counts = await _counts(db)

    assert rejected.value.code == "CFFEX_SETTLEMENT_SOURCE_DESCRIPTOR_UNAPPROVED"
    assert source.calls == []
    assert persist_calls == 0
    assert counts == (0, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload_mutator",
    [_add_nested_row_token, _add_nested_row_access_key],
    ids=("access-token", "access-key"),
)
async def test_nested_credential_shaped_source_row_never_reaches_store(
    payload_mutator: Callable[[dict[str, object]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw row evidence must reject nested credential-shaped keys without retaining them."""
    source = _FakeCffexSource(
        [_actual_akshare_row("IF2609")],
        payload_mutator=payload_mutator,
    )
    target = _target("IF2609")
    persist_calls = 0

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)

        async def unexpected_persist(*args: object, **kwargs: object) -> object:
            nonlocal persist_calls
            persist_calls += 1
            raise AssertionError("credential-shaped source row must fail before Store persistence")

        monkeypatch.setattr(store, "persist_provider_result", unexpected_persist)
        with pytest.raises(CffexSettlementCollectorError) as rejected:
            await _collector(
                store=store,
                source=source,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=(target,))
        counts = await _counts(db)

    assert rejected.value.code == "CFFEX_SETTLEMENT_SOURCE_SENSITIVE_PAYLOAD_REJECTED"
    assert "must-not-persist" not in str(rejected.value)
    assert source.calls == [TRADING_DATE]
    assert persist_calls == 0
    assert counts == (0, 0, 0)


@pytest.mark.asyncio
async def test_source_revision_must_match_the_reviewed_descriptor_before_store_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source cannot self-select a new revision while retaining a reviewed origin."""
    source = _FakeCffexSource(
        [_actual_akshare_row("IF2609")],
        source_revision="fixture-cffex-unreviewed-v2",
    )
    target = _target("IF2609")
    persist_calls = 0

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)

        async def unexpected_persist(*args: object, **kwargs: object) -> object:
            nonlocal persist_calls
            persist_calls += 1
            raise AssertionError("unreviewed source revision must fail before Store persistence")

        monkeypatch.setattr(store, "persist_provider_result", unexpected_persist)
        with pytest.raises(CffexSettlementCollectorError) as rejected:
            await _collector(
                store=store,
                source=source,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=(target,))
        counts = await _counts(db)

    assert rejected.value.code == "CFFEX_SETTLEMENT_SOURCE_DESCRIPTOR_MISMATCH"
    assert source.calls == [TRADING_DATE]
    assert persist_calls == 0
    assert counts == (0, 0, 0)


@pytest.mark.asyncio
async def test_maps_one_cffex_batch_once_publishes_then_reads_locally() -> None:
    """One explicit date maps legacy fields and later rereads no source request."""
    source = _FakeCffexSource([_row("IF2609")])
    target = _target("IF2609")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        collector = _collector(store=store, source=source, clock=lambda: LOCAL_RECEIVED_AT)
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
        await _collector(
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
        report = await _collector(
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
            await _collector(
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
async def test_cancellation_after_second_publication_reports_two_durable_prefixes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation after a sealed second receipt returns both durable receipt IDs."""
    source = _FakeCffexSource([_actual_akshare_row("IF2609"), _actual_akshare_row("IH2609")])
    targets = (_target("IF2609"), _target("IH2609"))
    second_persistence_is_durable = asyncio.Event()
    release_second_persistence_return = asyncio.Event()
    cancellation_wait_started = asyncio.Event()

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        original_persist = store.persist_provider_result
        original_await_after_cancellation = collector_module._await_persistence_after_cancellation
        persist_attempts = 0

        async def persist_then_block_before_second_return(*args: object, **kwargs: object):
            nonlocal persist_attempts
            persist_attempts += 1
            persisted = await original_persist(*args, **kwargs)
            if persist_attempts == 2:
                second_persistence_is_durable.set()
                await release_second_persistence_return.wait()
            return persisted

        async def observe_cancellation_wait(persistence_task: asyncio.Task[object]) -> object:
            cancellation_wait_started.set()
            return await original_await_after_cancellation(persistence_task)

        monkeypatch.setattr(store, "persist_provider_result", persist_then_block_before_second_return)
        monkeypatch.setattr(
            collector_module,
            "_await_persistence_after_cancellation",
            observe_cancellation_wait,
        )
        collection_task = asyncio.create_task(
            _collector(
                store=store,
                source=source,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=targets)
        )

        try:
            await asyncio.wait_for(second_persistence_is_durable.wait(), timeout=1.0)
            collection_task.cancel()
            await asyncio.wait_for(cancellation_wait_started.wait(), timeout=1.0)
            assert not collection_task.done()
            release_second_persistence_return.set()

            with pytest.raises(CffexSettlementCollectorPartialPublishCancelledError) as cancelled:
                await collection_task
        finally:
            release_second_persistence_return.set()
            if not collection_task.done():
                collection_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await collection_task

        first_rows = await store.read_observation_revisions(
            targets[0].context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        second_rows = await store.read_observation_revisions(
            targets[1].context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        counts = await _counts(db)

    assert source.calls == [TRADING_DATE]
    assert persist_attempts == 2
    assert isinstance(cancelled.value, asyncio.CancelledError)
    assert cancelled.value.code == "CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED_CANCELLED"
    assert len(cancelled.value.persisted_fetches) == 2
    assert len(first_rows) == 1
    assert len(second_rows) == 1
    assert counts == (2, 2, 2)


@pytest.mark.asyncio
async def test_cancellation_during_lease_release_reports_the_complete_durable_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The post-publication lease release cannot create an unreported cancel window."""
    source = _FakeCffexSource([_actual_akshare_row("IF2609")])
    target = _target("IF2609")
    release_started = asyncio.Event()
    release_can_complete = asyncio.Event()
    cancellation_wait_started = asyncio.Event()

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        lease_manager = store.fetch_lease_manager()
        original_release = lease_manager.release
        original_await_after_cancellation = collector_module._await_lease_release_after_cancellation

        async def release_after_blocking(*args: object, **kwargs: object) -> bool:
            release_started.set()
            await release_can_complete.wait()
            return await original_release(*args, **kwargs)

        async def observe_cancellation_wait(release_task: asyncio.Task[bool]) -> bool:
            cancellation_wait_started.set()
            return await original_await_after_cancellation(release_task)

        monkeypatch.setattr(store, "fetch_lease_manager", lambda: lease_manager)
        monkeypatch.setattr(lease_manager, "release", release_after_blocking)
        monkeypatch.setattr(
            collector_module,
            "_await_lease_release_after_cancellation",
            observe_cancellation_wait,
        )
        collection_task = asyncio.create_task(
            _collector(
                store=store,
                source=source,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=(target,))
        )

        try:
            await asyncio.wait_for(release_started.wait(), timeout=1.0)
            collection_task.cancel()
            await asyncio.wait_for(cancellation_wait_started.wait(), timeout=1.0)
            assert not collection_task.done()
            release_can_complete.set()

            with pytest.raises(CffexSettlementCollectorPartialPublishCancelledError) as cancelled:
                await collection_task
        finally:
            release_can_complete.set()
            if not collection_task.done():
                collection_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await collection_task

        rows = await store.read_observation_revisions(
            target.context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        counts = await _counts(db)

    assert source.calls == [TRADING_DATE]
    assert cancelled.value.code == "CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED_CANCELLED"
    assert len(cancelled.value.persisted_fetches) == 1
    assert len(rows) == 1
    assert counts == (1, 1, 1)


@pytest.mark.asyncio
async def test_cancellation_during_failed_lease_release_keeps_the_durable_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing release task cannot hide an already published series from cancellation."""
    source = _FakeCffexSource([_actual_akshare_row("IF2609")])
    target = _target("IF2609")
    release_started = asyncio.Event()
    release_can_fail = asyncio.Event()
    cancellation_wait_started = asyncio.Event()

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        lease_manager = store.fetch_lease_manager()
        original_await_after_cancellation = collector_module._await_lease_release_after_cancellation

        async def fail_release_after_cancellation(*_args: object, **_kwargs: object) -> bool:
            release_started.set()
            await release_can_fail.wait()
            raise MarketDataFetchLeaseError("FETCH_LEASE_RELEASE_CONFLICT")

        async def observe_cancellation_wait(release_task: asyncio.Task[bool]) -> bool:
            cancellation_wait_started.set()
            return await original_await_after_cancellation(release_task)

        monkeypatch.setattr(store, "fetch_lease_manager", lambda: lease_manager)
        monkeypatch.setattr(lease_manager, "release", fail_release_after_cancellation)
        monkeypatch.setattr(
            collector_module,
            "_await_lease_release_after_cancellation",
            observe_cancellation_wait,
        )
        collection_task = asyncio.create_task(
            _collector(
                store=store,
                source=source,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=(target,))
        )

        try:
            await asyncio.wait_for(release_started.wait(), timeout=1.0)
            collection_task.cancel()
            await asyncio.wait_for(cancellation_wait_started.wait(), timeout=1.0)
            assert not collection_task.done()
            release_can_fail.set()

            with pytest.raises(CffexSettlementCollectorPartialPublishCancelledError) as cancelled:
                await collection_task
        finally:
            release_can_fail.set()
            if not collection_task.done():
                collection_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await collection_task

        rows = await store.read_observation_revisions(
            target.context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        counts = await _counts(db)

    assert source.calls == [TRADING_DATE]
    assert cancelled.value.code == "CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED_CANCELLED"
    assert isinstance(cancelled.value.__cause__, MarketDataFetchLeaseError)
    assert len(cancelled.value.persisted_fetches) == 1
    assert len(rows) == 1
    assert counts == (1, 1, 1)


@pytest.mark.asyncio
async def test_cancellation_during_false_lease_release_keeps_the_durable_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A negative release result has the same cancellation reconciliation contract."""
    source = _FakeCffexSource([_actual_akshare_row("IF2609")])
    target = _target("IF2609")
    release_started = asyncio.Event()
    release_can_return = asyncio.Event()
    cancellation_wait_started = asyncio.Event()

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        lease_manager = store.fetch_lease_manager()
        original_await_after_cancellation = collector_module._await_lease_release_after_cancellation

        async def return_false_after_cancellation(*_args: object, **_kwargs: object) -> bool:
            release_started.set()
            await release_can_return.wait()
            return False

        async def observe_cancellation_wait(release_task: asyncio.Task[bool]) -> bool:
            cancellation_wait_started.set()
            return await original_await_after_cancellation(release_task)

        monkeypatch.setattr(store, "fetch_lease_manager", lambda: lease_manager)
        monkeypatch.setattr(lease_manager, "release", return_false_after_cancellation)
        monkeypatch.setattr(
            collector_module,
            "_await_lease_release_after_cancellation",
            observe_cancellation_wait,
        )
        collection_task = asyncio.create_task(
            _collector(
                store=store,
                source=source,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=(target,))
        )

        try:
            await asyncio.wait_for(release_started.wait(), timeout=1.0)
            collection_task.cancel()
            await asyncio.wait_for(cancellation_wait_started.wait(), timeout=1.0)
            assert not collection_task.done()
            release_can_return.set()

            with pytest.raises(CffexSettlementCollectorPartialPublishCancelledError) as cancelled:
                await collection_task
        finally:
            release_can_return.set()
            if not collection_task.done():
                collection_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await collection_task

        rows = await store.read_observation_revisions(
            target.context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        counts = await _counts(db)

    assert source.calls == [TRADING_DATE]
    assert cancelled.value.code == "CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED_CANCELLED"
    assert isinstance(cancelled.value.__cause__, CffexSettlementCollectorFetchLeaseReleaseError)
    assert len(cancelled.value.persisted_fetches) == 1
    assert len(rows) == 1
    assert counts == (1, 1, 1)


@pytest.mark.asyncio
async def test_failed_lease_release_exposes_the_complete_durable_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A normal return is impossible when a later lease-release error is unresolved."""
    source = _FakeCffexSource([_actual_akshare_row("IF2609")])
    target = _target("IF2609")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        lease_manager = store.fetch_lease_manager()

        async def fail_release(*_args: object, **_kwargs: object) -> bool:
            raise MarketDataFetchLeaseError("FETCH_LEASE_RELEASE_CONFLICT")

        monkeypatch.setattr(store, "fetch_lease_manager", lambda: lease_manager)
        monkeypatch.setattr(lease_manager, "release", fail_release)
        with pytest.raises(CffexSettlementCollectorFetchLeaseReleaseError) as failed:
            await _collector(
                store=store,
                source=source,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=(target,))

        rows = await store.read_observation_revisions(
            target.context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        counts = await _counts(db)

    assert source.calls == [TRADING_DATE]
    assert failed.value.code == "CFFEX_SETTLEMENT_FETCH_LEASE_RELEASE_FAILED"
    assert isinstance(failed.value.__cause__, MarketDataFetchLeaseError)
    assert len(failed.value.persisted_fetches) == 1
    assert len(rows) == 1
    assert counts == (1, 1, 1)


@pytest.mark.asyncio
async def test_false_lease_release_exposes_the_complete_durable_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A false release result is observable without erasing the durable receipt IDs."""
    source = _FakeCffexSource([_actual_akshare_row("IF2609")])
    target = _target("IF2609")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        lease_manager = store.fetch_lease_manager()

        async def return_false_release(*_args: object, **_kwargs: object) -> bool:
            return False

        monkeypatch.setattr(store, "fetch_lease_manager", lambda: lease_manager)
        monkeypatch.setattr(lease_manager, "release", return_false_release)
        with pytest.raises(CffexSettlementCollectorFetchLeaseReleaseError) as failed:
            await _collector(
                store=store,
                source=source,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=(target,))

        rows = await store.read_observation_revisions(
            target.context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        counts = await _counts(db)

    assert source.calls == [TRADING_DATE]
    assert failed.value.code == "CFFEX_SETTLEMENT_FETCH_LEASE_RELEASE_FAILED"
    assert failed.value.__cause__ is None
    assert len(failed.value.persisted_fetches) == 1
    assert len(rows) == 1
    assert counts == (1, 1, 1)


@pytest.mark.asyncio
async def test_generic_lease_release_failure_exposes_the_complete_durable_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Driver failures after publication remain reconcilable without leaking their type."""
    source = _FakeCffexSource([_actual_akshare_row("IF2609")])
    target = _target("IF2609")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        lease_manager = store.fetch_lease_manager()

        async def fail_release(*_args: object, **_kwargs: object) -> bool:
            raise RuntimeError("fixture release driver failure")

        monkeypatch.setattr(store, "fetch_lease_manager", lambda: lease_manager)
        monkeypatch.setattr(lease_manager, "release", fail_release)
        with pytest.raises(CffexSettlementCollectorFetchLeaseReleaseError) as failed:
            await _collector(
                store=store,
                source=source,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=(target,))

        rows = await store.read_observation_revisions(
            target.context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        counts = await _counts(db)

    assert source.calls == [TRADING_DATE]
    assert failed.value.code == "CFFEX_SETTLEMENT_FETCH_LEASE_RELEASE_FAILED"
    assert isinstance(failed.value.__cause__, RuntimeError)
    assert len(failed.value.persisted_fetches) == 1
    assert len(rows) == 1
    assert counts == (1, 1, 1)


@pytest.mark.asyncio
async def test_store_cancellation_then_failed_release_keeps_every_durable_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second cancellation during release cannot erase Store's first cancellation prefix."""
    source = _FakeCffexSource([_actual_akshare_row("IF2609"), _actual_akshare_row("IH2609")])
    targets = (_target("IF2609"), _target("IH2609"))
    second_persistence_is_durable = asyncio.Event()
    release_second_persistence_return = asyncio.Event()
    store_cancellation_wait_started = asyncio.Event()
    release_started = asyncio.Event()
    release_can_return = asyncio.Event()
    release_cancellation_wait_started = asyncio.Event()

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        lease_manager = store.fetch_lease_manager()
        original_persist = store.persist_provider_result
        original_await_persistence = collector_module._await_persistence_after_cancellation
        original_await_release = collector_module._await_lease_release_after_cancellation
        persist_attempts = 0

        async def persist_then_block_before_second_return(*args: object, **kwargs: object):
            nonlocal persist_attempts
            persist_attempts += 1
            persisted = await original_persist(*args, **kwargs)
            if persist_attempts == 2:
                second_persistence_is_durable.set()
                await release_second_persistence_return.wait()
            return persisted

        async def observe_store_cancellation_wait(
            persistence_task: asyncio.Task[object],
        ) -> object:
            store_cancellation_wait_started.set()
            return await original_await_persistence(persistence_task)

        async def return_false_after_second_cancellation(*_args: object, **_kwargs: object) -> bool:
            release_started.set()
            await release_can_return.wait()
            return False

        async def observe_release_cancellation_wait(release_task: asyncio.Task[bool]) -> bool:
            release_cancellation_wait_started.set()
            return await original_await_release(release_task)

        monkeypatch.setattr(store, "persist_provider_result", persist_then_block_before_second_return)
        monkeypatch.setattr(store, "fetch_lease_manager", lambda: lease_manager)
        monkeypatch.setattr(lease_manager, "release", return_false_after_second_cancellation)
        monkeypatch.setattr(
            collector_module,
            "_await_persistence_after_cancellation",
            observe_store_cancellation_wait,
        )
        monkeypatch.setattr(
            collector_module,
            "_await_lease_release_after_cancellation",
            observe_release_cancellation_wait,
        )
        collection_task = asyncio.create_task(
            _collector(
                store=store,
                source=source,
                clock=lambda: LOCAL_RECEIVED_AT,
            ).collect(trading_date=TRADING_DATE, targets=targets)
        )

        try:
            await asyncio.wait_for(second_persistence_is_durable.wait(), timeout=1.0)
            collection_task.cancel()
            await asyncio.wait_for(store_cancellation_wait_started.wait(), timeout=1.0)
            release_second_persistence_return.set()
            await asyncio.wait_for(release_started.wait(), timeout=1.0)
            collection_task.cancel()
            await asyncio.wait_for(release_cancellation_wait_started.wait(), timeout=1.0)
            assert not collection_task.done()
            release_can_return.set()

            with pytest.raises(CffexSettlementCollectorPartialPublishCancelledError) as cancelled:
                await collection_task
        finally:
            release_second_persistence_return.set()
            release_can_return.set()
            if not collection_task.done():
                collection_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await collection_task

        first_rows = await store.read_observation_revisions(
            targets[0].context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        second_rows = await store.read_observation_revisions(
            targets[1].context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        counts = await _counts(db)

    assert source.calls == [TRADING_DATE]
    assert persist_attempts == 2
    assert cancelled.value.code == "CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED_CANCELLED"
    assert isinstance(cancelled.value.__cause__, CffexSettlementCollectorFetchLeaseReleaseError)
    assert len(cancelled.value.persisted_fetches) == 2
    assert len(first_rows) == 1
    assert len(second_rows) == 1
    assert counts == (2, 2, 2)


@pytest.mark.asyncio
async def test_duplicate_or_missing_metric_rejects_whole_batch_before_source_receipt() -> None:
    """A corrupted source response never writes a partial canonical receipt."""
    target = _target("IF2609")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        duplicate_source = _FakeCffexSource([_row("IF2609"), _row("IF2609")])
        duplicate_collector = _collector(
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
        missing_collector = _collector(
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
        collector = _collector(
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
        collector = _collector(
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
@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("adjustment", "adjusted"),
        ("price_basis", "close"),
        ("currency", "USD"),
        ("unit", "share"),
        ("family_contract_version", "market-data-kline-v1"),
        ("source_policy_id", "market-cffex-settlement-nearby-v1"),
    ],
)
async def test_non_native_settlement_contract_axes_never_reach_source(
    field_name: str,
    invalid_value: str,
) -> None:
    """A CFFEX settlement receipt cannot inherit nearby bars semantics or family revisions."""
    target = _target("IF2609")
    invalid_query = target.context.query.model_copy(update={field_name: invalid_value})
    invalid_target = CffexSettlementCollectionTarget(
        context=replace(target.context, query=invalid_query),
        source_authorization=target.source_authorization,
    )
    source = _FakeCffexSource([_actual_akshare_row("IF2609")])

    async with async_session_maker() as db:
        collector = _collector(
            store=MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT),
            source=source,
            clock=lambda: LOCAL_RECEIVED_AT,
        )
        with pytest.raises(CffexSettlementCollectorError) as rejected:
            await collector.collect(trading_date=TRADING_DATE, targets=(invalid_target,))

    assert rejected.value.code == "CFFEX_SETTLEMENT_TARGET_CONTRACT_INVALID"
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
        collector = _collector(
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
async def test_currently_disabled_source_registry_never_reaches_cffex_provider() -> None:
    """A post-resolution registry revocation blocks provider I/O at preflight."""
    source = _FakeCffexSource([_actual_akshare_row("IF2609")])
    target = _target("IF2609")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        registry = await db.scalar(
            select(AssetDataSourceRegistry).where(AssetDataSourceRegistry.source_id == PROVIDER_ID)
        )
        assert registry is not None
        registry.enabled = False
        await db.commit()

        collector = _collector(
            store=MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT),
            source=source,
            clock=lambda: LOCAL_RECEIVED_AT,
        )
        with pytest.raises(MarketDataStoreError) as rejected:
            await collector.collect(trading_date=TRADING_DATE, targets=(target,))

    assert rejected.value.code == "SOURCE_AUTHORIZATION_REGISTRY_DENIED"
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
            await _collector(
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
