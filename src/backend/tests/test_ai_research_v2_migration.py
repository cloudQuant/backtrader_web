"""Schema contract for the protocol-v2 trusted research aggregates."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DatabaseError

import app.config as app_config
from alembic import command

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PARENT = "20260811_asset_research_task_leases"
_PRE_STORAGE_REFERENCE_HEAD = "20260905_ai_research_holdout_candidate_hash"
_PRE_WORKFLOW_VERSION_HEAD = "20260906_ai_research_search_allocation"
_PRE_FREEZE_RECEIPT_HEAD = "20260906_ai_research_workflow_version"
_PRE_HOLDOUT_REQUEST_HEAD = "20260907_ai_research_candidate_freeze_receipt"
_PRE_HOLDOUT_CLAIM_HEAD = "20260907_ai_research_holdout_request"
_PRE_HOLDOUT_FINALIZE_HEAD = "20260907_ai_research_holdout_claim"
_PRE_EVIDENCE_COMMAND_HEAD = "20260907_ai_research_holdout_finalize"
_HEAD = "20260908_ai_research_evidence_command"
_LATEST_HEAD = "20260908_ai_research_approval_authority"
_INTEGRATED_HEAD = "20260911_market_data_b2_completeness_evidence"
_GATE_UNIQUE_NAME = "uq_ai_research_gate_decision_evaluation_input_gate"
_EVIDENCE_COMMAND_COLUMNS = {
    "command_id": "ai_research_holdout_evaluation_commands",
    "evaluation_id": "ai_research_evaluations",
    "artifact_binding_id": "ai_research_holdout_artifact_bindings",
    "terminal_access_audit_id": "ai_research_holdout_access_audits",
}
_EVIDENCE_COMMAND_INDEXES = {
    "ix_ai_research_evidence_package_command_created",
    "ix_ai_research_evidence_package_evaluation",
    "ix_ai_research_evidence_package_artifact_binding",
    "ix_ai_research_evidence_package_terminal_audit",
    "uq_ai_research_evidence_package_command",
}
_EVIDENCE_UPDATE_TRIGGER = "trg_ai_research_evidence_package_update_guard"
_EVIDENCE_DELETE_TRIGGER = "trg_ai_research_evidence_package_delete_guard"
_EVIDENCE_INSERT_TRIGGER = "trg_ai_research_evidence_package_migration_insert_freeze"
_EVIDENCE_FREEZE_TRIGGER = "trg_ai_research_evidence_package_migration_freeze"
_TABLES = {
    "ai_research_capability_profiles",
    "ai_research_config_profiles",
    "ai_research_data_prechecks",
    "ai_research_hypothesis_versions",
    "ai_research_experiment_epochs",
    "ai_research_dataset_snapshots",
    "ai_research_forward_observation_epochs",
    "ai_research_forward_observation_snapshots",
    "ai_research_runs",
    "ai_research_tasks",
    "ai_research_task_events",
    "ai_research_artifacts",
    "ai_research_artifact_contents",
    "ai_research_candidates",
    "ai_research_candidate_freeze_receipts",
    "ai_research_evidence_packages",
    "ai_research_trials",
    "ai_research_model_invocations",
    "ai_research_holdout_authorizations",
    "ai_research_holdout_evaluation_commands",
    "ai_research_holdout_request_audits",
    "ai_research_holdout_access_audits",
    "ai_research_holdout_artifact_bindings",
    "ai_research_evaluations",
    "ai_research_gate_decisions",
    "ai_research_approval_requests",
    "ai_research_human_decisions",
    "ai_research_governance_decisions",
    "ai_research_stage_attempts",
    "ai_research_stage_artifact_bindings",
    "ai_research_generation_materializations",
    "ai_research_discovery_executions",
    "ai_research_quota_buckets",
    "ai_research_quota_reservations",
}


def _config(database_url: str) -> Config:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _upgrade(config: Config, database_url: str, revision: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, revision)
    finally:
        engine.dispose()


def _downgrade(config: Config, database_url: str, revision: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, revision)
    finally:
        engine.dispose()


def _offline_config(database_url: str) -> tuple[Config, StringIO]:
    output = StringIO()
    config = Config(str(_BACKEND_ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config, output


def test_evidence_command_graph_revision_loads_via_alembic_script_directory() -> None:
    """The revision must load through Alembic's transient module loader."""

    script = ScriptDirectory.from_config(_config("sqlite://"))
    loaded = script.get_revision(_HEAD)

    assert loaded is not None
    assert loaded.module.revision == _HEAD


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///fixture.db",
        "postgresql://fixture:fixture@127.0.0.1/fixture",
        "mysql+pymysql://fixture:fixture@127.0.0.1/fixture",
        "mariadb+pymysql://fixture:fixture@127.0.0.1/fixture",
    ],
)
def test_evidence_command_graph_offline_upgrade_and_downgrade_are_reviewable(
    database_url: str,
) -> None:
    """Every supported dialect must render the nullable graph and safe rollback SQL."""

    config, upgrade_output = _offline_config(database_url)
    command.upgrade(
        config,
        f"{_PRE_EVIDENCE_COMMAND_HEAD}:{_HEAD}",
        sql=True,
    )

    rendered_upgrade = upgrade_output.getvalue()
    for column_name in _EVIDENCE_COMMAND_COLUMNS:
        assert column_name in rendered_upgrade
    for index_name in _EVIDENCE_COMMAND_INDEXES:
        assert index_name in rendered_upgrade
    assert "uq_ai_research_evidence_package_command_manifest" not in rendered_upgrade
    assert "ck_ai_research_evidence_package_command_graph" in rendered_upgrade
    precheck_errors = {
        "EVIDENCE_COMMAND_GRAPH_PARTIAL_DATA",
        "EVIDENCE_COMMAND_GRAPH_DUPLICATE_COMMAND",
        "EVIDENCE_COMMAND_GRAPH_ORPHAN_COMMAND",
        "EVIDENCE_COMMAND_GRAPH_ORPHAN_EVALUATION",
        "EVIDENCE_COMMAND_GRAPH_ORPHAN_ARTIFACT_BINDING",
        "EVIDENCE_COMMAND_GRAPH_ORPHAN_TERMINAL_ACCESS_AUDIT",
    }
    for error_code in precheck_errors:
        assert f"MANUAL PRECHECK: {error_code}" in rendered_upgrade
    assert "HAVING COUNT(*) > 1" in rendered_upgrade
    for target_table in _EVIDENCE_COMMAND_COLUMNS.values():
        assert f"LEFT JOIN {target_table}" in rendered_upgrade
    insert_position = rendered_upgrade.index(f"CREATE TRIGGER {_EVIDENCE_INSERT_TRIGGER}")
    freeze_position = rendered_upgrade.index(f"CREATE TRIGGER {_EVIDENCE_FREEZE_TRIGGER}")
    delete_position = rendered_upgrade.index(f"CREATE TRIGGER {_EVIDENCE_DELETE_TRIGGER}")
    column_position = rendered_upgrade.index("command_id")
    precheck_position = rendered_upgrade.index(
        "MANUAL PRECHECK: EVIDENCE_COMMAND_GRAPH_PARTIAL_DATA"
    )
    unique_position = rendered_upgrade.index("uq_ai_research_evidence_package_command")
    update_position = rendered_upgrade.index(f"CREATE TRIGGER {_EVIDENCE_UPDATE_TRIGGER}")
    freeze_drop_position = rendered_upgrade.rindex(_EVIDENCE_FREEZE_TRIGGER)
    assert insert_position < freeze_position < column_position
    assert delete_position < column_position
    assert column_position < precheck_position < unique_position
    insert_drop_position = rendered_upgrade.rindex(_EVIDENCE_INSERT_TRIGGER)
    assert column_position < update_position < freeze_drop_position < insert_drop_position
    assert "EVIDENCE_PACKAGE_IMMUTABLE" in rendered_upgrade
    assert _HEAD in rendered_upgrade

    config, downgrade_output = _offline_config(database_url)
    command.downgrade(
        config,
        f"{_HEAD}:{_PRE_EVIDENCE_COMMAND_HEAD}",
        sql=True,
    )

    rendered_downgrade = downgrade_output.getvalue()
    assert "MANUAL PRECHECK: EVIDENCE_COMMAND_GRAPH_DOWNGRADE_BLOCKED" in rendered_downgrade
    for column_name in _EVIDENCE_COMMAND_COLUMNS:
        assert column_name in rendered_downgrade
    downgrade_insert_create = rendered_downgrade.index(f"CREATE TRIGGER {_EVIDENCE_INSERT_TRIGGER}")
    downgrade_freeze_create = rendered_downgrade.index(f"CREATE TRIGGER {_EVIDENCE_FREEZE_TRIGGER}")
    downgrade_precheck = rendered_downgrade.index(
        "MANUAL PRECHECK: EVIDENCE_COMMAND_GRAPH_DOWNGRADE_BLOCKED"
    )
    update_guard_drop = rendered_downgrade.index(_EVIDENCE_UPDATE_TRIGGER)
    final_column_drop = max(
        rendered_downgrade.rindex(column_name) for column_name in _EVIDENCE_COMMAND_COLUMNS
    )
    delete_guard_drop = rendered_downgrade.rindex(_EVIDENCE_DELETE_TRIGGER)
    downgrade_freeze_drop = rendered_downgrade.rindex(_EVIDENCE_FREEZE_TRIGGER)
    downgrade_insert_drop = rendered_downgrade.rindex(_EVIDENCE_INSERT_TRIGGER)
    assert downgrade_insert_create < downgrade_freeze_create < downgrade_precheck
    assert downgrade_precheck < update_guard_drop < final_column_drop
    assert final_column_drop < delete_guard_drop < downgrade_freeze_drop < downgrade_insert_drop


@pytest.mark.parametrize(
    "database_url",
    [
        "mysql+pymysql://fixture:fixture@127.0.0.1/fixture",
        "mariadb+pymysql://fixture:fixture@127.0.0.1/fixture",
    ],
)
def test_evidence_package_mysql_family_offline_update_guard_uses_explicit_delimiter(
    database_url: str,
) -> None:
    """The rendered compound trigger must be directly consumable by mysql-family clients."""

    config, output = _offline_config(database_url)
    command.upgrade(config, f"{_PRE_EVIDENCE_COMMAND_HEAD}:{_HEAD}", sql=True)
    rendered = output.getvalue()

    assert "DELIMITER $$" in rendered
    assert (
        f"CREATE TRIGGER {_EVIDENCE_UPDATE_TRIGGER} BEFORE UPDATE "
        "ON ai_research_evidence_packages FOR EACH ROW BEGIN IF NOT"
    ) in rendered
    assert "END IF; END$$" in rendered
    assert rendered.index("DELIMITER $$") < rendered.index(
        f"CREATE TRIGGER {_EVIDENCE_UPDATE_TRIGGER}"
    )
    assert rendered.index(f"CREATE TRIGGER {_EVIDENCE_UPDATE_TRIGGER}") < rendered.index(
        "DELIMITER ;"
    )


def test_evidence_command_graph_downgrade_rechecks_after_insert_write_fence(
    tmp_path,
    monkeypatch,
) -> None:
    """The last destructive precheck must execute only after INSERT is actually fenced."""

    database_url = f"sqlite:///{tmp_path / 'evidence-command-downgrade-insert-fence.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)
    observed: dict[str, bool] = {}

    def inject_insert_at_final_precheck(
        connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany: bool,
    ) -> None:
        normalized = " ".join(statement.upper().split())
        if observed or not (
            normalized.startswith("SELECT 1 FROM AI_RESEARCH_EVIDENCE_PACKAGES WHERE")
            and "COMMAND_ID IS NOT NULL" in normalized
        ):
            return
        try:
            connection.execute(
                text(
                    "INSERT INTO ai_research_evidence_packages "
                    "(id, user_id, run_id, candidate_id, command_id, evaluation_id, "
                    "artifact_binding_id, terminal_access_audit_id, promotion_policy_version, "
                    "gate_input_evidence_hash, manifest, manifest_hash, approval_binding_hash, "
                    "status, created_at) VALUES "
                    "(:id, :user_id, :run_id, :candidate_id, NULL, NULL, NULL, NULL, "
                    "'promotion-v1', :gate_hash, :manifest, :manifest_hash, :binding_hash, "
                    "'ACTIVE', :created_at)"
                ),
                {
                    "id": "a1111111-1111-1111-1111-111111111111",
                    "user_id": "a2222222-2222-2222-2222-222222222222",
                    "run_id": "a3333333-3333-3333-3333-333333333333",
                    "candidate_id": "a4444444-4444-4444-4444-444444444444",
                    "gate_hash": "1" * 64,
                    "manifest": json.dumps(
                        {"manifest_version": "ai_research_evidence_manifest/v1"}
                    ),
                    "manifest_hash": "2" * 64,
                    "binding_hash": "3" * 64,
                    "created_at": "2026-09-08 00:00:00",
                },
            )
        except DatabaseError as exc:
            observed["insert_fenced"] = "EVIDENCE_PACKAGE_IMMUTABLE" in str(exc)
        else:
            observed["insert_fenced"] = False

    event.listen(Engine, "before_cursor_execute", inject_insert_at_final_precheck)
    try:
        _downgrade(config, database_url, _PRE_EVIDENCE_COMMAND_HEAD)
    finally:
        event.remove(Engine, "before_cursor_execute", inject_insert_at_final_precheck)

    assert observed == {"insert_fenced": True}
    assert "command_id" not in {
        item["name"]
        for item in inspect(create_engine(database_url)).get_columns(
            "ai_research_evidence_packages"
        )
    }


