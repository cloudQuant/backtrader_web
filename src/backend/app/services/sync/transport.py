from __future__ import annotations

import asyncio
import shlex
from pathlib import Path

from app.schemas.sync import SyncConfig


def build_local_mysqldump_args(
    config: SyncConfig,
    database: str,
    sync_mode: str,
    password: str,
) -> list[str]:
    args = [
        "mysqldump",
        "--single-transaction",
        "--skip-lock-tables",
        "--set-gtid-purged=OFF",
        "--default-character-set=utf8mb4",
        "-h",
        config.local_mysql_host,
        "-P",
        str(config.local_mysql_port),
        "-u",
        config.local_mysql_user,
        f"-p{password}",
    ]
    if sync_mode == "schema_only":
        args.extend(
            [
                "--no-data",
                "--skip-comments",
                "--skip-dump-date",
                "--skip-add-drop-table",
                "--skip-add-drop-trigger",
                "--skip-triggers",
            ]
        )
    elif sync_mode == "data_only":
        args.extend(["--no-create-info", "--replace", "--skip-triggers"])
    else:
        args.extend(["--routines", "--triggers", "--events"])
    args.append(database)
    return args


def build_local_table_dump_args(
    config: SyncConfig,
    database: str,
    table: str,
    password: str,
) -> list[str]:
    args = build_local_mysqldump_args(config, database, "data_only", password)
    args.append(table)
    return args


def build_local_incremental_table_dump_args(
    config: SyncConfig,
    database: str,
    table: str,
    password: str,
    where_sql: str,
) -> list[str]:
    return [
        "mysqldump",
        "--single-transaction",
        "--skip-lock-tables",
        "--set-gtid-purged=OFF",
        "--default-character-set=utf8mb4",
        "--no-create-info",
        "--replace",
        f"--where={where_sql}",
        "-h",
        config.local_mysql_host,
        "-P",
        str(config.local_mysql_port),
        "-u",
        config.local_mysql_user,
        f"-p{password}",
        database,
        table,
    ]


def build_local_mysql_query_args(config: SyncConfig, sql: str, password: str) -> list[str]:
    return [
        "mysql",
        "-h",
        config.local_mysql_host,
        "-P",
        str(config.local_mysql_port),
        "-u",
        config.local_mysql_user,
        f"-p{password}",
        "-N",
        "-B",
        "-e",
        sql,
    ]


def build_local_mysql_import_args(
    config: SyncConfig,
    database: str,
    password: str,
    force: bool = False,
) -> list[str]:
    args = [
        "mysql",
        "-h",
        config.local_mysql_host,
        "-P",
        str(config.local_mysql_port),
        "-u",
        config.local_mysql_user,
        f"-p{password}",
    ]
    if force:
        args.append("--force")
    args.append(database)
    return args


def build_remote_mysqldump_command(
    config: SyncConfig,
    database: str,
    sync_mode: str,
    password: str,
) -> str:
    args = [
        "mysqldump",
        "--single-transaction",
        "--skip-lock-tables",
        "--set-gtid-purged=OFF",
        "--default-character-set=utf8mb4",
        "-h",
        config.remote_mysql_host,
        "-P",
        str(config.remote_mysql_port),
        "-u",
        config.remote_mysql_user,
    ]
    if sync_mode == "schema_only":
        args.extend(
            [
                "--no-data",
                "--skip-comments",
                "--skip-dump-date",
                "--skip-add-drop-table",
                "--skip-add-drop-trigger",
                "--skip-triggers",
            ]
        )
    elif sync_mode == "data_only":
        args.extend(["--no-create-info", "--replace", "--skip-triggers"])
    else:
        args.extend(["--routines", "--triggers", "--events"])
    args.append(database)
    return f"MYSQL_PWD={shlex.quote(password)} {join_command(args)}"


def build_remote_mysqldump_args(
    config: SyncConfig,
    database: str,
    sync_mode: str,
    password: str,
) -> list[str]:
    args = [
        "mysqldump",
        "--single-transaction",
        "--skip-lock-tables",
        "--set-gtid-purged=OFF",
        "--default-character-set=utf8mb4",
        "-h",
        config.remote_mysql_host,
        "-P",
        str(config.remote_mysql_port),
        "-u",
        config.remote_mysql_user,
        f"-p{password}",
    ]
    if sync_mode == "schema_only":
        args.extend(
            [
                "--no-data",
                "--skip-comments",
                "--skip-dump-date",
                "--skip-add-drop-table",
                "--skip-add-drop-trigger",
                "--skip-triggers",
            ]
        )
    elif sync_mode == "data_only":
        args.extend(["--no-create-info", "--replace", "--skip-triggers"])
    else:
        args.extend(["--routines", "--triggers", "--events"])
    args.append(database)
    return args


