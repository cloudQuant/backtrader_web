"""Normalized storage-model contracts for Iteration 197 market data."""

from __future__ import annotations

import hashlib
import importlib.util
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.db.database import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]
CATALOG_REVISION = "20260908_market_data_catalog"
OBSERVATIONS_REVISION = "20260908_market_data_observations"
STORAGE_TABLES = {
    "md_instrument_lookup_keys",
    "md_data_series",
    "md_source_snapshots",
    "md_observation_revisions",
    "md_calendar_snapshots",
    "md_calendar_events",
}


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _load_observations_migration() -> ModuleType:
    """Load the revision module directly for offline schema-recovery probes."""
    migration_path = (
        BACKEND_ROOT / "alembic" / "versions" / "20260908_market_data_observations.py"
    )
    spec = importlib.util.spec_from_file_location("iteration197_observations_migration", migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _publication_table_columns(monkeypatch: pytest.MonkeyPatch, migration: ModuleType) -> tuple[object, ...]:
    """Capture the migration's actual publication-table contract without a database."""
    captured: dict[str, tuple[object, ...]] = {}

    class _CapturingOperations:
        def __init__(self, operations: object) -> None:
            del operations

        def create_table(self, table_name: str, *columns: object, **kwargs: object) -> None:
            del kwargs
            captured[table_name] = columns

        def create_index(
            self,
            index_name: str,
            table_name: str,
            columns: list[str],
            **kwargs: object,
        ) -> None:
            del index_name, table_name, columns, kwargs

    monkeypatch.setattr(migration, "_SchemaAwareOperations", _CapturingOperations)
    migration.upgrade()
    return captured["md_publications"]


class _PreexistingPublicationInspector:
    """Offline inspector payload for a startup-created PostgreSQL publication table."""

    def __init__(
        self,
        migration: ModuleType,
        columns: tuple[object, ...],
        *,
        published_at_type: sa.types.TypeEngine[object],
        check_sql: str,
    ) -> None:
        expected_columns = migration._column_definitions("md_publications", columns)
        self._columns = [
            {
                "name": column_name,
                "type": published_at_type if column_name == "published_at" else column.type,
                "nullable": column.nullable,
                "default": None,
            }
            for column_name, column in expected_columns.items()
        ]
        self._indexes = [
            {
                "name": index_name,
                "column_names": list(specification[0]),
                "unique": specification[1],
            }
            for index_name, specification in migration._TABLE_INDEX_SPECS["md_publications"].items()
        ]
        self._uniques = [
            {"name": name, "column_names": list(columns)}
            for name, columns in migration._TABLE_UNIQUE_SPECS["md_publications"].items()
        ]
        self._checks = [
            {
                "name": "ck_md_publication_entity_sha256_length",
                "sqltext": check_sql,
            }
        ]

    def get_columns(self, table_name: str) -> list[dict[str, object]]:
        assert table_name == "md_publications"
        return self._columns

    def get_indexes(self, table_name: str) -> list[dict[str, object]]:
        assert table_name == "md_publications"
        return self._indexes

    def get_unique_constraints(self, table_name: str) -> list[dict[str, object]]:
        assert table_name == "md_publications"
        return self._uniques

    def get_check_constraints(self, table_name: str) -> list[dict[str, object]]:
        assert table_name == "md_publications"
        return self._checks

    def get_foreign_keys(self, table_name: str) -> list[dict[str, object]]:
        assert table_name == "md_publications"
        return []

    def get_pk_constraint(self, table_name: str) -> dict[str, list[str]]:
        assert table_name == "md_publications"
        return {"constrained_columns": ["id"]}


def _preexisting_publication_contract(
    monkeypatch: pytest.MonkeyPatch,
    *,
    published_at_type: sa.types.TypeEngine[object],
    check_sql: str | None = None,
    dialect_name: str = "postgresql",
) -> tuple[bool, str]:
    """Run the schema-completeness check against a no-server inspector fixture."""
    migration = _load_observations_migration()
    columns = _publication_table_columns(monkeypatch, migration)
    expected_check_sql = next(
        str(constraint.sqltext)
        for constraint in columns
        if isinstance(constraint, sa.CheckConstraint)
        and constraint.name == "ck_md_publication_entity_sha256_length"
    )
    inspector = _PreexistingPublicationInspector(
        migration,
        columns,
        published_at_type=published_at_type,
        check_sql=expected_check_sql if check_sql is None else check_sql,
    )
    dialect = {
        "mysql": mysql.dialect(),
        "postgresql": postgresql.dialect(),
        "sqlite": sqlite.dialect(),
    }[dialect_name]
    bind = SimpleNamespace(dialect=dialect)
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: bind))
    monkeypatch.setattr(migration.sa, "inspect", lambda bind: inspector)
    return migration._table_is_complete("md_publications", columns)


