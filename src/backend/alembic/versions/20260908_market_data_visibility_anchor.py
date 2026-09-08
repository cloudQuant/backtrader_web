"""Add a complete global visibility anchor for market-data publication receipts.

Revision ID: 20260908_market_data_visibility_anchor
Revises: 20260908_market_data_shared_dataset_bindings
Create Date: 2026-09-08

Existing sealed receipts are assigned a deterministic sequence by their legacy
visibility time and immutable receipt ID.  The migration does not alter any
legacy AkShare table or market-data entity payload; it only makes receipt order
explicit and creates the singleton allocator used by future post-commit seals.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import context, op

revision = "20260908_market_data_visibility_anchor"
down_revision = "20260908_market_data_shared_dataset_bindings"
branch_labels = None
depends_on = None

_PUBLICATIONS_TABLE = "md_publications"
_ALLOCATOR_TABLE = "md_visibility_sequence_allocator"
_VISIBILITY_SEQUENCE_INDEX = "uq_md_publication_visibility_sequence"
_VISIBLE_ANCHOR_INDEX = "ix_md_publication_visible_anchor"
_VISIBILITY_SEQUENCE_CHECK = "ck_md_publication_visibility_sequence_positive"
_VISIBILITY_STATE_CHECK = "ck_md_publication_visibility_state"
_PIT_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")
_MYSQL_MAINTENANCE_FENCE_ENV = "MARKET_DATA_VISIBILITY_ANCHOR_MAINTENANCE_FENCE"
_MYSQL_MIGRATION_LOCK_NAME = "ai_for_investor.market_data.visibility_anchor"
_LOCK_TIMEOUT_SECONDS = 5


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_offline() -> bool:
    return context.is_offline_mode()


def _normalized_check_expression(expression: object) -> str:
    return "".join(str(expression).split()).lower()


def _publication_columns(bind: sa.Connection) -> dict[str, dict[str, object]]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_PUBLICATIONS_TABLE):
        raise RuntimeError(
            "MARKET_DATA_VISIBILITY_ANCHOR_SCHEMA_UNREADY: md_publications missing"
        )
    return {str(column["name"]): column for column in inspector.get_columns(_PUBLICATIONS_TABLE)}


def _ensure_visibility_sequence_column(bind: sa.Connection) -> None:
    """Add the new nullable transition column exactly once.

    ``Base.metadata.create_all`` can predate Alembic stamping in local and
    development installs.  Accept that complete startup-created column, but
    fail closed on an incompatible hand-made substitute.
    """
    columns = _publication_columns(bind)
    existing = columns.get("visibility_sequence")
    if existing is None:
        op.add_column(
            _PUBLICATIONS_TABLE,
            sa.Column("visibility_sequence", sa.BigInteger(), nullable=True),
        )
        return
    if (
        existing["type"]._type_affinity is not sa.Integer
        or not bool(existing.get("nullable"))
    ):
        raise RuntimeError(
            "MARKET_DATA_VISIBILITY_ANCHOR_SCHEMA_DRIFT: "
            "md_publications.visibility_sequence"
        )


def _backfill_sealed_visibility_sequences(bind: sa.Connection) -> tuple[int, object | None]:
    """Assign a deterministic order or validate a pre-created complete column."""
    metadata = sa.MetaData()
    publications = sa.Table(_PUBLICATIONS_TABLE, metadata, autoload_with=bind)
    rows = list(
        bind.execute(
            sa.select(
                publications.c.id,
                publications.c.published_at,
                publications.c.visibility_sequence,
            )
            .where(publications.c.published_at.is_not(None))
            .order_by(publications.c.published_at, publications.c.id)
        ).mappings()
    )
    invalid_pending = bind.execute(
        sa.select(publications.c.id)
        .where(
            publications.c.published_at.is_(None),
            publications.c.visibility_sequence.is_not(None),
        )
        .limit(1)
    ).scalar()
    if invalid_pending is not None:
        raise RuntimeError(
            "MARKET_DATA_VISIBILITY_SEQUENCE_STATE_INVALID: pending receipt has a sequence"
        )
    existing_sequences = [row["visibility_sequence"] for row in rows]
    if any(sequence is not None for sequence in existing_sequences):
        if any(sequence is None for sequence in existing_sequences):
            raise RuntimeError(
                "MARKET_DATA_VISIBILITY_SEQUENCE_MIXED_BACKFILL_UNSAFE"
            )
        normalized = [int(sequence) for sequence in existing_sequences]
        if any(sequence < 1 for sequence in normalized) or len(set(normalized)) != len(normalized):
            raise RuntimeError("MARKET_DATA_VISIBILITY_SEQUENCE_EXISTING_INVALID")
        ordered_by_sequence = sorted(rows, key=lambda row: int(row["visibility_sequence"]))
        if any(
            earlier["published_at"] > later["published_at"]
            for earlier, later in zip(ordered_by_sequence, ordered_by_sequence[1:], strict=False)
        ):
            raise RuntimeError("MARKET_DATA_VISIBILITY_SEQUENCE_TIME_ORDER_INVALID")
        last = ordered_by_sequence[-1] if ordered_by_sequence else None
        return (max(normalized) + 1 if normalized else 1), (
            last["published_at"] if last is not None else None
        )
    for sequence, row in enumerate(rows, start=1):
        result = bind.execute(
            publications.update()
            .where(
                publications.c.id == row["id"],
                publications.c.visibility_sequence.is_(None),
            )
            .values(visibility_sequence=sequence)
        )
        if result.rowcount != 1:
            raise RuntimeError("MARKET_DATA_VISIBILITY_SEQUENCE_BACKFILL_CONFLICT")
    return len(rows) + 1, (rows[-1]["published_at"] if rows else None)


def _ensure_publication_checks(bind: sa.Connection) -> None:
    desired = {
        _VISIBILITY_SEQUENCE_CHECK: "visibility_sequence IS NULL OR visibility_sequence >= 1",
        _VISIBILITY_STATE_CHECK: (
            "(published_at IS NULL AND visibility_sequence IS NULL) OR "
            "(published_at IS NOT NULL AND visibility_sequence >= 1)"
        ),
    }
    observed = {
        str(check["name"]): _normalized_check_expression(check.get("sqltext", ""))
        for check in sa.inspect(bind).get_check_constraints(_PUBLICATIONS_TABLE)
        if check.get("name")
    }
    missing: dict[str, str] = {}
    for name, expression in desired.items():
        actual = observed.get(name)
        expected = _normalized_check_expression(expression)
        if actual is None:
            missing[name] = expression
        elif actual != expected:
            raise RuntimeError(
                "MARKET_DATA_VISIBILITY_ANCHOR_SCHEMA_DRIFT: "
                f"{name}={actual!r}"
            )
    if missing:
        # SQLite requires a reflected batch rebuild for named CHECKs.
        with op.batch_alter_table(_PUBLICATIONS_TABLE) as batch:
            for name, expression in missing.items():
                batch.create_check_constraint(name, expression)


def _ensure_index(
    bind: sa.Connection,
    *,
    name: str,
    columns: tuple[str, ...],
    unique: bool,
) -> None:
    inspector = sa.inspect(bind)
    indexes = {
        str(index["name"]): (
            tuple(str(column) for column in index.get("column_names") or ()),
            bool(index.get("unique")),
        )
        for index in inspector.get_indexes(_PUBLICATIONS_TABLE)
        if index.get("name")
    }
    uniques = {
        str(constraint["name"]): tuple(
            str(column) for column in constraint.get("column_names") or ()
        )
        for constraint in inspector.get_unique_constraints(_PUBLICATIONS_TABLE)
        if constraint.get("name")
    }
    expected = (columns, unique)
    if name in indexes:
        if indexes[name] != expected:
            raise RuntimeError(
                "MARKET_DATA_VISIBILITY_ANCHOR_SCHEMA_DRIFT: "
                f"{name}={indexes[name]!r}"
            )
        return
    if unique and name in uniques:
        if uniques[name] != columns:
            raise RuntimeError(
                "MARKET_DATA_VISIBILITY_ANCHOR_SCHEMA_DRIFT: "
                f"{name}={uniques[name]!r}"
            )
        return
    op.create_index(name, _PUBLICATIONS_TABLE, list(columns), unique=unique)


def _ensure_allocator(
    bind: sa.Connection,
    *,
    next_sequence: int,
    last_visible_at: object | None,
) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_ALLOCATOR_TABLE):
        op.create_table(
            _ALLOCATOR_TABLE,
            sa.Column("singleton_id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("next_visibility_sequence", sa.BigInteger(), nullable=False),
            sa.Column("last_visible_at", _PIT_DATETIME, nullable=True),
            sa.Column("created_at", _PIT_DATETIME, nullable=False),
            sa.CheckConstraint(
                "singleton_id = 1",
                name="ck_md_visibility_sequence_allocator_singleton",
            ),
            sa.CheckConstraint(
                "next_visibility_sequence >= 1",
                name="ck_md_visibility_sequence_allocator_next_positive",
            ),
        )
    allocator = sa.Table(_ALLOCATOR_TABLE, sa.MetaData(), autoload_with=bind)
    rows = list(
        bind.execute(
            sa.select(
                allocator.c.singleton_id,
                allocator.c.next_visibility_sequence,
                allocator.c.last_visible_at,
            )
        ).mappings()
    )
    if not rows:
        bind.execute(
            allocator.insert().values(
                singleton_id=1,
                next_visibility_sequence=next_sequence,
                last_visible_at=last_visible_at,
                created_at=_utc_now(),
            )
        )
        return
    if len(rows) != 1 or rows[0]["singleton_id"] != 1:
        raise RuntimeError("MARKET_DATA_VISIBILITY_ALLOCATOR_STATE_INVALID")
    if int(rows[0]["next_visibility_sequence"]) < next_sequence:
        raise RuntimeError("MARKET_DATA_VISIBILITY_ALLOCATOR_STATE_INVALID")


@contextmanager
def _ddl_maintenance_fence() -> Iterator[None]:
    """Serialize migration DDL and drain old MySQL writers before backfill."""
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    if dialect_name == "postgresql":
        bind.execute(sa.text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT_SECONDS}s'"))
        yield
        return
    if dialect_name != "mysql":
        yield
        return
    if os.getenv(_MYSQL_MAINTENANCE_FENCE_ENV) != "confirmed":
        raise RuntimeError(
            "MARKET_DATA_VISIBILITY_ANCHOR_MAINTENANCE_FENCE_REQUIRED: "
            "stop market-data writers and set "
            f"{_MYSQL_MAINTENANCE_FENCE_ENV}=confirmed before MySQL DDL"
        )
    bind.execute(sa.text(f"SET SESSION lock_wait_timeout = {_LOCK_TIMEOUT_SECONDS}"))
    acquired = bind.execute(
        sa.text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
        {"lock_name": _MYSQL_MIGRATION_LOCK_NAME, "timeout_seconds": _LOCK_TIMEOUT_SECONDS},
    ).scalar_one()
    if acquired != 1:
        raise RuntimeError(
            "MARKET_DATA_VISIBILITY_ANCHOR_MIGRATION_LOCK_UNAVAILABLE: "
            "could not acquire the migration fence"
        )
    try:
        yield
    finally:
        bind.execute(sa.text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": _MYSQL_MIGRATION_LOCK_NAME})


def _assert_downgrade_safe(bind: sa.Connection) -> None:
    columns = _publication_columns(bind)
    if "visibility_sequence" not in columns:
        return
    publications = sa.Table(_PUBLICATIONS_TABLE, sa.MetaData(), autoload_with=bind)
    sealed = bind.execute(
        sa.select(publications.c.id)
        .where(
            publications.c.published_at.is_not(None),
            publications.c.visibility_sequence.is_not(None),
        )
        .limit(1)
    ).scalar()
    if sealed is not None:
        raise RuntimeError(
            "MARKET_DATA_VISIBILITY_ANCHOR_DOWNGRADE_BLOCKED: "
            "sealed receipt order is immutable evidence"
        )


def upgrade() -> None:
    """Backfill receipt order and install the durable global allocator."""
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_VISIBILITY_ANCHOR_OFFLINE_UNSUPPORTED: "
            "the receipt-sequence backfill requires an online database connection"
        )
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        _ensure_visibility_sequence_column(bind)
        next_sequence, last_visible_at = _backfill_sealed_visibility_sequences(bind)
        _ensure_publication_checks(bind)
        _ensure_index(
            bind,
            name=_VISIBILITY_SEQUENCE_INDEX,
            columns=("visibility_sequence",),
            unique=True,
        )
        _ensure_index(
            bind,
            name=_VISIBLE_ANCHOR_INDEX,
            columns=("published_at", "visibility_sequence"),
            unique=False,
        )
        _ensure_allocator(
            bind,
            next_sequence=next_sequence,
            last_visible_at=last_visible_at,
        )


def downgrade() -> None:
    """Remove only the derived receipt-order machinery."""
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_VISIBILITY_ANCHOR_DOWNGRADE_OFFLINE_UNSUPPORTED: "
            "dropping a populated receipt column requires an online connection"
        )
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        _assert_downgrade_safe(bind)
        inspector = sa.inspect(bind)
        if inspector.has_table(_ALLOCATOR_TABLE):
            op.drop_table(_ALLOCATOR_TABLE)
        if "visibility_sequence" not in _publication_columns(bind):
            return
        indexes = {
            str(index["name"])
            for index in inspector.get_indexes(_PUBLICATIONS_TABLE)
            if index.get("name")
        }
        uniques = {
            str(constraint["name"])
            for constraint in inspector.get_unique_constraints(_PUBLICATIONS_TABLE)
            if constraint.get("name")
        }
        checks = {
            str(check["name"])
            for check in inspector.get_check_constraints(_PUBLICATIONS_TABLE)
            if check.get("name")
        }
        with op.batch_alter_table(_PUBLICATIONS_TABLE) as batch:
            if _VISIBLE_ANCHOR_INDEX in indexes:
                batch.drop_index(_VISIBLE_ANCHOR_INDEX)
            if _VISIBILITY_SEQUENCE_INDEX in indexes:
                batch.drop_index(_VISIBILITY_SEQUENCE_INDEX)
            elif _VISIBILITY_SEQUENCE_INDEX in uniques:
                batch.drop_constraint(_VISIBILITY_SEQUENCE_INDEX, type_="unique")
            for constraint_name in (_VISIBILITY_STATE_CHECK, _VISIBILITY_SEQUENCE_CHECK):
                if constraint_name in checks:
                    batch.drop_constraint(constraint_name, type_="check")
            batch.drop_column("visibility_sequence")
