"""Isolated SQLite harness contracts for the legacy daily-bar import adapters.

These tests intentionally construct every collaborator directly against the
pytest in-memory SQLite fixture.  They seed only the FK-required fixture
provider row; they do not register a production provider/source policy, open a
project database, invoke a route or scheduler, or call AkShare/OpenBB.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import async_session_maker
from app.models.data_governance import DgProvider
from app.models.market_data_platform import (
    MdPublication,
    MdPublicationReleaseHold,
    MdSourcePayload,
    MdSourceSnapshot,
)
from app.services.market_data.coverage import EventKey, TimeWindow
from app.services.market_data.fetch_lease import MarketDataFetchLeaseManager
from app.services.market_data.legacy_stock_daily_canonical_writer import (
    LegacyStockDailyCanonicalWriterAdapter,
)
from app.services.market_data.legacy_stock_daily_evidence_gate_adapter import (
    LegacyStockDailyCanonicalTarget,
    LegacyStockDailyEvidenceGateAdapter,
    LegacyStockDailyEvidenceGateAdapterError,
    LegacyStockDailySourceProvenance,
)
from app.services.market_data.legacy_stock_daily_import import (
    LEGACY_STOCK_DAILY_PROVIDER_ID,
    LEGACY_STOCK_DAILY_ROUTE_ID,
    LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
    LEGACY_STOCK_DAILY_TABLE,
    FrozenLegacyStockDailyCalendar,
    FrozenLegacyStockDailyIdentity,
    LegacyStockDailyImportAttestation,
    LegacyStockDailyImporter,
    LegacyStockDailyImportError,
)
from app.services.market_data.legacy_stock_daily_source_repository import (
    LegacyStockDailySourceRepository,
    LegacyStockDailySourceRepositoryError,
    inspect_legacy_stock_daily_source_schema,
)
from app.services.market_data.publication import (
    PUBLICATION_RELEASE_HOLD_STATE_QUARANTINED,
    MarketDataVisibilityAnchor,
)
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.store import (
    UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
    MarketDataStore,
    _DeferredLegacyImportCandidate,
)
from tests.market_data_platform.test_store import (
    CANONICAL_ID,
    METADATA_VERSION,
    _at,
    _context,
    _seed_dataset_and_provider,
    _sha,
)

UTC = timezone.utc
_NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)
_ALL_DAILY_FIELDS = ("open", "high", "low", "close", "volume", "change_pct")
_SOURCE_REVISION = "stock_zh_a_hist:isolated-fixture-v1"


@dataclass(frozen=True, slots=True)
class _Harness:
    """Explicitly injected collaborators for one non-production import test."""

    context: ResolvedMarketDataQueryContext
    store: MarketDataStore
    source_repository: LegacyStockDailySourceRepository
    evidence_gate: LegacyStockDailyEvidenceGateAdapter
    importer: LegacyStockDailyImporter
    calendar: FrozenLegacyStockDailyCalendar
    attestation: LegacyStockDailyImportAttestation
    frozen_identities: dict[str, FrozenLegacyStockDailyIdentity]


async def _create_source_table(db: AsyncSession) -> None:
    """Create only the physical table used by this isolated SQLite fixture."""
    # This name is not part of SQLAlchemy metadata, so clean the in-memory
    # fixture explicitly between tests.  It never points at a project database.
    await db.execute(text('DROP TABLE IF EXISTS "STOCK_ZH_A_HIST"'))
    await db.execute(
        text(
            """
            CREATE TABLE "STOCK_ZH_A_HIST" (
                "symbol" TEXT NOT NULL,
                "data_date" TEXT NOT NULL,
                "开盘" NUMERIC NOT NULL,
                "最高" NUMERIC NOT NULL,
                "最低" NUMERIC NOT NULL,
                "收盘" NUMERIC NOT NULL,
                "成交量" INTEGER NOT NULL,
                "涨跌幅" NUMERIC NOT NULL,
                "unreviewed_extra" TEXT
            )
            """
        )
    )
    await db.execute(
        text(
            """
            INSERT INTO "STOCK_ZH_A_HIST"
                ("symbol", "data_date", "开盘", "最高", "最低", "收盘", "成交量", "涨跌幅", "unreviewed_extra")
            VALUES
                (:symbol, :data_date, :open, :high, :low, :close, :volume, :change_pct, :extra)
            """
        ),
        (
            {
                "symbol": "600000",
                "data_date": "2026-09-07",
                "open": 10.0,
                "high": 10.7,
                "low": 9.8,
                "close": 10.5,
                "volume": 123_400,
                "change_pct": 2.94,
                "extra": "must-not-enter-projection",
            },
            {
                "symbol": "600000",
                "data_date": "2026-09-08",
                "open": 10.5,
                "high": 10.8,
                "low": 10.1,
                "close": 10.2,
                "volume": 98_700,
                "change_pct": -2.86,
                "extra": "must-not-enter-projection",
            },
        ),
    )
    await db.commit()


def _calendar() -> FrozenLegacyStockDailyCalendar:
    """Return a frozen source-date-to-event map; never derive event time from a date."""
    return FrozenLegacyStockDailyCalendar(
        calendar_snapshot_id="isolated-calendar-cn-sse-2026-09-v1",
        calendar_code="CN-SSE",
        calendar_version="2026.09.fixture",
        timezone_name="Asia/Shanghai",
        data_kind="bars",
        frequency="1d",
        coverage_window=TimeWindow(start_at=_at(16, day=6), end_at=_at(16, day=9)),
        visibility_anchor=MarketDataVisibilityAnchor(
            visible_at=_at(8, day=10),
            max_visibility_sequence=0,
        ),
        event_key_by_trading_date={
            date(2026, 9, 7): EventKey(_at(7, day=7)),
            date(2026, 9, 8): EventKey(_at(7, day=8)),
        },
    )


async def _harness(db: AsyncSession) -> _Harness:
    """Wire the adapters only after test control-plane fixture rows exist."""
    await _seed_dataset_and_provider(db, provider_id=LEGACY_STOCK_DAILY_PROVIDER_ID)
    provider = await db.scalar(select(DgProvider))
    assert provider is not None
    provider.name = "Legacy mixed warehouse fixture"
    await db.commit()
    await _create_source_table(db)

    candidate_schema = await inspect_legacy_stock_daily_source_schema(db)
    source_repository = LegacyStockDailySourceRepository(
        db,
        approved_schema_sha256=candidate_schema.schema_sha256,
    )
    context = _context(
        start=_at(16, day=6),
        end=_at(16, day=9),
        required_fields=_ALL_DAILY_FIELDS,
    )
    store = MarketDataStore(db, clock=lambda: _NOW)
    lease = await MarketDataFetchLeaseManager(db, clock=lambda: _NOW).acquire(
        _sha("legacy-stock-daily-isolated-fixture-lease")
    )
    assert lease is not None
    target = LegacyStockDailyCanonicalTarget(
        context=context,
        fetch_lease=lease,
    )
    source_provenance = LegacyStockDailySourceProvenance(
        source_revision=_SOURCE_REVISION,
        approval_reference="TEST-ONLY-LEGACY-STOCK-DAILY-IMPORT",
        known_possible_upstreams=("akshare", "eastmoney", "tencent"),
    )
    evidence_gate = LegacyStockDailyEvidenceGateAdapter(
        source_repository=source_repository,
        store=store,
        source_provenance=source_provenance,
        targets=(target,),
        clock=lambda: _NOW,
    )
    writer = LegacyStockDailyCanonicalWriterAdapter(
        store=store,
        evidence_gate=evidence_gate,
        clock=lambda: _NOW,
    )
    attestation = LegacyStockDailyImportAttestation(
        source_id=LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
        source_revision=_SOURCE_REVISION,
        adjustment="qfq",
        source_timezone="Asia/Shanghai",
        retrieved_at=_at(8, day=10),
        schema_version="stock-zh-a-hist-v1",
    )
    identity = FrozenLegacyStockDailyIdentity(
        provider_symbol="600000",
        canonical_id=CANONICAL_ID,
        market="CN-SSE",
        identity_revision="fixture-identity-revision-v1",
        instrument_metadata_version=METADATA_VERSION,
    )
    return _Harness(
        context=context,
        store=store,
        source_repository=source_repository,
        evidence_gate=evidence_gate,
        importer=LegacyStockDailyImporter(
            reader=source_repository,
            writer=writer,
            evidence_gate=evidence_gate,
            clock=lambda: _NOW,
        ),
        calendar=_calendar(),
        attestation=attestation,
        frozen_identities={"600000": identity},
    )


@pytest.mark.asyncio
async def test_isolated_sqlite_harness_stages_reviews_promotes_and_records_mixed_provenance() -> (
    None
):
    """A supplied SQLite fixture is the only concrete adapter environment."""
    async with async_session_maker() as db:
        harness = await _harness(db)

        report = await harness.importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=harness.attestation,
            calendar=harness.calendar,
            frozen_identities=harness.frozen_identities,
            dry_run=False,
        )

        assert report.action == "imported"
        assert report.source_row_count == 2
        assert report.normalized_bar_count == 2
        assert report.accepted_event_keys == (
            EventKey(_at(7, day=7)),
            EventKey(_at(7, day=8)),
        )
        assert {bar.source_available_at for bar in report.local_only_bars} == {_NOW}
        assert {bar.available_at for bar in report.local_only_bars} == {_NOW}

        snapshots = list((await db.scalars(select(MdSourceSnapshot))).all())
        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert snapshot.source_id == LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID
        assert snapshot.platform == LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID
        assert snapshot.source_authorization_state == "UNVERIFIED_COMPATIBILITY"
        assert snapshot.source_authorization_descriptor_sha256 is None
        assert snapshot.provenance_json["unverified_compatibility"] == {
            "version": "market-data-unverified-source-write-v1",
            "reason": UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            "decision": "UNVERIFIED",
        }
        receipt_payload = snapshot.payload_manifest_json["receipt_payload"]
        provenance = receipt_payload["legacy_import"]["source_provenance"]
        assert provenance == {
            "approval_reference": "TEST-ONLY-LEGACY-STOCK-DAILY-IMPORT",
            "known_possible_upstreams": ["akshare", "eastmoney", "tencent"],
            "per_row_provider_attribution": "unavailable",
            "provenance_class": "mixed_legacy_warehouse",
            "provider_id": LEGACY_STOCK_DAILY_PROVIDER_ID,
            "route_id": LEGACY_STOCK_DAILY_ROUTE_ID,
            "source_registry_id": LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
            "source_revision": _SOURCE_REVISION,
        }
        source_payload = await db.scalar(select(MdSourcePayload))
        assert source_payload is not None
        source_batch = json.loads(bytes(source_payload.canonical_payload_bytes))
        assert all("unreviewed_extra" not in row for row in source_batch["rows"])
        # Product/local-first reads require a verified source registry receipt.
        # The private writer reread above is the only harness seam permitted to
        # inspect this mixed, unverified warehouse data.
        assert (
            await harness.store.read_observations(
                harness.context,
                knowledge_cutoff=_NOW,
                allowed_source_registry_ids=frozenset({LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID}),
            )
            == ()
        )


@pytest.mark.asyncio
async def test_schema_digest_mismatch_stops_before_fixed_projection_read() -> None:
    """A candidate digest is descriptive until an exact reviewed value is supplied."""
    async with async_session_maker() as db:
        await _create_source_table(db)
        repository = LegacyStockDailySourceRepository(
            db,
            approved_schema_sha256="0" * 64,
        )

        with pytest.raises(LegacyStockDailySourceRepositoryError) as rejected:
            await repository.read_rows(
                table_name=LEGACY_STOCK_DAILY_TABLE,
                source_columns=(
                    "symbol",
                    "data_date",
                    "开盘",
                    "最高",
                    "最低",
                    "收盘",
                    "成交量",
                    "涨跌幅",
                ),
                source_schema_sha256="0" * 64,
            )

        assert rejected.value.code == "LEGACY_STOCK_DAILY_SOURCE_SCHEMA_APPROVAL_MISMATCH"


@pytest.mark.asyncio
async def test_file_backed_sqlite_is_rejected_before_a_legacy_table_can_be_opened(tmp_path) -> None:
    """The harness must not become a reader for an application's SQLite file."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'project-like.sqlite'}")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with sessions() as db:
            with pytest.raises(LegacyStockDailySourceRepositoryError) as rejected:
                LegacyStockDailySourceRepository(
                    db,
                    approved_schema_sha256="0" * 64,
                )
    finally:
        await engine.dispose()

    assert rejected.value.code == "LEGACY_STOCK_DAILY_SOURCE_CONNECTION_NOT_ISOLATED"