def test_observation_schema_recovery_rejects_postgresql_timestamp_without_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PostgreSQL timestamp without timezone cannot satisfy a PIT table contract."""
    complete, detail = _preexisting_publication_contract(
        monkeypatch,
        published_at_type=postgresql.TIMESTAMP(timezone=False),
    )

    assert not complete
    assert "invalid_columns" in detail
    assert "published_at" in detail


def test_observation_schema_recovery_accepts_sqlite_datetime_without_timezone_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SQLite reflection may erase timezone metadata from a complete startup schema."""
    complete, detail = _preexisting_publication_contract(
        monkeypatch,
        published_at_type=sa.DateTime(),
        dialect_name="sqlite",
    )

    assert complete, detail


def test_observation_schema_recovery_rejects_mysql_datetime_without_microseconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pre-existing MySQL DATETIME(0) cannot preserve PIT publication order."""
    complete, detail = _preexisting_publication_contract(
        monkeypatch,
        published_at_type=mysql.DATETIME(fsp=0),
        dialect_name="mysql",
    )

    assert not complete
    assert "invalid_columns" in detail
    assert "published_at" in detail


def test_observation_migration_uses_mysql_microsecond_datetime_for_pit_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The migration keeps a B receipt later than A after MySQL persistence."""
    migration = _load_observations_migration()
    columns = _publication_table_columns(monkeypatch, migration)
    table = sa.Table("md_publications", sa.MetaData(), *columns)

    ddl = str(sa.schema.CreateTable(table).compile(dialect=mysql.dialect()))

    assert "published_at DATETIME(6)" in ddl
    assert "created_at DATETIME(6)" in ddl