def test_evidence_command_graph_downgrade_precheck_block_restores_temporary_guards(
    monkeypatch,
) -> None:
    """A pre-DDL safety block must remove only the temporary fences it installed."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    bind = SimpleNamespace(dialect=SimpleNamespace(name="mysql"))
    events: list[str] = []
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)
    monkeypatch.setattr(
        migration,
        "_create_insert_guard",
        lambda _bind: events.append("create-insert"),
    )
    monkeypatch.setattr(
        migration,
        "_create_freeze_guard",
        lambda _bind: events.append("create-update-freeze"),
    )

    def blocked_precheck(_bind) -> None:
        events.append("precheck")
        raise RuntimeError("EVIDENCE_COMMAND_GRAPH_DOWNGRADE_BLOCKED")

    monkeypatch.setattr(migration, "_assert_downgrade_safe", blocked_precheck)
    monkeypatch.setattr(
        migration,
        "_drop_freeze_guard",
        lambda _bind: events.append("drop-update-freeze"),
    )
    monkeypatch.setattr(
        migration,
        "_drop_insert_guard",
        lambda _bind: events.append("drop-insert"),
    )
    monkeypatch.setattr(
        migration,
        "_drop_guard",
        lambda *_args: events.append("drop-permanent"),
    )
    monkeypatch.setattr(
        migration,
        "_downgrade_online",
        lambda _bind: events.append("ddl"),
    )

    with pytest.raises(RuntimeError, match="^EVIDENCE_COMMAND_GRAPH_DOWNGRADE_BLOCKED$"):
        migration.downgrade()

    assert events == [
        "create-insert",
        "create-update-freeze",
        "precheck",
        "drop-update-freeze",
        "drop-insert",
    ]


def test_evidence_command_graph_downgrade_ddl_failure_retains_write_fences(
    monkeypatch,
) -> None:
    """After destructive DDL starts, a failure must leave both fences for marker-loss retry."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    bind = SimpleNamespace(dialect=SimpleNamespace(name="mysql"))
    events: list[str] = []
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)
    monkeypatch.setattr(
        migration,
        "_create_insert_guard",
        lambda _bind: events.append("create-insert"),
    )
    monkeypatch.setattr(
        migration,
        "_create_freeze_guard",
        lambda _bind: events.append("create-update-freeze"),
    )
    monkeypatch.setattr(
        migration,
        "_assert_downgrade_safe",
        lambda _bind: events.append("precheck"),
    )
    monkeypatch.setattr(
        migration,
        "_drop_guard",
        lambda *_args: events.append("drop-permanent-update"),
    )
    monkeypatch.setattr(
        migration,
        "_drop_freeze_guard",
        lambda _bind: events.append("drop-update-freeze"),
    )
    monkeypatch.setattr(
        migration,
        "_drop_insert_guard",
        lambda _bind: events.append("drop-insert"),
    )

    def failed_ddl(_bind) -> None:
        events.append("ddl-failed")
        raise RuntimeError("INJECTED_NONTRANSACTIONAL_DDL_FAILURE")

    monkeypatch.setattr(migration, "_downgrade_online", failed_ddl)

    with pytest.raises(RuntimeError, match="^INJECTED_NONTRANSACTIONAL_DDL_FAILURE$"):
        migration.downgrade()

    assert events == [
        "create-insert",
        "create-update-freeze",
        "precheck",
        "drop-permanent-update",
        "ddl-failed",
    ]


def test_evidence_command_graph_upgrade_preflight_runs_after_insert_write_fence(
    tmp_path,
    monkeypatch,
) -> None:
    """Expansion preflight also runs with INSERT blocked throughout the DDL window."""

    database_url = f"sqlite:///{tmp_path / 'evidence-command-upgrade-insert-fence.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _PRE_EVIDENCE_COMMAND_HEAD)
    observed: dict[str, bool] = {}

    def inject_insert_at_upgrade_precheck(
        connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany: bool,
    ) -> None:
        normalized = " ".join(statement.upper().split())
        if observed or not normalized.startswith(
            "SELECT 1 FROM AI_RESEARCH_EVIDENCE_PACKAGES AS PACKAGE WHERE NOT"
        ):
            return
        try:
            connection.execute(
                text(
                    "INSERT INTO ai_research_evidence_packages "
                    "(id, user_id, run_id, candidate_id, command_id, evaluation_id, "
                    "artifact_binding_id, terminal_access_audit_id, promotion_policy_version, "
                    "gate_input_evidence_hash, manifest, manifest_hash, approval_binding_hash, "
                    "status, created_at) VALUES "
                    "(:id, :user_id, :run_id, :candidate_id, NULL, NULL, NULL, NULL, "
                    "'promotion-v1', :gate_hash, :manifest, :manifest_hash, :binding_hash, "
                    "'ACTIVE', :created_at)"
                ),
                {
                    "id": "91111111-1111-1111-1111-111111111111",
                    "user_id": "92222222-2222-2222-2222-222222222222",
                    "run_id": "93333333-3333-3333-3333-333333333333",
                    "candidate_id": "94444444-4444-4444-4444-444444444444",
                    "gate_hash": "1" * 64,
                    "manifest": json.dumps(
                        {"manifest_version": "ai_research_evidence_manifest/v1"}
                    ),
                    "manifest_hash": "2" * 64,
                    "binding_hash": "3" * 64,
                    "created_at": "2026-09-08 00:00:00",
                },
            )
        except DatabaseError as exc:
            observed["insert_fenced"] = "EVIDENCE_PACKAGE_IMMUTABLE" in str(exc)
        else:
            observed["insert_fenced"] = False

    event.listen(Engine, "before_cursor_execute", inject_insert_at_upgrade_precheck)
    try:
        _upgrade(config, database_url, _HEAD)
    finally:
        event.remove(Engine, "before_cursor_execute", inject_insert_at_upgrade_precheck)

    assert observed == {"insert_fenced": True}


@pytest.mark.parametrize(
    ("dirty_kind", "orphan_column", "expected_error"),
    [
        ("partial", None, "EVIDENCE_COMMAND_GRAPH_PARTIAL_DATA"),
        ("duplicate", None, "EVIDENCE_COMMAND_GRAPH_DUPLICATE_COMMAND"),
        ("orphan", "command_id", "EVIDENCE_COMMAND_GRAPH_ORPHAN_COMMAND"),
        ("orphan", "evaluation_id", "EVIDENCE_COMMAND_GRAPH_ORPHAN_EVALUATION"),
        (
            "orphan",
            "artifact_binding_id",
            "EVIDENCE_COMMAND_GRAPH_ORPHAN_ARTIFACT_BINDING",
        ),
        (
            "orphan",
            "terminal_access_audit_id",
            "EVIDENCE_COMMAND_GRAPH_ORPHAN_TERMINAL_ACCESS_AUDIT",
        ),
    ],
)
def test_evidence_command_graph_upgrade_preflight_rejects_dirty_authority_data(
    tmp_path,
    monkeypatch,
    dirty_kind: str,
    orphan_column: str | None,
    expected_error: str,
) -> None:
    """Upgrade preflight must name dirty rows before DDL can bless or obscure them."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    engine = create_engine(f"sqlite:///{tmp_path / f'evidence-dirty-{expected_error}.db'}")
    try:
        with engine.begin() as connection:
            for target_table in _EVIDENCE_COMMAND_COLUMNS.values():
                connection.execute(
                    text(f"CREATE TABLE {target_table} (id VARCHAR(36) PRIMARY KEY)")
                )
            connection.execute(
                text(
                    "CREATE TABLE ai_research_evidence_packages ("
                    "id VARCHAR(36) PRIMARY KEY, command_id VARCHAR(36), "
                    "evaluation_id VARCHAR(36), artifact_binding_id VARCHAR(36), "
                    "terminal_access_audit_id VARCHAR(36))"
                )
            )
            authority_ids = {
                "command_id": "command-ok",
                "evaluation_id": "evaluation-ok",
                "artifact_binding_id": "binding-ok",
                "terminal_access_audit_id": "audit-ok",
            }
            for column_name, target_table in _EVIDENCE_COMMAND_COLUMNS.items():
                connection.execute(
                    text(f"INSERT INTO {target_table} (id) VALUES (:id)"),
                    {"id": authority_ids[column_name]},
                )

            first = dict(authority_ids)
            if dirty_kind == "partial":
                first.update(
                    evaluation_id=None,
                    artifact_binding_id=None,
                    terminal_access_audit_id=None,
                )
            elif orphan_column is not None:
                first[orphan_column] = "missing-authority"
            insert = text(
                "INSERT INTO ai_research_evidence_packages "
                "(id, command_id, evaluation_id, artifact_binding_id, terminal_access_audit_id) "
                "VALUES (:id, :command_id, :evaluation_id, :artifact_binding_id, "
                ":terminal_access_audit_id)"
            )
            connection.execute(insert, {"id": "package-one", **first})
            if dirty_kind == "duplicate":
                connection.execute(insert, {"id": "package-two", **authority_ids})

            with pytest.raises(RuntimeError, match=f"^{expected_error}$"):
                migration._assert_upgrade_data_clean(connection)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "column_definition",
    [
        "TEXT",
        "VARCHAR(35)",
        "VARCHAR(36) NOT NULL",
    ],
)
def test_evidence_command_graph_reentry_rejects_wrong_existing_column_contract(
    tmp_path,
    monkeypatch,
    column_definition: str,
) -> None:
    """Marker-loss recovery must not bless a lookalike authority column."""

    database_url = f"sqlite:///{tmp_path / 'evidence-command-column-conflict.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _PRE_EVIDENCE_COMMAND_HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE ai_research_evidence_packages ADD COLUMN command_id "
                    f"{column_definition} REFERENCES "
                    "ai_research_holdout_evaluation_commands(id) ON DELETE RESTRICT"
                )
            )
        with pytest.raises(RuntimeError, match="^EVIDENCE_COMMAND_GRAPH_COLUMN_CONFLICT$"):
            _upgrade(config, database_url, _HEAD)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "foreign_key_sql",
    [
        (
            "REFERENCES ai_research_holdout_evaluation_commands(id) ON DELETE RESTRICT "
            "REFERENCES ai_research_evaluations(id) ON DELETE RESTRICT"
        ),
        "REFERENCES ai_research_holdout_evaluation_commands(id) ON DELETE CASCADE",
    ],
)
def test_evidence_command_graph_reentry_rejects_ambiguous_or_weak_foreign_key(
    tmp_path,
    monkeypatch,
    foreign_key_sql: str,
) -> None:
    """Exactly one RESTRICT FK may bind each authority column to its expected target."""

    database_url = f"sqlite:///{tmp_path / 'evidence-command-fk-conflict.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _PRE_EVIDENCE_COMMAND_HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE ai_research_evidence_packages ADD COLUMN command_id "
                    f"VARCHAR(36) {foreign_key_sql}"
                )
            )
        with pytest.raises(
            RuntimeError,
            match="^EVIDENCE_COMMAND_GRAPH_FOREIGN_KEY_CONFLICT$",
        ):
            _upgrade(config, database_url, _HEAD)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "unsafe_metadata",
    [
        {"dialect_options": {"sqlite_where": "command_id IS NOT NULL"}},
        {"filter_definition": "command_id IS NOT NULL"},
        {"include_columns": ["created_at"]},
        {"dialect_options": {"mysql_length": {"command_id": 12}}},
        {"column_names": [None], "expressions": ["lower(command_id)"]},
        {"dialect_options": {"postgresql_ops": {"command_id": "text_pattern_ops"}}},
        {"dialect_options": {"mysql_with_parser": "ngram"}},
        {"dialect_options": {"mysql_visible": False}},
        {"dialect_options": {"postgresql_nulls_not_distinct": True}},
    ],
)
def test_evidence_command_graph_reentry_rejects_partial_command_unique_index(
    tmp_path,
    monkeypatch,
    unsafe_metadata: dict[str, object],
) -> None:
    """A same-name unique index with hidden semantics is not the command authority."""

    database_url = f"sqlite:///{tmp_path / 'evidence-command-unsafe-index.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)
    migration = ScriptDirectory.from_config(config).get_revision(_HEAD).module
    real_inspect = inspect
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            delegate = real_inspect(connection)

            class UnsafeIndexInspector:
                def __getattr__(self, name: str):
                    return getattr(delegate, name)

                def get_indexes(self, table_name: str) -> list[dict[str, object]]:
                    indexes = [dict(item) for item in delegate.get_indexes(table_name)]
                    for item in indexes:
                        if item.get("name") == "uq_ai_research_evidence_package_command":
                            item.update(unsafe_metadata)
                    return indexes

            monkeypatch.setattr(migration.sa, "inspect", lambda _bind: UnsafeIndexInspector())
            monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
            with pytest.raises(RuntimeError, match="^EVIDENCE_COMMAND_GRAPH_INDEX_CONFLICT$"):
                migration._upgrade_online(connection)
    finally:
        engine.dispose()


@pytest.mark.parametrize("dialect_name", ["mysql", "mariadb"])
def test_evidence_command_graph_mysql_family_reentry_accepts_unique_index_type(
    tmp_path,
    monkeypatch,
    dialect_name: str,
) -> None:
    """MySQL-family ``type=UNIQUE`` reflection is metadata, not an index drift."""

    database_url = f"sqlite:///{tmp_path / f'evidence-command-{dialect_name}-index.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)
    migration = ScriptDirectory.from_config(config).get_revision(_HEAD).module
    real_inspect = inspect
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            delegate = real_inspect(connection)

            class MysqlFamilyIndexInspector:
                def __getattr__(self, name: str):
                    return getattr(delegate, name)

                @staticmethod
                def get_foreign_keys(_table_name: str) -> list[dict[str, object]]:
                    return [
                        {
                            "name": f"fk_ai_research_evidence_package_{column_name}",
                            "constrained_columns": [column_name],
                            "referred_table": target_table,
                            "referred_columns": ["id"],
                            "options": {"ondelete": "RESTRICT"},
                        }
                        for column_name, target_table in _EVIDENCE_COMMAND_COLUMNS.items()
                    ]

                def get_indexes(self, table_name: str) -> list[dict[str, object]]:
                    indexes = [dict(item) for item in delegate.get_indexes(table_name)]
                    for item in indexes:
                        if item.get("name") == "uq_ai_research_evidence_package_command":
                            item["type"] = "UNIQUE"
                    return indexes

            mysql_family_bind = SimpleNamespace(
                dialect=SimpleNamespace(name=dialect_name),
                execute=connection.execute,
            )
            monkeypatch.setattr(
                migration.sa,
                "inspect",
                lambda _bind: MysqlFamilyIndexInspector(),
            )
            monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)

            migration._upgrade_online(mysql_family_bind)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    (
        "dialect_name",
        "reflected_unique",
        "expected_unique",
        "reflected_type",
        "expected_match",
    ),
    [
        ("mysql", True, True, "UNIQUE", True),
        ("mariadb", True, True, "UNIQUE", True),
        ("sqlite", True, True, "UNIQUE", False),
        ("postgresql", True, True, "UNIQUE", False),
        ("mysql", False, False, "UNIQUE", False),
        ("mysql", True, True, "BTREE", False),
    ],
)
def test_evidence_command_graph_unique_reflection_type_is_dialect_scoped(
    dialect_name: str,
    reflected_unique: bool,
    expected_unique: bool,
    reflected_type: str,
    expected_match: bool,
) -> None:
    """Only a unique MySQL-family target may expose ``type=UNIQUE`` metadata."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    reflected = {
        "name": "uq_ai_research_evidence_package_command",
        "column_names": ["command_id"],
        "unique": reflected_unique,
        "type": reflected_type,
    }

    assert (
        migration._index_matches(
            reflected,
            columns=("command_id",),
            unique=expected_unique,
            dialect_name=dialect_name,
        )
        is expected_match
    )


