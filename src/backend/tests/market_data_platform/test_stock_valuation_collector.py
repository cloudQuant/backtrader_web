"""Offline contracts for the default-off captured stock-valuation candidate."""

from __future__ import annotations

import asyncio
import hashlib
import json
import socket
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

import app.services.market_data.stock_valuation_collector as collector_module
from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry
from app.models.data_governance import DgDataset, DgProvider
from app.models.market_data_platform import MdObservationRevision, MdPublication, MdSourceSnapshot
from app.schemas.asset_research import InstrumentIdentity, StockIdentityDetails
from app.schemas.market_data_platform import MarketDataQueryRequest, ResolvedMarketDataQuery
from app.services.market_data.access import MarketDataSourceAuthorization
from app.services.market_data.catalog import DatasetStorageResolution
from app.services.market_data.coverage import QueryIdentity
from app.services.market_data.identity import ResolvedMarketDataIdentity
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.snapshot_importer import FrozenSnapshotIdentity
from app.services.market_data.stock_valuation_collector import (
    STOCK_VALUATION_ADJUSTMENT,
    STOCK_VALUATION_CAPTURE_ENDPOINT,
    STOCK_VALUATION_COLLECTOR_VERSION,
    STOCK_VALUATION_CURRENCY,
    STOCK_VALUATION_DATASET_CODE,
    STOCK_VALUATION_EVENT_AT_SEMANTICS,
    STOCK_VALUATION_PRICE_BASIS,
    STOCK_VALUATION_REQUIRED_FIELDS,
    STOCK_VALUATION_SOURCE_POLICY_ID,
    STOCK_VALUATION_UNIT,
    StockValuationCapturedBatch,
    StockValuationCollectionTarget,
    StockValuationCollector,
    StockValuationCollectorError,
    StockValuationCollectorPartialPublishCancelledError,
    StockValuationCollectorPartialPublishError,
)
from app.services.market_data.store import MarketDataStore, MarketDataStoreError

UTC = timezone.utc
CAPTURED_AT = datetime(2026, 9, 8, 7, 15, tzinfo=UTC)
LOCAL_RECEIVED_AT = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)
DATASET_ID = "dataset-stock-valuation"
PROVIDER_ID = "akshare"
SOURCE_REVISION = "akshare.stock_zh_a_spot_em:captured-fixture-v1"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _capture_window() -> tuple[datetime, datetime]:
    return CAPTURED_AT, CAPTURED_AT + timedelta(microseconds=1)


def _identity(*, symbol: str, canonical_id: str, venue: str) -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="stock",
        identity_level="ASSET",
        canonical_id=canonical_id,
        display_symbol=symbol,
        name=f"A-share {symbol}",
        venue=venue,
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="EXCHANGE_SYMBOL",
        identifier_value=symbol,
        product_type="EQUITY",
        metadata_version="stock-valuation-v1",
        details=StockIdentityDetails(exchange_symbol=symbol),
    )


def _context(*, symbol: str, canonical_id: str, venue: str) -> ResolvedMarketDataQueryContext:
    start, end = _capture_window()
    request = MarketDataQueryRequest.model_validate(
        {
            "identity": {"canonical_id": canonical_id},
            "dataset_code": STOCK_VALUATION_DATASET_CODE,
            "data_kind": "valuation_snapshot",
            "frequency": "snapshot",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "required_fields": sorted(STOCK_VALUATION_REQUIRED_FIELDS),
            "adjustment": STOCK_VALUATION_ADJUSTMENT,
            "price_basis": STOCK_VALUATION_PRICE_BASIS,
            "currency": STOCK_VALUATION_CURRENCY,
            "unit": STOCK_VALUATION_UNIT,
            "source_policy_id": STOCK_VALUATION_SOURCE_POLICY_ID,
            "consistency": "display",
            "purpose": "display",
            "mode": "local_only",
        }
    )
    query = ResolvedMarketDataQuery.from_request(
        request,
        canonical_id=canonical_id,
        dataset_code=STOCK_VALUATION_DATASET_CODE,
        instrument_metadata_version="stock-valuation-v1",
    )
    identity = _identity(symbol=symbol, canonical_id=canonical_id, venue=venue)
    resolved_identity = ResolvedMarketDataIdentity(
        instrument_id=f"instrument:stock:{venue}:{symbol}",
        canonical_id=canonical_id,
        asset_type="stock",
        metadata_version="stock-valuation-v1",
        venue=venue,
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
            dataset_code=STOCK_VALUATION_DATASET_CODE,
            storage_id="canonical-market-data",
            engine="postgresql",
            database_name="market_data",
            physical_table="md_observation_revisions",
            write_mode="canonical_read_write",
        ),
        coverage_identity=QueryIdentity(
            dataset_code=STOCK_VALUATION_DATASET_CODE,
            canonical_id=canonical_id,
            asset_type="stock",
            instrument_metadata_version="stock-valuation-v1",
            data_kind="valuation_snapshot",
            market=venue,
            frequency="snapshot",
            source_policy_id=STOCK_VALUATION_SOURCE_POLICY_ID,
            adjustment=STOCK_VALUATION_ADJUSTMENT,
            price_basis=STOCK_VALUATION_PRICE_BASIS,
            currency=STOCK_VALUATION_CURRENCY,
            unit=STOCK_VALUATION_UNIT,
        ),
    )