def test_observation_schema_recovery_rejects_same_named_wrong_check_expression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reused CHECK name cannot hide an altered immutable-evidence rule."""
    complete, detail = _preexisting_publication_contract(
        monkeypatch,
        published_at_type=postgresql.TIMESTAMP(timezone=True),
        check_sql="length(entity_sha256) = 63",
    )

    assert not complete
    assert "invalid_checks" in detail
    assert "ck_md_publication_entity_sha256_length" in detail


def test_storage_models_register_generic_cross_asset_fact_tables() -> None:
    """The normalized layer registers generic facts and exact lookup keys."""
    from app.models.asset_research import AssetInstrument
    from app.models.data_governance import DgDataset, DgProvider
    from app.models.market_data_platform import (
        MdCalendarEvent,
        MdCalendarSnapshot,
        MdDataSeries,
        MdInstrumentLookupKey,
        MdObservationRevision,
        MdSourceSnapshot,
    )

    assert STORAGE_TABLES <= set(Base.metadata.tables)
    assert "normalized_symbol" not in MdInstrumentLookupKey.__table__.c.keys()
    assert {
        "asset_type",
        "market",
        "symbol",
        "instrument_id",
        "canonical_id",
        "metadata_version",
        "is_active",
    } <= set(MdInstrumentLookupKey.__table__.c.keys())
    assert "symbol" not in MdDataSeries.__table__.c.keys()
    assert {"dataset_id", "canonical_id", "data_kind", "semantic_key_sha256"} <= set(
        MdDataSeries.__table__.c.keys()
    )
    assert {"series_id", "event_time", "available_at", "source_snapshot_id", "fields_json"} <= set(
        MdObservationRevision.__table__.c.keys()
    )
    assert {"calendar_code", "calendar_version", "snapshot_sha256"} <= set(
        MdCalendarSnapshot.__table__.c.keys()
    )
    assert {"calendar_snapshot_id", "trading_date", "event_type", "event_sha256"} <= set(
        MdCalendarEvent.__table__.c.keys()
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        now = datetime(2026, 9, 8, tzinfo=timezone.utc)
        with Session(engine) as session:
            stock_dataset = DgDataset(
                id="dataset-stock",
                dataset_code="market.stock_daily",
                display_name="Stock daily bars",
                domain="market",
            )
            crypto_dataset = DgDataset(
                id="dataset-crypto",
                dataset_code="market.crypto_quote",
                display_name="Crypto quote snapshots",
                domain="market",
            )
            provider = DgProvider(
                id="provider-akshare",
                provider_id="akshare",
                name="AkShare",
                category="market",
            )
            stock_instrument = AssetInstrument(
                id="instrument-stock-v1",
                canonical_id="instrument:stock:cn:600000",
                asset_type="stock",
                identity_level="PRODUCT",
                identity_json={},
                metadata_version="instrument-v1",
            )
            stock_instrument_v2 = AssetInstrument(
                id="instrument-stock-v2",
                canonical_id="instrument:stock:cn:600000",
                asset_type="stock",
                identity_level="PRODUCT",
                identity_json={},
                metadata_version="instrument-v2",
            )
            crypto_instrument = AssetInstrument(
                id="instrument-crypto-v1",
                canonical_id="instrument:crypto:btc-usdt",
                asset_type="crypto",
                identity_level="PRODUCT",
                identity_json={},
                metadata_version="instrument-v1",
            )
            stock_lookup = MdInstrumentLookupKey(
                id="lookup-stock-v1",
                asset_type="stock",
                market="CN-SSE",
                symbol="600000",
                instrument_id=stock_instrument.id,
                canonical_id=stock_instrument.canonical_id,
                metadata_version=stock_instrument.metadata_version,
                is_active=True,
            )
            crypto_lookup = MdInstrumentLookupKey(
                id="lookup-crypto-v1",
                asset_type="crypto",
                market="BINANCE",
                symbol="BTC-USDT",
                instrument_id=crypto_instrument.id,
                canonical_id=crypto_instrument.canonical_id,
                metadata_version=crypto_instrument.metadata_version,
                is_active=True,
            )
            stock_series = MdDataSeries(
                id="series-stock",
                dataset_id=stock_dataset.id,
                canonical_id="instrument:stock:cn:600000",
                data_kind="bars",
                frequency="1d",
                semantic_key_sha256=_sha("stock-series"),
                semantic_identity_json={"price_basis": "close", "currency": "CNY"},
            )
            crypto_series = MdDataSeries(
                id="series-crypto",
                dataset_id=crypto_dataset.id,
                canonical_id="instrument:crypto:btc-usdt",
                data_kind="quote_snapshot",
                frequency=None,
                semantic_key_sha256=_sha("crypto-series"),
                semantic_identity_json={"price_basis": "mid", "currency": "USDT"},
            )
            source_snapshot = MdSourceSnapshot(
                id="source-snapshot-1",
                provider_id=provider.id,
                platform="akshare",
                source_id="stock_zh_a_hist",
                adapter_id="akshare.stock.v1",
                endpoint_version="v1",
                request_fingerprint_sha256=_sha("request-1"),
                payload_sha256=_sha("payload-1"),
                request_json={"symbol": "600000"},
                payload_manifest_json={"uri": "raw://payload-1"},
                provenance_json={"upstream": "eastmoney"},
                retrieved_at=now,
            )
            session.add_all(
                [
                    stock_dataset,
                    crypto_dataset,
                    provider,
                    stock_instrument,
                    stock_instrument_v2,
                    crypto_instrument,
                    stock_lookup,
                    crypto_lookup,
                    stock_series,
                    crypto_series,
                    source_snapshot,
                ]
            )
            session.commit()

        with Session(engine) as session:
            exact_lookup = session.scalar(
                select(MdInstrumentLookupKey).where(
                    MdInstrumentLookupKey.asset_type == "stock",
                    MdInstrumentLookupKey.market == "CN-SSE",
                    MdInstrumentLookupKey.symbol == "600000",
                    MdInstrumentLookupKey.is_active.is_(True),
                )
            )
            assert exact_lookup is not None
            assert exact_lookup.canonical_id == "instrument:stock:cn:600000"
            assert exact_lookup.active_lookup_scope == "ACTIVE"
            assert session.scalar(select(MdDataSeries).where(MdDataSeries.id == "series-stock"))
            assert session.scalar(select(MdDataSeries).where(MdDataSeries.id == "series-crypto"))
            duplicate_key = MdDataSeries(
                id="series-duplicate",
                dataset_id="dataset-crypto",
                canonical_id="instrument:crypto:btc-usdt-alt",
                data_kind="quote_snapshot",
                semantic_key_sha256=_sha("stock-series"),
                semantic_identity_json={},
            )
            session.add(duplicate_key)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        with Session(engine) as session:
            duplicate_active_lookup = MdInstrumentLookupKey(
                id="lookup-stock-v2",
                asset_type="stock",
                market="CN-SSE",
                symbol="600000",
                instrument_id="instrument-stock-v2",
                canonical_id="instrument:stock:cn:600000",
                metadata_version="instrument-v2",
                is_active=True,
            )
            session.add(duplicate_active_lookup)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        with Session(engine) as session:
            # Core SQL bypasses the ORM event that normally assigns ACTIVE.
            # The database check must still reject NULL because unique indexes
            # permit multiple NULLs on the supported database engines.
            with pytest.raises(IntegrityError):
                session.execute(
                    MdInstrumentLookupKey.__table__.insert().values(
                        id="lookup-active-null-scope",
                        asset_type="stock",
                        market="CN-SSE",
                        symbol="scope-null",
                        instrument_id="instrument-stock-v2",
                        canonical_id="instrument:stock:cn:600000",
                        metadata_version="instrument-null-scope",
                        is_active=True,
                        active_lookup_scope=None,
                        valid_from=now,
                        created_at=now,
                    )
                )
            session.rollback()

        with Session(engine) as session:
            zero_length_history = MdInstrumentLookupKey(
                id="lookup-stock-zero-length-history",
                asset_type="stock",
                market="CN-SSE",
                symbol="600000",
                instrument_id="instrument-stock-v2",
                canonical_id="instrument:stock:cn:600000",
                metadata_version="instrument-zero-length-history",
                is_active=False,
                valid_from=now,
                valid_to=now,
            )
            session.add(zero_length_history)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        assert "ix_md_instrument_lookup_active_exact" in {
            index["name"] for index in inspect(engine).get_indexes("md_instrument_lookup_keys")
        }
    finally:
        engine.dispose()


def test_observation_revisions_are_append_only_with_source_and_quality_provenance() -> None:
    """One logical event can retain revisions without overwriting prior source evidence."""
    from app.models.data_governance import DgDataset, DgProvider
    from app.models.market_data_platform import (
        ImmutableMarketDataRecordError,
        MdDataSeries,
        MdObservationRevision,
        MdSourceSnapshot,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        event_time = datetime(2026, 9, 8, 1, 30, tzinfo=timezone.utc)
        available_at = datetime(2026, 9, 8, 1, 31, tzinfo=timezone.utc)
        with Session(engine) as session:
            session.add_all(
                [
                    DgDataset(
                        id="dataset-bars",
                        dataset_code="market.stock_daily",
                        display_name="Stock daily bars",
                        domain="market",
                    ),
                    DgProvider(
                        id="provider-1",
                        provider_id="akshare",
                        name="AkShare",
                        category="market",
                    ),
                    MdDataSeries(
                        id="series-1",
                        dataset_id="dataset-bars",
                        canonical_id="instrument:stock:cn:600000",
                        data_kind="bars",
                        frequency="1d",
                        semantic_key_sha256=_sha("series-1"),
                        semantic_identity_json={},
                    ),
                    MdSourceSnapshot(
                        id="source-1",
                        provider_id="provider-1",
                        platform="akshare",
                        source_id="stock_zh_a_hist",
                        adapter_id="akshare.stock.v1",
                        endpoint_version="v1",
                        request_fingerprint_sha256=_sha("request-1"),
                        payload_sha256=_sha("payload-1"),
                        request_json={},
                        payload_manifest_json={},
                        provenance_json={},
                        retrieved_at=available_at,
                    ),
                    MdSourceSnapshot(
                        id="source-2",
                        provider_id="provider-1",
                        platform="akshare",
                        source_id="stock_zh_a_hist",
                        adapter_id="akshare.stock.v1",
                        endpoint_version="v2",
                        request_fingerprint_sha256=_sha("request-2"),
                        payload_sha256=_sha("payload-2"),
                        request_json={},
                        payload_manifest_json={},
                        provenance_json={},
                        retrieved_at=available_at,
                    ),
                ]
            )
            session.add(
                MdObservationRevision(
                    id="observation-1",
                    series_id="series-1",
                    event_time=event_time,
                    event_end=available_at,
                    available_at=available_at,
                    source_snapshot_id="source-1",
                    quality_status="accepted",
                    quality_policy_version="quality-v1",
                    quality_details_json={"gates": ["schema", "calendar"]},
                    fields_json={"open": "10.0", "close": "10.5"},
                    fields_sha256=_sha("fields-1"),
                    revision_number=1,
                    revision_key_sha256=_sha("revision-1"),
                    normalization_version="normalization-v1",
                    source_record_key="600000/2026-09-08",
                    provenance_json={"raw_row": 7},
                    committed_at=available_at,
                )
            )
            session.commit()

        with Session(engine) as session:
            revision = session.scalar(
                select(MdObservationRevision).where(MdObservationRevision.id == "observation-1")
            )
            assert revision is not None
            assert revision.source_snapshot_id == "source-1"
            assert revision.quality_policy_version == "quality-v1"
            assert revision.fields_json["close"] == "10.5"

            revision.quality_status = "rejected"
            with pytest.raises(ImmutableMarketDataRecordError):
                session.flush()
            session.rollback()

        with Session(engine) as session:
            session.add(
                MdObservationRevision(
                    id="observation-duplicate",
                    series_id="series-1",
                    event_time=event_time,
                    event_end=available_at,
                    available_at=available_at,
                    source_snapshot_id="source-2",
                    quality_status="accepted",
                    quality_policy_version="quality-v1",
                    quality_details_json={},
                    fields_json={"open": "10.0", "close": "10.6"},
                    fields_sha256=_sha("fields-2"),
                    revision_number=1,
                    revision_key_sha256=_sha("revision-2"),
                    normalization_version="normalization-v1",
                    source_record_key="600000/2026-09-08",
                    provenance_json={},
                    committed_at=available_at,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_versioned_calendar_snapshots_keep_distinct_session_events() -> None:
    """Calendar facts are versioned independently of a particular asset class."""
    from app.models.market_data_platform import MdCalendarEvent, MdCalendarSnapshot

    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            snapshot = MdCalendarSnapshot(
                id="calendar-1",
                calendar_code="CN-SSE",
                calendar_version="2026.09.08",
                timezone_name="Asia/Shanghai",
                snapshot_sha256=_sha("calendar-1"),
                definition_json={"weekend": ["SAT", "SUN"]},
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 12, 31),
            )
            event = MdCalendarEvent(
                id="calendar-event-1",
                calendar_snapshot_id=snapshot.id,
                trading_date=date(2026, 9, 8),
                event_type="session",
                session_code="day",
                is_trading_day=True,
                event_start=datetime(2026, 9, 8, 1, 30, tzinfo=timezone.utc),
                event_end=datetime(2026, 9, 8, 7, 0, tzinfo=timezone.utc),
                event_payload_json={
                    "coverage": {"data_kind": "bars", "frequency": "1d"},
                    "open": "09:30",
                    "close": "15:00",
                },
                event_sha256=_sha("calendar-event-1"),
            )
            session.add_all([snapshot, event])
            session.commit()

        with Session(engine) as session:
            session.add(
                MdCalendarEvent(
                    id="calendar-event-duplicate",
                    calendar_snapshot_id="calendar-1",
                    trading_date=date(2026, 9, 8),
                    event_type="session",
                    session_code="day",
                    is_trading_day=True,
                    event_start=datetime(2026, 9, 8, 1, 30, tzinfo=timezone.utc),
                    event_end=datetime(2026, 9, 8, 7, 0, tzinfo=timezone.utc),
                    event_payload_json={"coverage": {"data_kind": "bars", "frequency": "1d"}},
                    event_sha256=_sha("calendar-event-duplicate"),
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_observation_migration_upgrades_and_downgrades_sqlite_without_legacy_rewrite(
    tmp_path: Path,
) -> None:
    """The expand-only migration adds normalized tables and leaves legacy facts untouched."""
    database_path = tmp_path / "market-data-observations.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _config(database_url)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, CATALOG_REVISION)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE legacy_market_facts "
                    "(symbol VARCHAR(32) NOT NULL, close NUMERIC NOT NULL)"
                )
            )
            connection.execute(
                text("INSERT INTO legacy_market_facts (symbol, close) VALUES ('600000', 10.5)")
            )

        command.upgrade(config, OBSERVATIONS_REVISION)
        inspector = inspect(engine)
        assert STORAGE_TABLES <= set(inspector.get_table_names())
        assert {
            "uq_md_instrument_lookup_key_active",
            "uq_md_data_series_semantic_key_sha256",
            "uq_md_observation_revision_series_event_number",
        } <= {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("md_observation_revisions")
            if constraint["name"]
        } | {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("md_data_series")
            if constraint["name"]
        } | {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("md_instrument_lookup_keys")
            if constraint["name"]
        }
        assert engine.connect().execute(
            text("SELECT symbol, close FROM legacy_market_facts")
        ).one() == (
            "600000",
            10.5,
        )

        command.downgrade(config, CATALOG_REVISION)
        assert not (STORAGE_TABLES & set(inspect(engine).get_table_names()))
        assert engine.connect().execute(
            text("SELECT symbol, close FROM legacy_market_facts")
        ).one() == (
            "600000",
            10.5,
        )
    finally:
        engine.dispose()


def test_observation_migration_rejects_same_named_wrong_column_contract(tmp_path: Path) -> None:
    """Evidence recovery verifies typed columns before it accepts a pre-created table."""
    database_path = tmp_path / "wrong-observation-columns.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, CATALOG_REVISION)
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE md_instrument_lookup_keys (
                        id VARCHAR(36) PRIMARY KEY,
                        asset_type INTEGER NULL,
                        market VARCHAR(128) NOT NULL,
                        symbol VARCHAR(128) NOT NULL,
                        instrument_id VARCHAR(36) NOT NULL,
                        canonical_id VARCHAR(512) NOT NULL,
                        metadata_version VARCHAR(64) NOT NULL,
                        is_active BOOLEAN NOT NULL,
                        active_lookup_scope VARCHAR(16),
                        valid_from DATETIME NOT NULL,
                        valid_to DATETIME,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )

        with pytest.raises(
            RuntimeError,
            match="MARKET_DATA_OBSERVATIONS_PARTIAL_SCHEMA_UNSAFE",
        ) as unsafe:
            command.upgrade(config, OBSERVATIONS_REVISION)
    finally:
        engine.dispose()

    assert "invalid_columns" in str(unsafe.value)
    assert "asset_type" in str(unsafe.value)


def test_observation_revision_is_linear_child_of_catalog_revision() -> None:
    """The revision remains on the catalog branch and keeps a single Alembic head."""
    script = ScriptDirectory.from_config(_config("sqlite://"))

    revision = script.get_revision(OBSERVATIONS_REVISION)
    assert revision is not None
    assert revision.down_revision == CATALOG_REVISION
    assert len(script.get_heads()) == 1


@pytest.mark.parametrize(
    "database_url",
    [
        "mysql+aiomysql://market_data:fixture@localhost/market_data",
        "postgresql+asyncpg://market_data:fixture@localhost/market_data",
    ],
)
def test_observation_migration_renders_for_supported_server_dialects(database_url: str) -> None:
    """The migration uses portable DDL and never emits a legacy fact-table rewrite."""
    output = StringIO()
    config = _config(database_url)
    config.output_buffer = output

    command.upgrade(
        config,
        f"{CATALOG_REVISION}:{OBSERVATIONS_REVISION}",
        sql=True,
    )

    rendered = output.getvalue()
    assert "CREATE TABLE md_instrument_lookup_keys" in rendered
    assert "CREATE TABLE md_observation_revisions" in rendered
    assert "legacy_market_facts" not in rendered