def test_evidence_command_graph_check_matcher_requires_exact_equivalence() -> None:
    """Backtick normalization must not turn a token superset into an accepted CHECK."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    valid = (
        "((`command_id` IS NULL AND `evaluation_id` IS NULL AND "
        "`artifact_binding_id` IS NULL AND `terminal_access_audit_id` IS NULL) OR "
        "(`command_id` IS NOT NULL AND `evaluation_id` IS NOT NULL AND "
        "`artifact_binding_id` IS NOT NULL AND `terminal_access_audit_id` IS NOT NULL))"
    )

    assert migration._graph_check_matches(valid)
    assert not migration._graph_check_matches(f"({valid}) OR 1 = 1")
    assert not migration._graph_check_matches(f"({valid}) AND 1 = 0")


def test_evidence_command_graph_reentry_accepts_real_mysql_reflected_check() -> None:
    """MySQL wraps each null predicate; grouping, rather than parentheses, is authoritative."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    reflected = (
        "(((`command_id` is null) and (`evaluation_id` is null) and "
        "(`artifact_binding_id` is null) and (`terminal_access_audit_id` is null)) or "
        "((`command_id` is not null) and (`evaluation_id` is not null) and "
        "(`artifact_binding_id` is not null) and "
        "(`terminal_access_audit_id` is not null)))"
    )
    wrong_grouping = (
        "(((`command_id` is null) and (`evaluation_id` is null)) or "
        "((`artifact_binding_id` is null) and (`terminal_access_audit_id` is null)) or "
        "((`command_id` is not null) and (`evaluation_id` is not null) and "
        "(`artifact_binding_id` is not null) and "
        "(`terminal_access_audit_id` is not null)))"
    )

    assert migration._graph_check_matches(reflected)
    assert not migration._graph_check_matches(wrong_grouping)


def test_evidence_package_database_guard_allows_only_irreversible_withdrawal(
    tmp_path,
    monkeypatch,
) -> None:
    """The database, not caller discipline, owns package immutability."""

    database_url = f"sqlite:///{tmp_path / 'evidence-package-guard.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)
    engine = create_engine(database_url)
    package_id = "e1111111-1111-1111-1111-111111111111"
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.execute(
                text(
                    "INSERT INTO ai_research_evidence_packages "
                    "(id, user_id, run_id, candidate_id, command_id, evaluation_id, "
                    "artifact_binding_id, terminal_access_audit_id, promotion_policy_version, "
                    "gate_input_evidence_hash, manifest, manifest_hash, approval_binding_hash, "
                    "status, created_at) VALUES "
                    "(:id, :user_id, :run_id, :candidate_id, NULL, NULL, NULL, NULL, "
                    "'promotion-v1', :gate_hash, :manifest, :manifest_hash, :binding_hash, "
                    "'ACTIVE', :created_at)"
                ),
                {
                    "id": package_id,
                    "user_id": "e2222222-2222-2222-2222-222222222222",
                    "run_id": "e3333333-3333-3333-3333-333333333333",
                    "candidate_id": "e4444444-4444-4444-4444-444444444444",
                    "gate_hash": "1" * 64,
                    "manifest": json.dumps(
                        {"manifest_version": "ai_research_evidence_manifest/v1"}
                    ),
                    "manifest_hash": "2" * 64,
                    "binding_hash": "3" * 64,
                    "created_at": "2026-09-08 00:00:00",
                },
            )
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")

        forbidden_updates = {
            "user_id": "e5555555-5555-5555-5555-555555555555",
            "run_id": "e5555555-5555-5555-5555-555555555555",
            "candidate_id": "e5555555-5555-5555-5555-555555555555",
            "command_id": "e5555555-5555-5555-5555-555555555555",
            "evaluation_id": "e5555555-5555-5555-5555-555555555555",
            "artifact_binding_id": "e5555555-5555-5555-5555-555555555555",
            "terminal_access_audit_id": "e5555555-5555-5555-5555-555555555555",
            "promotion_policy_version": "promotion-v2",
            "gate_input_evidence_hash": "4" * 64,
            "manifest": json.dumps({"tampered": True}),
            "manifest_hash": "5" * 64,
            "approval_binding_hash": "6" * 64,
            "created_at": "2026-09-09 00:00:00",
        }
        for column_name, value in forbidden_updates.items():
            with engine.begin() as connection:
                with pytest.raises(DatabaseError, match="EVIDENCE_PACKAGE_IMMUTABLE"):
                    connection.execute(
                        text(
                            "UPDATE ai_research_evidence_packages SET status = 'WITHDRAWN', "
                            f"{column_name} = :value WHERE id = :id"
                        ),
                        {"value": value, "id": package_id},
                    )

        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="EVIDENCE_PACKAGE_IMMUTABLE"):
                connection.execute(
                    text(
                        "UPDATE ai_research_evidence_packages SET status = 'ACTIVE' WHERE id = :id"
                    ),
                    {"id": package_id},
                )
            with pytest.raises(DatabaseError, match="EVIDENCE_PACKAGE_IMMUTABLE"):
                connection.execute(
                    text("DELETE FROM ai_research_evidence_packages WHERE id = :id"),
                    {"id": package_id},
                )

        with engine.begin() as connection:
            assert (
                connection.execute(
                    text(
                        "UPDATE ai_research_evidence_packages SET status = 'WITHDRAWN' "
                        "WHERE id = :id"
                    ),
                    {"id": package_id},
                ).rowcount
                == 1
            )
        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="EVIDENCE_PACKAGE_IMMUTABLE"):
                connection.execute(
                    text(
                        "UPDATE ai_research_evidence_packages SET status = 'WITHDRAWN' "
                        "WHERE id = :id"
                    ),
                    {"id": package_id},
                )
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT status FROM ai_research_evidence_packages WHERE id = :id"),
                    {"id": package_id},
                )
                == "WITHDRAWN"
            )

        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="EVIDENCE_PACKAGE_IMMUTABLE"):
                connection.execute(
                    text(
                        "UPDATE ai_research_evidence_packages SET status = 'ACTIVE' WHERE id = :id"
                    ),
                    {"id": package_id},
                )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "weak_when",
    [
        "WHEN 0",
        "WHEN NEW.status = 'NEVER'",
        "WHEN NOT (NEW.status = 'WITHDRAWN' AND OLD.status = 'WITHDRAWN')",
    ],
)
def test_evidence_package_guard_reentry_rejects_semantically_weak_existing_trigger(
    tmp_path,
    monkeypatch,
    weak_when: str,
) -> None:
    """A marker-complete trigger must not pass reentry unless its full semantics match."""

    database_url = f"sqlite:///{tmp_path / 'evidence-package-weak-guard.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)
    immutable_markers = (
        "id user_id run_id candidate_id command_id evaluation_id artifact_binding_id "
        "terminal_access_audit_id promotion_policy_version gate_input_evidence_hash manifest "
        "manifest_hash approval_binding_hash created_at"
    )
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER {_EVIDENCE_UPDATE_TRIGGER}"))
            connection.execute(
                text(
                    f"CREATE TRIGGER {_EVIDENCE_UPDATE_TRIGGER} BEFORE UPDATE "
                    f"ON ai_research_evidence_packages {weak_when} BEGIN "
                    "SELECT RAISE(ABORT, 'EVIDENCE_PACKAGE_IMMUTABLE WITHDRAWN UPDATE "
                    f"{immutable_markers}'); END"
                )
            )
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": _PRE_EVIDENCE_COMMAND_HEAD},
            )

        with pytest.raises(RuntimeError, match="^EVIDENCE_PACKAGE_GUARD_CONFLICT$"):
            _upgrade(config, database_url, _HEAD)
    finally:
        engine.dispose()


def _postgresql_delete_guard_reflection() -> list[object]:
    expected_signature = (
        "11 deny_ai_research_evidence_package_delete BEGIN "
        "RAISE EXCEPTION 'EVIDENCE_PACKAGE_IMMUTABLE'; RETURN OLD; END;"
    )
    return [
        _EVIDENCE_DELETE_TRIGGER,
        expected_signature,
        "public",
        "public",
        42,
        42,
        "public",
        "O",
        None,
        "",
        "CREATE TRIGGER trg_ai_research_evidence_package_delete_guard BEFORE DELETE ON "
        "public.ai_research_evidence_packages FOR EACH ROW EXECUTE FUNCTION "
        "public.deny_ai_research_evidence_package_delete()",
        "CREATE OR REPLACE FUNCTION public.deny_ai_research_evidence_package_delete() "
        "RETURNS trigger LANGUAGE plpgsql AS $function$ BEGIN RAISE EXCEPTION "
        "'EVIDENCE_PACKAGE_IMMUTABLE'; RETURN OLD; END; $function$",
    ]


def _postgresql_function_reflection(
    trigger_row: list[object],
    *,
    reference_count: int = 1,
    target_reference_count: int = 1,
) -> list[object]:
    return [
        trigger_row[6],
        trigger_row[3],
        73,
        73,
        trigger_row[11],
        reference_count,
        target_reference_count,
    ]


class _PostgresqlGuardBind:
    def __init__(
        self,
        *,
        trigger_rows: list[list[object]],
        function_rows: list[list[object]],
    ) -> None:
        self.dialect = SimpleNamespace(name="postgresql")
        self.trigger_rows = trigger_rows
        self.function_rows = function_rows
        self.queries: list[str] = []

    def execute(self, statement, _params):
        rendered = str(statement)
        self.queries.append(rendered)
        if "FROM pg_proc AS procedure" in rendered:
            return [tuple(row) for row in self.function_rows]
        if "FROM pg_trigger AS trigger" in rendered:
            return [tuple(row) for row in self.trigger_rows]
        raise AssertionError(f"unexpected PostgreSQL catalog query: {rendered}")


def _postgresql_guard_bind(row: list[object]) -> _PostgresqlGuardBind:
    return _PostgresqlGuardBind(
        trigger_rows=[row],
        function_rows=[_postgresql_function_reflection(row)],
    )


def test_evidence_package_postgresql_guard_reentry_accepts_exact_reflection(monkeypatch) -> None:
    """A current-schema, enabled, unconditional PostgreSQL guard is resumable."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    row = _postgresql_delete_guard_reflection()
    expected_signature = str(row[1])
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)

    assert migration._existing_guard_matches(
        _postgresql_guard_bind(row),
        _EVIDENCE_DELETE_TRIGGER,
        expected_signature,
    )


@pytest.mark.parametrize(
    "drift",
    [
        "disabled",
        "when_false",
        "update_of",
        "null_tgattr",
        "other_schema",
        "relation_oid",
        "resolved_relation_oid",
        "function_schema",
        "wrong_trigger_definition",
        "wrong_function_body",
    ],
)
def test_evidence_package_postgresql_guard_reentry_rejects_reflection_drift(
    monkeypatch,
    drift: str,
) -> None:
    """PostgreSQL reflection metadata and full DDL are part of guard identity."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    row = _postgresql_delete_guard_reflection()
    expected_signature = str(row[1])
    if drift == "disabled":
        row[7] = "D"
    elif drift == "when_false":
        row[8] = "{CONST :consttype 16 :constvalue false}"
        row[10] = str(row[10]).replace(
            "FOR EACH ROW",
            "FOR EACH ROW WHEN (false)",
        )
    elif drift == "update_of":
        row[9] = "2"
        row[10] = str(row[10]).replace(
            "BEFORE DELETE",
            "BEFORE UPDATE OF status",
        )
    elif drift == "null_tgattr":
        row[9] = None
    elif drift == "other_schema":
        row[2] = "shadow"
        row[4] = 84
    elif drift == "relation_oid":
        row[4] = 84
    elif drift == "resolved_relation_oid":
        row[5] = 84
    elif drift == "function_schema":
        row[6] = "shadow"
    elif drift == "wrong_trigger_definition":
        row[10] = str(row[10]).replace("BEFORE DELETE", "AFTER DELETE")
    elif drift == "wrong_function_body":
        row[11] = str(row[11]).replace("RETURN OLD", "RETURN NEW")

    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    with pytest.raises(RuntimeError, match="^EVIDENCE_PACKAGE_GUARD_CONFLICT$"):
        migration._existing_guard_matches(
            _postgresql_guard_bind(row),
            _EVIDENCE_DELETE_TRIGGER,
            expected_signature,
        )


def test_evidence_package_postgresql_guard_creates_function_only_when_absent(
    monkeypatch,
) -> None:
    """A new PostgreSQL guard must not use CREATE OR REPLACE against an unknown function."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    emitted: list[str] = []
    bind = _PostgresqlGuardBind(trigger_rows=[], function_rows=[])
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "execute", lambda statement: emitted.append(str(statement)))

    migration._create_delete_guard(bind)

    assert len(emitted) == 2
    assert emitted[0].startswith("CREATE FUNCTION deny_ai_research_evidence_package_delete()")
    assert "OR REPLACE" not in emitted[0]
    assert emitted[1].startswith(f"CREATE TRIGGER {_EVIDENCE_DELETE_TRIGGER}")


def test_evidence_package_postgresql_guard_reuses_exact_orphan_function(
    monkeypatch,
) -> None:
    """Function-created/trigger-missing is a legal partial application when unused."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    trigger_row = _postgresql_delete_guard_reflection()
    bind = _PostgresqlGuardBind(
        trigger_rows=[],
        function_rows=[
            _postgresql_function_reflection(
                trigger_row,
                reference_count=0,
                target_reference_count=0,
            )
        ],
    )
    emitted: list[str] = []
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "execute", lambda statement: emitted.append(str(statement)))

    migration._create_delete_guard(bind)

    assert len(emitted) == 1
    assert emitted[0].startswith(f"CREATE TRIGGER {_EVIDENCE_DELETE_TRIGGER}")
    assert all("CREATE FUNCTION" not in statement for statement in emitted)


