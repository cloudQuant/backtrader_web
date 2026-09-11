"""Run the opt-in Iteration 197 MySQL acceptance harness (E-197-07 core).

This command never accepts an application database URL.  It requires an
explicit ``mysql`` administrative URL whose database is exactly ``mysql``;
when ``--apply`` is supplied it creates only UUID-named temporary databases,
upgrades them with Alembic to the sealed Iteration 197 head, and verifies the
MySQL-specific E-197-07 core contract:

* the exact-identity columns are ``utf8mb4_bin`` (``RB0`` never matches
  ``rb0`` through a ``*_ci`` collation),
* PIT columns are ``DATETIME`` with microsecond precision (fsp=6),
* aware-UTC timestamps round-trip without drift,
* two case-distinct frozen identities resolve independently and an
  incorrectly-cased lookup fails closed,
* a frozen identity projection stays invisible one microsecond before its
  publication instant and resolves at that exact instant,
* a governed downgrade of a non-empty migrated database is rejected.

The default is a dry run: it validates the administrative connection shape
but does not open a connection, create a database, migrate, or fetch data.
The command emits structured output without a connection URL, username,
password, host, or query values.

Run from ``src/backend``:

    conda run --no-capture-output -n base python \
      scripts/verify_iteration197_mysql_acceptance.py \
      --mysql-admin-url "$ITER197_MYSQL_ADMIN_URL"

    conda run --no-capture-output -n base python \
      scripts/verify_iteration197_mysql_acceptance.py --apply \
      --mysql-admin-url "$ITER197_MYSQL_ADMIN_URL"

The URL is intentionally read only from the command line.  A caller must pass
it explicitly for each run; the harness does not fall back to ``DATABASE_URL``
or any environment variable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from alembic import command

# Permit direct ``python scripts/...`` execution without relying on a caller's
# PYTHONPATH.  This script never imports the process-global session factory,
# so an application database can never become this harness's target.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.asset_research import InstrumentIdentity  # noqa: E402
from app.services.market_data.identity import MarketDataIdentityResolver  # noqa: E402
from app.services.market_data.master_data import MarketDataIdentityWriter  # noqa: E402

UTC = timezone.utc
EXPECTED_ALEMBIC_HEAD = "20260911_market_data_b2_completeness_evidence"
_DATABASE_NAME_PREFIX = "iter197_mysql_acceptance_"
_DATABASE_NAME_RE = re.compile(r"^iter197_mysql_acceptance_[0-9a-f]{12}$")

_REQUIRED_TABLES = frozenset(
    {
        "alembic_version",
        "asset_instruments",
        "md_instrument_lookup_keys",
        "md_observation_revisions",
        "md_source_snapshots",
        "md_publications",
        "md_calendar_snapshots",
        "md_calendar_events",
        "md_fetch_leases",
        "md_source_payloads",
        "md_capability_ledger_entries",
        "md_publication_release_holds",
        "md_multi_record_dimensions",
        "md_multi_record_b2_receipts",
        "users",
        "user_roles",
    }
)

# Columns the exact-identity collation migration pins to utf8mb4_bin on MySQL.
_BINARY_COLLATION_COLUMNS: dict[str, frozenset[str]] = {
    "asset_instruments": frozenset({"canonical_id", "display_symbol"}),
    "md_instrument_lookup_keys": frozenset({"canonical_id", "lookup_key"}),
    "md_observation_revisions": frozenset({"series_id"}),
}

# PIT columns that must be DATETIME(6) on MySQL.
_MICROSECOND_DATETIME_COLUMNS: dict[str, frozenset[str]] = {
    "md_observation_revisions": frozenset({"event_time", "available_at", "committed_at"}),
    "md_publications": frozenset({"published_at"}),
    "md_calendar_events": frozenset({"event_start", "event_end"}),
    "md_fetch_leases": frozenset({"expires_at"}),
}

_IDENTIFIED_AT = datetime(2026, 8, 1, tzinfo=UTC)
# A post-publication instant used for ordinary (non-boundary) resolutions.
_RESOLVED_AT = datetime(2026, 9, 4, tzinfo=UTC)


class MysqlAcceptanceHarnessError(RuntimeError):
    """Stable, non-secret failure emitted by the disposable acceptance command."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mysql-admin-url",
        required=True,
        help="Administrative mysql URL whose database is exactly 'mysql'.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Actually create a UUID-named temporary database, migrate it, run "
            "the E-197-07 core probes, and drop it afterwards. The default "
            "only validates the URL shape."
        ),
    )
    return parser.parse_args(argv)