@pytest.mark.asyncio
async def test_private_harness_wiring_refuses_a_different_store_session() -> None:
    """A gate or writer cannot redirect isolated source rows into another Store."""
    async with async_session_maker() as db, async_session_maker() as other_db:
        harness = await _harness(db)
        other_store = MarketDataStore(other_db, clock=lambda: _NOW)

        with pytest.raises(ValueError, match="source repository's injected isolated session"):
            LegacyStockDailyEvidenceGateAdapter(
                source_repository=harness.source_repository,
                store=other_store,
                source_provenance=harness.evidence_gate.source_provenance,
                targets=(),
                clock=lambda: _NOW,
            )
        with pytest.raises(ValueError, match="evidence gate's isolated Store instance"):
            LegacyStockDailyCanonicalWriterAdapter(
                store=other_store,
                evidence_gate=harness.evidence_gate,
                clock=lambda: _NOW,
            )


@pytest.mark.asyncio
async def test_akshare_relabel_is_rejected_before_the_isolated_fixture_is_read() -> None:
    """A mixed warehouse cannot be converted into an AkShare attestation string."""
    async with async_session_maker() as db:
        harness = await _harness(db)
        relabeled = LegacyStockDailyImportAttestation(
            source_id="akshare",
            source_revision=_SOURCE_REVISION,
            adjustment="qfq",
            source_timezone="Asia/Shanghai",
            retrieved_at=_at(8, day=10),
            schema_version="stock-zh-a-hist-v1",
        )

        with pytest.raises(LegacyStockDailyImportError) as rejected:
            await harness.importer.import_table(
                table_name=LEGACY_STOCK_DAILY_TABLE,
                attestation=relabeled,
                calendar=harness.calendar,
                frozen_identities=harness.frozen_identities,
                dry_run=True,
            )

        assert rejected.value.code == "LEGACY_STOCK_DAILY_ATTESTATION_SEMANTICS_INVALID"
        assert await db.scalar(select(MdSourceSnapshot.id)) is None


