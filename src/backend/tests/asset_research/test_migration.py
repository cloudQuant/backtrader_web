"""Fresh-database migration contract for the multi-asset research foundation."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

import app.config as app_config
from alembic import command

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARENT = "20260801_stock_signal_predictions"
_HEAD = "20260811_asset_research_task_leases"
_LEGACY_HEAD = "20260805_asset_research_outcome_reliability"
_TABLES = {
    "asset_instruments",
    "asset_data_source_registry",
    "asset_position_context_snapshots",
    "asset_source_snapshots",
    "asset_analysis_tasks",
    "asset_analysis_reports",
    "asset_analysis_exports",
    "asset_report_publications",
    "asset_schedule_manifests",
    "asset_signal_schedules",
    "asset_signal_runs",
    "asset_signal_predictions",
    "asset_signal_outcomes",
    "asset_model_registry",
    "asset_model_status_events",
}
_CHECKS = {
    "asset_position_context_snapshots": {
        "ck_asset_position_context_owner",
        "ck_asset_position_context_value",
        "ck_asset_position_context_quantities",
    },
    "asset_analysis_tasks": {
        "ck_asset_task_owner",
        "ck_asset_task_status",
        "ck_asset_task_progress",
        "ck_asset_task_lease_pair",
        "ck_asset_task_attempt_count",
    },
    "asset_signal_schedules": {
        "ck_asset_schedule_owner",
        "ck_asset_schedule_no_position_context",
        "ck_asset_schedule_manifest_owner",
    },
    "asset_schedule_manifests": {
        "ck_asset_schedule_manifest_scope",
        "ck_asset_schedule_manifest_status",
        "ck_asset_schedule_manifest_evidence",
        "ck_asset_schedule_manifest_retirement",
    },
    "asset_signal_runs": {
        "ck_asset_run_owner",
        "ck_asset_run_exactly_one_source",
        "ck_asset_run_status",
        "ck_asset_run_prediction_terminal",
    },
    "asset_signal_predictions": {
        "ck_asset_prediction_owner",
        "ck_asset_prediction_actionability",
        "ck_asset_option_long_context_snapshot",
        "ck_asset_option_long_context_window",
        "ck_asset_prediction_outcome_lease_pair",
    },
    "asset_signal_outcomes": {
        "ck_asset_outcome_status",
        "ck_asset_outcome_maturity_reason",
    },
    "asset_model_registry": {"ck_asset_model_registry_status"},
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


def test_asset_research_revision_is_the_only_linear_head() -> None:
    script = ScriptDirectory.from_config(_config("sqlite://"))
    assert script.get_heads() == [_HEAD]


def test_option_context_migration_renders_mysql_preflight_and_constraints() -> None:
    """Offline DDL review must retain, rather than crash before, data preflights."""
    output = StringIO()
    config = Config(str(_BACKEND_ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", "mysql+pymysql://fixture:fixture@127.0.0.1/fixture")

    command.upgrade(
        config,
        "20260809_asset_research_maturity_reason_contract:"
        "20260810_asset_research_option_context_binding",
        sql=True,
    )

    rendered = output.getvalue()
    assert "ASSET_POSITION_CONTEXT_BINDING_BACKFILL_REQUIRED" in rendered
    assert "ASSET_OPTION_LONG_CONTEXT_WINDOW_BACKFILL_REQUIRED" in rendered
    assert "fk_asset_prediction_position_context_binding" in rendered
    assert "fk_asset_prediction_position_context_window" in rendered
    assert "ck_asset_option_long_context_window" in rendered


def test_asset_research_migration_expands_and_rolls_back_without_touching_stock_tables(
    tmp_path, monkeypatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'asset_research.db'}"
    monkeypatch.setattr(app_config, "_settings", app_config.Settings(DATABASE_URL=database_url))
    config = _config(database_url)

    _upgrade(config, database_url, _PARENT)
    before = set(inspect(create_engine(database_url)).get_table_names())
    _upgrade(config, database_url, _HEAD)

    engine = create_engine(database_url)
    try:
        after = set(inspect(engine).get_table_names())
        assert _TABLES <= after
        assert {
            "stock_analysis_tasks",
            "stock_analysis_reports",
            "stock_signal_predictions",
        } <= after
        for table_name in _TABLES:
            assert {
                "retention_class",
                "retention_expires_at",
                "legal_hold",
                "tombstoned_at",
            } <= {column["name"] for column in inspect(engine).get_columns(table_name)}
        for table_name, expected_checks in _CHECKS.items():
            observed_checks = {
                check["name"] for check in inspect(engine).get_check_constraints(table_name)
            }
            assert expected_checks <= observed_checks
        prediction_columns = {
            column["name"] for column in inspect(engine).get_columns("asset_signal_predictions")
        }
        assert {
            "outcome_lease_token",
            "outcome_lease_expires_at",
            "outcome_last_attempt_at",
            "outcome_last_error_code",
            "position_context_snapshot_as_of_at",
            "position_context_snapshot_available_at",
            "position_context_snapshot_expires_at",
        } <= prediction_columns
        task_columns = {
            column["name"] for column in inspect(engine).get_columns("asset_analysis_tasks")
        }
        assert {
            "lease_token",
            "lease_expires_at",
            "lease_heartbeat_at",
            "attempt_count",
        } <= task_columns
        context_unique_constraints = {
            constraint["name"]
            for constraint in inspect(engine).get_unique_constraints(
                "asset_position_context_snapshots"
            )
        }
        assert {
            "uq_asset_position_context_prediction_binding",
            "uq_asset_position_context_prediction_window",
        } <= context_unique_constraints
        prediction_foreign_keys = {
            foreign_key["name"]
            for foreign_key in inspect(engine).get_foreign_keys("asset_signal_predictions")
        }
        assert {
            "fk_asset_prediction_position_context_binding",
            "fk_asset_prediction_position_context_window",
        } <= prediction_foreign_keys
        run_columns = {
            column["name"] for column in inspect(engine).get_columns("asset_signal_runs")
        }
        assert {"prediction_id", "prediction_link_role"} <= run_columns
        schedule_columns = {
            column["name"] for column in inspect(engine).get_columns("asset_signal_schedules")
        }
        assert {
            "approved_manifest_id",
            "manifest_entry_key",
            "manifest_content_hash",
            "system_target_key",
        } <= schedule_columns
        manifest_column_metadata = {
            column["name"]: column
            for column in inspect(engine).get_columns("asset_schedule_manifests")
        }
        assert manifest_column_metadata["evidence_uri"]["nullable"] is False
        assert manifest_column_metadata["evidence_content_hash"]["nullable"] is False
        with engine.begin() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO asset_signal_runs "
                        "(id, run_key, cutoff_policy_version, owner_scope, run_type, asset_type, "
                        "as_of_at, cutoff_at, policy_version, status, counts_json, created_at) "
                        "VALUES (:id, :run_key, :cutoff_policy_version, :owner_scope, :run_type, "
                        ":asset_type, :as_of_at, :cutoff_at, :policy_version, :status, :counts_json, "
                        ":created_at)"
                    ),
                    {
                        "id": "run-without-source",
                        "run_key": "a" * 64,
                        "cutoff_policy_version": "fixture-v1",
                        "owner_scope": "ADMIN_EVAL",
                        "run_type": "MANUAL",
                        "asset_type": "futures",
                        "as_of_at": "2026-08-01T00:00:00+00:00",
                        "cutoff_at": "2026-08-01T00:00:00+00:00",
                        "policy_version": "fixture-v1",
                        "status": "PENDING",
                        "counts_json": "{}",
                        "created_at": "2026-08-01T00:00:00+00:00",
                    },
                )
            connection.execute(
                text(
                    "INSERT INTO asset_signal_runs "
                    "(id, run_key, task_id, cutoff_policy_version, owner_scope, run_type, "
                    "asset_type, as_of_at, cutoff_at, policy_version, status, counts_json, created_at) "
                    "VALUES (:id, :run_key, :task_id, :cutoff_policy_version, :owner_scope, "
                    ":run_type, :asset_type, :as_of_at, :cutoff_at, :policy_version, :status, "
                    ":counts_json, :created_at)"
                ),
                {
                    "id": "run-trigger-fixture",
                    "run_key": "b" * 64,
                    "task_id": "task-trigger-fixture",
                    "cutoff_policy_version": "fixture-v1",
                    "owner_scope": "ADMIN_EVAL",
                    "run_type": "MANUAL",
                    "asset_type": "futures",
                    "as_of_at": "2026-08-01T00:00:00+00:00",
                    "cutoff_at": "2026-08-01T00:00:00+00:00",
                    "policy_version": "fixture-v1",
                    "status": "RUNNING",
                    "counts_json": "{}",
                    "created_at": "2026-08-01T00:00:00+00:00",
                },
            )
            with pytest.raises(IntegrityError):
                connection.execute(
                    text("UPDATE asset_signal_runs SET status = 'SUCCEEDED' WHERE id = :id"),
                    {"id": "run-trigger-fixture"},
                )
            connection.execute(
                text(
                    "UPDATE asset_signal_runs "
                    "SET prediction_id = :prediction_id, prediction_link_role = :link_role, "
                    "status = 'SUCCEEDED' WHERE id = :run_id"
                ),
                {
                    "run_id": "run-trigger-fixture",
                    "prediction_id": "prediction-trigger-fixture",
                    "link_role": "CREATED",
                    "created_at": "2026-08-01T00:00:00+00:00",
                },
            )
            with pytest.raises(IntegrityError):
                connection.execute(
                    text("UPDATE asset_signal_runs SET prediction_id = NULL WHERE id = :run_id"),
                    {"run_id": "run-trigger-fixture"},
                )
            connection.execute(
                text(
                    """
                    INSERT INTO asset_instruments (
                        id, canonical_id, asset_type, identity_level, identity_json,
                        metadata_version, lifecycle_status, valid_from, created_at
                    ) VALUES (
                        'manifest-fixture-instrument', 'futures:TEST:MANIFEST:CNY', 'futures',
                        'CONTRACT', '{}', 'fixture-v1', 'ACTIVE',
                        '2026-08-01T00:00:00+00:00', '2026-08-01T00:00:00+00:00'
                    )
                    """
                )
            )
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_schedule_manifests (
                            id, manifest_key, manifest_version, owner_scope, approval_reference,
                            content_hash, approved_by, approved_at, status,
                            retirement_reason_codes_json, created_at
                        ) VALUES (
                            'manifest-without-evidence', 'fixture', 'invalid', 'PUBLIC_SHADOW',
                            'TEST-ONLY', :content_hash, 'fixture-admin',
                            '2026-08-01T00:00:00+00:00', 'ACTIVE', '[]',
                            '2026-08-01T00:00:00+00:00'
                        )
                        """
                    ),
                    {"content_hash": "b" * 64},
                )
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_signal_schedules (
                            id, owner_scope, instrument_id, asset_type, canonical_id,
                            identity_version, horizon_code, horizon_spec_json, position_context,
                            cron_expression, timezone, cutoff_policy, cutoff_policy_version,
                            misfire_policy, schedule_version, enabled, created_at, updated_at
                        ) VALUES (
                            'manifest-invalid-schedule', 'PUBLIC_SHADOW',
                            'manifest-fixture-instrument', 'futures', 'futures:TEST:MANIFEST:CNY',
                            'fixture-v1', 'standard', '{}', 'UNKNOWN', '0 19 * * *', 'UTC',
                            'fixture-policy', 'fixture-v1', 'SKIP', 1, 0,
                            '2026-08-01T00:00:00+00:00', '2026-08-01T00:00:00+00:00'
                        )
                        """
                    )
                )
            connection.execute(
                text(
                    """
                    INSERT INTO asset_schedule_manifests (
                        id, manifest_key, manifest_version, owner_scope, approval_reference,
                        evidence_uri, evidence_content_hash, content_hash, approved_by, approved_at,
                        status, retirement_reason_codes_json, created_at
                    ) VALUES (
                        'manifest-fixture', 'fixture', 'v1', 'PUBLIC_SHADOW', 'TEST-ONLY',
                        'evidence://test/fixture', :evidence_hash, :content_hash, 'fixture-admin',
                        '2026-08-01T00:00:00+00:00', 'ACTIVE', '[]',
                        '2026-08-01T00:00:00+00:00'
                    )
                    """
                ),
                {"evidence_hash": "c" * 64, "content_hash": "d" * 64},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO asset_signal_schedules (
                        id, owner_scope, approved_manifest_id, manifest_entry_key,
                        manifest_content_hash, system_target_key, instrument_id, asset_type,
                        canonical_id, identity_version, horizon_code, horizon_spec_json,
                        position_context, cron_expression, timezone, cutoff_policy,
                        cutoff_policy_version, misfire_policy, schedule_version, enabled,
                        created_at, updated_at
                    ) VALUES (
                        'manifest-valid-schedule', 'PUBLIC_SHADOW', 'manifest-fixture', 'fixture-entry',
                        :content_hash, :target_key, 'manifest-fixture-instrument', 'futures',
                        'futures:TEST:MANIFEST:CNY', 'fixture-v1', 'standard', '{}', 'UNKNOWN',
                        '0 19 * * *', 'UTC', 'fixture-policy', 'fixture-v1', 'SKIP', 1, 1,
                        '2026-08-01T00:00:00+00:00', '2026-08-01T00:00:00+00:00'
                    )
                    """
                ),
                {"content_hash": "d" * 64, "target_key": "e" * 64},
            )
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM asset_signal_schedules WHERE id = 'manifest-valid-schedule'")
            )
            connection.execute(
                text("DELETE FROM asset_schedule_manifests WHERE id = 'manifest-fixture'")
            )
    finally:
        engine.dispose()

    _downgrade(config, database_url, _PARENT)
    engine = create_engine(database_url)
    try:
        reverted = set(inspect(engine).get_table_names())
        assert not (_TABLES & reverted)
        assert before <= reverted
    finally:
        engine.dispose()