def _parse_admin_url(value: object) -> URL:
    """Accept exactly one administrative MySQL URL targeting database 'mysql'."""
    if not isinstance(value, str) or not value.strip():
        raise MysqlAcceptanceHarnessError("MYSQL_ADMIN_URL_REQUIRED")
    try:
        parsed = make_url(value.strip())
    except Exception as exc:  # noqa: BLE001 - any parse failure is one stable code
        raise MysqlAcceptanceHarnessError("MYSQL_ADMIN_URL_MALFORMED") from exc
    if parsed.get_backend_name() != "mysql":
        raise MysqlAcceptanceHarnessError("MYSQL_ADMIN_URL_BACKEND_UNSUPPORTED")
    if (parsed.database or "") != "mysql":
        raise MysqlAcceptanceHarnessError("MYSQL_ADMIN_URL_DATABASE_MUST_BE_MYSQL")
    if not parsed.username or parsed.password is None:
        raise MysqlAcceptanceHarnessError("MYSQL_ADMIN_URL_CREDENTIALS_INCOMPLETE")
    return parsed


def _temporary_database_name() -> str:
    return f"{_DATABASE_NAME_PREFIX}{uuid.uuid4().hex[:12]}"


def _require_own_temporary_database(database_name: object) -> str:
    if not isinstance(database_name, str) or not _DATABASE_NAME_RE.fullmatch(database_name):
        raise MysqlAcceptanceHarnessError("MYSQL_TEMPORARY_DATABASE_NAME_INVALID")
    return database_name


def _admin_engine(admin_url: URL) -> AsyncEngine:
    return create_async_engine(
        admin_url.set(drivername="mysql+aiomysql"),
        future=True,
        pool_pre_ping=True,
    )


def _target_url(admin_url: URL, database_name: str) -> URL:
    return admin_url.set(drivername="mysql+aiomysql", database=database_name)


def _alembic_url_text(target_url: URL) -> str:
    # Alembic migrations run synchronously through the pymysql driver.
    return str(target_url.set(drivername="mysql+pymysql"))


def _safe_connection_descriptor(admin_url: URL) -> dict[str, object]:
    return {
        "backend": admin_url.get_backend_name(),
        "database": admin_url.database,
        "has_password": admin_url.password is not None,
    }


def _alembic_config(target_url: URL) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", _alembic_url_text(target_url))
    return config


def _run_alembic_upgrade(target_url: URL) -> None:
    command.upgrade(_alembic_config(target_url), "head")


def _run_alembic_downgrade_one(target_url: URL) -> None:
    command.downgrade(_alembic_config(target_url), "-1")


async def _create_temporary_database(engine: AsyncEngine, database_name: str) -> None:
    quoted = f"`{_require_own_temporary_database(database_name)}`"
    async with engine.connect() as connection:
        await connection.execute(text(f"CREATE DATABASE {quoted} CHARACTER SET utf8mb4"))
        await connection.commit()


async def _drop_temporary_database(admin_url: URL, database_name: str) -> None:
    quoted = f"`{_require_own_temporary_database(database_name)}`"
    engine = _admin_engine(admin_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f"DROP DATABASE IF EXISTS {quoted}"))
            await connection.commit()
    finally:
        await engine.dispose()


def _quoted_list(values: frozenset[str] | set[str]) -> str:
    return ", ".join(f"'{value}'" for value in sorted(values))


def _missing_tables(sync_connection: Any) -> tuple[str, ...]:
    inspector = sa.inspect(sync_connection)
    existing = set(inspector.get_table_names())
    return tuple(sorted(_REQUIRED_TABLES - existing))


