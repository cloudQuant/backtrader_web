from __future__ import annotations

import asyncio
import os
import re
import shlex
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.schemas.sync import SyncConfig
from app.services.sync.schema_diff import validate_mysql_identifier

_MYSQL_PASSWORD_ARG_RE = re.compile(r"(?<!\w)-p(?P<password>[^\s'\"\\]+)")
_MYSQL_PASSWORD_ENV_RE = re.compile(r"MYSQL_PWD=(?P<quote>['\"]?)(?P<secret>.*?)(?P=quote)(?=\s|$)")
_MYSQL_DEFAULTS_PASSWORD_RE = re.compile(
    r"password\s*=\s*(?P<quote>['\"]?)(?P<password>.*?)(?P=quote)(?=\s|$)",
    re.IGNORECASE,
)
_SENSITIVE_MARK = "****"
_MYSQL_DEFAULTS_VAR = "$_bt_mysql_defaults"
_MYSQL_DEFAULTS_HEREDOC = "BT_MYSQL_DEFAULTS"
_DOCKER_SCRIPT_HEREDOC = "BT_SYNC_DOCKER_SCRIPT"
_DOCKER_DEFAULTS_HEREDOC = "BT_SYNC_DOCKER_DEFAULTS"


class SensitiveArgs(list[str]):
    """Command argv with sensitive MySQL credentials kept outside argv."""

    def __init__(self, args: list[str], *, mysql_password: str) -> None:
        super().__init__(args)
        self.mysql_password = mysql_password


class InternalWhereSql(str):
    """WHERE SQL produced by internal sync builders."""


def internal_where_sql(value: str) -> InternalWhereSql:
    return InternalWhereSql(value)


def _require_internal_where_sql(where_sql: str) -> str:
    if not isinstance(where_sql, InternalWhereSql):
        raise ValueError("mysqldump --where SQL must be produced by internal sync builders")
    return str(where_sql)


def redact_text(text: str) -> str:
    """Redact MySQL CLI credentials from command text and error output."""
    redacted = _MYSQL_PASSWORD_ARG_RE.sub(f"-p{_SENSITIVE_MARK}", text)
    redacted = _MYSQL_PASSWORD_ENV_RE.sub(f"MYSQL_PWD={_SENSITIVE_MARK}", redacted)
    return _MYSQL_DEFAULTS_PASSWORD_RE.sub(f"password={_SENSITIVE_MARK}", redacted)


def redact_command(args: list[str]) -> str:
    """Return a shell-style command preview with sensitive values redacted."""
    if isinstance(args, SensitiveArgs):
        return redact_text(join_command(mysql_args_with_defaults_file(args, _SENSITIVE_MARK)))
    return redact_text(" ".join(shlex.quote(arg) for arg in args))


def _mysql_defaults_content(password: str) -> str:
    if "\n" in password or "\r" in password:
        raise ValueError("MySQL password must not contain newline characters")
    escaped = password.replace("\\", "\\\\").replace('"', '\\"')
    return f'[client]\npassword="{escaped}"\n'


def mysql_args_with_defaults_file(args: list[str], defaults_file: str) -> list[str]:
    """Insert --defaults-extra-file immediately after the MySQL CLI program."""
    if not args:
        return []
    return [args[0], f"--defaults-extra-file={defaults_file}", *args[1:]]


def _join_sensitive_mysql_command(args: SensitiveArgs) -> str:
    defaults_content = _mysql_defaults_content(args.mysql_password)
    if not args:
        return ""
    command_parts = [
        shlex.quote(args[0]),
        f'--defaults-extra-file="{_MYSQL_DEFAULTS_VAR}"',
        *(shlex.quote(arg) for arg in args[1:]),
    ]
    command = " ".join(command_parts)
    return (
        "(_bt_mysql_defaults=$(mktemp); "
        'chmod 600 "$_bt_mysql_defaults"; '
        "trap 'rm -f \"$_bt_mysql_defaults\"' EXIT; "
        f"cat > \"$_bt_mysql_defaults\" <<'{_MYSQL_DEFAULTS_HEREDOC}'\n"
        f"{defaults_content}"
        f"{_MYSQL_DEFAULTS_HEREDOC}\n"
        f"{command})"
    )


@contextmanager
def _materialized_exec_args(args: list[str]) -> Iterator[list[str]]:
    if not isinstance(args, SensitiveArgs):
        yield list(args)
        return

    fd, defaults_file = tempfile.mkstemp(prefix="bt-sync-mysql-", suffix=".cnf", text=True)
    try:
        os.chmod(defaults_file, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_mysql_defaults_content(args.mysql_password))
        yield mysql_args_with_defaults_file(args, defaults_file)
    finally:
        try:
            os.unlink(defaults_file)
        except FileNotFoundError:
            pass


def compose_docker_shell_command(container: str, script: str) -> str:
    """Run a shell script inside a Docker container without putting it in docker argv."""
    return (
        f"docker exec -i {shlex.quote(container)} sh -s <<'{_DOCKER_SCRIPT_HEREDOC}'\n"
        f"{script}\n"
        f"{_DOCKER_SCRIPT_HEREDOC}"
    )


def compose_docker_write_mysql_defaults_command(
    container: str,
    defaults_file: str,
    password: str,
) -> str:
    """Write a temporary MySQL defaults file inside a container via stdin."""
    defaults_content = _mysql_defaults_content(password)
    quoted_defaults_file = shlex.quote(defaults_file)
    return (
        f"docker exec -i {shlex.quote(container)} sh -s <<'{_DOCKER_DEFAULTS_HEREDOC}'\n"
        "set -eu\n"
        "umask 077\n"
        f"cat > {quoted_defaults_file} <<'{_MYSQL_DEFAULTS_HEREDOC}'\n"
        f"{defaults_content}"
        f"{_MYSQL_DEFAULTS_HEREDOC}\n"
        f"chmod 600 {quoted_defaults_file}\n"
        f"{_DOCKER_DEFAULTS_HEREDOC}"
    )