def test_maturity_reason_migration_refuses_legacy_undefined_values(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'legacy_maturity_reason.db'}"
    config = _config(database_url)
    _upgrade(config, database_url, "20260808_asset_research_manifest_evidence_required")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO asset_signal_outcomes (
                        id, prediction_id, outcome_kind, head_spec_hash, horizon_code,
                        evaluator_version, status, maturity_reason, metrics_json, risk_json,
                        reason_codes_json
                    ) VALUES (
                        'legacy-invalid-outcome', 'legacy-prediction', 'futures.contract_pnl', :head_spec_hash,
                        'fixture-horizon', 'fixture-v1', 'PENDING', 'MATURED', '{}', '{}', '[]'
                    )
                    """
                ),
                {"head_spec_hash": "a" * 64},
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="ASSET_OUTCOME_MATURITY_REASON_BACKFILL_REQUIRED"):
        _upgrade(config, database_url, _HEAD)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == ("20260808_asset_research_manifest_evidence_required")
    finally:
        engine.dispose()


def test_option_context_binding_migration_refuses_an_unbound_legacy_prediction(tmp_path) -> None:
    """Upgrade must stop instead of inventing ownership for an old context reference."""
    database_url = f"sqlite:///{tmp_path / 'legacy_option_context_binding.db'}"
    config = _config(database_url)
    previous_head = "20260809_asset_research_maturity_reason_contract"
    _upgrade(config, database_url, previous_head)

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO asset_signal_predictions (
                        id, prediction_key, decision_input_hash, owner_scope, user_id, instrument_id,
                        asset_type, canonical_id, identity_version, as_of_at, horizon_code,
                        horizon_spec_json, position_context, position_context_snapshot_id,
                        candidate_decision_json, published_decision_json, actionability, quality_status,
                        quality_json, snapshot_id, head_spec_set_hash, feature_version, policy_version,
                        model_version, calibration_version, capability_version,
                        compliance_policy_version, cutoff_policy_version, cost_snapshot_json, created_at
                    ) VALUES (
                        'legacy-unbound-context-prediction', :prediction_key, :input_hash, 'USER',
                        'legacy-owner', 'legacy-option-instrument', 'option',
                        'option:XSHG:LEGACY:CNY', 'fixture-v1', '2026-08-01T12:00:00+00:00',
                        'fixture-horizon', '{}', 'LONG', 'missing-context-snapshot', '{}', '{}',
                        'RESEARCH_ONLY', 'ELIGIBLE', '{}', 'legacy-source-snapshot', :head_spec_hash,
                        'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1',
                        'fixture-v1', 'fixture-v1', '{}', '2026-08-01T12:00:00+00:00'
                    )
                    """
                ),
                {
                    "prediction_key": "a" * 64,
                    "input_hash": "b" * 64,
                    "head_spec_hash": "c" * 64,
                },
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="ASSET_POSITION_CONTEXT_BINDING_BACKFILL_REQUIRED"):
        _upgrade(config, database_url, _HEAD)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == (previous_head)
    finally:
        engine.dispose()


