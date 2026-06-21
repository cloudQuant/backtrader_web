"""Security-focused tests for sync transport command handling."""

import sys
from pathlib import Path
from typing import Any

import pytest

from app.schemas.sync import SyncConfig
from app.services.sync import transport


def make_config() -> SyncConfig:
    return SyncConfig(
        connection_mode="ssh_docker",
        local_mysql_host="127.0.0.1",
        local_mysql_port=3306,
        local_mysql_user="local_user",
        remote_host="db.example.test",
        remote_user="deploy",
        remote_ssh_key="/tmp/test_sync_key",
        remote_container="mysql-app",
        remote_mysql_host="mysql",
        remote_mysql_port=3306,
        remote_mysql_user="remote_user",
    )


class FakeProcess:
    def __init__(self, captured: dict[str, Any], returncode: int = 0) -> None:
        self.captured = captured
        self.returncode = returncode

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        self.captured["input"] = input
        defaults_arg = next(
            (
                arg
                for arg in self.captured["args"]
                if isinstance(arg, str) and arg.startswith("--defaults-extra-file=")
            ),
            None,
        )
        if defaults_arg is not None:
            defaults_path = defaults_arg.split("=", 1)[1]
            self.captured["defaults_path"] = defaults_path
            self.captured["defaults_content"] = Path(defaults_path).read_text("utf-8")
        return b"ok", b""

    def kill(self) -> None:
        self.captured["killed"] = True


def test_redact_command_masks_mysql_password_arg() -> None:
    command = transport.redact_command(["mysql", "-uroot", "-ps3cr3t!", "-e", "SELECT 1"])

    assert "s3cr3t" not in command
    assert "-p****" in command


def test_redact_command_masks_embedded_mysql_pwd_env() -> None:
    command = transport.redact_command(
        ["bash", "-lc", "MYSQL_PWD='pa ss word' mysqldump -h db example"]
    )

    assert "pa ss word" not in command
    assert "MYSQL_PWD=****" in command


@pytest.mark.asyncio
async def test_run_exec_failure_uses_redacted_command() -> None:
    with pytest.raises(RuntimeError) as exc:
        await transport.run_exec(
            [sys.executable, "-c", "raise SystemExit(1)", "-ps3cr3t!"], timeout=5
        )

    message = str(exc.value)
    assert "s3cr3t" not in message
    assert "-p****" in message


def test_mysql_builders_keep_password_out_of_argv() -> None:
    args = transport.build_local_mysql_query_args(make_config(), "SELECT 1", "s3cr3t!")

    assert isinstance(args, transport.SensitiveArgs)
    assert "s3cr3t" not in " ".join(args)
    assert not any(arg.startswith("-p") for arg in args)
    assert "--defaults-extra-file=****" in transport.redact_command(args)


def test_mysql_dump_builder_rejects_invalid_identifier() -> None:
    with pytest.raises(ValueError):
        transport.build_local_mysqldump_args(make_config(), "demo;DROP", "schema_only", "s3cr3t!")


def test_incremental_dump_requires_internal_where_sql() -> None:
    with pytest.raises(ValueError, match="internal sync builders"):
        transport.build_local_incremental_table_dump_args(
            make_config(),
            "demo",
            "orders",
            "s3cr3t!",
            "id = 1",  # type: ignore[arg-type]
        )


def test_incremental_dump_accepts_internal_where_sql() -> None:
    args = transport.build_local_incremental_table_dump_args(
        make_config(),
        "demo",
        "orders",
        "s3cr3t!",
        transport.internal_where_sql("`id` = '1'"),
    )

    assert "--where=`id` = '1'" in args


def test_join_command_uses_defaults_file_script_without_mysql_pwd() -> None:
    args = transport.build_local_mysql_query_args(make_config(), "SELECT 1", "s3cr3t!")
    command = transport.join_command(args)

    assert "MYSQL_PWD" not in command
    assert "-ps3cr3t" not in command
    assert "--defaults-extra-file=" in command
    assert 'password="s3cr3t!"' in command


@pytest.mark.asyncio
async def test_run_exec_materializes_sensitive_args_with_temp_defaults_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_create_subprocess_exec(*args: str, **kwargs: Any) -> FakeProcess:
        captured["args"] = list(args)
        captured["kwargs"] = kwargs
        return FakeProcess(captured)

    monkeypatch.setattr(transport.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    stdout = await transport.run_exec(
        transport.build_local_mysql_query_args(make_config(), "SELECT 1", "s3cr3t!"),
        timeout=5,
    )

    assert stdout == "ok"
    assert "s3cr3t!" not in " ".join(captured["args"])
    assert not any(arg.startswith("-p") for arg in captured["args"])
    assert 'password="s3cr3t!"' in captured["defaults_content"]
    assert not Path(captured["defaults_path"]).exists()


@pytest.mark.asyncio
async def test_run_bash_sends_script_via_stdin_not_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_create_subprocess_exec(*args: str, **kwargs: Any) -> FakeProcess:
        captured["args"] = list(args)
        captured["kwargs"] = kwargs
        return FakeProcess(captured)

    monkeypatch.setattr(transport.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    await transport.run_bash("echo s3cr3t!", timeout=5)

    assert captured["args"] == ["bash", "-s"]
    assert "s3cr3t!" not in " ".join(captured["args"])
    assert captured["input"] == b"echo s3cr3t!"


@pytest.mark.asyncio
async def test_run_ssh_sends_remote_script_via_stdin_not_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_create_subprocess_exec(*args: str, **kwargs: Any) -> FakeProcess:
        captured["args"] = list(args)
        captured["kwargs"] = kwargs
        return FakeProcess(captured)

    monkeypatch.setattr(transport.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    await transport.run_ssh(make_config(), "echo s3cr3t!", timeout=5, connect_timeout=10)

    assert captured["args"][-2:] == ["bash", "-s"]
    assert "s3cr3t!" not in " ".join(captured["args"])
    assert captured["input"] == b"echo s3cr3t!"


def test_remote_docker_shell_command_avoids_sh_lc_argv_script() -> None:
    command = transport.compose_remote_dump_command(
        "mysql-app",
        transport.build_remote_mysqldump_command(make_config(), "demo", "schema_only", "s3cr3t!"),
        "/tmp/demo.sql.gz",
        compress=True,
    )

    assert " sh -lc " not in command
    assert "docker exec -i mysql-app sh -s" in command
    assert "MYSQL_PWD" not in command