@pytest.mark.parametrize(
    "drift",
    ["wrong_body", "wrong_schema", "wrong_oid", "referenced_by_other_trigger"],
)
def test_evidence_package_postgresql_guard_rejects_conflicting_orphan_function(
    monkeypatch,
    drift: str,
) -> None:
    """An orphan function is reusable only with exact identity, body, and zero trigger users."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    trigger_row = _postgresql_delete_guard_reflection()
    function_row = _postgresql_function_reflection(
        trigger_row,
        reference_count=0,
        target_reference_count=0,
    )
    if drift == "wrong_body":
        function_row[4] = str(function_row[4]).replace("RETURN OLD", "RETURN NEW")
    elif drift == "wrong_schema":
        function_row[0] = "shadow"
    elif drift == "wrong_oid":
        function_row[2] = 74
    elif drift == "referenced_by_other_trigger":
        function_row[5] = 1

    bind = _PostgresqlGuardBind(trigger_rows=[], function_rows=[function_row])
    emitted: list[str] = []
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "execute", lambda statement: emitted.append(str(statement)))

    with pytest.raises(RuntimeError, match="^EVIDENCE_PACKAGE_GUARD_CONFLICT$"):
        migration._create_delete_guard(bind)

    assert emitted == []


def test_evidence_package_postgresql_guard_drop_revalidates_exact_pair(monkeypatch) -> None:
    """DROP is allowed only after independently resolving the exact target and sole function use."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    trigger_row = _postgresql_delete_guard_reflection()
    bind = _postgresql_guard_bind(trigger_row)
    emitted: list[str] = []
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "execute", lambda statement: emitted.append(str(statement)))

    migration._drop_guard(
        bind,
        _EVIDENCE_DELETE_TRIGGER,
        "deny_ai_research_evidence_package_delete",
    )

    assert len(bind.queries) == 2
    assert "FROM pg_trigger AS trigger" in bind.queries[0]
    assert "FROM pg_proc AS procedure" in bind.queries[1]
    assert emitted == [
        "DROP TRIGGER IF EXISTS trg_ai_research_evidence_package_delete_guard "
        "ON ai_research_evidence_packages",
        "DROP FUNCTION IF EXISTS deny_ai_research_evidence_package_delete()",
    ]


@pytest.mark.parametrize("drift", ["wrong_body", "wrong_schema", "external_reference"])
def test_evidence_package_postgresql_guard_drop_rejects_function_conflict(
    monkeypatch,
    drift: str,
) -> None:
    """Downgrade must not delete a colliding or externally referenced function."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    trigger_row = _postgresql_delete_guard_reflection()
    function_row = _postgresql_function_reflection(trigger_row)
    if drift == "wrong_body":
        function_row[4] = str(function_row[4]).replace("RETURN OLD", "RETURN NEW")
    elif drift == "wrong_schema":
        function_row[0] = "shadow"
    elif drift == "external_reference":
        function_row[5] = 2

    bind = _PostgresqlGuardBind(
        trigger_rows=[trigger_row],
        function_rows=[function_row],
    )
    emitted: list[str] = []
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "execute", lambda statement: emitted.append(str(statement)))

    with pytest.raises(RuntimeError, match="^EVIDENCE_PACKAGE_GUARD_CONFLICT$"):
        migration._drop_guard(
            bind,
            _EVIDENCE_DELETE_TRIGGER,
            "deny_ai_research_evidence_package_delete",
        )

    assert emitted == []


def test_evidence_package_postgresql_guard_drop_resumes_exact_orphan_cleanup(
    monkeypatch,
) -> None:
    """A crash after trigger DROP may resume by deleting its exact unused function."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    trigger_row = _postgresql_delete_guard_reflection()
    bind = _PostgresqlGuardBind(
        trigger_rows=[],
        function_rows=[
            _postgresql_function_reflection(
                trigger_row,
                reference_count=0,
                target_reference_count=0,
            )
        ],
    )
    emitted: list[str] = []
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "execute", lambda statement: emitted.append(str(statement)))

    migration._drop_guard(
        bind,
        _EVIDENCE_DELETE_TRIGGER,
        "deny_ai_research_evidence_package_delete",
    )

    assert emitted == ["DROP FUNCTION IF EXISTS deny_ai_research_evidence_package_delete()"]


def test_evidence_package_postgresql_guard_drop_is_idempotent_when_pair_is_absent(
    monkeypatch,
) -> None:
    """A marker-loss retry performs no DDL after both migration-owned objects are gone."""

    migration = ScriptDirectory.from_config(_config("sqlite://")).get_revision(_HEAD).module
    bind = _PostgresqlGuardBind(trigger_rows=[], function_rows=[])
    emitted: list[str] = []
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.op, "execute", lambda statement: emitted.append(str(statement)))

    migration._drop_guard(
        bind,
        _EVIDENCE_DELETE_TRIGGER,
        "deny_ai_research_evidence_package_delete",
    )

    assert emitted == []


def test_evidence_package_guard_rejects_repeated_withdrawn_update(
    tmp_path,
    monkeypatch,
) -> None:
    """Only the state transition is legal; an idempotent service must not issue a second UPDATE."""

    database_url = f"sqlite:///{tmp_path / 'evidence-package-repeated-withdrawal.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)
    package_id = "b1111111-1111-1111-1111-111111111111"
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.execute(
                text(
                    "INSERT INTO ai_research_evidence_packages "
                    "(id, user_id, run_id, candidate_id, command_id, evaluation_id, "
                    "artifact_binding_id, terminal_access_audit_id, promotion_policy_version, "
                    "gate_input_evidence_hash, manifest, manifest_hash, approval_binding_hash, "
                    "status, created_at) VALUES "
                    "(:id, :user_id, :run_id, :candidate_id, NULL, NULL, NULL, NULL, "
                    "'promotion-v1', :gate_hash, :manifest, :manifest_hash, :binding_hash, "
                    "'ACTIVE', :created_at)"
                ),
                {
                    "id": package_id,
                    "user_id": "b2222222-2222-2222-2222-222222222222",
                    "run_id": "b3333333-3333-3333-3333-333333333333",
                    "candidate_id": "b4444444-4444-4444-4444-444444444444",
                    "gate_hash": "1" * 64,
                    "manifest": json.dumps(
                        {"manifest_version": "ai_research_evidence_manifest/v1"}
                    ),
                    "manifest_hash": "2" * 64,
                    "binding_hash": "3" * 64,
                    "created_at": "2026-09-08 00:00:00",
                },
            )
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")

        with engine.begin() as connection:
            assert (
                connection.execute(
                    text(
                        "UPDATE ai_research_evidence_packages SET status = 'WITHDRAWN' "
                        "WHERE id = :id"
                    ),
                    {"id": package_id},
                ).rowcount
                == 1
            )
        with engine.begin() as connection:
            with pytest.raises(DatabaseError, match="EVIDENCE_PACKAGE_IMMUTABLE"):
                connection.execute(
                    text(
                        "UPDATE ai_research_evidence_packages SET status = 'WITHDRAWN' "
                        "WHERE id = :id"
                    ),
                    {"id": package_id},
                )
    finally:
        engine.dispose()


def test_evidence_command_graph_upgrade_resumes_after_partial_sqlite_ddl(
    tmp_path,
    monkeypatch,
) -> None:
    """A revision retry must preserve completed DDL and finish the missing graph."""

    database_url = f"sqlite:///{tmp_path / 'evidence-command-partial.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _PRE_EVIDENCE_COMMAND_HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE ai_research_evidence_packages ADD COLUMN command_id "
                    "VARCHAR(36) CONSTRAINT fk_ai_research_evidence_package_command "
                    "REFERENCES ai_research_holdout_evaluation_commands(id) ON DELETE RESTRICT"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX ix_ai_research_evidence_package_command_created "
                    "ON ai_research_evidence_packages (command_id, created_at)"
                )
            )

        _upgrade(config, database_url, _HEAD)
        inspector = inspect(engine)
        columns = {
            column["name"]: column
            for column in inspector.get_columns("ai_research_evidence_packages")
        }
        assert _EVIDENCE_COMMAND_COLUMNS.keys() <= columns.keys()
        assert all(columns[name]["nullable"] for name in _EVIDENCE_COMMAND_COLUMNS)
        assert _EVIDENCE_COMMAND_INDEXES <= {
            index["name"] for index in inspector.get_indexes("ai_research_evidence_packages")
        }
    finally:
        engine.dispose()


def test_evidence_command_graph_partial_sqlite_reentry_runs_named_preflight_before_check_ddl(
    tmp_path,
    monkeypatch,
) -> None:
    """A partial marker-loss row must fail by contract before SQLite validates new CHECK DDL."""

    database_url = f"sqlite:///{tmp_path / 'evidence-command-partial-dirty.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _PRE_EVIDENCE_COMMAND_HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE ai_research_evidence_packages ADD COLUMN command_id "
                    "VARCHAR(36) CONSTRAINT fk_ai_research_evidence_package_command "
                    "REFERENCES ai_research_holdout_evaluation_commands(id) ON DELETE RESTRICT"
                )
            )
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.execute(
                text(
                    "INSERT INTO ai_research_evidence_packages "
                    "(id, user_id, run_id, candidate_id, command_id, "
                    "promotion_policy_version, gate_input_evidence_hash, manifest, "
                    "manifest_hash, approval_binding_hash, status, created_at) VALUES "
                    "(:id, :user_id, :run_id, :candidate_id, :command_id, "
                    "'promotion-v1', :gate_hash, :manifest, :manifest_hash, "
                    ":binding_hash, 'ACTIVE', :created_at)"
                ),
                {
                    "id": "d1111111-1111-1111-1111-111111111111",
                    "user_id": "d2222222-2222-2222-2222-222222222222",
                    "run_id": "d3333333-3333-3333-3333-333333333333",
                    "candidate_id": "d4444444-4444-4444-4444-444444444444",
                    "command_id": "d5555555-5555-5555-5555-555555555555",
                    "gate_hash": "1" * 64,
                    "manifest": json.dumps(
                        {"manifest_version": "ai_research_evidence_manifest/v1"}
                    ),
                    "manifest_hash": "2" * 64,
                    "binding_hash": "3" * 64,
                    "created_at": "2026-09-08 00:00:00",
                },
            )
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")

        with pytest.raises(RuntimeError, match="^EVIDENCE_COMMAND_GRAPH_PARTIAL_DATA$"):
            _upgrade(config, database_url, _HEAD)
    finally:
        engine.dispose()


def test_evidence_command_graph_upgrade_is_idempotent_when_revision_marker_is_lost(
    tmp_path,
    monkeypatch,
) -> None:
    """A fully applied schema must be accepted when MySQL-style revision state lags DDL."""

    database_url = f"sqlite:///{tmp_path / 'evidence-command-reentry.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": _PRE_EVIDENCE_COMMAND_HEAD},
            )
        _upgrade(config, database_url, _HEAD)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == _HEAD
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://fixture:fixture@127.0.0.1/fixture",
        "mysql+pymysql://fixture:fixture@127.0.0.1/fixture",
        "mariadb+pymysql://fixture:fixture@127.0.0.1/fixture",
    ],
)
def test_holdout_finalize_offline_upgrade_renders_manual_duplicate_precheck(
    database_url: str,
) -> None:
    """Offline DDL must be reviewable without pretending a SELECT was evaluated."""

    config, output = _offline_config(database_url)

    command.upgrade(
        config,
        f"{_PRE_HOLDOUT_FINALIZE_HEAD}:{_PRE_EVIDENCE_COMMAND_HEAD}",
        sql=True,
    )

    rendered = output.getvalue()
    assert "MANUAL PRECHECK: HOLDOUT_GATE_DECISION_DUPLICATES" in rendered
    assert "HAVING COUNT(*) > 1" in rendered
    assert _PRE_EVIDENCE_COMMAND_HEAD in rendered
    assert _GATE_UNIQUE_NAME in rendered


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://fixture:fixture@127.0.0.1/fixture",
        "mysql+pymysql://fixture:fixture@127.0.0.1/fixture",
        "mariadb+pymysql://fixture:fixture@127.0.0.1/fixture",
    ],
)
def test_holdout_finalize_offline_downgrade_renders_manual_nonempty_prechecks(
    database_url: str,
) -> None:
    """Offline downgrade must expose every destructive-decision query to operators."""

    config, output = _offline_config(database_url)

    command.downgrade(
        config,
        f"{_PRE_EVIDENCE_COMMAND_HEAD}:{_PRE_HOLDOUT_FINALIZE_HEAD}",
        sql=True,
    )

    rendered = output.getvalue()
    assert "MANUAL PRECHECK: HOLDOUT_FINALIZE_DOWNGRADE_BLOCKED" in rendered
    assert "FROM ai_research_holdout_artifact_bindings" in rendered
    assert "FROM ai_research_holdout_access_audits" in rendered
    assert "FROM ai_research_gate_decisions" in rendered