def test_option_context_binding_migration_refuses_an_expired_legacy_long_context(tmp_path) -> None:
    """Upgrade must not rewrite an expired historical option context as a valid close input."""
    database_url = f"sqlite:///{tmp_path / 'legacy_option_context_window.db'}"
    config = _config(database_url)
    previous_head = "20260809_asset_research_maturity_reason_contract"
    _upgrade(config, database_url, previous_head)

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO asset_position_context_snapshots (
                        id, owner_scope, user_id, instrument_id, asset_type, canonical_id,
                        identity_version, position_context, long_quantity, short_quantity,
                        as_of_at, available_at, expires_at, source_type, source_manifest_json,
                        content_hash, created_at
                    ) VALUES (
                        'legacy-expired-context', 'USER', 'legacy-owner',
                        'legacy-option-instrument', 'option', 'option:XSHG:LEGACY:CNY',
                        'fixture-v1', 'LONG', 1, 0, '2026-08-01T10:00:00+00:00',
                        '2026-08-01T10:00:00+00:00', '2026-08-01T11:00:00+00:00',
                        'USER_DECLARED', '{}', :context_hash, '2026-08-01T10:00:00+00:00'
                    )
                    """
                ),
                {"context_hash": "a" * 64},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO asset_signal_predictions (
                        id, prediction_key, decision_input_hash, owner_scope, user_id, instrument_id,
                        asset_type, canonical_id, identity_version, as_of_at, horizon_code,
                        horizon_spec_json, position_context, position_context_snapshot_id,
                        candidate_decision_json, published_decision_json, actionability, quality_status,
                        quality_json, snapshot_id, head_spec_set_hash, feature_version, policy_version,
                        model_version, calibration_version, capability_version,
                        compliance_policy_version, cutoff_policy_version, cost_snapshot_json, created_at
                    ) VALUES (
                        'legacy-expired-context-prediction', :prediction_key, :input_hash, 'USER',
                        'legacy-owner', 'legacy-option-instrument', 'option',
                        'option:XSHG:LEGACY:CNY', 'fixture-v1', '2026-08-01T12:00:00+00:00',
                        'fixture-horizon', '{}', 'LONG', 'legacy-expired-context', '{}', '{}',
                        'RESEARCH_ONLY', 'ELIGIBLE', '{}', 'legacy-source-snapshot', :head_spec_hash,
                        'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1',
                        'fixture-v1', 'fixture-v1', '{}', '2026-08-01T12:00:00+00:00'
                    )
                    """
                ),
                {
                    "prediction_key": "b" * 64,
                    "input_hash": "c" * 64,
                    "head_spec_hash": "d" * 64,
                },
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="ASSET_OPTION_LONG_CONTEXT_WINDOW_BACKFILL_REQUIRED"):
        _upgrade(config, database_url, _HEAD)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == (previous_head)
    finally:
        engine.dispose()