@pytest.mark.asyncio
async def test_staged_review_failure_quarantines_before_promotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A corrupted private reread cannot progress from a durable hold to visibility."""
    async with async_session_maker() as db:
        harness = await _harness(db)
        original_reread = harness.store._read_deferred_legacy_import_candidate

        async def corrupt_reread(
            *args: object,
            **kwargs: object,
        ) -> _DeferredLegacyImportCandidate:
            candidate = await original_reread(*args, **kwargs)
            return replace(candidate, observations=())

        monkeypatch.setattr(
            harness.store,
            "_read_deferred_legacy_import_candidate",
            corrupt_reread,
        )
        with pytest.raises(LegacyStockDailyImportError):
            await harness.importer.import_table(
                table_name=LEGACY_STOCK_DAILY_TABLE,
                attestation=harness.attestation,
                calendar=harness.calendar,
                frozen_identities=harness.frozen_identities,
                dry_run=False,
            )

        holds = list((await db.scalars(select(MdPublicationReleaseHold))).all())
        assert len(holds) == 1
        assert holds[0].state == PUBLICATION_RELEASE_HOLD_STATE_QUARANTINED
        assert (
            await harness.store.read_observations(
                harness.context,
                knowledge_cutoff=_NOW,
            )
            == ()
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper_kind",
    ("request_context", "receipt", "shared_payload", "rebound_permit_context"),
)
async def test_persisted_evidence_tampering_quarantines_before_any_local_read(
    monkeypatch: pytest.MonkeyPatch,
    tamper_kind: str,
) -> None:
    """The private reread must trust stored evidence, never caller-side DTOs."""
    async with async_session_maker() as db:
        harness = await _harness(db)
        original_stage = harness.store.stage_provider_result_for_deferred_release

        async def stage_then_tamper(*args: object, **kwargs: object):
            staged = await original_stage(*args, **kwargs)
            snapshot = await db.get(MdSourceSnapshot, staged.source_snapshot_id)
            assert snapshot is not None
            if tamper_kind == "request_context":
                request_json = json.loads(json.dumps(snapshot.request_json))
                request_json["resolved_query"]["canonical_id"] = "forged-canonical-id"
                await db.execute(
                    update(MdSourceSnapshot)
                    .where(MdSourceSnapshot.id == snapshot.id)
                    .values(request_json=request_json)
                )
            elif tamper_kind == "receipt":
                payload_manifest = json.loads(json.dumps(snapshot.payload_manifest_json))
                payload_manifest["receipt_payload"]["legacy_import"]["source_receipt"][
                    "source_receipt_id"
                ] = "forged-source-receipt"
                await db.execute(
                    update(MdSourceSnapshot)
                    .where(MdSourceSnapshot.id == snapshot.id)
                    .values(payload_manifest_json=payload_manifest)
                )
            elif tamper_kind == "rebound_permit_context":
                # Rebind the snapshot/publication hash as an adversarial
                # database write. Store's shared-payload checks still pass;
                # the writer must reject the persisted permit/context binding.
                payload_manifest = json.loads(json.dumps(snapshot.payload_manifest_json))
                payload_manifest["receipt_payload"]["legacy_import"]["write_permit"][
                    "resolved_context_sha256"
                ] = "0" * 64
                source_payload = await db.scalar(select(MdSourcePayload))
                assert source_payload is not None
                raw_payload = dict(payload_manifest["receipt_payload"])
                raw_payload["source_batch"] = json.loads(
                    bytes(source_payload.canonical_payload_bytes)
                )
                rebound_payload_sha256 = hashlib.sha256(
                    json.dumps(
                        raw_payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()
                await db.execute(
                    update(MdSourceSnapshot)
                    .where(MdSourceSnapshot.id == snapshot.id)
                    .values(
                        payload_manifest_json=payload_manifest,
                        payload_sha256=rebound_payload_sha256,
                    )
                )
                await db.execute(
                    update(MdPublication)
                    .where(MdPublication.id == staged.publication_id)
                    .values(entity_sha256=rebound_payload_sha256)
                )
            else:
                source_payload = await db.scalar(select(MdSourcePayload))
                assert source_payload is not None
                await db.execute(
                    update(MdSourcePayload)
                    .where(MdSourcePayload.content_sha256 == source_payload.content_sha256)
                    .values(canonical_payload_bytes=b'{"forged":true}')
                )
            await db.commit()
            return staged

        monkeypatch.setattr(
            harness.store,
            "stage_provider_result_for_deferred_release",
            stage_then_tamper,
        )
        with pytest.raises(LegacyStockDailyImportError):
            await harness.importer.import_table(
                table_name=LEGACY_STOCK_DAILY_TABLE,
                attestation=harness.attestation,
                calendar=harness.calendar,
                frozen_identities=harness.frozen_identities,
                dry_run=False,
            )

        holds = list((await db.scalars(select(MdPublicationReleaseHold))).all())
        assert len(holds) == 1
        assert holds[0].state == PUBLICATION_RELEASE_HOLD_STATE_QUARANTINED
        assert await harness.store.read_observations(harness.context, knowledge_cutoff=_NOW) == ()
        assert (
            await harness.store.read_observation_revisions(
                harness.context,
                knowledge_cutoff=_NOW,
            )
            == ()
        )


@pytest.mark.asyncio
async def test_promotion_gate_failure_quarantines_the_hidden_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed post-stage authorization does not expose a canonical observation."""
    async with async_session_maker() as db:
        harness = await _harness(db)

        async def deny_promotion(*_args: object, **_kwargs: object) -> None:
            raise LegacyStockDailyEvidenceGateAdapterError(
                "LEGACY_STOCK_DAILY_PROMOTION_AUTHORIZATION_UNVERIFIED"
            )

        monkeypatch.setattr(harness.evidence_gate, "assert_promotion_allowed", deny_promotion)
        with pytest.raises(LegacyStockDailyImportError):
            await harness.importer.import_table(
                table_name=LEGACY_STOCK_DAILY_TABLE,
                attestation=harness.attestation,
                calendar=harness.calendar,
                frozen_identities=harness.frozen_identities,
                dry_run=False,
            )

        holds = list((await db.scalars(select(MdPublicationReleaseHold))).all())
        assert len(holds) == 1
        assert holds[0].state == PUBLICATION_RELEASE_HOLD_STATE_QUARANTINED
        assert (
            await harness.store.read_observations(
                harness.context,
                knowledge_cutoff=_NOW,
            )
            == ()
        )