@pytest.mark.parametrize(
    "database_url",
    [
        "mysql+pymysql://fixture:fixture@127.0.0.1/fixture",
        "mariadb+pymysql://fixture:fixture@127.0.0.1/fixture",
    ],
)
def test_holdout_finalize_mysql_family_offline_ddl_keeps_guards_and_orders_gate_last(
    database_url: str,
) -> None:
    """Non-transactional DDL must not open an audit-mutation protection window."""

    config, output = _offline_config(database_url)

    command.upgrade(
        config,
        f"{_PRE_HOLDOUT_FINALIZE_HEAD}:{_PRE_EVIDENCE_COMMAND_HEAD}",
        sql=True,
    )

    rendered = output.getvalue()
    assert "DROP TRIGGER IF EXISTS trg_ai_research_holdout_access_audit" not in rendered
    access_constraint_position = rendered.index("ck_ai_research_holdout_access_audit_action")
    binding_position = rendered.index("CREATE TABLE ai_research_holdout_artifact_bindings")
    gate_unique_position = rendered.index(_GATE_UNIQUE_NAME)
    assert access_constraint_position < binding_position < gate_unique_position


@pytest.mark.parametrize("dialect_name", ["mysql", "mariadb"])
def test_holdout_finalize_mysql_retry_skips_an_existing_correct_gate_unique(
    monkeypatch,
    dialect_name: str,
) -> None:
    """A retry after auto-committed gate DDL must resume instead of wedging on its name."""

    script = ScriptDirectory.from_config(_config("sqlite://"))
    migration = script.get_revision(_PRE_EVIDENCE_COMMAND_HEAD).module

    class ExistingGateInspector:
        @staticmethod
        def get_unique_constraints(_table_name: str) -> list[dict[str, object]]:
            return [
                {
                    "name": _GATE_UNIQUE_NAME,
                    "column_names": [
                        "evaluation_id",
                        "policy_version",
                        "input_evidence_hash",
                        "gate_code",
                    ],
                }
            ]

    bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: ExistingGateInspector())

    def unexpected_batch(*_args, **_kwargs):
        raise AssertionError("existing gate uniqueness must be treated as completed DDL")

    monkeypatch.setattr(migration.op, "batch_alter_table", unexpected_batch)

    migration._create_gate_unique_constraint(bind)


def test_protocol_v2_migration_is_a_linear_expand_only_revision(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'trusted-research.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == [_INTEGRATED_HEAD]
    _upgrade(config, database_url, _PARENT)
    before = set(inspect(create_engine(database_url)).get_table_names())
    _upgrade(config, database_url, _LATEST_HEAD)
    after = set(inspect(create_engine(database_url)).get_table_names())

    assert _TABLES <= after
    assert _TABLES.isdisjoint(before)
    invocation_columns = {
        column["name"]: column
        for column in inspect(create_engine(database_url)).get_columns(
            "ai_research_model_invocations"
        )
    }
    assert invocation_columns["provider_reported_model"]["nullable"] is True
    reservation_columns = {
        column["name"]: column
        for column in inspect(create_engine(database_url)).get_columns(
            "ai_research_quota_reservations"
        )
    }
    assert reservation_columns["reservation_context"]["nullable"] is True
    assert {"ai_research_runs", "ai_research_tasks"} <= after
    run_columns = {
        column["name"]
        for column in inspect(create_engine(database_url)).get_columns("ai_research_runs")
    }
    assert {"data_precheck_id", "workflow_version"} <= run_columns
    assert "candidate_hash" in {
        column["name"]
        for column in inspect(create_engine(database_url)).get_columns(
            "ai_research_holdout_authorizations"
        )
    }
    holdout_uniques = {
        constraint["name"]
        for constraint in inspect(create_engine(database_url)).get_unique_constraints(
            "ai_research_holdout_authorizations"
        )
    }
    assert "uq_ai_research_holdout_authorization_epoch" in holdout_uniques
    assert "uq_ai_research_holdout_authorization_binding" not in holdout_uniques
    assert "storage_reference_hash" in {
        column["name"]
        for column in inspect(create_engine(database_url)).get_columns(
            "ai_research_dataset_snapshots"
        )
    }
    assert {
        "object_receipt_id",
        "object_logical_id",
        "object_version",
        "object_digest",
        "object_size_bytes",
        "integrity_status",
        "integrity_checked_at",
        "integrity_receipt_hash",
        "snapshot_identity_hash",
    } <= {
        column["name"]
        for column in inspect(create_engine(database_url)).get_columns(
            "ai_research_dataset_snapshots"
        )
    }
    assert "ck_ai_research_dataset_integrity_status" in {
        constraint["name"]
        for constraint in inspect(create_engine(database_url)).get_check_constraints(
            "ai_research_dataset_snapshots"
        )
    }
    assert {"artifact_id", "content", "created_at"} <= {
        column["name"]
        for column in inspect(create_engine(database_url)).get_columns(
            "ai_research_artifact_contents"
        )
    }
    assert {"user_id", "run_id", "task_id", "stage_attempt_id", "artifact_id"} <= {
        column["name"]
        for column in inspect(create_engine(database_url)).get_columns(
            "ai_research_stage_artifact_bindings"
        )
    }
    assert "uq_ai_research_task_idempotency" in {
        constraint["name"]
        for constraint in inspect(create_engine(database_url)).get_unique_constraints(
            "ai_research_tasks"
        )
    }
    assert "uq_ai_research_epoch_owner_family" in {
        constraint["name"]
        for constraint in inspect(create_engine(database_url)).get_unique_constraints(
            "ai_research_experiment_epochs"
        )
    }
    assert "uq_ai_research_stage_output_binding_attempt" in {
        constraint["name"]
        for constraint in inspect(create_engine(database_url)).get_unique_constraints(
            "ai_research_stage_artifact_bindings"
        )
    }
    assert {
        "uq_ai_research_generation_materialization_attempt",
        "uq_ai_research_generation_materialization_candidate",
        "uq_ai_research_generation_materialization_invocation",
        "uq_ai_research_generation_materialization_manifest",
    } <= {
        constraint["name"]
        for constraint in inspect(create_engine(database_url)).get_unique_constraints(
            "ai_research_generation_materializations"
        )
    }
    discovery_execution_columns = {
        column["name"]: column
        for column in inspect(create_engine(database_url)).get_columns(
            "ai_research_discovery_executions"
        )
    }
    assert {
        "id",
        "operation_id",
        "user_id",
        "run_id",
        "task_id",
        "stage_attempt_id",
        "candidate_id",
        "quota_reservation_id",
        "command_hash",
        "command_json",
        "search_epoch_id",
        "search_ordinal",
        "search_budget_hash",
        "trial_id",
        "result_json",
        "status",
        "error_code",
        "created_at",
        "updated_at",
    } <= set(discovery_execution_columns)
    assert all(
        discovery_execution_columns[name]["nullable"]
        for name in ("search_epoch_id", "search_ordinal", "search_budget_hash", "trial_id")
    )
    assert "ck_ai_research_discovery_execution_status" in {
        constraint["name"]
        for constraint in inspect(create_engine(database_url)).get_check_constraints(
            "ai_research_discovery_executions"
        )
    }
    assert {
        "uq_ai_research_discovery_execution_attempt",
        "uq_ai_research_discovery_execution_reservation",
    } <= {
        constraint["name"]
        for constraint in inspect(create_engine(database_url)).get_unique_constraints(
            "ai_research_discovery_executions"
        )
    }
    assert {"event_sequence"} <= {
        column["name"]
        for column in inspect(create_engine(database_url)).get_columns("ai_research_tasks")
    }
    assert {
        "id",
        "user_id",
        "task_id",
        "run_id",
        "sequence_no",
        "event_type",
        "stage",
        "status",
        "error_code",
        "stage_attempt_id",
        "trace_id",
        "created_at",
    } <= {
        column["name"]
        for column in inspect(create_engine(database_url)).get_columns("ai_research_task_events")
    }
    receipt_columns = {
        column["name"]: column
        for column in inspect(create_engine(database_url)).get_columns(
            "ai_research_candidate_freeze_receipts"
        )
    }
    assert set(receipt_columns) == {
        "id",
        "user_id",
        "run_id",
        "experiment_epoch_id",
        "candidate_id",
        "candidate_hash",
        "workflow_version",
        "generation_materialization_hash",
        "ledger_hash",
        "attempt_count_total",
        "market_trial_count",
        "search_budget_hash",
        "dataset_snapshot_hash",
        "dataset_snapshot_identity_hash",
        "code_hash",
        "dependency_hash",
        "hypothesis_hash",
        "environment_hash",
        "cost_model_hash",
        "checker_version",
        "frozen_by",
        "frozen_at",
    }
    assert all(not column["nullable"] for column in receipt_columns.values())
    assert {
        "ck_ai_research_candidate_freeze_receipt_workflow",
        "ck_ai_research_candidate_freeze_receipt_checker",
        "ck_ai_research_candidate_freeze_receipt_counts",
    } <= {
        constraint["name"]
        for constraint in inspect(create_engine(database_url)).get_check_constraints(
            "ai_research_candidate_freeze_receipts"
        )
    }
    assert "uq_ai_research_candidate_freeze_receipt_candidate" in {
        constraint["name"]
        for constraint in inspect(create_engine(database_url)).get_unique_constraints(
            "ai_research_candidate_freeze_receipts"
        )
    }
    assert {
        "ix_ai_research_candidate_freeze_receipt_owner_run",
        "ix_ai_research_candidate_freeze_receipt_epoch",
    } <= {
        index["name"]
        for index in inspect(create_engine(database_url)).get_indexes(
            "ai_research_candidate_freeze_receipts"
        )
    }
    forward_epoch_columns = {
        column["name"]
        for column in inspect(create_engine(database_url)).get_columns(
            "ai_research_forward_observation_epochs"
        )
    }
    assert {"freeze_receipt_id", "freeze_receipt_fingerprint"} <= forward_epoch_columns
    assert "ck_ai_research_forward_epoch_freeze_receipt_pair" in {
        constraint["name"]
        for constraint in inspect(create_engine(database_url)).get_check_constraints(
            "ai_research_forward_observation_epochs"
        )
    }
    assert any(
        foreign_key["referred_table"] == "ai_research_candidate_freeze_receipts"
        and foreign_key["constrained_columns"] == ["freeze_receipt_id"]
        for foreign_key in inspect(create_engine(database_url)).get_foreign_keys(
            "ai_research_forward_observation_epochs"
        )
    )
    command_inspector = inspect(create_engine(database_url))
    command_columns = {
        column["name"]: column
        for column in command_inspector.get_columns("ai_research_holdout_evaluation_commands")
    }
    assert set(command_columns) == {
        "id",
        "user_id",
        "run_id",
        "workspace_id",
        "experiment_epoch_id",
        "candidate_id",
        "candidate_hash",
        "expected_candidate_state",
        "freeze_receipt_id",
        "freeze_receipt_fingerprint",
        "dataset_snapshot_id",
        "dataset_policy_version",
        "sealed_dataset_hash",
        "sealed_dataset_identity_hash",
        "policy_version",
        "evaluator_identity",
        "evaluator_version",
        "capability_profile_id",
        "capability_profile_version",
        "capability_evidence_hash",
        "authorization_id",
        "evaluation_id",
        "request_hash",
        "idempotency_key",
        "trace_id",
        "status",
        "stage",
        "error_code",
        "lease_owner",
        "lease_token_hash",
        "lease_generation",
        "lease_expires_at",
        "lease_heartbeat_at",
        "attempt_count",
        "started_at",
        "created_at",
        "updated_at",
    }
    assert "lease_token" not in command_columns
    assert command_columns["authorization_id"]["nullable"] is True
    assert command_columns["evaluation_id"]["nullable"] is True
    assert {
        "ck_ai_research_holdout_command_status",
        "ck_ai_research_holdout_command_stage",
        "ck_ai_research_holdout_command_candidate_state",
        "ck_ai_research_holdout_command_binding_pair",
        "ck_ai_research_holdout_command_lease_group",
        "ck_ai_research_holdout_command_state_bindings",
        "ck_ai_research_holdout_command_attempt_count",
        "ck_ai_research_holdout_command_lease_generation",
    } <= {
        constraint["name"]
        for constraint in command_inspector.get_check_constraints(
            "ai_research_holdout_evaluation_commands"
        )
    }
    stage_constraint = next(
        constraint["sqltext"]
        for constraint in command_inspector.get_check_constraints(
            "ai_research_holdout_evaluation_commands"
        )
        if constraint["name"] == "ck_ai_research_holdout_command_stage"
    )
    assert "REQUEST_HOLDOUT" in stage_constraint
    assert "HOLDOUT_PENDING" in stage_constraint
    assert "ix_ai_research_holdout_command_claim" in {
        index["name"]
        for index in command_inspector.get_indexes("ai_research_holdout_evaluation_commands")
    }
    assert {
        "uq_ai_research_holdout_command_idempotency",
        "uq_ai_research_holdout_command_epoch",
        "uq_ai_research_holdout_command_freeze_receipt",
        "uq_ai_research_holdout_command_authorization",
        "uq_ai_research_holdout_command_evaluation",
    } <= {
        constraint["name"]
        for constraint in command_inspector.get_unique_constraints(
            "ai_research_holdout_evaluation_commands"
        )
    }
    command_foreign_tables = {
        foreign_key["referred_table"]
        for foreign_key in command_inspector.get_foreign_keys(
            "ai_research_holdout_evaluation_commands"
        )
    }
    assert {
        "users",
        "ai_research_runs",
        "ai_research_experiment_epochs",
        "ai_research_candidates",
        "ai_research_candidate_freeze_receipts",
        "ai_research_dataset_snapshots",
        "ai_research_holdout_authorizations",
        "ai_research_evaluations",
    } <= command_foreign_tables
    audit_columns = {
        column["name"]: column
        for column in command_inspector.get_columns("ai_research_holdout_request_audits")
    }
    assert set(audit_columns) == {
        "id",
        "actor_user_id",
        "candidate_id",
        "expected_candidate_hash",
        "resolved_snapshot_id",
        "purpose",
        "result",
        "reason_code",
        "command_id",
        "request_hash",
        "trace_id",
        "created_at",
    }
    assert not any(
        forbidden in column_name
        for column_name in audit_columns
        for forbidden in ("token", "uri", "metric")
    )
    assert {
        "ck_ai_research_holdout_request_audit_purpose",
        "ck_ai_research_holdout_request_audit_result",
        "ck_ai_research_holdout_request_audit_authority",
    } <= {
        constraint["name"]
        for constraint in command_inspector.get_check_constraints(
            "ai_research_holdout_request_audits"
        )
    }
    audit_checks = {
        constraint["name"]: constraint["sqltext"]
        for constraint in command_inspector.get_check_constraints(
            "ai_research_holdout_request_audits"
        )
    }
    assert "UNKNOWN" in audit_checks["ck_ai_research_holdout_request_audit_result"]
    authority_check = audit_checks["ck_ai_research_holdout_request_audit_authority"]
    assert "ACCEPTED" in authority_check
    assert "REJECTED" in authority_check
    assert "UNKNOWN" in authority_check
    assert "command_id IS NOT NULL" in authority_check
    assert "resolved_snapshot_id IS NOT NULL" in authority_check
    assert "command_id IS NULL" in authority_check
    assert "resolved_snapshot_id IS NULL" in authority_check
    assert "uq_ai_research_holdout_request_audit_command" in {
        constraint["name"]
        for constraint in command_inspector.get_unique_constraints(
            "ai_research_holdout_request_audits"
        )
    }
    assert {
        foreign_key["referred_table"]
        for foreign_key in command_inspector.get_foreign_keys("ai_research_holdout_request_audits")
    } == {"users", "ai_research_holdout_evaluation_commands"}
    with create_engine(database_url).connect() as connection:
        audit_triggers = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'trigger' AND tbl_name = 'ai_research_holdout_request_audits'"
                )
            )
        }
    assert audit_triggers == {
        "trg_ai_research_holdout_request_audit_no_update",
        "trg_ai_research_holdout_request_audit_no_delete",
    }
    access_audit_columns = {
        column["name"]
        for column in command_inspector.get_columns("ai_research_holdout_access_audits")
    }
    assert access_audit_columns == {
        "id",
        "actor_identity",
        "evaluator_version",
        "requested_command_id",
        "action",
        "result",
        "reason_code",
        "command_id",
        "authorization_id",
        "evaluation_id",
        "experiment_epoch_id",
        "candidate_id",
        "dataset_snapshot_id",
        "lease_generation",
        "trace_id",
        "created_at",
    }
    assert not any(
        forbidden in column_name
        for column_name in access_audit_columns
        for forbidden in ("token", "hash", "uri", "metric", "evidence")
    )
    assert {
        "ck_ai_research_holdout_access_audit_action",
        "ck_ai_research_holdout_access_audit_result",
        "ck_ai_research_holdout_access_audit_outcome",
        "ck_ai_research_holdout_access_audit_authority",
    } <= {
        constraint["name"]
        for constraint in command_inspector.get_check_constraints(
            "ai_research_holdout_access_audits"
        )
    }
    assert "uq_ai_research_holdout_access_audit_event" in {
        constraint["name"]
        for constraint in command_inspector.get_unique_constraints(
            "ai_research_holdout_access_audits"
        )
    }
    assert "uq_ai_research_evaluation_authorization" in {
        constraint["name"]
        for constraint in command_inspector.get_unique_constraints("ai_research_evaluations")
    }
    with create_engine(database_url).connect() as connection:
        access_audit_triggers = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                    "AND tbl_name = 'ai_research_holdout_access_audits'"
                )
            )
        }
    assert access_audit_triggers == {
        "trg_ai_research_holdout_access_audit_no_update",
        "trg_ai_research_holdout_access_audit_no_delete",
    }
    access_audit_checks = {
        constraint["name"]: constraint["sqltext"]
        for constraint in command_inspector.get_check_constraints(
            "ai_research_holdout_access_audits"
        )
    }
    access_action_check = access_audit_checks["ck_ai_research_holdout_access_audit_action"]
    access_outcome_check = access_audit_checks["ck_ai_research_holdout_access_audit_outcome"]
    for action in (
        "CHECKPOINT_RECORDED",
        "CHECKPOINT_REJECTED",
        "CHECKPOINT_UNKNOWN",
        "FINALIZE_COMPLETED",
        "FINALIZE_REJECTED",
        "FINALIZE_UNKNOWN",
        "RECONCILE_COMPLETED",
        "RECONCILE_REJECTED",
    ):
        assert action in access_action_check
        assert action in access_outcome_check

    binding_columns = {
        column["name"]: column
        for column in command_inspector.get_columns("ai_research_holdout_artifact_bindings")
    }
    assert set(binding_columns) == {
        "id",
        "user_id",
        "run_id",
        "command_id",
        "authorization_id",
        "evaluation_id",
        "experiment_epoch_id",
        "candidate_id",
        "dataset_snapshot_id",
        "artifact_id",
        "claim_access_audit_id",
        "request_hash",
        "lease_owner",
        "lease_generation",
        "lease_expires_at",
        "binding_schema_version",
        "authority_binding_hash",
        "created_at",
    }
    assert all(not column["nullable"] for column in binding_columns.values())
    binding_checks = {
        constraint["name"]: constraint["sqltext"]
        for constraint in command_inspector.get_check_constraints(
            "ai_research_holdout_artifact_bindings"
        )
    }
    assert {
        "ck_ai_research_holdout_artifact_binding_generation",
        "ck_ai_research_holdout_artifact_binding_schema",
    } <= set(binding_checks)
    assert (
        "lease_generation > 0"
        in binding_checks["ck_ai_research_holdout_artifact_binding_generation"]
    )
    assert (
        "holdout-artifact-binding-v1"
        in binding_checks["ck_ai_research_holdout_artifact_binding_schema"]
    )
    assert {
        "uq_ai_research_holdout_artifact_binding_command",
        "uq_ai_research_holdout_artifact_binding_authorization",
        "uq_ai_research_holdout_artifact_binding_evaluation",
        "uq_ai_research_holdout_artifact_binding_artifact",
        "uq_ai_research_holdout_artifact_binding_claim_audit",
        "uq_ai_research_holdout_artifact_binding_authority_hash",
    } <= {
        constraint["name"]
        for constraint in command_inspector.get_unique_constraints(
            "ai_research_holdout_artifact_bindings"
        )
    }
    assert {
        "users",
        "ai_research_runs",
        "ai_research_holdout_evaluation_commands",
        "ai_research_holdout_authorizations",
        "ai_research_evaluations",
        "ai_research_experiment_epochs",
        "ai_research_candidates",
        "ai_research_dataset_snapshots",
        "ai_research_artifacts",
        "ai_research_holdout_access_audits",
    } == {
        foreign_key["referred_table"]
        for foreign_key in command_inspector.get_foreign_keys(
            "ai_research_holdout_artifact_bindings"
        )
    }
    assert {
        "ix_ai_research_holdout_artifact_binding_owner_run",
        "ix_ai_research_holdout_artifact_binding_epoch_candidate",
    } <= {
        index["name"]
        for index in command_inspector.get_indexes("ai_research_holdout_artifact_bindings")
    }
    with create_engine(database_url).connect() as connection:
        binding_triggers = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                    "AND tbl_name = 'ai_research_holdout_artifact_bindings'"
                )
            )
        }
    assert binding_triggers == {
        "trg_ai_research_holdout_artifact_binding_no_update",
        "trg_ai_research_holdout_artifact_binding_no_delete",
    }
    evidence_columns = {
        column["name"]: column
        for column in command_inspector.get_columns("ai_research_evidence_packages")
    }
    assert _EVIDENCE_COMMAND_COLUMNS.keys() <= evidence_columns.keys()
    assert all(evidence_columns[name]["nullable"] for name in _EVIDENCE_COMMAND_COLUMNS)
    evidence_foreign_keys = {
        foreign_key["constrained_columns"][0]: foreign_key["referred_table"]
        for foreign_key in command_inspector.get_foreign_keys("ai_research_evidence_packages")
        if len(foreign_key["constrained_columns"]) == 1
        and foreign_key["constrained_columns"][0] in _EVIDENCE_COMMAND_COLUMNS
    }
    assert evidence_foreign_keys == _EVIDENCE_COMMAND_COLUMNS
    evidence_checks = {
        constraint["name"]: constraint["sqltext"]
        for constraint in command_inspector.get_check_constraints("ai_research_evidence_packages")
    }
    graph_check = evidence_checks["ck_ai_research_evidence_package_command_graph"]
    for column_name in _EVIDENCE_COMMAND_COLUMNS:
        assert f"{column_name} IS NULL" in graph_check
        assert f"{column_name} IS NOT NULL" in graph_check
    evidence_indexes = {
        index["name"]: index
        for index in command_inspector.get_indexes("ai_research_evidence_packages")
    }
    assert _EVIDENCE_COMMAND_INDEXES <= evidence_indexes.keys()
    assert evidence_indexes["uq_ai_research_evidence_package_command"]["column_names"] == [
        "command_id"
    ]
    assert evidence_indexes["uq_ai_research_evidence_package_command"]["unique"]
    gate_unique = next(
        constraint
        for constraint in command_inspector.get_unique_constraints("ai_research_gate_decisions")
        if constraint["name"] == "uq_ai_research_gate_decision_evaluation_input_gate"
    )
    assert gate_unique["column_names"] == [
        "evaluation_id",
        "policy_version",
        "input_evidence_hash",
        "gate_code",
    ]
    with create_engine(database_url).connect() as connection:
        gate_triggers = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                    "AND tbl_name = 'ai_research_gate_decisions'"
                )
            )
        }
    assert gate_triggers == {
        "trg_ai_research_gate_decision_no_update",
        "trg_ai_research_gate_decision_no_delete",
    }

    _downgrade(config, database_url, _PARENT)
    assert _TABLES.isdisjoint(set(inspect(create_engine(database_url)).get_table_names()))