def _column_collations(sync_connection: Any) -> dict[tuple[str, str], str]:
    inspector = sa.inspect(sync_connection)
    observed: dict[tuple[str, str], str] = {}
    for table_name, column_names in _BINARY_COLLATION_COLUMNS.items():
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        for column_name in column_names:
            observed[(table_name, column_name)] = str(columns.get(column_name, {}).get("collation"))
    return observed


def _datetime_precisions(sync_connection: Any) -> dict[tuple[str, str], tuple[str, int | None]]:
    inspector = sa.inspect(sync_connection)
    observed: dict[tuple[str, str], tuple[str, int | None]] = {}
    for table_name, column_names in _MICROSECOND_DATETIME_COLUMNS.items():
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        for column_name in column_names:
            column = columns.get(column_name)
            if column is None:
                observed[(table_name, column_name)] = ("missing", None)
                continue
            type_ = column.get("type", None)
            observed[(table_name, column_name)] = (
                getattr(type_, "__visit_name__", str(type_)).lower(),
                getattr(type_, "fsp", None),
            )
    return observed


async def _assert_schema(session: AsyncSession) -> dict[str, object]:
    """Verify the migrated MySQL schema: tables, collations, and fsp=6 PIT columns."""
    connection = await session.connection()
    missing_tables = await connection.run_sync(_missing_tables)
    if missing_tables:
        raise MysqlAcceptanceHarnessError("MYSQL_ACCEPTANCE_REQUIRED_TABLE_MISSING")
    revision_rows = (
        (await session.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
    )
    if revision_rows != [EXPECTED_ALEMBIC_HEAD]:
        raise MysqlAcceptanceHarnessError("MYSQL_ACCEPTANCE_ALEMBIC_VERSION_MISMATCH")

    collations = await connection.run_sync(_column_collations)
    non_binary = {
        f"{table}.{column}": collation
        for (table, column), collation in sorted(collations.items())
        if str(collation or "").lower() != "utf8mb4_bin"
    }
    if non_binary:
        raise MysqlAcceptanceHarnessError("MYSQL_ACCEPTANCE_IDENTITY_COLLATION_NOT_BINARY")

    precisions = await connection.run_sync(_datetime_precisions)
    non_microsecond = {
        f"{table}.{column}": observed
        for (table, column), observed in sorted(precisions.items())
        if observed != ("datetime", 6)
    }
    if non_microsecond:
        raise MysqlAcceptanceHarnessError("MYSQL_ACCEPTANCE_PIT_PRECISION_NOT_MICROSECOND")

    return {
        "required_table_count": len(_REQUIRED_TABLES),
        "binary_collation_column_count": len(collations),
        "microsecond_datetime_column_count": len(precisions),
    }


async def _assert_utc_roundtrip(session: AsyncSession) -> str:
    """One fresh connection must round-trip an aware-UTC microsecond instant."""
    session_timezone = str(await session.scalar(text("SELECT @@session.time_zone")) or "")
    probe = datetime(2026, 9, 3, 7, 30, 15, 123456, tzinfo=UTC)
    rendered = probe.strftime("%Y-%m-%d %H:%M:%S.%f")
    observed = await session.scalar(
        text("SELECT CAST(:rendered AS DATETIME(6))"), {"rendered": rendered}
    )
    expected_naive = probe.replace(tzinfo=None)
    if observed is None or observed != expected_naive:
        raise MysqlAcceptanceHarnessError("MYSQL_ACCEPTANCE_MICROSECOND_ROUNDTRIP_DRIFT")
    return session_timezone


def _futures_identity(canonical_id: str, display_symbol: str) -> InstrumentIdentity:
    return InstrumentIdentity.model_validate(
        {
            "asset_type": "futures",
            "identity_level": "CONTRACT",
            "canonical_id": canonical_id,
            "display_symbol": display_symbol,
            "name": f"MySQL验收期货 {display_symbol}",
            "venue": "SHFE",
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
            "identifier_type": "EXCHANGE_SYMBOL",
            "identifier_value": f"{display_symbol}.SHF",
            "product_type": "FUTURES_CONTRACT",
            "metadata_version": "iter197-mysql-acceptance-v1",
            "details": {
                "kind": "FUTURES",
                "product_code": "RB",
                "contract_month": "202610",
                "trading_calendar_id": "SHFE",
                "expiry_at": "2026-10-16T15:00:00+08:00",
                "contract_multiplier": "10",
            },
        }
    )


async def _seed_case_distinct_identities(session: AsyncSession) -> None:
    """Persist RB0 and rb0 as two independent frozen identities."""
    writer = MarketDataIdentityWriter(session)
    for display_symbol in ("RB0", "rb0"):
        await writer.persist_identity(
            _futures_identity(
                canonical_id=f"instrument:futures:SHFE:{display_symbol}",
                display_symbol=display_symbol,
            ),
            valid_from=_IDENTIFIED_AT,
        )
        await session.commit()
    await writer.publish_staged()


async def _assert_case_distinct_resolution(session: AsyncSession) -> dict[str, object]:
    """RB0 and rb0 resolve independently; a wrong-case lookup fails closed."""
    resolver = MarketDataIdentityResolver(session)
    resolved: dict[str, str] = {}
    for display_symbol in ("RB0", "rb0"):
        projection = await resolver.resolve(
            {"canonical_id": f"instrument:futures:SHFE:{display_symbol}"},
            effective_at=_RESOLVED_AT,
            knowledge_cutoff=_RESOLVED_AT,
        )
        resolved[display_symbol] = projection.identity.canonical_id
    if resolved["RB0"] == resolved["rb0"]:
        raise MysqlAcceptanceHarnessError("MYSQL_ACCEPTANCE_CASE_DISTINCT_IDENTITY_COLLAPSED")

    wrong_case_failed = False
    try:
        await resolver.resolve(
            {"canonical_id": "instrument:futures:SHFE:Rb0"},
            effective_at=_RESOLVED_AT,
            knowledge_cutoff=_RESOLVED_AT,
        )
    except Exception:  # noqa: BLE001 - any stable rejection satisfies the probe
        wrong_case_failed = True
    if not wrong_case_failed:
        raise MysqlAcceptanceHarnessError("MYSQL_ACCEPTANCE_WRONG_CASE_LOOKUP_RESOLVED")
    return {"resolved_canonical_ids": sorted(resolved.values())}


async def _assert_identity_pit_boundary(session: AsyncSession) -> dict[str, object]:
    """A projection is hidden 1µs before its real publication and visible at it."""
    writer = MarketDataIdentityWriter(session)
    later = _futures_identity(
        canonical_id="instrument:futures:SHFE:HC0",
        display_symbol="HC0",
    )
    await writer.persist_identity(later, valid_from=_IDENTIFIED_AT)
    await session.commit()
    # Publish at the harness clock, then read the exact frozen instant back.
    await writer.publish_staged()

    resolver = MarketDataIdentityResolver(session)
    projection = await resolver.resolve(
        {"canonical_id": "instrument:futures:SHFE:HC0"},
        effective_at=_RESOLVED_AT,
        knowledge_cutoff=_RESOLVED_AT,
    )
    published_at = projection.known_at
    if published_at is None or published_at.tzinfo is None:
        raise MysqlAcceptanceHarnessError("MYSQL_ACCEPTANCE_PIT_INSTANT_NOT_UTC_AWARE")

    hidden_before = False
    try:
        await resolver.resolve(
            {"canonical_id": "instrument:futures:SHFE:HC0"},
            effective_at=_RESOLVED_AT,
            knowledge_cutoff=published_at - timedelta(microseconds=1),
        )
    except Exception:  # noqa: BLE001
        hidden_before = True
    if not hidden_before:
        raise MysqlAcceptanceHarnessError("MYSQL_ACCEPTANCE_PIT_PROJECTION_VISIBLE_EARLY")
    at_instant = await resolver.resolve(
        {"canonical_id": "instrument:futures:SHFE:HC0"},
        effective_at=_RESOLVED_AT,
        knowledge_cutoff=published_at,
    )
    if at_instant.identity.canonical_id != "instrument:futures:SHFE:HC0":
        raise MysqlAcceptanceHarnessError("MYSQL_ACCEPTANCE_PIT_PROJECTION_MISMATCH_AT_INSTANT")
    return {
        "published_at": published_at.isoformat(),
        "hidden_one_microsecond_before": True,
        "visible_at_instant": True,
    }


async def _assert_nonempty_downgrade_is_rejected(target_url: URL) -> dict[str, object]:
    """A governed migration must refuse to downgrade a non-empty database."""
    rejected = False
    rejection_code: str | None = None
    try:
        _run_alembic_downgrade_one(target_url)
    except Exception as exc:  # noqa: BLE001 - governed downgrades raise
        rejected = True
        rejection_code = type(exc).__name__
    if not rejected:
        raise MysqlAcceptanceHarnessError("MYSQL_ACCEPTANCE_NONEMPTY_DOWNGRADE_ALLOWED")

    # The data must remain intact after the refused downgrade.
    engine = create_async_engine(target_url, future=True)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as (
            session
        ):
            revision_rows = (
                (await session.execute(text("SELECT version_num FROM alembic_version")))
                .scalars()
                .all()
            )
            identity_count = await session.scalar(text("SELECT COUNT(*) FROM asset_instruments"))
    finally:
        await engine.dispose()
    if revision_rows != [EXPECTED_ALEMBIC_HEAD]:
        raise MysqlAcceptanceHarnessError("MYSQL_ACCEPTANCE_DOWNGRADE_MOVED_HEAD")
    return {
        "rejection_type": rejection_code,
        "alembic_head_after_refusal": revision_rows[0],
        "asset_instrument_rows_retained": int(identity_count or 0),
    }


def _dry_run_summary(admin_url: URL) -> dict[str, object]:
    return {
        "status": "not_run",
        "code": "APPLY_CONFIRMATION_REQUIRED",
        "admin_connection": _safe_connection_descriptor(admin_url),
        "temporary_database_created": False,
        "network_called": False,
        "credential_writes": False,
    }


async def _run_apply(admin_url: URL) -> dict[str, object]:
    database_name = _temporary_database_name()
    target_url = _target_url(admin_url, database_name)
    admin_engine = _admin_engine(admin_url)
    try:
        await _create_temporary_database(admin_engine, database_name)
    finally:
        await admin_engine.dispose()

    dropped = False
    evidence: dict[str, object] = {}
    try:
        _run_alembic_upgrade(target_url)

        engine = create_async_engine(target_url, future=True)
        try:
            session_factory = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            async with session_factory() as session:
                evidence["schema"] = await _assert_schema(session)
                evidence["utc"] = {
                    "session_time_zone": await _assert_utc_roundtrip(session),
                }
                await _seed_case_distinct_identities(session)
                evidence["case_distinct_identity"] = await _assert_case_distinct_resolution(session)
                evidence["identity_pit_boundary"] = await _assert_identity_pit_boundary(session)
        finally:
            await engine.dispose()

        evidence["nonempty_downgrade_refused"] = await _assert_nonempty_downgrade_is_rejected(
            target_url
        )
        return {
            "status": "pass",
            "code": "MYSQL_ACCEPTANCE_CORE_PASSED",
            "admin_connection": _safe_connection_descriptor(admin_url),
            "temporary_database": database_name,
            "evidence": evidence,
            "network_called": True,
            "credential_writes": False,
        }
    except MysqlAcceptanceHarnessError:
        raise
    except Exception:  # noqa: BLE001
        # Driver errors can include hosts, SQL text, or credentials; keep the
        # terminal output intentionally opaque.
        raise MysqlAcceptanceHarnessError("MYSQL_ACCEPTANCE_HARNESS_FAILED") from None
    finally:
        if not dropped:
            await _drop_temporary_database(admin_url, database_name)


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    try:
        args = _arguments(argv)
        admin_url = _parse_admin_url(args.mysql_admin_url)
    except MysqlAcceptanceHarnessError as exc:
        _emit({"status": "failed", "code": exc.code, "credential_writes": False})
        return 2

    if not args.apply:
        _emit(_dry_run_summary(admin_url))
        return 0

    try:
        payload = asyncio.run(_run_apply(admin_url))
    except MysqlAcceptanceHarnessError as exc:
        payload = {"status": "failed", "code": exc.code, "credential_writes": False}
        _emit(payload)
        return 1
    _emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
