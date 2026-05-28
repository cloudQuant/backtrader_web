#!/usr/bin/env python3
"""
Migrate akshare_web management metadata into backtrader_web.

This script only migrates akshare management tables into the main application
database. Runtime warehouse data in ``akshare_data`` remains in place.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src/backend"))

import app.models  # noqa: E402,F401
from app.db.database import Base  # noqa: E402


TABLE_MAPPINGS = [
    ("data_scripts", "ak_data_scripts"),
    ("data_tables", "ak_data_tables"),
    ("interface_categories", "ak_interface_categories"),
    ("data_interfaces", "ak_data_interfaces"),
    ("interface_parameters", "ak_interface_parameters"),
    ("scheduled_tasks", "ak_scheduled_tasks"),
    ("task_executions", "ak_task_executions"),
]

TRUNCATE_ORDER = [
    "ak_interface_parameters",
    "ak_data_interfaces",
    "ak_interface_categories",
    "ak_task_executions",
    "ak_scheduled_tasks",
    "ak_data_tables",
    "ak_data_scripts",
]

INSERT_ORDER = [
    ("data_scripts", "ak_data_scripts"),
    ("data_tables", "ak_data_tables"),
    ("interface_categories", "ak_interface_categories"),
    ("data_interfaces", "ak_data_interfaces"),
    ("interface_parameters", "ak_interface_parameters"),
    ("scheduled_tasks", "ak_scheduled_tasks"),
    ("task_executions", "ak_task_executions"),
]

REQUIRED_USER_COLUMNS = {"user_id"}
OPTIONAL_USER_COLUMNS = {"created_by", "updated_by", "operator_id"}


@dataclass
class TableReport:
    source_table: str
    target_table: str
    source_rows: int = 0
    inserted_rows: int = 0
    skipped_rows: int = 0
    user_fallback_rows: int = 0
    missing_table: bool = False


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


async def table_exists(engine: AsyncEngine, table_name: str) -> bool:
    async with engine.connect() as conn:
        return await conn.run_sync(lambda sync_conn: inspect(sync_conn).has_table(table_name))


async def reflect_table(engine: AsyncEngine, table_name: str) -> Table:
    metadata = MetaData()

    async with engine.connect() as conn:
        await conn.run_sync(lambda sync_conn: metadata.reflect(bind=sync_conn, only=[table_name]))

    return metadata.tables[table_name]


def get_target_table(table_name: str) -> Table:
    return Base.metadata.tables[table_name]


async def fetch_rows(conn: AsyncConnection, table_name: str) -> list[dict[str, Any]]:
    result = await conn.execute(text(f"SELECT * FROM {table_name}"))
    return [dict(row) for row in result.mappings().all()]


async def fetch_target_users(conn: AsyncConnection) -> tuple[dict[str, str], dict[str, str], str | None]:
    username_map: dict[str, str] = {}
    email_map: dict[str, str] = {}
    fallback_user_id: str | None = None

    result = await conn.execute(text("SELECT id, username, email FROM users ORDER BY created_at ASC"))
    for row in result.mappings().all():
        user_id = str(row["id"])
        if fallback_user_id is None:
            fallback_user_id = user_id
        username = str(row["username"]).strip().lower() if row.get("username") else ""
        email = str(row["email"]).strip().lower() if row.get("email") else ""
        if username:
            username_map[username] = user_id
        if email:
            email_map[email] = user_id
        if username == os.getenv("ADMIN_USERNAME", "admin").strip().lower():
            fallback_user_id = user_id

    return username_map, email_map, fallback_user_id


async def build_legacy_user_map(
    legacy_conn: AsyncConnection,
    target_conn: AsyncConnection,
) -> tuple[dict[str, str | None], str | None, list[dict[str, Any]]]:
    username_map, email_map, fallback_user_id = await fetch_target_users(target_conn)
    unresolved: list[dict[str, Any]] = []
    user_map: dict[str, str | None] = {}

    users_table_exists = await legacy_conn.run_sync(lambda sync_conn: inspect(sync_conn).has_table("users"))
    if not users_table_exists:
        return user_map, fallback_user_id, unresolved

    result = await legacy_conn.execute(text("SELECT id, username, email FROM users"))
    for row in result.mappings().all():
        legacy_id = str(row["id"])
        username = str(row["username"]).strip().lower() if row.get("username") else ""
        email = str(row["email"]).strip().lower() if row.get("email") else ""
        mapped = None
        if username and username in username_map:
            mapped = username_map[username]
        elif email and email in email_map:
            mapped = email_map[email]

        user_map[legacy_id] = mapped
        if mapped is None:
            unresolved.append({
                "legacy_user_id": legacy_id,
                "username": row.get("username"),
                "email": row.get("email"),
            })

    return user_map, fallback_user_id, unresolved


def remap_user_id(
    column_name: str,
    value: Any,
    user_map: dict[str, str | None],
    fallback_user_id: str | None,
) -> tuple[Any, bool]:
    if value is None:
        return None, False

    mapped = user_map.get(str(value))
    if mapped:
        return mapped, False
    if column_name in REQUIRED_USER_COLUMNS:
        return fallback_user_id, True
    return None, True


def resolve_column_default(column: Any) -> tuple[Any, bool]:
    default = getattr(column, "default", None)
    if default is None:
        return None, False

    value = getattr(default, "arg", default)
    if callable(value):
        try:
            return value(), True
        except TypeError:
            return None, False
    if isinstance(value, (dict, list, set)):
        return copy.deepcopy(value), True
    return value, True


async def truncate_target_tables(target_conn: AsyncConnection) -> None:
    for table_name in TRUNCATE_ORDER:
        if await target_conn.run_sync(lambda sync_conn, name=table_name: inspect(sync_conn).has_table(name)):
            await target_conn.execute(text(f"DELETE FROM {table_name}"))


async def migrate_table(
    legacy_conn: AsyncConnection,
    target_conn: AsyncConnection,
    source_table_name: str,
    target_table_name: str,
    dry_run: bool,
    user_map: dict[str, str | None],
    fallback_user_id: str | None,
) -> TableReport:
    report = TableReport(source_table=source_table_name, target_table=target_table_name)

    source_exists = await legacy_conn.run_sync(
        lambda sync_conn: inspect(sync_conn).has_table(source_table_name)
    )
    target_exists = await target_conn.run_sync(
        lambda sync_conn: inspect(sync_conn).has_table(target_table_name)
    )

    if not source_exists or not target_exists:
        report.missing_table = True
        return report

    source_rows = await fetch_rows(legacy_conn, source_table_name)
    report.source_rows = len(source_rows)

    if not source_rows:
        return report

    target_table = get_target_table(target_table_name)
    target_columns = set(target_table.c.keys())
    insert_rows: list[dict[str, Any]] = []

    for row in source_rows:
        transformed: dict[str, Any] = {}
        skipped = False
        for column_name, value in row.items():
            if column_name not in target_columns:
                continue
            if column_name in REQUIRED_USER_COLUMNS | OPTIONAL_USER_COLUMNS:
                value, used_fallback = remap_user_id(column_name, value, user_map, fallback_user_id)
                report.user_fallback_rows += int(used_fallback)
                if column_name in REQUIRED_USER_COLUMNS and value is None:
                    skipped = True
                    break
            transformed[column_name] = value

        for column in target_table.columns:
            if column.name in transformed:
                continue
            default_value, has_default = resolve_column_default(column)
            if has_default:
                transformed[column.name] = default_value

        missing_required = [
            column.name
            for column in target_table.columns
            if (
                not column.nullable
                and column.server_default is None
                and not column.autoincrement
                and column.name not in transformed
            )
        ]
        if missing_required:
            skipped = True

        if skipped:
            report.skipped_rows += 1
            continue

        insert_rows.append(transformed)

    if not dry_run and insert_rows:
        await target_conn.execute(target_table.insert(), insert_rows)
    report.inserted_rows = len(insert_rows)
    return report


async def run_migration(args: argparse.Namespace) -> int:
    legacy_database_url = get_required_env("LEGACY_AKSHARE_DATABASE_URL")
    target_database_url = get_required_env("DATABASE_URL")

    if os.getenv("LEGACY_SQLITE_DATABASE_URL"):
        print("Note: LEGACY_SQLITE_DATABASE_URL is configured but not used by this script.")

    legacy_engine = create_async_engine(legacy_database_url)
    target_engine = create_async_engine(target_database_url)
    reports: list[TableReport] = []

    try:
        async with legacy_engine.connect() as legacy_conn, target_engine.begin() as target_conn:
            user_map, fallback_user_id, unresolved_users = await build_legacy_user_map(
                legacy_conn,
                target_conn,
            )

            if args.truncate_target and not args.dry_run:
                await truncate_target_tables(target_conn)

            for source_table, target_table in INSERT_ORDER:
                report = await migrate_table(
                    legacy_conn,
                    target_conn,
                    source_table,
                    target_table,
                    dry_run=args.dry_run,
                    user_map=user_map,
                    fallback_user_id=fallback_user_id,
                )
                reports.append(report)

            summary = {
                "dry_run": args.dry_run,
                "truncate_target": args.truncate_target,
                "fallback_user_id": fallback_user_id,
                "unresolved_legacy_users": unresolved_users,
                "tables": [asdict(item) for item in reports],
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
            return 0
    finally:
        await legacy_engine.dispose()
        await target_engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        default="src/backend/.env",
        help="Path to env file used for loading DATABASE_URL and LEGACY_AKSHARE_DATABASE_URL",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and transform data without writing to the target database",
    )
    parser.add_argument(
        "--no-truncate-target",
        action="store_true",
        help="Do not clear target ak_* tables before inserting data",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env_file(Path(args.env_file))
    args.truncate_target = not args.no_truncate_target
    return asyncio.run(run_migration(args))


if __name__ == "__main__":
    raise SystemExit(main())
