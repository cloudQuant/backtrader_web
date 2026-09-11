"""Migration safety contracts for deferred legacy-daily publication holds."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "20260910_market_data_capability_ledger"
REVISION = "20260911_market_data_deferred_publications"
INTEGRATED_HEAD_REVISION = "20260911_market_data_b2_completeness_evidence"
TABLE = "md_publication_release_holds"
UTC = timezone.utc
NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)


def _config(database_path: Path) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    return config


def _hold_values(
    sequence: int,
    *,
    state: str,
    quarantine_code: str | None = None,
    quarantined_at: datetime | None = None,
    promotion_evidence_sha256: str | None = None,
    promoted_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "id": f"hold-{sequence}",
        "publication_id": f"publication-{sequence}",
        "source_snapshot_id": f"snapshot-{sequence}",
        "workflow_kind": "legacy_stock_daily_import",
        "state": state,
        "intent_sha256": "i" * 64,
        "quarantine_code": quarantine_code,
        "quarantined_at": quarantined_at,
        "promotion_evidence_sha256": promotion_evidence_sha256,
        "promoted_at": promoted_at,
        "created_at": NOW,
    }


def test_deferred_publication_revision_is_an_ancestor_of_the_single_alembic_head(
    tmp_path: Path,
) -> None:
    """The additive child remains in the linear graph after the B2 successor."""
    script = ScriptDirectory.from_config(_config(tmp_path / "head.sqlite3"))

    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS_REVISION
    assert script.get_heads() == [INTEGRATED_HEAD_REVISION]


def test_sqlite_upgrade_keeps_evidence_parents_and_enforces_hold_state_contracts(
    tmp_path: Path,
) -> None:
    """The pilot adds only a child table and rejects malformed workflow states."""
    database_path = tmp_path / "deferred-publications.sqlite3"
    config = _config(database_path)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, PREVIOUS_REVISION)
        publication_columns_before = {
            column["name"] for column in inspect(engine).get_columns("md_publications")
        }
        source_snapshot_columns_before = {
            column["name"] for column in inspect(engine).get_columns("md_source_snapshots")
        }

        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, REVISION)
        config.attributes.pop("connection", None)

        inspector = inspect(engine)
        assert publication_columns_before == {
            column["name"] for column in inspector.get_columns("md_publications")
        }
        assert source_snapshot_columns_before == {
            column["name"] for column in inspector.get_columns("md_source_snapshots")
        }
        assert {
            "id",
            "publication_id",
            "source_snapshot_id",
            "workflow_kind",
            "state",
            "intent_sha256",
            "quarantine_code",
            "quarantined_at",
            "promotion_evidence_sha256",
            "promoted_at",
            "created_at",
        } == {column["name"] for column in inspector.get_columns(TABLE)}
        assert {
            constraint["name"]: tuple(constraint.get("column_names") or ())
            for constraint in inspector.get_unique_constraints(TABLE)
            if constraint.get("name")
        } == {
            "uq_md_publication_release_hold_publication": ("publication_id",),
            "uq_md_publication_release_hold_source_snapshot": ("source_snapshot_id",),
        }
        assert {
            index["name"]: (tuple(index.get("column_names") or ()), bool(index.get("unique")))
            for index in inspector.get_indexes(TABLE)
            if index.get("name")
        } == {"ix_md_publication_release_hold_state_created": (("state", "created_at"), False)}
        assert {
            foreign_key["name"]: (
                tuple(foreign_key.get("constrained_columns") or ()),
                foreign_key.get("referred_table"),
                tuple(foreign_key.get("referred_columns") or ()),
                (foreign_key.get("options") or {}).get("ondelete"),
            )
            for foreign_key in inspector.get_foreign_keys(TABLE)
            if foreign_key.get("name")
        } == {
            "fk_md_publication_release_hold_publication": (
                ("publication_id",),
                "md_publications",
                ("id",),
                "RESTRICT",
            ),
            "fk_md_publication_release_hold_source_snapshot": (
                ("source_snapshot_id",),
                "md_source_snapshots",
                ("id",),
                "RESTRICT",
            ),
        }

        holds = sa.Table(TABLE, sa.MetaData(), autoload_with=engine)
        valid_rows = (
            _hold_values(1, state="DEFERRED"),
            _hold_values(
                2,
                state="QUARANTINED",
                quarantine_code="SOURCE_SCHEMA_MISMATCH",
                quarantined_at=NOW,
            ),
            _hold_values(
                3,
                state="PROMOTED",
                promotion_evidence_sha256="p" * 64,
                promoted_at=NOW,
            ),
        )
        with engine.begin() as connection:
            connection.execute(holds.insert(), valid_rows)

        invalid_rows = (
            _hold_values(
                4,
                state="DEFERRED",
                quarantine_code="NOT_ALLOWED",
                quarantined_at=NOW,
            ),
            _hold_values(5, state="QUARANTINED", quarantined_at=NOW),
            _hold_values(
                6,
                state="QUARANTINED",
                quarantine_code="MISMATCH",
                quarantined_at=NOW,
                promotion_evidence_sha256="p" * 64,
                promoted_at=NOW,
            ),
            _hold_values(7, state="PROMOTED", promoted_at=NOW),
            _hold_values(
                8,
                state="PROMOTED",
                quarantine_code="MISMATCH",
                quarantined_at=NOW,
                promotion_evidence_sha256="p" * 64,
                promoted_at=NOW,
            ),
            _hold_values(9, state="DEFERRED") | {"intent_sha256": "short"},
            _hold_values(
                10,
                state="PROMOTED",
                promotion_evidence_sha256="short",
                promoted_at=NOW,
            ),
        )
        for values in invalid_rows:
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(holds.insert().values(**values))

        # SQLite does not enforce declared foreign keys unless each connection
        # opts in. Verify the actual child-table contract with enforcement on;
        # reflection above alone cannot prove an orphan receipt is rejected.
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            with pytest.raises(IntegrityError):
                connection.execute(holds.insert().values(**_hold_values(11, state="DEFERRED")))
            connection.rollback()
    finally:
        config.attributes.pop("connection", None)
        engine.dispose()


def test_sqlite_downgrade_blocks_populated_hold_and_allows_empty_round_trip(tmp_path: Path) -> None:
    """A real hold is never silently erased, while an empty pilot can roll back."""
    database_path = tmp_path / "deferred-publications-downgrade.sqlite3"
    config = _config(database_path)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, REVISION)
        holds = sa.Table(TABLE, sa.MetaData(), autoload_with=engine)
        with engine.begin() as connection:
            connection.execute(holds.insert().values(**_hold_values(1, state="DEFERRED")))

        with pytest.raises(
            RuntimeError, match="MARKET_DATA_PUBLICATION_RELEASE_HOLD_DOWNGRADE_BLOCKED"
        ):
            command.downgrade(config, PREVIOUS_REVISION)
        with engine.connect() as connection:
            assert connection.scalar(text(f"SELECT COUNT(*) FROM {TABLE}")) == 1

        with engine.begin() as connection:
            connection.execute(holds.delete())
        command.downgrade(config, PREVIOUS_REVISION)
        assert TABLE not in set(inspect(engine).get_table_names())

        command.upgrade(config, REVISION)
        assert TABLE in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
