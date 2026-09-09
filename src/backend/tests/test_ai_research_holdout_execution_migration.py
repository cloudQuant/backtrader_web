"""Migration contract for the durable sealed-holdout execution journal."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from alembic import command

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PREVIOUS = "20260908_ai_research_evidence_command"
_HEAD = "20260908_ai_research_holdout_executions"
_INTEGRATED_HEAD = "20260909_market_data_research_binding_consumers"
_TABLE = "ai_research_holdout_executions"
_COLUMNS = {
    "id",
    "operation_id",
    "user_id",
    "command_id",
    "evaluation_id",
    "command_hash",
    "lease_owner",
    "lease_generation",
    "lease_expires_at",
    "state",
    "command_json",
    "result_hash",
    "result_json",
    "error_code",
    "prepared_at",
    "dispatched_at",
    "observed_at",
    "not_executed_at",
    "settled_at",
    "updated_at",
}
_UNIQUES = {
    "uq_ai_research_holdout_execution_operation",
    "uq_ai_research_holdout_execution_command",
}
_INDEXES = {
    "ix_ai_research_holdout_execution_state_updated",
    "ix_ai_research_holdout_execution_owner_command",
}
_CHECKS = {
    "ck_ai_research_holdout_execution_state",
    "ck_ai_research_holdout_execution_generation",
    "ck_ai_research_holdout_execution_result_group",
    "ck_ai_research_holdout_execution_result_state",
    "ck_ai_research_holdout_execution_error_state",
    "ck_ai_research_holdout_execution_settlement",
}


def _config(database_url: str, *, output: StringIO | None = None) -> Config:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _run_online(database_url: str, revision: str) -> None:
    config = _config(database_url)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, revision)
    finally:
        engine.dispose()


def test_holdout_execution_revision_has_an_approval_successor_in_the_integrated_graph() -> None:
    script = ScriptDirectory.from_config(_config("sqlite://"))
    migration = script.get_revision(_HEAD)

    assert migration is not None
    assert migration.down_revision == _PREVIOUS
    assert script.get_heads() == [_INTEGRATED_HEAD]


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///fixture.db",
        "postgresql://fixture:fixture@127.0.0.1/fixture",
        "mysql+pymysql://fixture:fixture@127.0.0.1/fixture",
        "mariadb+pymysql://fixture:fixture@127.0.0.1/fixture",
    ],
)
def test_holdout_execution_offline_upgrade_and_downgrade_are_reviewable(
    database_url: str,
) -> None:
    upgrade_output = StringIO()
    command.upgrade(
        _config(database_url, output=upgrade_output),
        f"{_PREVIOUS}:{_HEAD}",
        sql=True,
    )
    rendered_upgrade = upgrade_output.getvalue()

    assert f"CREATE TABLE {_TABLE}" in rendered_upgrade
    for column in _COLUMNS:
        assert column in rendered_upgrade
    for constraint in _UNIQUES | _INDEXES | _CHECKS:
        assert constraint in rendered_upgrade
    assert "EXECUTION_OBSERVED_RECONCILING" in rendered_upgrade
    assert "HOLDOUT_EXECUTION_SCHEMA_CONFLICT" in rendered_upgrade

    downgrade_output = StringIO()
    command.downgrade(
        _config(database_url, output=downgrade_output),
        f"{_HEAD}:{_PREVIOUS}",
        sql=True,
    )
    rendered_downgrade = downgrade_output.getvalue()
    assert "MANUAL PRECHECK: HOLDOUT_EXECUTION_DOWNGRADE_BLOCKED" in rendered_downgrade
    assert f"DROP TABLE {_TABLE}" in rendered_downgrade


def test_holdout_execution_sqlite_online_schema_and_recovery_action(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'holdout-execution.db'}"
    _run_online(database_url, _HEAD)

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert {column["name"] for column in inspector.get_columns(_TABLE)} == _COLUMNS
        assert {unique["name"] for unique in inspector.get_unique_constraints(_TABLE)} == _UNIQUES
        assert {index["name"] for index in inspector.get_indexes(_TABLE)} == _INDEXES
        execution_checks = {check["name"] for check in inspector.get_check_constraints(_TABLE)}
        assert _CHECKS <= execution_checks
        access_checks = {
            check["name"]: str(check.get("sqltext") or "")
            for check in inspector.get_check_constraints("ai_research_holdout_access_audits")
        }
        assert (
            "EXECUTION_OBSERVED_RECONCILING"
            in access_checks["ck_ai_research_holdout_access_audit_action"]
        )
        assert (
            "EXECUTION_OBSERVED_RECONCILING"
            in access_checks["ck_ai_research_holdout_access_audit_outcome"]
        )
    finally:
        engine.dispose()


def test_holdout_execution_sqlite_exact_rerun_is_idempotent(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'holdout-execution-rerun.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": _PREVIOUS},
            )
    finally:
        engine.dispose()

    _run_online(database_url, _HEAD)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                == _HEAD
            )
    finally:
        engine.dispose()


def test_holdout_execution_sqlite_partial_schema_rerun_fails_closed(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'holdout-execution-partial.db'}"
    _run_online(database_url, _PREVIOUS)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f"CREATE TABLE {_TABLE} (id VARCHAR(36) PRIMARY KEY)"))
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="HOLDOUT_EXECUTION_SCHEMA_CONFLICT"):
        _run_online(database_url, _HEAD)


def test_holdout_execution_sqlite_downgrade_refuses_retained_journal(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'holdout-execution-downgrade.db'}"
    _run_online(database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.execute(
                text(
                    f"INSERT INTO {_TABLE} "
                    "(id, operation_id, user_id, command_id, evaluation_id, command_hash, "
                    "lease_owner, lease_generation, lease_expires_at, state, command_json, "
                    "prepared_at, updated_at) "
                    "VALUES ('execution-1', 'operation-1', 'user-1', 'command-1', "
                    "'evaluation-1', :digest, 'worker-1', 1, CURRENT_TIMESTAMP, "
                    "'PREPARED', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"digest": "a" * 64},
            )
    finally:
        engine.dispose()

    config = _config(database_url)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            with pytest.raises(RuntimeError, match="HOLDOUT_EXECUTION_DOWNGRADE_BLOCKED"):
                command.downgrade(config, _PREVIOUS)
    finally:
        engine.dispose()