def _source_authorization(
    *,
    venue: str,
    purpose: str = "display",
    decision: str = "ALLOW",
    source_registry_id: str = PROVIDER_ID,
) -> MarketDataSourceAuthorization:
    values: dict[str, object] = {
        "source_registry_id": source_registry_id,
        "registry_updated_at": LOCAL_RECEIVED_AT.isoformat(),
        "asset_type": "stock",
        "market": venue,
        "purpose": purpose,
        "license_status": "APPROVED",
        "allowed_uses": ("DISPLAY",),
        "jurisdictions": ("CN-SSE", "CN-SZSE"),
        "effective_from": datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
        "effective_to": None,
        "retention_policy": "MARKET-DATA-V1",
        "retention_expires_at": None,
        "redistribution_policy": "NO_REDISTRIBUTION",
        "principal_scope": "principal-v1:stock-valuation-offline-test",
        "tenant_scope": "default",
        "entitlement_revision": _sha("stock-valuation-offline-entitlement"),
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


def _target(symbol: str, *, venue: str) -> StockValuationCollectionTarget:
    canonical_id = f"instrument:stock:{venue}:{symbol}"
    return StockValuationCollectionTarget(
        context=_context(symbol=symbol, canonical_id=canonical_id, venue=venue),
        source_authorization=_source_authorization(venue=venue),
        frozen_identity=FrozenSnapshotIdentity(
            canonical_id=canonical_id,
            asset_type="stock",
            provider_symbol=symbol,
            market=venue,
        ),
    )


async def _seed_control_plane(db) -> None:
    db.add_all(
        [
            DgDataset(
                id=DATASET_ID,
                dataset_code=STOCK_VALUATION_DATASET_CODE,
                display_name="Captured stock valuation candidate",
                domain="market",
                canonical_schema={
                    "event_at": "timestamp",
                    "market_cap": "decimal",
                    "float_market_cap": "decimal",
                    "pe": "decimal",
                    "pb": "decimal",
                },
                primary_key=["canonical_id", "event_at"],
            ),
            DgProvider(
                id="provider-akshare-stock-valuation",
                provider_id=PROVIDER_ID,
                name="AkShare captured stock valuation",
                category="market",
                is_active=True,
            ),
            AssetDataSourceRegistry(
                source_id=PROVIDER_ID,
                asset_types=["stock"],
                jurisdictions=["CN-SSE", "CN-SZSE"],
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
    market_cap: object = "1000000000",
    float_market_cap: object = "800000000",
    pe: object = "15.2",
    pb: object = "1.5",
) -> dict[str, object]:
    return {
        "代码": symbol,
        "总市值": market_cap,
        "流通市值": float_market_cap,
        "市盈率-动态": pe,
        "市净率": pb,
    }


def _capture_payload(
    rows: list[dict[str, object]],
    *,
    source_revision: str = SOURCE_REVISION,
    mutate_capture: Callable[[dict[str, object]], object] | None = None,
    declared_hash: str | None = None,
) -> dict[str, object]:
    capture: dict[str, object] = {
        "asset_type": "stock",
        "captured_at": CAPTURED_AT.isoformat(),
        "collector_version": STOCK_VALUATION_COLLECTOR_VERSION,
        "endpoint": STOCK_VALUATION_CAPTURE_ENDPOINT,
        "provider_id": PROVIDER_ID,
        "request_shape": {"args": [], "kwargs": {}},
        "source_revision": source_revision,
        "time_basis": "collector_observed",
    }
    if mutate_capture is not None:
        mutate_capture(capture)
    computed_hash = hashlib.sha256(
        collector_module._canonical_json(  # noqa: SLF001 - fixture must match receipt digest.
            {"capture": capture, "response_rows": rows},
            maximum_bytes=collector_module._MAX_SOURCE_BATCH_BYTES,  # noqa: SLF001
            overflow_code="STOCK_VALUATION_SOURCE_RESPONSE_TOO_LARGE",
        )
    ).hexdigest()
    capture["batch_sha256"] = declared_hash or computed_hash
    return {"capture": capture, "response_rows": rows}


def _batch(
    rows: list[dict[str, object]],
    *,
    source_revision: str = SOURCE_REVISION,
    mutate_capture: Callable[[dict[str, object]], object] | None = None,
    declared_hash: str | None = None,
) -> StockValuationCapturedBatch:
    return StockValuationCapturedBatch(
        provider_id=PROVIDER_ID,
        source_revision=source_revision,
        captured_at=CAPTURED_AT,
        raw_payload=_capture_payload(
            rows,
            source_revision=source_revision,
            mutate_capture=mutate_capture,
            declared_hash=declared_hash,
        ),
    )


def _collector(*, store: MarketDataStore) -> StockValuationCollector:
    return StockValuationCollector(store=store, clock=lambda: LOCAL_RECEIVED_AT)


async def _counts(db) -> tuple[int, int, int]:
    return (
        int(await db.scalar(select(func.count()).select_from(MdSourceSnapshot)) or 0),
        int(await db.scalar(select(func.count()).select_from(MdObservationRevision)) or 0),
        int(await db.scalar(select(func.count()).select_from(MdPublication)) or 0),
    )


def test_private_snapshot_has_no_public_family_or_query_service_coverage() -> None:
    """The stored candidate cannot borrow a public family or snapshot freshness SLA."""
    from app.services.market_data.query_service import (  # Imported lazily to keep fixture local.
        MarketDataQueryServiceError,
        _uses_snapshot_freshness,
    )

    context = _target("600000", venue="CN-SSE").context

    assert context.query.family_id is None
    assert context.query.family_contract_version is None
    with pytest.raises(MarketDataQueryServiceError, match="DATA_KIND_COVERAGE_UNSUPPORTED"):
        _uses_snapshot_freshness(context)


@pytest.mark.asyncio
async def test_captured_batch_recursively_freezes_caller_owned_raw_payload() -> None:
    """Post-construction source mutations cannot change the batch being verified."""
    rows = [_row("600000")]
    raw_payload = _capture_payload(rows)
    batch = StockValuationCapturedBatch(
        provider_id=PROVIDER_ID,
        source_revision=SOURCE_REVISION,
        captured_at=CAPTURED_AT,
        raw_payload=raw_payload,
    )
    capture = raw_payload["capture"]
    assert isinstance(capture, dict)
    capture["endpoint"] = "forged-after-construction"
    rows[0]["总市值"] = "0"
    rows.append(_row("600123"))
    target = _target("600000", venue="CN-SSE")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        report = await _collector(store=store).publish_captured_batch(batch=batch, targets=(target,))
        local_rows = await store.read_observation_revisions(
            target.context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )

    assert report.source_row_count == 1
    assert len(local_rows) == 1
    assert local_rows[0].fields["market_cap"] == "1000000000"


@pytest.mark.asyncio
async def test_offline_batch_persists_two_known_targets_and_quarantines_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The only callable path accepts a fixture batch and has no fetch capability."""
    assert not hasattr(StockValuationCollector, "fetch")
    assert not hasattr(StockValuationCollector, "collect")
    targets = (_target("600000", venue="CN-SSE"), _target("000001", venue="CN-SZSE"))

    def unexpected_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("captured-batch collector must not open a network connection")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        monkeypatch.setattr(socket, "create_connection", unexpected_network)
        report = await _collector(store=store).publish_captured_batch(
            batch=_batch([_row("600000"), _row("000001"), _row("600123")]),
            targets=targets,
        )
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
        snapshots = list((await db.execute(select(MdSourceSnapshot))).scalars())

    assert report.published_target_count == 2
    assert report.source_row_count == 3
    assert report.source_batch_bytes > 0
    assert report.quarantined_provider_symbols == ("600123",)
    assert [(item.provider_symbol, item.reason_code) for item in report.quarantined_rows] == [
        ("600123", "STOCK_VALUATION_UNKNOWN_IDENTITY")
    ]
    assert len(first_rows) == len(second_rows) == 1
    assert first_rows[0].event_at == CAPTURED_AT
    assert dict(first_rows[0].fields) == {
        "float_market_cap": "800000000",
        "market_cap": "1000000000",
        "pb": "1.5",
        "pe": "15.2",
    }
    assert "as_of" not in first_rows[0].fields
    assert len(snapshots) == 2
    payloads = [snapshot.payload_manifest_json["raw_payload"] for snapshot in snapshots]
    assert {payload["collector"]["source_batch_sha256"] for payload in payloads} == {
        report.source_batch_sha256
    }
    for payload in payloads:
        collector = payload["collector"]
        assert collector["time_basis"] == "collector_observed"
        assert collector["source_event_time"] is None
        assert collector["source_as_of"] is None
        assert collector["event_at"] == CAPTURED_AT.isoformat()
        assert collector["event_window"] == {
            "start_at": CAPTURED_AT.isoformat(),
            "end_at": (CAPTURED_AT + timedelta(microseconds=1)).isoformat(),
        }
        assert collector["event_at_semantics"] == STOCK_VALUATION_EVENT_AT_SEMANTICS
        assert collector["capture_endpoint"] == STOCK_VALUATION_CAPTURE_ENDPOINT
        assert collector["source_revision"] == SOURCE_REVISION
        assert collector["quarantined_provider_symbols"] == ["600123"]
        assert collector["quarantined_rows"] == [
            {
                "row_index": 2,
                "provider_symbol": "600123",
                "reason_code": "STOCK_VALUATION_UNKNOWN_IDENTITY",
            }
        ]
    assert all(target.context.query.family_id is None for target in targets)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda rows: rows[0].pop("总市值"),
            "STOCK_VALUATION_ROW_REQUIRED_FIELD_MISSING",
        ),
        (
            lambda rows: rows[0].__setitem__("市盈率-动态", "not-a-number"),
            "STOCK_VALUATION_ROW_FIELD_INVALID",
        ),
        (
            lambda rows: rows[0].__setitem__("市盈率-动态", float("nan")),
            "STOCK_VALUATION_ROW_FIELD_INVALID",
        ),
        (
            lambda rows: rows.append(_row("600000")),
            "STOCK_VALUATION_ROW_DUPLICATE",
        ),
        (
            lambda rows: rows[0].__setitem__("更新时间", CAPTURED_AT.isoformat()),
            "STOCK_VALUATION_TIME_BASIS_INVALID",
        ),
    ],
)
async def test_bad_or_source_timestamped_rows_reject_before_any_receipt(
    mutate: Callable[[list[dict[str, object]]], object],
    expected_code: str,
) -> None:
    """Missing, invalid, ambiguous, and source-time claims cannot publish facts."""
    rows = [_row("600000")]
    mutate(rows)
    target = _target("600000", venue="CN-SSE")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        with pytest.raises(StockValuationCollectorError) as rejected:
            await _collector(
                store=MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
            ).publish_captured_batch(
                batch=_batch(rows),
                targets=(target,),
            )
        counts = await _counts(db)

    assert rejected.value.code == expected_code
    assert counts == (0, 0, 0)


@pytest.mark.asyncio
async def test_unknown_invalid_rows_are_safely_quarantined_without_blocking_known_target() -> None:
    """An unmapped bad row remains receipt evidence and can never become a fact."""
    target = _target("600000", venue="CN-SSE")
    unknown_nan = _row("600123", pe=float("nan"))
    unknown_missing = _row("600124")
    unknown_missing.pop("总市值")

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        report = await _collector(store=store).publish_captured_batch(
            batch=_batch([_row("600000"), unknown_nan, unknown_missing]),
            targets=(target,),
        )
        local_rows = await store.read_observation_revisions(
            target.context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        snapshot = await db.scalar(select(MdSourceSnapshot))
        counts = await _counts(db)

    assert len(local_rows) == 1
    assert counts == (1, 1, 1)
    assert [(item.provider_symbol, item.reason_code) for item in report.quarantined_rows] == [
        ("600123", "STOCK_VALUATION_UNKNOWN_ROW_FIELD_INVALID"),
        ("600124", "STOCK_VALUATION_UNKNOWN_ROW_REQUIRED_FIELD_MISSING"),
    ]
    assert snapshot is not None
    receipt = snapshot.payload_manifest_json["raw_payload"]
    assert receipt["collector"]["quarantined_provider_symbols"] == ["600123", "600124"]
    assert receipt["collector"]["quarantined_rows"] == [
        {
            "row_index": 1,
            "provider_symbol": "600123",
            "reason_code": "STOCK_VALUATION_UNKNOWN_ROW_FIELD_INVALID",
        },
        {
            "row_index": 2,
            "provider_symbol": "600124",
            "reason_code": "STOCK_VALUATION_UNKNOWN_ROW_REQUIRED_FIELD_MISSING",
        },
    ]
    assert "nan" not in json.dumps(receipt["source_batch"], ensure_ascii=False).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutate_capture", "declared_hash", "expected_code"),
    [
        (
            lambda capture: capture.__setitem__("provider_id", "openbb"),
            None,
            "STOCK_VALUATION_SOURCE_REQUEST_INVALID",
        ),
        (
            lambda capture: capture.__setitem__("endpoint", "stock_zh_a_hist"),
            None,
            "STOCK_VALUATION_SOURCE_REQUEST_INVALID",
        ),
        (
            lambda capture: capture.__setitem__("request_shape", {"args": ["600000"], "kwargs": {}}),
            None,
            "STOCK_VALUATION_SOURCE_REQUEST_INVALID",
        ),
        (
            lambda capture: capture.__setitem__("collector_version", "forged-collector"),
            None,
            "STOCK_VALUATION_SOURCE_REQUEST_INVALID",
        ),
        (
            lambda capture: capture.__setitem__("source_revision", "forged-revision"),
            None,
            "STOCK_VALUATION_SOURCE_REQUEST_INVALID",
        ),
        (None, "0" * 64, "STOCK_VALUATION_SOURCE_BATCH_HASH_INVALID"),
    ],
)
async def test_forged_capture_envelope_rejects_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
    mutate_capture: Callable[[dict[str, object]], object] | None,
    declared_hash: str | None,
    expected_code: str,
) -> None:
    """The typed batch cannot relabel a same-shaped response as the AkShare capture."""
    target = _target("600000", venue="CN-SSE")
    persist_calls = 0

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)

        async def unexpected_persist(*_args: object, **_kwargs: object) -> object:
            nonlocal persist_calls
            persist_calls += 1
            raise AssertionError("forged capture evidence must fail before Store persistence")

        monkeypatch.setattr(store, "persist_provider_result", unexpected_persist)
        with pytest.raises(StockValuationCollectorError) as rejected:
            await _collector(store=store).publish_captured_batch(
                batch=_batch(
                    [_row("600000")],
                    mutate_capture=mutate_capture,
                    declared_hash=declared_hash,
                ),
                targets=(target,),
            )
        counts = await _counts(db)

    assert rejected.value.code == expected_code
    assert persist_calls == 0
    assert counts == (0, 0, 0)


@pytest.mark.asyncio
async def test_non_display_or_non_local_target_context_is_rejected_before_persistence() -> None:
    """The private candidate cannot be repurposed for research, backtest, or refresh."""
    target = _target("600000", venue="CN-SSE")
    invalid_targets = (
        replace(
            target,
            context=replace(
                target.context,
                query=target.context.query.model_copy(update={"mode": "local_first"}),
            ),
        ),
        replace(
            target,
            context=replace(
                target.context,
                query=target.context.query.model_copy(update={"consistency": "strict"}),
            ),
        ),
        replace(
            target,
            context=replace(
                target.context,
                query=target.context.query.model_copy(update={"purpose": "research"}),
            ),
        ),
        replace(
            target,
            context=replace(
                target.context,
                storage=replace(target.context.storage, dataset_code="market.valuation"),
            ),
        ),
    )

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        for invalid_target in invalid_targets:
            with pytest.raises(StockValuationCollectorError) as rejected:
                await _collector(
                    store=MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
                ).publish_captured_batch(
                    batch=_batch([_row("600000")]),
                    targets=(invalid_target,),
                )
            assert rejected.value.code == "STOCK_VALUATION_TARGET_CONTRACT_INVALID"
            assert await _counts(db) == (0, 0, 0)


@pytest.mark.asyncio
async def test_identity_authorization_and_sensitive_payload_fail_before_persistence() -> None:
    """All identity and source-grant checks complete before a Store receipt exists."""
    target = _target("600000", venue="CN-SSE")
    bad_identity = replace(
        target,
        frozen_identity=FrozenSnapshotIdentity(
            canonical_id="instrument:stock:CN-SSE:other",
            asset_type="stock",
            provider_symbol="600000",
            market="CN-SSE",
        ),
    )
    denied_authorization = replace(
        target,
        source_authorization=replace(target.source_authorization, decision="DENY"),
    )
    sensitive_row = _row("600000")
    sensitive_row["metadata"] = {"access_token": "must-not-persist"}
    attempts = (
        (_batch([_row("600000")]), (bad_identity,), "STOCK_VALUATION_TARGET_IDENTITY_MISMATCH"),
        (
            _batch([_row("600000")]),
            (denied_authorization,),
            "STOCK_VALUATION_TARGET_AUTHORIZATION_INVALID",
        ),
        (
            _batch([sensitive_row]),
            (target,),
            "STOCK_VALUATION_SOURCE_SENSITIVE_PAYLOAD_REJECTED",
        ),
    )

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        for batch, targets, expected_code in attempts:
            with pytest.raises(StockValuationCollectorError) as rejected:
                await _collector(
                    store=MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
                ).publish_captured_batch(batch=batch, targets=targets)
            counts = await _counts(db)

            assert rejected.value.code == expected_code
            assert "must-not-persist" not in str(rejected.value)
            assert counts == (0, 0, 0)

        registry = await db.scalar(
            select(AssetDataSourceRegistry).where(AssetDataSourceRegistry.source_id == PROVIDER_ID)
        )
        assert registry is not None
        registry.enabled = False
        await db.commit()
        with pytest.raises(StockValuationCollectorError) as registry_rejected:
            await _collector(
                store=MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
            ).publish_captured_batch(
                batch=_batch([_row("600000")]),
                targets=(target,),
            )
        counts_after_registry_rejection = await _counts(db)

    assert registry_rejected.value.code == "STOCK_VALUATION_SOURCE_AUTHORIZATION_REJECTED"
    assert counts_after_registry_rejection == (0, 0, 0)


@pytest.mark.asyncio
async def test_source_receipt_fanout_budgets_and_target_limit_fail_before_store_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All byte limits preflight exact evidence before authorization or persistence."""
    targets = (_target("600000", venue="CN-SSE"), _target("000001", venue="CN-SZSE"))

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        persist_calls = 0

        async def unexpected_persist(*_args: object, **_kwargs: object) -> object:
            nonlocal persist_calls
            persist_calls += 1
            raise AssertionError("fanout budget must fail before Store persistence")

        monkeypatch.setattr(store, "persist_provider_result", unexpected_persist)
        source_batch = _batch([_row("600000"), _row("000001")])
        source_bytes = len(
            collector_module._canonical_json(  # noqa: SLF001 - verify complete envelope size.
                source_batch.raw_payload,
                maximum_bytes=collector_module._MAX_SOURCE_BATCH_BYTES,  # noqa: SLF001
                overflow_code="STOCK_VALUATION_SOURCE_RESPONSE_TOO_LARGE",
            )
        )
        monkeypatch.setattr(collector_module, "_MAX_SOURCE_BATCH_BYTES", source_bytes - 1)
        with pytest.raises(StockValuationCollectorError) as source_budget_rejected:
            await _collector(store=store).publish_captured_batch(
                batch=source_batch,
                targets=targets,
            )
        counts_after_source_budget = await _counts(db)

        monkeypatch.setattr(collector_module, "_MAX_SOURCE_BATCH_BYTES", 2 * 1024 * 1024)
        monkeypatch.setattr(collector_module, "_MAX_SINGLE_RECEIPT_BYTES", 1)
        with pytest.raises(StockValuationCollectorError) as single_receipt_rejected:
            await _collector(store=store).publish_captured_batch(
                batch=_batch([_row("600000"), _row("000001")]),
                targets=targets,
            )
        counts_after_single_receipt = await _counts(db)

        monkeypatch.setattr(collector_module, "_MAX_SINGLE_RECEIPT_BYTES", 10 * 1024 * 1024)
        monkeypatch.setattr(collector_module, "_MAX_REPLICATED_RECEIPT_BYTES", 1)
        with pytest.raises(StockValuationCollectorError) as budget_rejected:
            await _collector(store=store).publish_captured_batch(
                batch=_batch([_row("600000"), _row("000001")]),
                targets=targets,
            )
        counts_after_budget = await _counts(db)

        monkeypatch.setattr(collector_module, "_MAX_REPLICATED_RECEIPT_BYTES", 32 * 1024 * 1024)
        monkeypatch.setattr(collector_module, "_MAX_TARGETS_PER_BATCH", 1)
        with pytest.raises(StockValuationCollectorError) as target_rejected:
            await _collector(store=store).publish_captured_batch(
                batch=_batch([_row("600000"), _row("000001")]),
                targets=targets,
            )
        counts_after_target_limit = await _counts(db)

    assert source_budget_rejected.value.code == "STOCK_VALUATION_SOURCE_RESPONSE_TOO_LARGE"
    assert single_receipt_rejected.value.code == "STOCK_VALUATION_RECEIPT_EVIDENCE_TOO_LARGE"
    assert budget_rejected.value.code == "STOCK_VALUATION_RECEIPT_EVIDENCE_TOO_LARGE"
    assert target_rejected.value.code == "STOCK_VALUATION_TARGETS_TOO_MANY"
    assert persist_calls == 0
    assert (
        counts_after_source_budget
        == counts_after_single_receipt
        == counts_after_budget
        == counts_after_target_limit
        == (0, 0, 0)
    )


@pytest.mark.asyncio
async def test_later_store_failure_exposes_only_the_durable_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sequential publication never pretends its two target writes are atomic."""
    targets = (_target("000001", venue="CN-SZSE"), _target("600000", venue="CN-SSE"))

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        original_persist = store.persist_provider_result
        persist_attempts = 0

        async def fail_second(*args: object, **kwargs: object):
            nonlocal persist_attempts
            persist_attempts += 1
            if persist_attempts == 2:
                raise MarketDataStoreError("OBSERVATION_WRITE_FAILED")
            return await original_persist(*args, **kwargs)

        monkeypatch.setattr(store, "persist_provider_result", fail_second)
        with pytest.raises(StockValuationCollectorPartialPublishError) as partial:
            await _collector(store=store).publish_captured_batch(
                batch=_batch([_row("000001"), _row("600000")]),
                targets=targets,
            )
        prefix_rows = await store.read_observation_revisions(
            targets[0].context,
            knowledge_cutoff=LOCAL_RECEIVED_AT + timedelta(seconds=1),
            allowed_source_registry_ids=frozenset({PROVIDER_ID}),
        )
        counts = await _counts(db)

    assert persist_attempts == 2
    assert partial.value.code == "STOCK_VALUATION_BATCH_PARTIALLY_PUBLISHED"
    assert len(partial.value.persisted_fetches) == 1
    assert len(prefix_rows) == 1
    assert counts == (1, 1, 1)


@pytest.mark.asyncio
async def test_cancellation_after_durable_write_returns_the_complete_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cancel cannot hide a target receipt that published before task return."""
    targets = (_target("000001", venue="CN-SZSE"), _target("600000", venue="CN-SSE"))
    second_persistence_is_durable = asyncio.Event()
    release_second_return = asyncio.Event()

    async with async_session_maker() as db:
        await _seed_control_plane(db)
        store = MarketDataStore(db, clock=lambda: LOCAL_RECEIVED_AT)
        original_persist = store.persist_provider_result
        persist_attempts = 0

        async def persist_then_block_second_return(*args: object, **kwargs: object):
            nonlocal persist_attempts
            persist_attempts += 1
            persisted = await original_persist(*args, **kwargs)
            if persist_attempts == 2:
                second_persistence_is_durable.set()
                await release_second_return.wait()
            return persisted

        monkeypatch.setattr(store, "persist_provider_result", persist_then_block_second_return)
        task = asyncio.create_task(
            _collector(store=store).publish_captured_batch(
                batch=_batch([_row("000001"), _row("600000")]),
                targets=targets,
            )
        )
        try:
            await asyncio.wait_for(second_persistence_is_durable.wait(), timeout=1.0)
            task.cancel()
            release_second_return.set()
            with pytest.raises(StockValuationCollectorPartialPublishCancelledError) as cancelled:
                await task
        finally:
            release_second_return.set()
            if not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        counts = await _counts(db)

    assert persist_attempts == 2
    assert cancelled.value.code == "STOCK_VALUATION_BATCH_PARTIALLY_PUBLISHED_CANCELLED"
    assert len(cancelled.value.persisted_fetches) == 2
    assert counts == (2, 2, 2)