def test_holdout_request_downgrade_refuses_to_discard_queued_work(
    tmp_path,
    monkeypatch,
) -> None:
    """A rollback cannot silently delete an accepted holdout command."""

    database_url = f"sqlite:///{tmp_path / 'trusted-research-holdout-request.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)
    engine = create_engine(database_url)
    command_id = "b1111111-1111-1111-1111-111111111111"
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ai_research_holdout_evaluation_commands "
                    "(id, user_id, run_id, workspace_id, experiment_epoch_id, candidate_id, "
                    "candidate_hash, expected_candidate_state, freeze_receipt_id, "
                    "freeze_receipt_fingerprint, dataset_snapshot_id, dataset_policy_version, "
                    "sealed_dataset_hash, sealed_dataset_identity_hash, policy_version, "
                    "evaluator_identity, evaluator_version, capability_profile_id, "
                    "capability_profile_version, capability_evidence_hash, authorization_id, "
                    "evaluation_id, request_hash, idempotency_key, trace_id, status, stage, "
                    "error_code, created_at, updated_at) VALUES "
                    "(:id, :user_id, :run_id, NULL, :epoch_id, :candidate_id, :candidate_hash, "
                    "'FROZEN', :receipt_id, :receipt_hash, :dataset_id, 'policy-v1', "
                    ":dataset_hash, :dataset_identity_hash, 'promotion-v1', "
                    "'migration-evaluator', 'migration-evaluator-image', 'migration-profile', "
                    "'v1', :evidence_hash, NULL, NULL, :request_hash, 'migration-request', "
                    "'migration-trace', 'QUEUED', 'REQUEST_HOLDOUT', NULL, :created_at, "
                    ":created_at)"
                ),
                {
                    "id": command_id,
                    "user_id": "b2222222-2222-2222-2222-222222222222",
                    "run_id": "b3333333-3333-3333-3333-333333333333",
                    "epoch_id": "b4444444-4444-4444-4444-444444444444",
                    "candidate_id": "b5555555-5555-5555-5555-555555555555",
                    "candidate_hash": "1" * 64,
                    "receipt_id": "b6666666-6666-6666-6666-666666666666",
                    "receipt_hash": "2" * 64,
                    "dataset_id": "b7777777-7777-7777-7777-777777777777",
                    "dataset_hash": "3" * 64,
                    "dataset_identity_hash": "4" * 64,
                    "evidence_hash": "5" * 64,
                    "request_hash": "6" * 64,
                    "created_at": "2026-09-07 00:00:00",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO ai_research_holdout_request_audits "
                    "(id, actor_user_id, candidate_id, expected_candidate_hash, "
                    "resolved_snapshot_id, purpose, result, reason_code, command_id, "
                    "request_hash, trace_id, created_at) VALUES "
                    "(:id, :actor_user_id, :candidate_id, :candidate_hash, :snapshot_id, "
                    "'HOLDOUT_EVALUATION_REQUEST', 'ACCEPTED', 'HOLDOUT_REQUEST_QUEUED', "
                    ":command_id, :request_hash, 'migration-trace', :created_at)"
                ),
                {
                    "id": "b8888888-8888-8888-8888-888888888888",
                    "actor_user_id": "b2222222-2222-2222-2222-222222222222",
                    "candidate_id": "b5555555-5555-5555-5555-555555555555",
                    "candidate_hash": "1" * 64,
                    "snapshot_id": "b7777777-7777-7777-7777-777777777777",
                    "command_id": command_id,
                    "request_hash": "6" * 64,
                    "created_at": "2026-09-07 00:00:00",
                },
            )

        for mutation in (
            "UPDATE ai_research_holdout_request_audits SET reason_code = 'changed'",
            "DELETE FROM ai_research_holdout_request_audits",
        ):
            with engine.begin() as connection:
                with pytest.raises(DatabaseError, match="HOLDOUT_REQUEST_AUDIT_IMMUTABLE"):
                    connection.execute(text(mutation))

        with pytest.raises(RuntimeError, match="HOLDOUT_REQUEST_DOWNGRADE_BLOCKED"):
            _downgrade(config, database_url, _PRE_HOLDOUT_REQUEST_HEAD)

        assert "ai_research_holdout_evaluation_commands" in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT status FROM ai_research_holdout_evaluation_commands WHERE id = :id"
                    ),
                    {"id": command_id},
                ).scalar_one()
                == "QUEUED"
            )
    finally:
        engine.dispose()