def build_local_mysqldump_args(
    config: SyncConfig,
    database: str,
    sync_mode: str,
    password: str,
) -> list[str]:
    database = validate_mysql_identifier(database, "database")
    args: list[str] = [
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
    return SensitiveArgs(args, mysql_password=password)


def build_local_table_dump_args(
    config: SyncConfig,
    database: str,
    table: str,
    password: str,
) -> list[str]:
    table = validate_mysql_identifier(table, "table")
    args = build_local_mysqldump_args(config, database, "data_only", password)
    args.append(table)
    return args


def build_local_incremental_table_dump_args(
    config: SyncConfig,
    database: str,
    table: str,
    password: str,
    where_sql: InternalWhereSql,
) -> list[str]:
    database = validate_mysql_identifier(database, "database")
    table = validate_mysql_identifier(table, "table")
    where_sql = internal_where_sql(_require_internal_where_sql(where_sql))
    return SensitiveArgs(
        [
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
            database,
            table,
        ],
        mysql_password=password,
    )


def build_local_mysql_query_args(config: SyncConfig, sql: str, password: str) -> list[str]:
    return SensitiveArgs(
        [
            "mysql",
            "-h",
            config.local_mysql_host,
            "-P",
            str(config.local_mysql_port),
            "-u",
            config.local_mysql_user,
            "-N",
            "-B",
            "-e",
            sql,
        ],
        mysql_password=password,
    )


def build_local_mysql_import_args(
    config: SyncConfig,
    database: str,
    password: str,
    force: bool = False,
) -> list[str]:
    database = validate_mysql_identifier(database, "database")
    args: list[str] = [
        "mysql",
        "-h",
        config.local_mysql_host,
        "-P",
        str(config.local_mysql_port),
        "-u",
        config.local_mysql_user,
    ]
    if force:
        args.append("--force")
    args.append(database)
    return SensitiveArgs(args, mysql_password=password)


def build_remote_mysqldump_command(
    config: SyncConfig,
    database: str,
    sync_mode: str,
    password: str,
) -> str:
    database = validate_mysql_identifier(database, "database")
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
    return join_command(SensitiveArgs(args, mysql_password=password))


def build_remote_mysqldump_args(
    config: SyncConfig,
    database: str,
    sync_mode: str,
    password: str,
) -> list[str]:
    database = validate_mysql_identifier(database, "database")
    args: list[str] = [
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
    return SensitiveArgs(args, mysql_password=password)


def build_remote_table_dump_args(
    config: SyncConfig,
    database: str,
    table: str,
    password: str,
) -> list[str]:
    table = validate_mysql_identifier(table, "table")
    args = build_remote_mysqldump_args(config, database, "data_only", password)
    args.append(table)
    return args


def build_remote_incremental_table_dump_args(
    config: SyncConfig,
    database: str,
    table: str,
    password: str,
    where_sql: InternalWhereSql,
) -> list[str]:
    database = validate_mysql_identifier(database, "database")
    table = validate_mysql_identifier(table, "table")
    where_sql = internal_where_sql(_require_internal_where_sql(where_sql))
    return SensitiveArgs(
        [
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
            database,
            table,
        ],
        mysql_password=password,
    )


def build_remote_mysql_query_args(config: SyncConfig, sql: str, password: str) -> list[str]:
    return SensitiveArgs(
        [
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
        ],
        mysql_password=password,
    )


def build_remote_mysql_import_args(
    config: SyncConfig,
    database: str,
    password: str,
    force: bool = False,
) -> list[str]:
    database = validate_mysql_identifier(database, "database")
    args: list[str] = [
        "mysql",
        "-h",
        config.remote_mysql_host,
        "-P",
        str(config.remote_mysql_port),
        "-u",
        config.remote_mysql_user,
    ]
    if force:
        args.append("--force")
    args.append(database)
    return SensitiveArgs(args, mysql_password=password)


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
    return join_command(SensitiveArgs(args, mysql_password=password))


def build_remote_mysql_import_command(config: SyncConfig, database: str, password: str) -> str:
    database = validate_mysql_identifier(database, "database")
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
    return join_command(SensitiveArgs(args, mysql_password=password))


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
        f"{compose_docker_shell_command(container, inner_dump_command)} "
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
    return await run_exec(
        build_ssh_base_args(config, connect_timeout) + ["bash", "-s"],
        timeout,
        input_text=command,
    )


async def run_bash(command: str, timeout: int) -> str:
    return await run_exec(["bash", "-s"], timeout, input_text=command)


async def run_exec(args: list[str], timeout: int, input_text: str | None = None) -> str:
    with _materialized_exec_args(args) as exec_args:
        proc = await asyncio.create_subprocess_exec(
            *exec_args,
            stdin=asyncio.subprocess.PIPE if input_text is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        input_bytes = input_text.encode("utf-8") if input_text is not None else None
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(input_bytes), timeout=timeout)
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            raise RuntimeError(f"命令执行超时（>{timeout}s）: {redact_command(args)}") from exc
    if proc.returncode != 0:
        error = redact_text((stderr or stdout).decode("utf-8", errors="ignore").strip())
        raise RuntimeError(error or f"命令执行失败: {redact_command(args)}")
    return stdout.decode("utf-8", errors="ignore").strip()


def join_command(args: list[str]) -> str:
    if isinstance(args, SensitiveArgs):
        return _join_sensitive_mysql_command(args)
    return " ".join(shlex.quote(arg) for arg in args)
