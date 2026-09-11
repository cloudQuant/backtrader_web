"""Safety contracts for the opt-in Iteration 197 MySQL acceptance harness."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.engine import URL

from scripts import verify_iteration197_mysql_acceptance as harness


def _admin_url(
    *,
    drivername: str = "mysql",
    database: str = "mysql",
    username: str = "root",
    password: str = "pw",
) -> str:
    return URL.create(
        drivername=drivername,
        username=username,
        password=password,
        host="127.0.0.1",
        port=3306,
        database=database,
    ).render_as_string(hide_password=False)


def test_admin_url_requires_the_exact_mysql_admin_database() -> None:
    parsed = harness._parse_admin_url(_admin_url())
    assert parsed.get_backend_name() == "mysql"
    assert parsed.database == "mysql"

    with pytest.raises(harness.MysqlAcceptanceHarnessError) as wrong_backend:
        harness._parse_admin_url(_admin_url(drivername="postgresql"))
    assert wrong_backend.value.code == "MYSQL_ADMIN_URL_BACKEND_UNSUPPORTED"

    with pytest.raises(harness.MysqlAcceptanceHarnessError) as wrong_database:
        harness._parse_admin_url(_admin_url(database="app_db"))
    assert wrong_database.value.code == "MYSQL_ADMIN_URL_DATABASE_MUST_BE_MYSQL"

    with pytest.raises(harness.MysqlAcceptanceHarnessError) as missing_password:
        harness._parse_admin_url(_admin_url().replace("root:pw@", "root@"))
    assert missing_password.value.code == "MYSQL_ADMIN_URL_CREDENTIALS_INCOMPLETE"


def test_temporary_database_names_are_owned_and_uuid_shaped() -> None:
    name = harness._temporary_database_name()
    assert harness._require_own_temporary_database(name) == name

    for unsafe in ("mysql", "iter197_mysql_acceptance_", "iter197_mysql_acceptance_zz"):
        with pytest.raises(harness.MysqlAcceptanceHarnessError) as rejected:
            harness._require_own_temporary_database(unsafe)
        assert rejected.value.code == "MYSQL_TEMPORARY_DATABASE_NAME_INVALID"


def test_dry_run_emits_not_run_without_network_or_credentials(capsys) -> None:
    assert harness.main(["--mysql-admin-url", _admin_url()]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "not_run"
    assert payload["code"] == "APPLY_CONFIRMATION_REQUIRED"
    assert payload["network_called"] is False
    assert payload["temporary_database_created"] is False
    assert payload["credential_writes"] is False
    # The descriptor must not leak the host, username, or password.
    assert set(payload["admin_connection"]) == {"backend", "database", "has_password"}


def test_apply_never_connects_before_the_explicit_flag(monkeypatch, capsys) -> None:
    def fail_if_connected(*args, **kwargs):
        del args, kwargs
        pytest.fail("a dry run must not build an engine or open a connection")

    monkeypatch.setattr(harness, "_admin_engine", fail_if_connected)
    monkeypatch.setattr(harness, "create_async_engine", fail_if_connected)

    assert harness.main(["--mysql-admin-url", _admin_url()]) == 0


def test_invalid_admin_url_is_a_stable_terminal_failure(capsys) -> None:
    assert harness.main(["--mysql-admin-url", "not-a-url"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["code"] == "MYSQL_ADMIN_URL_MALFORMED"


def test_case_distinct_probe_identities_are_frozen_futures_contracts() -> None:
    upper = harness._futures_identity("instrument:futures:SHFE:RB0", "RB0")
    lower = harness._futures_identity("instrument:futures:SHFE:rb0", "rb0")
    assert upper.canonical_id != lower.canonical_id
    assert upper.asset_type == "futures"
    assert upper.details.kind == "FUTURES"