def test_holdout_access_audit_is_immutable_and_blocks_lossy_downgrade(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'trusted-research-holdout-claim.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            with pytest.raises(DatabaseError):
                connection.execute(
                    text(
                        "INSERT INTO ai_research_holdout_access_audits "
                        "(id, actor_identity, evaluator_version, requested_command_id, action, "
                        "result, reason_code, created_at) VALUES "
                        "('c0000000-0000-0000-0000-000000000000', 'worker', 'image', "
                        "'c1111111-1111-1111-1111-111111111111', 'CLAIM_STARTED', "
                        "'ACCEPTED', 'HOLDOUT_CLAIM_STARTED', '2026-09-07 00:00:00')"
                    )
                )
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ai_research_holdout_access_audits "
                    "(id, actor_identity, evaluator_version, requested_command_id, action, "
                    "result, reason_code, created_at) VALUES "
                    "('c2222222-2222-2222-2222-222222222222', 'worker', 'image', "
                    "'c1111111-1111-1111-1111-111111111111', 'CLAIM_REJECTED', "
                    "'REJECTED', 'HOLDOUT_CLAIM_COMMAND_NOT_FOUND', "
                    "'2026-09-07 00:00:00')"
                )
            )
        for mutation in (
            "UPDATE ai_research_holdout_access_audits SET reason_code = 'changed'",
            "DELETE FROM ai_research_holdout_access_audits",
        ):
            with engine.begin() as connection:
                with pytest.raises(DatabaseError, match="HOLDOUT_ACCESS_AUDIT_IMMUTABLE"):
                    connection.execute(text(mutation))
        with pytest.raises(RuntimeError, match="HOLDOUT_CLAIM_DOWNGRADE_BLOCKED"):
            _downgrade(config, database_url, _PRE_HOLDOUT_CLAIM_HEAD)
    finally:
        engine.dispose()


def test_holdout_artifact_binding_is_immutable_and_blocks_lossy_downgrade(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'trusted-research-holdout-finalize.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)
    engine = create_engine(database_url)
    binding_id = "e1111111-1111-1111-1111-111111111111"
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.execute(
                text(
                    "INSERT INTO ai_research_holdout_artifact_bindings "
                    "(id, user_id, run_id, command_id, authorization_id, evaluation_id, "
                    "experiment_epoch_id, candidate_id, dataset_snapshot_id, artifact_id, "
                    "claim_access_audit_id, request_hash, lease_owner, lease_generation, "
                    "lease_expires_at, binding_schema_version, authority_binding_hash, "
                    "created_at) VALUES "
                    "(:id, :user_id, :run_id, :command_id, :authorization_id, :evaluation_id, "
                    ":epoch_id, :candidate_id, :snapshot_id, :artifact_id, :claim_audit_id, "
                    ":request_hash, 'migration-evaluator', 1, :lease_expires_at, "
                    "'holdout-artifact-binding-v1', :binding_hash, :created_at)"
                ),
                {
                    "id": binding_id,
                    "user_id": "e2222222-2222-2222-2222-222222222222",
                    "run_id": "e3333333-3333-3333-3333-333333333333",
                    "command_id": "e4444444-4444-4444-4444-444444444444",
                    "authorization_id": "e5555555-5555-5555-5555-555555555555",
                    "evaluation_id": "e6666666-6666-6666-6666-666666666666",
                    "epoch_id": "e7777777-7777-7777-7777-777777777777",
                    "candidate_id": "e8888888-8888-8888-8888-888888888888",
                    "snapshot_id": "e9999999-9999-9999-9999-999999999999",
                    "artifact_id": "eaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "claim_audit_id": "ebbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                    "request_hash": "1" * 64,
                    "binding_hash": "2" * 64,
                    "lease_expires_at": "2026-09-07 00:05:00",
                    "created_at": "2026-09-07 00:00:00",
                },
            )
            connection.commit()

        for mutation in (
            "UPDATE ai_research_holdout_artifact_bindings SET lease_owner = 'changed'",
            "DELETE FROM ai_research_holdout_artifact_bindings",
        ):
            with engine.begin() as connection:
                with pytest.raises(DatabaseError, match="HOLDOUT_ARTIFACT_BINDING_IMMUTABLE"):
                    connection.execute(text(mutation))

        with pytest.raises(RuntimeError, match="HOLDOUT_FINALIZE_DOWNGRADE_BLOCKED"):
            _downgrade(config, database_url, _PRE_HOLDOUT_FINALIZE_HEAD)

        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT authority_binding_hash "
                        "FROM ai_research_holdout_artifact_bindings WHERE id = :id"
                    ),
                    {"id": binding_id},
                ).scalar_one()
                == "2" * 64
            )
    finally:
        engine.dispose()


def test_holdout_finalize_access_audit_outcomes_are_enforced_and_retained(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'trusted-research-finalize-audit.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ai_research_holdout_access_audits "
                    "(id, actor_identity, evaluator_version, requested_command_id, action, "
                    "result, reason_code, created_at) VALUES "
                    "('f1111111-1111-1111-1111-111111111111', 'worker', 'image', "
                    "'f2222222-2222-2222-2222-222222222222', 'CHECKPOINT_REJECTED', "
                    "'REJECTED', 'HOLDOUT_CHECKPOINT_STALE_LEASE', "
                    "'2026-09-07 00:00:00')"
                )
            )
            with pytest.raises(DatabaseError):
                connection.execute(
                    text(
                        "INSERT INTO ai_research_holdout_access_audits "
                        "(id, actor_identity, evaluator_version, requested_command_id, action, "
                        "result, reason_code, created_at) VALUES "
                        "('f3333333-3333-3333-3333-333333333333', 'worker', 'image', "
                        "'f4444444-4444-4444-4444-444444444444', 'FINALIZE_COMPLETED', "
                        "'REJECTED', 'INVALID_OUTCOME', '2026-09-07 00:00:00')"
                    )
                )

        with pytest.raises(RuntimeError, match="HOLDOUT_FINALIZE_DOWNGRADE_BLOCKED"):
            _downgrade(config, database_url, _PRE_HOLDOUT_FINALIZE_HEAD)

        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT action FROM ai_research_holdout_access_audits "
                        "WHERE id = 'f1111111-1111-1111-1111-111111111111'"
                    )
                ).scalar_one()
                == "CHECKPOINT_REJECTED"
            )
    finally:
        engine.dispose()


def test_holdout_gate_decisions_are_immutable_and_block_lossy_downgrade(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'trusted-research-finalize-gates.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)
    engine = create_engine(database_url)
    gate_id = "f5555555-5555-5555-5555-555555555555"
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ai_research_gate_decisions "
                    "(id, candidate_id, evaluation_id, gate_code, policy_version, "
                    "input_evidence_hash, status, reason, executor_version, evaluated_at) "
                    "VALUES (:id, :candidate_id, NULL, 'ROBUSTNESS', 'promotion-v1', "
                    ":evidence_hash, 'PASS', 'fixture', 'gate-engine-v1', :evaluated_at)"
                ),
                {
                    "id": gate_id,
                    "candidate_id": "f6666666-6666-6666-6666-666666666666",
                    "evidence_hash": "3" * 64,
                    "evaluated_at": "2026-09-07 00:00:00",
                },
            )

        for mutation in (
            "UPDATE ai_research_gate_decisions SET status = 'FAIL' WHERE id = :id",
            "DELETE FROM ai_research_gate_decisions WHERE id = :id",
        ):
            with engine.begin() as connection:
                with pytest.raises(DatabaseError, match="HOLDOUT_GATE_DECISION_IMMUTABLE"):
                    connection.execute(text(mutation), {"id": gate_id})

        with pytest.raises(RuntimeError, match="HOLDOUT_FINALIZE_DOWNGRADE_BLOCKED"):
            _downgrade(config, database_url, _PRE_HOLDOUT_FINALIZE_HEAD)

        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT status FROM ai_research_gate_decisions WHERE id = :id"),
                    {"id": gate_id},
                ).scalar_one()
                == "PASS"
            )
    finally:
        engine.dispose()


def test_holdout_finalize_upgrade_fails_closed_on_duplicate_gate_decisions(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'duplicate-holdout-gates.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _PRE_HOLDOUT_FINALIZE_HEAD)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            for ordinal in (1, 2):
                connection.execute(
                    text(
                        "INSERT INTO ai_research_gate_decisions "
                        "(id, candidate_id, evaluation_id, gate_code, policy_version, "
                        "input_evidence_hash, status, reason, executor_version, evaluated_at) "
                        "VALUES (:id, :candidate_id, :evaluation_id, 'ROBUSTNESS', "
                        "'promotion-v1', :evidence_hash, 'PASS', 'legacy duplicate', "
                        "'gate-engine-v1', :evaluated_at)"
                    ),
                    {
                        "id": f"f7{ordinal}11111-1111-1111-1111-111111111111",
                        "candidate_id": "f8888888-8888-8888-8888-888888888888",
                        "evaluation_id": "f9999999-9999-9999-9999-999999999999",
                        "evidence_hash": "4" * 64,
                        "evaluated_at": "2026-09-07 00:00:00",
                    },
                )
            connection.commit()

        with pytest.raises(RuntimeError, match="HOLDOUT_GATE_DECISION_DUPLICATES"):
            _upgrade(config, database_url, _HEAD)

        current_inspector = inspect(engine)
        assert "ai_research_holdout_artifact_bindings" not in current_inspector.get_table_names()
        assert "uq_ai_research_gate_decision_evaluation_input_gate" not in {
            constraint["name"]
            for constraint in current_inspector.get_unique_constraints("ai_research_gate_decisions")
        }
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM ai_research_gate_decisions "
                        "WHERE evaluation_id = 'f9999999-9999-9999-9999-999999999999'"
                    )
                ).scalar_one()
                == 2
            )
    finally:
        engine.dispose()


def test_candidate_freeze_receipt_downgrade_refuses_to_discard_strict_identity(
    tmp_path,
    monkeypatch,
) -> None:
    """A strict freeze identity must survive an attempted lossy downgrade."""

    database_url = f"sqlite:///{tmp_path / 'trusted-research-freeze-receipt.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)
    engine = create_engine(database_url)
    receipt_id = "a1111111-1111-1111-1111-111111111111"
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ai_research_candidate_freeze_receipts "
                    "(id, user_id, run_id, experiment_epoch_id, candidate_id, candidate_hash, "
                    "workflow_version, generation_materialization_hash, ledger_hash, "
                    "attempt_count_total, market_trial_count, search_budget_hash, "
                    "dataset_snapshot_hash, dataset_snapshot_identity_hash, code_hash, "
                    "dependency_hash, hypothesis_hash, "
                    "environment_hash, cost_model_hash, checker_version, frozen_by, frozen_at) "
                    "VALUES (:id, :user_id, :run_id, :epoch_id, :candidate_id, :candidate_hash, "
                    "'discovery-v1', :materialization_hash, :ledger_hash, 3, 2, :budget_hash, "
                    ":dataset_hash, :dataset_identity_hash, :code_hash, :dependency_hash, "
                    ":hypothesis_hash, "
                    ":environment_hash, :cost_hash, 'candidate-freeze-v1', :frozen_by, :frozen_at)"
                ),
                {
                    "id": receipt_id,
                    "user_id": "a2222222-2222-2222-2222-222222222222",
                    "run_id": "a3333333-3333-3333-3333-333333333333",
                    "epoch_id": "a4444444-4444-4444-4444-444444444444",
                    "candidate_id": "a5555555-5555-5555-5555-555555555555",
                    "candidate_hash": "1" * 64,
                    "materialization_hash": "2" * 64,
                    "ledger_hash": "3" * 64,
                    "budget_hash": "4" * 64,
                    "dataset_hash": "5" * 64,
                    "dataset_identity_hash": "b" * 64,
                    "code_hash": "6" * 64,
                    "dependency_hash": "7" * 64,
                    "hypothesis_hash": "8" * 64,
                    "environment_hash": "9" * 64,
                    "cost_hash": "a" * 64,
                    "frozen_by": "strict-freeze-test",
                    "frozen_at": "2026-09-07 00:00:00",
                },
            )

        for statement in (
            "UPDATE ai_research_candidate_freeze_receipts SET ledger_hash = '0' WHERE id = :id",
            "DELETE FROM ai_research_candidate_freeze_receipts WHERE id = :id",
        ):
            with pytest.raises(DatabaseError, match="CANDIDATE_FREEZE_RECEIPT_IMMUTABLE"):
                with engine.begin() as connection:
                    connection.execute(text(statement), {"id": receipt_id})

        with pytest.raises(RuntimeError, match="CANDIDATE_FREEZE_RECEIPT_DOWNGRADE_BLOCKED"):
            _downgrade(config, database_url, _PRE_FREEZE_RECEIPT_HEAD)

        assert "ai_research_candidate_freeze_receipts" in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT candidate_hash FROM ai_research_candidate_freeze_receipts "
                        "WHERE id = :id"
                    ),
                    {"id": receipt_id},
                ).scalar_one()
                == "1" * 64
            )
    finally:
        engine.dispose()


def test_candidate_freeze_receipt_upgrade_fails_closed_on_duplicate_epoch_tokens(
    tmp_path,
    monkeypatch,
) -> None:
    """Legacy bindings must be reconciled before epoch-wide uniqueness is installed."""

    database_url = f"sqlite:///{tmp_path / 'duplicate-holdout-epochs.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _PRE_FREEZE_RECEIPT_HEAD)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            for ordinal in (1, 2):
                connection.execute(
                    text(
                        "INSERT INTO ai_research_holdout_authorizations "
                        "(id, experiment_epoch_id, candidate_id, candidate_hash, "
                        "dataset_snapshot_id, policy_version, token_hash, status, "
                        "evaluator_identity, capability_profile_id, "
                        "capability_profile_version, capability_evidence_hash, issued_by, "
                        "issued_at, consumed_at, expires_at) "
                        "VALUES (:id, :epoch_id, :candidate_id, :candidate_hash, "
                        ":dataset_id, :policy_version, :token_hash, 'ISSUED', "
                        "'migration-evaluator', 'migration-profile', 'v1', :evidence_hash, "
                        "'migration-test', :issued_at, NULL, NULL)"
                    ),
                    {
                        "id": f"d{ordinal}111111-1111-1111-1111-111111111111",
                        "epoch_id": "d3111111-1111-1111-1111-111111111111",
                        "candidate_id": f"d4{ordinal}11111-1111-1111-1111-111111111111",
                        "candidate_hash": str(ordinal) * 64,
                        "dataset_id": f"d5{ordinal}11111-1111-1111-1111-111111111111",
                        "policy_version": f"legacy-policy-{ordinal}",
                        "token_hash": str(ordinal + 2) * 64,
                        "evidence_hash": "f" * 64,
                        "issued_at": "2026-09-07 00:00:00",
                    },
                )

        with pytest.raises(RuntimeError, match="HOLDOUT_AUTHORIZATION_EPOCH_DUPLICATES"):
            _upgrade(config, database_url, _HEAD)

        assert "ai_research_candidate_freeze_receipts" not in inspect(engine).get_table_names()
        holdout_uniques = {
            constraint["name"]
            for constraint in inspect(engine).get_unique_constraints(
                "ai_research_holdout_authorizations"
            )
        }
        assert "uq_ai_research_holdout_authorization_binding" in holdout_uniques
        assert "uq_ai_research_holdout_authorization_epoch" not in holdout_uniques
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM ai_research_holdout_authorizations "
                        "WHERE experiment_epoch_id = :epoch_id"
                    ),
                    {"epoch_id": "d3111111-1111-1111-1111-111111111111"},
                ).scalar_one()
                == 2
            )
    finally:
        engine.dispose()


