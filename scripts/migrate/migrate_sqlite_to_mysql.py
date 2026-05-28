#!/usr/bin/env python3
"""
Migrate legacy SQLite business data into the backtrader_web MySQL database.

This script copies the current application's non-akshare business tables from
``LEGACY_SQLITE_DATABASE_URL`` into ``DATABASE_URL``. Akshare management tables
are handled separately by ``migrate_akshare_web_to_mysql.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Boolean, MetaData, Table, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src/backend"))

import app.models  # noqa: E402,F401
from app.db.database import Base  # noqa: E402


EXCLUDED_TABLE_PREFIXES = ("ak_",)


@dataclass
class TableReport:
    table_name: str
    source_rows: int = 0
    inserted_rows: int = 0
    skipped_rows: int = 0
    failed_rows: int = 0
    missing_table: bool = False
    failure_samples: list[dict[str, Any]] = field(default_factory=list)


def load_env_file(env_file: Path) -> None:
    """Load ``KEY=VALUE`` pairs from a simple env file if present."""
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def get_target_tables() -> list[Table]:
    """Return non-akshare target tables in FK-safe order."""
    return [
        table
        for table in Base.metadata.sorted_tables
        if not table.name.startswith(EXCLUDED_TABLE_PREFIXES)
    ]


async def reflect_table(engine: AsyncEngine, table_name: str) -> Table:
    metadata = MetaData()

    async with engine.connect() as conn:
        await conn.run_sync(lambda sync_conn: metadata.reflect(bind=sync_conn, only=[table_name]))

    return metadata.tables[table_name]


async def fetch_rows(conn: AsyncConnection, table: Table) -> list[dict[str, Any]]:
    result = await conn.execute(select(table))
    return [dict(row) for row in result.mappings().all()]


def normalize_value(column: Any, value: Any) -> Any:
    """Normalize SQLite values for the target MySQL column type."""
    if value is None:
        return None

    if isinstance(column.type, JSON) and isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value

    if isinstance(column.type, Boolean):
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}

    return value


def build_insert_row(source_row: dict[str, Any], target_table: Table) -> tuple[dict[str, Any] | None, str | None]:
    """Project one source row onto the target table columns."""
    row: dict[str, Any] = {}

    for column in target_table.columns:
        if column.name not in source_row:
            continue
        row[column.name] = normalize_value(column, source_row[column.name])

    missing_required = [
        column.name
        for column in target_table.columns
        if (
            not column.nullable
            and column.default is None
            and column.server_default is None
            and not column.autoincrement
            and column.name not in row
        )
    ]
    if missing_required:
        return None, f"missing required columns: {', '.join(sorted(missing_required))}"

    return row, None


def get_primary_key_values(target_table: Table, row: dict[str, Any]) -> dict[str, Any]:
    return {column.name: row.get(column.name) for column in target_table.primary_key.columns}


async def truncate_target_tables(target_conn: AsyncConnection, target_tables: list[Table]) -> None:
    existing_tables = {
        table_name
        for table_name in await target_conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    }
    for table in reversed(target_tables):
        if table.name in existing_tables:
            await target_conn.execute(table.delete())


async def insert_rows(
    target_conn: AsyncConnection,
    target_table: Table,
    rows: list[dict[str, Any]],
    report: TableReport,
) -> None:
    """Insert rows with row-level fallback reporting."""
    if not rows:
        return

    try:
        async with target_conn.begin_nested():
            await target_conn.execute(target_table.insert(), rows)
        report.inserted_rows += len(rows)
        return
    except SQLAlchemyError:
        pass

    for row in rows:
        try:
            async with target_conn.begin_nested():
                await target_conn.execute(target_table.insert().values(**row))
            report.inserted_rows += 1
        except SQLAlchemyError as exc:
            report.failed_rows += 1
            if len(report.failure_samples) < 20:
                report.failure_samples.append(
                    {
                        "primary_key": get_primary_key_values(target_table, row),
                        "error": str(exc),
                    }
                )


async def migrate_table(
    source_conn: AsyncConnection,
    target_conn: AsyncConnection,
    source_engine: AsyncEngine,
    target_table: Table,
    dry_run: bool,
) -> TableReport:
    report = TableReport(table_name=target_table.name)

    source_exists = await source_conn.run_sync(
        lambda sync_conn: inspect(sync_conn).has_table(target_table.name)
    )
    target_exists = await target_conn.run_sync(
        lambda sync_conn: inspect(sync_conn).has_table(target_table.name)
    )
    if not source_exists or not target_exists:
        report.missing_table = True
        return report

    source_table = await reflect_table(source_engine, target_table.name)
    source_rows = await fetch_rows(source_conn, source_table)
    report.source_rows = len(source_rows)

    insert_rows_payload: list[dict[str, Any]] = []
    for source_row in source_rows:
        row, error = build_insert_row(source_row, target_table)
        if error is not None:
            report.skipped_rows += 1
            if len(report.failure_samples) < 20:
                report.failure_samples.append(
                    {
                        "primary_key": get_primary_key_values(target_table, source_row),
                        "error": error,
                    }
                )
            continue
        if row is not None:
            insert_rows_payload.append(row)

    if dry_run:
        report.inserted_rows = len(insert_rows_payload)
        return report

    await insert_rows(target_conn, target_table, insert_rows_payload, report)
    return report


async def run_migration(args: argparse.Namespace) -> int:
    source_database_url = get_required_env("LEGACY_SQLITE_DATABASE_URL")
    target_database_url = get_required_env("DATABASE_URL")

    if os.getenv("LEGACY_AKSHARE_DATABASE_URL"):
        print("Note: LEGACY_AKSHARE_DATABASE_URL is configured but not used by this script.")

    source_engine = create_async_engine(source_database_url)
    target_engine = create_async_engine(target_database_url)
    target_tables = get_target_tables()
    reports: list[TableReport] = []

    try:
        async with source_engine.connect() as source_conn, target_engine.begin() as target_conn:
            if args.truncate_target and not args.dry_run:
                await truncate_target_tables(target_conn, target_tables)

            for target_table in target_tables:
                reports.append(
                    await migrate_table(
                        source_conn=source_conn,
                        target_conn=target_conn,
                        source_engine=source_engine,
                        target_table=target_table,
                        dry_run=args.dry_run,
                    )
                )

            summary = {
                "dry_run": args.dry_run,
                "truncate_target": args.truncate_target,
                "excluded_table_prefixes": list(EXCLUDED_TABLE_PREFIXES),
                "tables": [asdict(item) for item in reports],
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
            return 0
    finally:
        await source_engine.dispose()
        await target_engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        default="src/backend/.env",
        help="Path to env file used for loading DATABASE_URL and LEGACY_SQLITE_DATABASE_URL",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and transform data without writing to the target database",
    )
    parser.add_argument(
        "--no-truncate-target",
        action="store_true",
        help="Do not clear target non-akshare tables before inserting data",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env_file(Path(args.env_file))
    args.truncate_target = not args.no_truncate_target
    return asyncio.run(run_migration(args))


if __name__ == "__main__":
    raise SystemExit(main())
