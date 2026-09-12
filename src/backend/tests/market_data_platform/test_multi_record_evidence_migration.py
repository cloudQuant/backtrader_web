"""Migration contracts for durable B2 completeness evidence."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_HEAD_REVISION = "20260911_market_data_semantic_record_keys"
B2_COMPLETENESS_EVIDENCE_REVISION = "20260911_market_data_b2_completeness_evidence"
RECEIPTS_TABLE = "md_b2_completeness_receipts"
ENTRIES_TABLE = "md_b2_completeness_manifest_entries"


def _config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _uniques(engine, table_name: str) -> dict[str, tuple[str, ...]]:
    return {
        str(item["name"]): tuple(str(column) for column in item.get("column_names") or ())
        for item in inspect(engine).get_unique_constraints(table_name)
        if item.get("name")
    }


def test_b2_completeness_evidence_migration_creates_immutable_parent_child_tables(
    tmp_path: Path,
) -> None:
    """The revision creates both tables, hashes, FKs, and an empty rollback path."""
    database_path = tmp_path / "b2-completeness-evidence.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, PREVIOUS_HEAD_REVISION)
        command.upgrade(config, B2_COMPLETENESS_EVIDENCE_REVISION)

        inspector = inspect(engine)
        assert inspector.has_table(RECEIPTS_TABLE)
        assert inspector.has_table(ENTRIES_TABLE)
        assert {
            "id",
            "series_id",
            "source_snapshot_id",
            "family_id",
            "family_contract_version",
            "selector_kind",
            "event_at",
            "selector_dimensions_json",
            "selector_digest",
            "manifest_sha256",
            "expected_record_count",
            "zero_record_evidence_sha256",
            "receipt_sha256",
            "created_at",
        } == {column["name"] for column in inspector.get_columns(RECEIPTS_TABLE)}
        assert {"receipt_id", "semantic_record_key_sha256", "created_at"} == {
            column["name"] for column in inspector.get_columns(ENTRIES_TABLE)
        }
        assert _uniques(engine, RECEIPTS_TABLE) == {
            "uq_md_b2_completeness_receipt_series_event_selector": (
                "series_id",
                "event_at",
                "selector_digest",
            ),
            "uq_md_b2_completeness_receipt_sha256": ("receipt_sha256",),
        }
        assert {
            item["name"]: (
                tuple(item.get("constrained_columns") or ()),
                item.get("referred_table"),
                tuple(item.get("referred_columns") or ()),
                (item.get("options") or {}).get("ondelete"),
            )
            for item in inspector.get_foreign_keys(ENTRIES_TABLE)
        } == {
            "fk_md_b2_completeness_entry_receipt": (
                ("receipt_id",),
                RECEIPTS_TABLE,
                ("id",),
                "RESTRICT",
            )
        }
        command.downgrade(config, PREVIOUS_HEAD_REVISION)
        assert not inspect(engine).has_table(RECEIPTS_TABLE)
        assert not inspect(engine).has_table(ENTRIES_TABLE)
    finally:
        engine.dispose()


def test_b2_completeness_evidence_migration_accepts_complete_orm_startup_schema(
    tmp_path: Path,
) -> None:
    """A startup-created current schema can be stamped at the predecessor safely."""
    import app.models.market_data_platform  # noqa: F401
    from app.db.database import Base

    database_path = tmp_path / "b2-completeness-startup-schema.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        Base.metadata.create_all(engine)
        command.stamp(config, PREVIOUS_HEAD_REVISION)
        command.upgrade(config, B2_COMPLETENESS_EVIDENCE_REVISION)
        assert {RECEIPTS_TABLE, ENTRIES_TABLE} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_b2_completeness_evidence_migration_rejects_a_child_only_partial_schema(
    tmp_path: Path,
) -> None:
    """A same-named child table cannot make the migration skip its parent receipt."""
    database_path = tmp_path / "b2-completeness-partial-schema.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, PREVIOUS_HEAD_REVISION)
        with engine.begin() as connection:
            connection.execute(text(f"CREATE TABLE {ENTRIES_TABLE} (receipt_id VARCHAR(36))"))

        with pytest.raises(RuntimeError, match="MARKET_DATA_B2_COMPLETENESS_EVIDENCE_SCHEMA_DRIFT"):
            command.upgrade(config, B2_COMPLETENESS_EVIDENCE_REVISION)
    finally:
        engine.dispose()


def test_b2_completeness_evidence_migration_rejects_a_weakened_startup_unique(
    tmp_path: Path,
) -> None:
    """A same-named receipt table without exact selector uniqueness is never accepted."""
    database_path = tmp_path / "b2-completeness-weakened-unique.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, B2_COMPLETENESS_EVIDENCE_REVISION)
        with engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            with operations.batch_alter_table(RECEIPTS_TABLE, recreate="always") as batch:
                batch.drop_constraint(
                    "uq_md_b2_completeness_receipt_series_event_selector",
                    type_="unique",
                )

        command.stamp(config, PREVIOUS_HEAD_REVISION)
        with pytest.raises(RuntimeError, match="MARKET_DATA_B2_COMPLETENESS_EVIDENCE_SCHEMA_DRIFT"):
            command.upgrade(config, B2_COMPLETENESS_EVIDENCE_REVISION)
    finally:
        engine.dispose()


def test_b2_completeness_evidence_downgrade_refuses_to_drop_nonempty_evidence(
    tmp_path: Path,
) -> None:
    """Rollback cannot erase a durable selector receipt after it was issued."""
    database_path = tmp_path / "b2-completeness-nonempty-downgrade.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, B2_COMPLETENESS_EVIDENCE_REVISION)
        with engine.begin() as connection:
            # The downgrade contract is about immutable-row existence.  This
            # migration test intentionally exercises that check independently
            # of parent-row fixtures; relational shape is asserted above.
            connection.execute(sa.text("PRAGMA foreign_keys=OFF"))
            connection.execute(
                text(
                    f"INSERT INTO {RECEIPTS_TABLE} "
                    "(id, series_id, source_snapshot_id, family_id, family_contract_version, "
                    "selector_kind, event_at, selector_dimensions_json, selector_digest, "
                    "manifest_sha256, expected_record_count, zero_record_evidence_sha256, "
                    "receipt_sha256, created_at) VALUES "
                    "('receipt-1', 'series-1', 'source-1', 'option.derivative', "
                    "'market-data-family-v1', 'slice', '2026-09-11 10:00:00', '{}', "
                    ":selector_digest, :manifest_sha256, 1, NULL, :receipt_sha256, "
                    "'2026-09-11 10:00:00')"
                ),
                {
                    "selector_digest": "a" * 64,
                    "manifest_sha256": "b" * 64,
                    "receipt_sha256": "c" * 64,
                },
            )

        with pytest.raises(
            RuntimeError,
            match="MARKET_DATA_B2_COMPLETENESS_EVIDENCE_DOWNGRADE_BLOCKED",
        ):
            command.downgrade(config, PREVIOUS_HEAD_REVISION)
    finally:
        engine.dispose()


def test_b2_completeness_evidence_revision_extends_the_only_integrated_head() -> None:
    """The durable B2 evidence table pair remains the current single-head extension."""
    script = ScriptDirectory.from_config(_config("sqlite://"))

    revision = script.get_revision(B2_COMPLETENESS_EVIDENCE_REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS_HEAD_REVISION
    assert script.get_heads() == [B2_COMPLETENESS_EVIDENCE_REVISION]


def test_b2_evidence_normalizer_accepts_mysql_clause_parentheses() -> None:
    """MySQL 9 parenthesises every boolean clause of a reflected CHECK.

    ``(a) and (b)`` / ``(a) or (b)`` reflections of the reviewed linear
    boolean checks must compare equal to their authored sources, while a
    genuinely different bound still differs.
    """
    import importlib.util
    from pathlib import Path

    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260911_market_data_b2_completeness_evidence.py"
    )
    spec = importlib.util.spec_from_file_location(
        "iteration197_b2_evidence_migration_module", migration_path
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    authored = "zero_record_evidence_sha256 IS NULL OR length(zero_record_evidence_sha256) = 64"
    mysql_reflected = (
        "(`zero_record_evidence_sha256` is null) or (length(`zero_record_evidence_sha256`) = 64)"
    )
    assert migration._normalized_expression(mysql_reflected) == migration._normalized_expression(
        authored
    )

    drifted = (
        "(`zero_record_evidence_sha256` is null) or (length(`zero_record_evidence_sha256`) = 63)"
    )
    assert migration._normalized_expression(drifted) != migration._normalized_expression(authored)

    # A string-literal check reflects with charset introducers on MySQL.
    authored_kind = "selector_kind IN ('slice', 'report')"
    mysql_kind = "(`selector_kind` in (_utf8mb4'slice',_utf8mb4'report'))"
    assert migration._normalized_expression(mysql_kind) == migration._normalized_expression(
        authored_kind
    )