def test_option_context_binding_migration_copies_a_valid_legacy_context_window(tmp_path) -> None:
    """A valid historical option LONG context is copied exactly before constraints attach."""
    database_url = f"sqlite:///{tmp_path / 'legacy_option_context_copy.db'}"
    config = _config(database_url)
    previous_head = "20260809_asset_research_maturity_reason_contract"
    _upgrade(config, database_url, previous_head)

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO asset_position_context_snapshots (
                        id, owner_scope, user_id, instrument_id, asset_type, canonical_id,
                        identity_version, position_context, long_quantity, short_quantity,
                        as_of_at, available_at, expires_at, source_type, source_manifest_json,
                        content_hash, created_at
                    ) VALUES (
                        'legacy-valid-context', 'USER', 'legacy-owner',
                        'legacy-option-instrument', 'option', 'option:XSHG:LEGACY:CNY',
                        'fixture-v1', 'LONG', 1, 0, '2026-08-01T10:00:00+00:00',
                        '2026-08-01T10:00:00+00:00', '2026-08-01T13:00:00+00:00',
                        'USER_DECLARED', '{}', :context_hash, '2026-08-01T10:00:00+00:00'
                    )
                    """
                ),
                {"context_hash": "a" * 64},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO asset_signal_predictions (
                        id, prediction_key, decision_input_hash, owner_scope, user_id, instrument_id,
                        asset_type, canonical_id, identity_version, as_of_at, horizon_code,
                        horizon_spec_json, position_context, position_context_snapshot_id,
                        candidate_decision_json, published_decision_json, actionability, quality_status,
                        quality_json, snapshot_id, head_spec_set_hash, feature_version, policy_version,
                        model_version, calibration_version, capability_version,
                        compliance_policy_version, cutoff_policy_version, cost_snapshot_json, created_at
                    ) VALUES (
                        'legacy-valid-context-prediction', :prediction_key, :input_hash, 'USER',
                        'legacy-owner', 'legacy-option-instrument', 'option',
                        'option:XSHG:LEGACY:CNY', 'fixture-v1', '2026-08-01T12:00:00+00:00',
                        'fixture-horizon', '{}', 'LONG', 'legacy-valid-context', '{}', '{}',
                        'RESEARCH_ONLY', 'ELIGIBLE', '{}', 'legacy-source-snapshot', :head_spec_hash,
                        'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1',
                        'fixture-v1', 'fixture-v1', '{}', '2026-08-01T12:00:00+00:00'
                    )
                    """
                ),
                {
                    "prediction_key": "b" * 64,
                    "input_hash": "c" * 64,
                    "head_spec_hash": "d" * 64,
                },
            )
    finally:
        engine.dispose()

    _upgrade(config, database_url, _HEAD)

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT position_context_snapshot_as_of_at,
                           position_context_snapshot_available_at,
                           position_context_snapshot_expires_at
                    FROM asset_signal_predictions
                    WHERE id = 'legacy-valid-context-prediction'
                    """
                )
            ).one()
            assert str(row[0]) == "2026-08-01T10:00:00+00:00"
            assert str(row[1]) == "2026-08-01T10:00:00+00:00"
            assert str(row[2]) == "2026-08-01T13:00:00+00:00"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("context_user_id", "context_instrument_id", "context_canonical_id", "context_state"),
    [
        ("foreign-owner", "owner-option", "option:XSHG:OWNER:CNY", "LONG"),
        ("option-owner", "foreign-option", "option:XSHG:FOREIGN:CNY", "LONG"),
        ("option-owner", "owner-option", "option:XSHG:OWNER:CNY", "FLAT"),
    ],
    ids=["other-user", "other-contract", "not-long"],
)
def test_option_long_prediction_cannot_bind_a_foreign_or_non_long_context(
    tmp_path,
    context_user_id: str,
    context_instrument_id: str,
    context_canonical_id: str,
    context_state: str,
) -> None:
    """A direct write cannot manufacture an option CLOSE authority from another context.

    The production change that makes this test fail is removal of the
    composite context binding foreign key or its required option-LONG window
    check.  A plain ``snapshot_id`` foreign key is insufficient: it proves
    only that *some* snapshot exists, not that it belongs to the prediction's
    owner, exact option contract and LONG position state.
    """
    database_url = f"sqlite:///{tmp_path / 'option_context_binding.db'}"
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys = ON"))
            connection.execute(
                text(
                    """
                    INSERT INTO users (id, username, email, hashed_password)
                    VALUES
                        ('option-owner', 'option_owner', 'option-owner@example.test', 'hash'),
                        ('foreign-owner', 'foreign_owner', 'foreign-owner@example.test', 'hash')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO asset_instruments (
                        id, canonical_id, asset_type, identity_level, identity_json,
                        metadata_version, lifecycle_status, valid_from, created_at
                    ) VALUES
                        ('owner-option', 'option:XSHG:OWNER:CNY', 'option', 'CONTRACT', '{}',
                         'fixture-v1', 'ACTIVE', '2026-08-01T00:00:00+00:00',
                         '2026-08-01T00:00:00+00:00'),
                        ('foreign-option', 'option:XSHG:FOREIGN:CNY', 'option', 'CONTRACT', '{}',
                         'fixture-v1', 'ACTIVE', '2026-08-01T00:00:00+00:00',
                         '2026-08-01T00:00:00+00:00')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO asset_position_context_snapshots (
                        id, owner_scope, user_id, instrument_id, asset_type, canonical_id,
                        identity_version, position_context, long_quantity, short_quantity,
                        as_of_at, available_at, expires_at, source_type, source_manifest_json,
                        content_hash, created_at
                    ) VALUES (
                        'foreign-long-context', 'USER', :context_user_id, :context_instrument_id, 'option',
                        :context_canonical_id, 'fixture-v1', :context_state,
                        :long_quantity, :short_quantity,
                        '2026-08-01T00:00:00+00:00', '2026-08-01T00:00:00+00:00',
                        '2026-09-01T00:00:00+00:00', 'USER_DECLARED', '{}', :context_hash,
                        '2026-08-01T00:00:00+00:00'
                    )
                    """
                ),
                {
                    "context_user_id": context_user_id,
                    "context_instrument_id": context_instrument_id,
                    "context_canonical_id": context_canonical_id,
                    "context_state": context_state,
                    "long_quantity": 1 if context_state == "LONG" else 0,
                    "short_quantity": 0,
                    "context_hash": "a" * 64,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO asset_source_snapshots (
                        id, instrument_id, asset_type, canonical_id, identity_version, cutoff_at,
                        raw_schema_version, raw_fields_json, source_manifest_json, content_hash,
                        license_tags_json, created_at
                    ) VALUES (
                        'owner-option-source', 'owner-option', 'option', 'option:XSHG:OWNER:CNY',
                        'fixture-v1', '2026-08-01T00:00:00+00:00', 'fixture-v1', '{}', '{}',
                        :source_hash, '[]', '2026-08-01T00:00:00+00:00'
                    )
                    """
                ),
                {"source_hash": "b" * 64},
            )
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_signal_predictions (
                            id, prediction_key, decision_input_hash, owner_scope, user_id,
                            instrument_id, asset_type, canonical_id, identity_version, as_of_at,
                            horizon_code, horizon_spec_json, position_context,
                            position_context_snapshot_id, position_context_snapshot_as_of_at,
                            position_context_snapshot_available_at,
                            position_context_snapshot_expires_at, candidate_decision_json,
                            published_decision_json, actionability, quality_status, quality_json,
                            snapshot_id, head_spec_set_hash, feature_version, policy_version,
                            model_version, calibration_version, capability_version,
                            compliance_policy_version, cutoff_policy_version, cost_snapshot_json,
                            created_at
                        ) VALUES (
                            'foreign-context-prediction', :prediction_key, :input_hash, 'USER',
                            'option-owner', 'owner-option', 'option', 'option:XSHG:OWNER:CNY',
                            'fixture-v1', '2026-08-01T12:00:00+00:00', 'fixture-horizon', '{}',
                            'LONG', 'foreign-long-context', '2026-08-01T00:00:00+00:00',
                            '2026-08-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00', '{}', '{}',
                            'RESEARCH_ONLY', 'ELIGIBLE',
                            '{}', 'owner-option-source', :head_spec_hash, 'fixture-v1', 'fixture-v1',
                            'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1', '{}',
                            '2026-08-01T12:00:00+00:00'
                        )
                        """
                    ),
                    {
                        "prediction_key": "c" * 64,
                        "input_hash": "d" * 64,
                        "head_spec_hash": "e" * 64,
                    },
                )
    finally:
        engine.dispose()


def test_option_long_prediction_cannot_bind_an_expired_context_snapshot(tmp_path) -> None:
    """A valid owner and contract still cannot use a context expired at prediction cutoff.

    The production change that makes this test fail is removal of the
    persisted context-window check.  The existing service check is not enough:
    this fixture performs the forbidden write directly against the migrated
    schema.
    """
    database_url = f"sqlite:///{tmp_path / 'option_context_expiry.db'}"
    config = _config(database_url)
    _upgrade(config, database_url, _HEAD)

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys = ON"))
            connection.execute(
                text(
                    """
                    INSERT INTO users (id, username, email, hashed_password)
                    VALUES ('option-owner', 'option_owner', 'option-owner@example.test', 'hash')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO asset_instruments (
                        id, canonical_id, asset_type, identity_level, identity_json,
                        metadata_version, lifecycle_status, valid_from, created_at
                    ) VALUES (
                        'owner-option', 'option:XSHG:OWNER:CNY', 'option', 'CONTRACT', '{}',
                        'fixture-v1', 'ACTIVE', '2026-08-01T00:00:00+00:00',
                        '2026-08-01T00:00:00+00:00'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO asset_position_context_snapshots (
                        id, owner_scope, user_id, instrument_id, asset_type, canonical_id,
                        identity_version, position_context, long_quantity, short_quantity,
                        as_of_at, available_at, expires_at, source_type, source_manifest_json,
                        content_hash, created_at
                    ) VALUES (
                        'expired-long-context', 'USER', 'option-owner', 'owner-option', 'option',
                        'option:XSHG:OWNER:CNY', 'fixture-v1', 'LONG', 1, 0,
                        '2026-08-01T00:00:00+00:00', '2026-08-01T00:00:00+00:00',
                        '2026-08-01T11:00:00+00:00', 'USER_DECLARED', '{}', :context_hash,
                        '2026-08-01T00:00:00+00:00'
                    )
                    """
                ),
                {"context_hash": "a" * 64},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO asset_source_snapshots (
                        id, instrument_id, asset_type, canonical_id, identity_version, cutoff_at,
                        raw_schema_version, raw_fields_json, source_manifest_json, content_hash,
                        license_tags_json, created_at
                    ) VALUES (
                        'owner-option-source', 'owner-option', 'option', 'option:XSHG:OWNER:CNY',
                        'fixture-v1', '2026-08-01T00:00:00+00:00', 'fixture-v1', '{}', '{}',
                        :source_hash, '[]', '2026-08-01T00:00:00+00:00'
                    )
                    """
                ),
                {"source_hash": "b" * 64},
            )
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_signal_predictions (
                            id, prediction_key, decision_input_hash, owner_scope, user_id,
                            instrument_id, asset_type, canonical_id, identity_version, as_of_at,
                            horizon_code, horizon_spec_json, position_context,
                            position_context_snapshot_id, position_context_snapshot_as_of_at,
                            position_context_snapshot_available_at,
                            position_context_snapshot_expires_at, candidate_decision_json,
                            published_decision_json, actionability, quality_status, quality_json,
                            snapshot_id, head_spec_set_hash, feature_version, policy_version,
                            model_version, calibration_version, capability_version,
                            compliance_policy_version, cutoff_policy_version, cost_snapshot_json,
                            created_at
                        ) VALUES (
                            'expired-context-prediction', :prediction_key, :input_hash, 'USER',
                            'option-owner', 'owner-option', 'option', 'option:XSHG:OWNER:CNY',
                            'fixture-v1', '2026-08-01T12:00:00+00:00', 'fixture-horizon', '{}',
                            'LONG', 'expired-long-context', '2026-08-01T00:00:00+00:00',
                            '2026-08-01T00:00:00+00:00', '2026-08-01T11:00:00+00:00', '{}', '{}',
                            'RESEARCH_ONLY', 'ELIGIBLE',
                            '{}', 'owner-option-source', :head_spec_hash, 'fixture-v1', 'fixture-v1',
                            'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1', '{}',
                            '2026-08-01T12:00:00+00:00'
                        )
                        """
                    ),
                    {
                        "prediction_key": "c" * 64,
                        "input_hash": "d" * 64,
                        "head_spec_hash": "e" * 64,
                    },
                )
    finally:
        engine.dispose()


def test_direct_run_relation_migrates_existing_legacy_link_rows(tmp_path) -> None:
    """Existing pre-redesign run links survive conversion without a trigger."""
    database_url = f"sqlite:///{tmp_path / 'legacy_asset_research.db'}"
    config = _config(database_url)
    _upgrade(config, database_url, _LEGACY_HEAD)

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO asset_signal_runs (
                        id, run_key, task_id, cutoff_policy_version, owner_scope, run_type,
                        asset_type, as_of_at, cutoff_at, policy_version, status, counts_json, created_at
                    ) VALUES (
                        'legacy-run', :run_key, 'legacy-task', 'fixture-v1', 'ADMIN_EVAL', 'MANUAL',
                        'futures', '2026-08-01T00:00:00+00:00', '2026-08-01T00:00:00+00:00',
                        'fixture-v1', 'SUCCEEDED', '{}', '2026-08-01T00:00:00+00:00'
                    )
                    """
                ),
                {"run_key": "c" * 64},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO asset_signal_run_predictions (
                        run_id, prediction_id, link_role, created_at,
                        retention_class, legal_hold
                    ) VALUES (
                        'legacy-run', 'legacy-prediction', 'REUSED',
                        '2026-08-01T00:00:00+00:00', 'research-v1', 0
                    )
                    """
                )
            )
    finally:
        engine.dispose()

    _upgrade(config, database_url, _HEAD)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT prediction_id, prediction_link_role FROM asset_signal_runs "
                    "WHERE id = 'legacy-run'"
                )
            ).one()
            assert row == ("legacy-prediction", "REUSED")
            assert "asset_signal_run_predictions" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