def test_workflow_version_migration_defaults_legacy_runs_without_rewriting_them(
    tmp_path, monkeypatch
) -> None:
    """Upgrade/downgrade retains the historical run and makes its graph explicit."""

    database_url = f"sqlite:///{tmp_path / 'trusted-research-workflow-version.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _PRE_WORKFLOW_VERSION_HEAD)
    engine = create_engine(database_url)
    user_id = "81111111-1111-1111-1111-111111111111"
    hypothesis_id = "82222222-2222-2222-2222-222222222222"
    run_id = "83333333-3333-3333-3333-333333333333"
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, username, email, hashed_password, is_active, created_at, updated_at) "
                    "VALUES (:id, :username, :email, :hashed_password, :is_active, "
                    ":created_at, :updated_at)"
                ),
                {
                    "id": user_id,
                    "username": "workflow-version-migration",
                    "email": "workflow-version-migration@example.test",
                    "hashed_password": "fixture",
                    "is_active": True,
                    "created_at": "2026-09-06 00:00:00",
                    "updated_at": "2026-09-06 00:00:00",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO ai_research_hypothesis_versions "
                    "(id, user_id, hypothesis_id, version_no, status, canonical_payload, "
                    "content_hash, created_at) VALUES "
                    "(:id, :user_id, :hypothesis_id, 1, 'CONFIRMED', :payload, "
                    ":content_hash, :created_at)"
                ),
                {
                    "id": hypothesis_id,
                    "user_id": user_id,
                    "hypothesis_id": "84444444-4444-4444-4444-444444444444",
                    "payload": json.dumps({"research_question": "fixture"}),
                    "content_hash": "a" * 64,
                    "created_at": "2026-09-06 00:00:00",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO ai_research_runs "
                    "(id, user_id, hypothesis_version_id, protocol_version, status, stage_cursor, "
                    "promotion_policy_version, request_hash, capability_profile_id, "
                    "capability_profile_version, capability_evidence_hash, trace_id, created_at) "
                    "VALUES (:id, :user_id, :hypothesis_version_id, 'v2', 'QUEUED', 'CLARIFY', "
                    "'promotion-v1', :request_hash, 'profile', 'v1', :evidence_hash, "
                    "'legacy-workflow-run', :created_at)"
                ),
                {
                    "id": run_id,
                    "user_id": user_id,
                    "hypothesis_version_id": hypothesis_id,
                    "request_hash": "b" * 64,
                    "evidence_hash": "c" * 64,
                    "created_at": "2026-09-06 00:00:00",
                },
            )

        _upgrade(config, database_url, _HEAD)
        with engine.connect() as connection:
            upgraded = (
                connection.execute(
                    text(
                        "SELECT protocol_version, status, stage_cursor, trace_id, workflow_version "
                        "FROM ai_research_runs WHERE id = :id"
                    ),
                    {"id": run_id},
                )
                .mappings()
                .one()
            )
        assert dict(upgraded) == {
            "protocol_version": "v2",
            "status": "QUEUED",
            "stage_cursor": "CLARIFY",
            "trace_id": "legacy-workflow-run",
            "workflow_version": "generation-v1",
        }

        _downgrade(config, database_url, _PRE_WORKFLOW_VERSION_HEAD)
        assert "workflow_version" not in {
            column["name"]
            for column in inspect(create_engine(database_url)).get_columns("ai_research_runs")
        }
        _upgrade(config, database_url, _HEAD)
        with engine.connect() as connection:
            restored_version = connection.execute(
                text("SELECT workflow_version FROM ai_research_runs WHERE id = :id"),
                {"id": run_id},
            ).scalar_one()
        assert restored_version == "generation-v1"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("workflow_version", "status", "stage_cursor"),
    [
        ("discovery-v1", "QUEUED", "CLARIFY"),
        ("future-server-graph-v9", "RUNNING", "VALIDATE_DISCOVERY"),
    ],
)
def test_workflow_version_downgrade_refuses_nonlegacy_runs(
    tmp_path,
    monkeypatch,
    workflow_version: str,
    status: str,
    stage_cursor: str,
) -> None:
    """Dropping a nonlegacy graph must never silently reinterpret its task history."""

    database_url = f"sqlite:///{tmp_path / 'trusted-research-workflow-downgrade.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    engine = create_engine(database_url)
    user_id = "91111111-1111-1111-1111-111111111111"
    hypothesis_id = "92222222-2222-2222-2222-222222222222"
    run_id = "93333333-3333-3333-3333-333333333333"
    try:
        _upgrade(config, database_url, _PRE_WORKFLOW_VERSION_HEAD)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, username, email, hashed_password, is_active, created_at, updated_at) "
                    "VALUES (:id, :username, :email, :hashed_password, :is_active, "
                    ":created_at, :updated_at)"
                ),
                {
                    "id": user_id,
                    "username": "workflow-version-downgrade",
                    "email": "workflow-version-downgrade@example.test",
                    "hashed_password": "fixture",
                    "is_active": True,
                    "created_at": "2026-09-06 00:00:00",
                    "updated_at": "2026-09-06 00:00:00",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO ai_research_hypothesis_versions "
                    "(id, user_id, hypothesis_id, version_no, status, canonical_payload, "
                    "content_hash, created_at) VALUES "
                    "(:id, :user_id, :hypothesis_id, 1, 'CONFIRMED', :payload, "
                    ":content_hash, :created_at)"
                ),
                {
                    "id": hypothesis_id,
                    "user_id": user_id,
                    "hypothesis_id": "94444444-4444-4444-4444-444444444444",
                    "payload": json.dumps({"research_question": "fixture"}),
                    "content_hash": "a" * 64,
                    "created_at": "2026-09-06 00:00:00",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO ai_research_runs "
                    "(id, user_id, hypothesis_version_id, protocol_version, status, stage_cursor, "
                    "promotion_policy_version, request_hash, capability_profile_id, "
                    "capability_profile_version, capability_evidence_hash, trace_id, created_at) "
                    "VALUES (:id, :user_id, :hypothesis_version_id, 'v2', 'QUEUED', 'CLARIFY', "
                    "'promotion-v1', :request_hash, 'profile', 'v1', :evidence_hash, "
                    "'workflow-downgrade-run', :created_at)"
                ),
                {
                    "id": run_id,
                    "user_id": user_id,
                    "hypothesis_version_id": hypothesis_id,
                    "request_hash": "b" * 64,
                    "evidence_hash": "c" * 64,
                    "created_at": "2026-09-06 00:00:00",
                },
            )
        _upgrade(config, database_url, _HEAD)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ai_research_runs SET workflow_version = :workflow_version, "
                    "status = :status, stage_cursor = :stage_cursor WHERE id = :id"
                ),
                {
                    "id": run_id,
                    "workflow_version": workflow_version,
                    "status": status,
                    "stage_cursor": stage_cursor,
                },
            )

        with pytest.raises(RuntimeError, match="RESEARCH_WORKFLOW_VERSION_DOWNGRADE_BLOCKED"):
            _downgrade(config, database_url, _PRE_WORKFLOW_VERSION_HEAD)

        with engine.connect() as connection:
            retained = (
                connection.execute(
                    text(
                        "SELECT workflow_version, status, stage_cursor FROM ai_research_runs WHERE id = :id"
                    ),
                    {"id": run_id},
                )
                .mappings()
                .one()
            )
        assert dict(retained) == {
            "workflow_version": workflow_version,
            "status": status,
            "stage_cursor": stage_cursor,
        }
    finally:
        engine.dispose()


def test_storage_reference_migration_backfills_existing_snapshot(tmp_path, monkeypatch) -> None:
    """A pre-existing v2 snapshot keeps its original opaque-reference binding."""

    database_url = f"sqlite:///{tmp_path / 'trusted-research-backfill.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _PRE_STORAGE_REFERENCE_HEAD)
    engine = create_engine(database_url)
    user_id = "11111111-1111-1111-1111-111111111111"
    snapshot_id = "22222222-2222-2222-2222-222222222222"
    storage_uri = "controlled://migration-fixture/discovery.parquet"
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, username, email, hashed_password, is_active, created_at, updated_at) "
                    "VALUES (:id, :username, :email, :hashed_password, :is_active, :created_at, :updated_at)"
                ),
                {
                    "id": user_id,
                    "username": "storage-reference-migration",
                    "email": "storage-reference-migration@example.test",
                    "hashed_password": "fixture",
                    "is_active": True,
                    "created_at": "2026-09-05 00:00:00",
                    "updated_at": "2026-09-05 00:00:00",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO ai_research_dataset_snapshots "
                    "(id, user_id, dataset_policy_version, partition_kind, instrument_manifest, "
                    "split_manifest, source_manifest, execution_policy, point_in_time_cutoff, "
                    "content_hash, storage_uri, license_tags, created_at) VALUES "
                    "(:id, :user_id, :dataset_policy_version, :partition_kind, :instrument_manifest, "
                    ":split_manifest, :source_manifest, :execution_policy, :point_in_time_cutoff, "
                    ":content_hash, :storage_uri, :license_tags, :created_at)"
                ),
                {
                    "id": snapshot_id,
                    "user_id": user_id,
                    "dataset_policy_version": "fixture-v1",
                    "partition_kind": "DISCOVERY",
                    "instrument_manifest": json.dumps({"symbols": ["RB0"]}),
                    "split_manifest": json.dumps({"start": "2024-01-01", "end": "2024-12-31"}),
                    "source_manifest": json.dumps({"provider": "fixture"}),
                    "execution_policy": json.dumps({"fill": "next_bar_open"}),
                    "point_in_time_cutoff": "2025-01-01 00:00:00",
                    "content_hash": "a" * 64,
                    "storage_uri": storage_uri,
                    "license_tags": json.dumps(["fixture-license"]),
                    "created_at": "2026-09-05 00:00:00",
                },
            )
        _upgrade(config, database_url, _HEAD)
        with engine.connect() as connection:
            actual = connection.execute(
                text(
                    "SELECT storage_reference_hash FROM ai_research_dataset_snapshots "
                    "WHERE id = :id"
                ),
                {"id": snapshot_id},
            ).scalar_one()
    finally:
        engine.dispose()

    from app.services.research.dataset_registry import storage_reference_hash

    assert actual == storage_reference_hash("DISCOVERY", storage_uri)


def test_epoch_family_unique_migration_refuses_ambiguous_legacy_disclosure_history(
    tmp_path,
    monkeypatch,
) -> None:
    """A duplicate legacy family must be reconciled, not silently collapsed."""

    database_url = f"sqlite:///{tmp_path / 'trusted-research-duplicate-family.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)
    _upgrade(config, database_url, _PRE_STORAGE_REFERENCE_HEAD)
    engine = create_engine(database_url)
    user_id = "33333333-3333-3333-3333-333333333333"
    hypothesis_id = "44444444-4444-4444-4444-444444444444"
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, username, email, hashed_password, is_active, created_at, updated_at) "
                    "VALUES (:id, :username, :email, :hashed_password, :is_active, :created_at, :updated_at)"
                ),
                {
                    "id": user_id,
                    "username": "epoch-family-migration",
                    "email": "epoch-family-migration@example.test",
                    "hashed_password": "fixture",
                    "is_active": True,
                    "created_at": "2026-09-05 00:00:00",
                    "updated_at": "2026-09-05 00:00:00",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO ai_research_hypothesis_versions "
                    "(id, user_id, hypothesis_id, version_no, status, canonical_payload, content_hash, created_at) "
                    "VALUES (:id, :user_id, :hypothesis_id, 1, 'CONFIRMED', :payload, :content_hash, :created_at)"
                ),
                {
                    "id": hypothesis_id,
                    "user_id": user_id,
                    "hypothesis_id": "55555555-5555-5555-5555-555555555555",
                    "payload": json.dumps({"research_question": "fixture"}),
                    "content_hash": "a" * 64,
                    "created_at": "2026-09-05 00:00:00",
                },
            )
            for epoch_id in (
                "66666666-6666-6666-6666-666666666666",
                "77777777-7777-7777-7777-777777777777",
            ):
                connection.execute(
                    text(
                        "INSERT INTO ai_research_experiment_epochs "
                        "(id, user_id, hypothesis_version_id, family_hash, search_budget, "
                        "dataset_policy_version, holdout_budget, status, opened_at) VALUES "
                        "(:id, :user_id, :hypothesis_version_id, :family_hash, :search_budget, "
                        ":dataset_policy_version, 1, 'CLOSED', :opened_at)"
                    ),
                    {
                        "id": epoch_id,
                        "user_id": user_id,
                        "hypothesis_version_id": hypothesis_id,
                        "family_hash": "b" * 64,
                        "search_budget": json.dumps({"max_trials": 3}),
                        "dataset_policy_version": "fixture-v1",
                        "opened_at": "2026-09-05 00:00:00",
                    },
                )

        with pytest.raises(RuntimeError, match="EXPERIMENT_EPOCH_FAMILY_DEDUPLICATION_REQUIRED"):
            _upgrade(config, database_url, _HEAD)
    finally:
        engine.dispose()