def build_remote_table_dump_args(
    config: SyncConfig,
    database: str,
    table: str,
    password: str,
) -> list[str]:
    args = build_remote_mysqldump_args(config, database, "data_only", password)
    args.append(table)
    return args


def build_remote_incremental_table_dump_args(
    config: SyncConfig,
    database: str,
    table: str,
    password: str,
    where_sql: str,
) -> list[str]:
    return [
        "mysqldump",
        "--single-transaction",
        "--skip-lock-tables",
        "--set-gtid-purged=OFF",
        "--default-character-set=utf8mb4",
        "--no-create-info",
        "--replace",
        f"--where={where_sql}",
        "-h",
        config.remote_mysql_host,
        "-P",
        str(config.remote_mysql_port),
        "-u",
        config.remote_mysql_user,
        f"-p{password}",
        database,
        table,
    ]


def build_remote_mysql_query_args(config: SyncConfig, sql: str, password: str) -> list[str]:
    return [
        "mysql",
        "-h",
        config.remote_mysql_host,
        "-P",
        str(config.remote_mysql_port),
        "-u",
        config.remote_mysql_user,
        f"-p{password}",
        "-N",
        "-B",
        "-e",
        sql,
    ]


def build_remote_mysql_import_args(
    config: SyncConfig,
    database: str,
    password: str,
    force: bool = False,
) -> list[str]:
    args = [
        "mysql",
        "-h",
        config.remote_mysql_host,
        "-P",
        str(config.remote_mysql_port),
        "-u",
        config.remote_mysql_user,
        f"-p{password}",
    ]
    if force:
        args.append("--force")
    args.append(database)
    return args


def build_remote_mysql_query_command(config: SyncConfig, sql: str, password: str) -> str:
    args = [
        "mysql",
        "-h",
        config.remote_mysql_host,
        "-P",
        str(config.remote_mysql_port),
        "-u",
        config.remote_mysql_user,
        "-N",
        "-B",
        "-e",
        sql,
    ]
    return f"MYSQL_PWD={shlex.quote(password)} {join_command(args)}"


def build_remote_mysql_import_command(config: SyncConfig, database: str, password: str) -> str:
    args = [
        "mysql",
        "-h",
        config.remote_mysql_host,
        "-P",
        str(config.remote_mysql_port),
        "-u",
        config.remote_mysql_user,
        database,
    ]
    return f"MYSQL_PWD={shlex.quote(password)} {join_command(args)}"


def compose_dump_command(dump_args: list[str], output_path: Path, compress: bool) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if compress:
        return f"set -o pipefail; {join_command(dump_args)} | gzip -c > {shlex.quote(str(output_path))}"
    return f"set -o pipefail; {join_command(dump_args)} > {shlex.quote(str(output_path))}"


def compose_remote_dump_command(
    container: str,
    inner_dump_command: str,
    output_path: str,
    compress: bool,
) -> str:
    pipe_target = "gzip -c" if compress else "cat"
    return (
        "set -o pipefail; "
        f"docker exec {shlex.quote(container)} sh -lc {shlex.quote(inner_dump_command)} "
        f"| {pipe_target} > {shlex.quote(output_path)}"
    )


def compose_import_command(*, input_path: str, mysql_command: str, compressed: bool) -> str:
    cat_command = "gunzip -c" if compressed else "cat"
    return f"set -o pipefail; {cat_command} {shlex.quote(input_path)} | {mysql_command}"


def compose_stream_command(dump_command: str, mysql_command: str) -> str:
    return f"set -o pipefail; {dump_command} | {mysql_command}"


def build_ssh_base_args(config: SyncConfig, connect_timeout: int) -> list[str]:
    key_path = str(Path(config.remote_ssh_key).expanduser())
    return [
        "ssh",
        "-i",
        key_path,
        "-o",
        f"ConnectTimeout={connect_timeout}",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{config.remote_user}@{config.remote_host}",
    ]


def build_scp_base_args(config: SyncConfig, connect_timeout: int) -> list[str]:
    key_path = str(Path(config.remote_ssh_key).expanduser())
    return [
        "scp",
        "-i",
        key_path,
        "-o",
        f"ConnectTimeout={connect_timeout}",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]


async def run_ssh(
    config: SyncConfig,
    command: str,
    timeout: int,
    connect_timeout: int,
) -> str:
    remote_command = join_command(["bash", "-lc", command])
    return await run_exec(build_ssh_base_args(config, connect_timeout) + [remote_command], timeout)


async def run_bash(command: str, timeout: int) -> str:
    return await run_exec(["bash", "-lc", command], timeout)


async def run_exec(args: list[str], timeout: int) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"命令执行超时（>{timeout}s）: {join_command(args)}") from exc
    if proc.returncode != 0:
        error = (stderr or stdout).decode("utf-8", errors="ignore").strip()
        raise RuntimeError(error or f"命令执行失败: {join_command(args)}")
    return stdout.decode("utf-8", errors="ignore").strip()


def join_command(args: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in args)
