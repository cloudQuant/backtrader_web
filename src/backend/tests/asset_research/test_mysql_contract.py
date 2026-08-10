"""Opt-in MySQL 9.4 contract for the direct run-to-prediction invariant.

The test never creates a database or commits fixture rows.  It runs only when
an operator explicitly points it at an already migrated schema and confirms
that transaction-scoped verification is intended.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, inspect, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.asset_research import AssetAnalysisTask, AssetInstrument
from app.models.user import User
from app.services.asset_research.orchestrator import AssetResearchOrchestrator
from app.services.asset_research.task_runner import AssetResearchTaskRunner

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_HEAD = "20260811_asset_research_task_leases"
_MYSQL_VERSION = "9.4.0"
_DATABASE_URL_ENV = "ASSET_RESEARCH_MYSQL_SHARED_SCHEMA_URL"
_CONFIRM_ENV = "ASSET_RESEARCH_MYSQL_SHARED_SCHEMA_CONFIRM"
_TASK_RUNNER_DATABASE_URL_ENV = "ASSET_RESEARCH_MYSQL_TASK_RUNNER_DISPOSABLE_URL"
_TASK_RUNNER_CONFIRM_ENV = "ASSET_RESEARCH_MYSQL_TASK_RUNNER_DISPOSABLE_CONFIRM"


def _shared_mysql_url() -> URL:
    """Return an explicitly approved existing-schema connection without DDL."""
    database_url = os.getenv(_DATABASE_URL_ENV)
    if not database_url or os.getenv(_CONFIRM_ENV) != "yes":
        pytest.skip(
            f"set {_DATABASE_URL_ENV} and {_CONFIRM_ENV}=yes for the real MySQL contract"
        )
    parsed = make_url(database_url)
    if parsed.get_backend_name() != "mysql" or not parsed.database:
        pytest.skip("real MySQL contract requires a concrete mysql database URL")
    # Keep this as a URL object instead of serializing it back to text.  A
    # configured password may contain URL-reserved characters; converting a
    # parsed URL to text and parsing it again can otherwise change the secret.
    return parsed.set(drivername="mysql+pymysql")


def _disposable_task_runner_url() -> URL:
    """Require a separate explicitly disposable schema before mutating task fixtures."""
    database_url = os.getenv(_TASK_RUNNER_DATABASE_URL_ENV)
    if not database_url or os.getenv(_TASK_RUNNER_CONFIRM_ENV) != "yes":
        pytest.skip(
            "set "
            f"{_TASK_RUNNER_DATABASE_URL_ENV} and {_TASK_RUNNER_CONFIRM_ENV}=yes "
            "for the mutating MySQL task-runner contract"
        )
    parsed = make_url(database_url)
    database = parsed.database or ""
    if parsed.get_backend_name() != "mysql" or not database.startswith("codex_iter191_"):
        pytest.skip("task-runner contract requires a disposable codex_iter191_* MySQL schema")
    return parsed.set(drivername="mysql+aiomysql")


def _assert_rejected(
    connection, sql: str, params: Mapping[str, object], expected_message: str
) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(DBAPIError) as error:
        connection.execute(text(sql), params)
    assert expected_message in str(error.value)


@pytest.mark.asyncio
async def test_mysql_interactive_task_runner_claims_and_releases_a_durable_lease() -> None:
    """Exercise the real MySQL claim path only in a disposable CI/local schema."""
    engine = create_async_engine(_disposable_task_runner_url(), pool_pre_ping=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    fixture_prefix = f"mysql-task-{uuid4().hex[:12]}"
    user_id = str(uuid4())
    instrument_id = str(uuid4())
    task_id = str(uuid4())

    class _FinishingService:
        def __init__(self, db: AsyncSession) -> None:
            self.db = db

        async def run_claimed_task(self, *, task_id: str, lease_token: str) -> None:
            task = await self.db.get(AssetAnalysisTask, task_id)
            assert task is not None
            assert task.status == "RUNNING"
            assert task.lease_token == lease_token
            task.status = "SUCCEEDED"
            task.progress = 100
            task.completed_at = datetime.now(timezone.utc)

    try:
        async with session_maker() as db:
            db.add(
                User(
                    id=user_id,
                    username=fixture_prefix,
                    email=f"{fixture_prefix}@example.test",
                    hashed_password="hash",
                )
            )
            db.add(
                AssetInstrument(
                    id=instrument_id,
                    canonical_id=f"futures:TEST:{fixture_prefix}:CNY",
                    asset_type="futures",
                    identity_level="CONTRACT",
                    identity_json={"fixture": fixture_prefix},
                    metadata_version="mysql-task-runner-v1",
                    lifecycle_status="ACTIVE",
                    valid_from=datetime(2026, 8, 3, tzinfo=timezone.utc),
                )
            )
            await db.flush()
            db.add(
                AssetAnalysisTask(
                    id=task_id,
                    user_id=user_id,
                    owner_scope="USER",
                    instrument_id=instrument_id,
                    asset_type="futures",
                    canonical_id=f"futures:TEST:{fixture_prefix}:CNY",
                    identity_version="mysql-task-runner-v1",
                    request_json={"fixture": fixture_prefix},
                    position_context="UNKNOWN",
                    horizon_code="session-1d",
                    status="QUEUED",
                    progress=0,
                )
            )
            await db.commit()

        runner = AssetResearchTaskRunner(
            session_maker=session_maker,
            orchestrator_factory=_FinishingService,
            lease_seconds=60,
            max_batch=1,
            max_concurrency=1,
        )
        assert await runner.run_due() == 1

        async with session_maker() as db:
            task = await db.get(AssetAnalysisTask, task_id)
            assert task is not None
            assert task.status == "SUCCEEDED"
            assert task.attempt_count == 1
            assert task.lease_token is None
            assert task.lease_expires_at is None
            assert task.lease_heartbeat_at is None
    finally:
        async with session_maker() as db:
            await db.execute(delete(AssetAnalysisTask).where(AssetAnalysisTask.id == task_id))
            await db.execute(delete(AssetInstrument).where(AssetInstrument.id == instrument_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_mysql_interactive_task_runner_does_not_revive_a_cancelled_task() -> None:
    """The MySQL terminal compare-and-set must preserve a concurrent cancellation."""
    engine = create_async_engine(_disposable_task_runner_url(), pool_pre_ping=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    fixture_prefix = f"mysql-cancel-{uuid4().hex[:12]}"
    user_id = str(uuid4())
    instrument_id = str(uuid4())
    task_id = str(uuid4())
    started = asyncio.Event()
    release = asyncio.Event()

    class _LateFinishingService:
        def __init__(self, db: AsyncSession) -> None:
            self.db = db

        async def run_claimed_task(self, *, task_id: str, lease_token: str) -> None:
            task = await self.db.get(AssetAnalysisTask, task_id)
            assert task is not None
            assert task.status == "RUNNING"
            assert task.lease_token == lease_token
            started.set()
            await release.wait()
            task.status = "SUCCEEDED"
            task.progress = 100
            task.completed_at = datetime.now(timezone.utc)

    worker: asyncio.Task[int] | None = None
    try:
        async with session_maker() as db:
            db.add(
                User(
                    id=user_id,
                    username=fixture_prefix,
                    email=f"{fixture_prefix}@example.test",
                    hashed_password="hash",
                )
            )
            db.add(
                AssetInstrument(
                    id=instrument_id,
                    canonical_id=f"futures:TEST:{fixture_prefix}:CNY",
                    asset_type="futures",
                    identity_level="CONTRACT",
                    identity_json={"fixture": fixture_prefix},
                    metadata_version="mysql-task-runner-v1",
                    lifecycle_status="ACTIVE",
                    valid_from=datetime(2026, 8, 3, tzinfo=timezone.utc),
                )
            )
            await db.flush()
            db.add(
                AssetAnalysisTask(
                    id=task_id,
                    user_id=user_id,
                    owner_scope="USER",
                    instrument_id=instrument_id,
                    asset_type="futures",
                    canonical_id=f"futures:TEST:{fixture_prefix}:CNY",
                    identity_version="mysql-task-runner-v1",
                    request_json={"fixture": fixture_prefix},
                    position_context="UNKNOWN",
                    horizon_code="session-1d",
                    status="QUEUED",
                    progress=0,
                )
            )
            await db.commit()

        runner = AssetResearchTaskRunner(
            session_maker=session_maker,
            orchestrator_factory=_LateFinishingService,
            lease_seconds=60,
            max_batch=1,
            max_concurrency=1,
        )
        worker = asyncio.create_task(runner.run_due())
        await asyncio.wait_for(started.wait(), timeout=5)

        async with session_maker() as db:
            response = await AssetResearchOrchestrator(db).cancel_task(
                user_id=user_id,
                task_id=task_id,
            )
            assert response is not None
            assert response.status == "CANCELLED"
            await db.commit()

        release.set()
        assert await asyncio.wait_for(worker, timeout=5) == 1

        async with session_maker() as db:
            task = await db.get(AssetAnalysisTask, task_id)
            assert task is not None
            assert task.status == "CANCELLED"
            assert task.lease_token is None
            assert task.lease_expires_at is None
            assert task.lease_heartbeat_at is None
    finally:
        release.set()
        if worker is not None and not worker.done():
            await worker
        async with session_maker() as db:
            await db.execute(delete(AssetAnalysisTask).where(AssetAnalysisTask.id == task_id))
            await db.execute(delete(AssetInstrument).where(AssetInstrument.id == instrument_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
        await engine.dispose()


def test_mysql_asset_research_constraints_are_enforced_transactionally() -> None:
    """A non-SUPER account can verify run and option-context contracts safely."""
    engine: Engine = create_engine(_shared_mysql_url())
    fixture_prefix = f"mysql{uuid4().hex[:8]}"
    instrument_id = f"{fixture_prefix}-instrument"
    snapshot_id = f"{fixture_prefix}-snapshot"
    manifest_id = f"{fixture_prefix}-manifest"
    schedule_id = f"{fixture_prefix}-schedule"
    run_id = f"{fixture_prefix}-run"
    prediction_id = f"{fixture_prefix}-prediction"
    canonical_id = "futures:TEST:MYSQL2609:CNY"
    option_owner_id = f"{fixture_prefix}-option-owner"
    option_foreign_owner_id = f"{fixture_prefix}-option-foreign-owner"
    option_instrument_id = f"{fixture_prefix}-opt-inst"
    option_foreign_instrument_id = f"{fixture_prefix}-opt-foreign-inst"
    option_source_id = f"{fixture_prefix}-opt-source"
    option_foreign_context_id = f"{fixture_prefix}-opt-foreign-ctx"
    option_expired_context_id = f"{fixture_prefix}-opt-expired-ctx"
    option_valid_context_id = f"{fixture_prefix}-opt-valid-ctx"
    option_foreign_prediction_id = f"{fixture_prefix}-opt-foreign-pred"
    option_expired_prediction_id = f"{fixture_prefix}-opt-expired-pred"
    option_valid_prediction_id = f"{fixture_prefix}-opt-valid-pred"
    option_canonical_id = "option:TEST:MYSQL-C-100:CALL:2027-08-01:100:USD"
    option_foreign_canonical_id = "option:TEST:MYSQL-C-110:CALL:2027-08-01:110:USD"
    context_as_of_at = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0) - timedelta(
        hours=1
    )
    context_expired_at = context_as_of_at + timedelta(minutes=1)
    prediction_as_of_at = context_as_of_at + timedelta(hours=2)
    context_valid_expires_at = prediction_as_of_at + timedelta(days=1)

    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT VERSION()")).scalar_one() == _MYSQL_VERSION
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == _HEAD
            )
            run_columns = {
                str(column["name"])
                for column in inspect(engine).get_columns("asset_signal_runs")
            }
            assert {"prediction_id", "prediction_link_role"} <= run_columns
            task_metadata = {
                str(column["name"]): column
                for column in inspect(engine).get_columns("asset_analysis_tasks")
            }
            assert {
                "lease_token",
                "lease_expires_at",
                "lease_heartbeat_at",
                "attempt_count",
            } <= set(task_metadata)
            assert task_metadata["attempt_count"]["nullable"] is False
            task_checks = {
                str(check["name"])
                for check in inspect(engine).get_check_constraints("asset_analysis_tasks")
                if check.get("name")
            }
            assert {"ck_asset_task_lease_pair", "ck_asset_task_attempt_count"} <= task_checks
            task_indexes = {
                str(index["name"]): tuple(str(column) for column in index["column_names"])
                for index in inspect(engine).get_indexes("asset_analysis_tasks")
                if index.get("name")
            }
            assert task_indexes["ix_asset_task_runner_claim"] == (
                "status",
                "lease_expires_at",
                "created_at",
            )
            assert "asset_signal_run_predictions" not in inspect(engine).get_table_names()
            manifest_metadata = {
                str(column["name"]): column
                for column in inspect(engine).get_columns("asset_schedule_manifests")
            }
            manifest_columns = set(manifest_metadata)
            assert {
                "idempotency_key",
                "idempotency_request_hash",
                "retirement_reason_codes_json",
            } <= manifest_columns
            assert manifest_metadata["evidence_uri"]["nullable"] is False
            assert manifest_metadata["evidence_content_hash"]["nullable"] is False
            manifest_checks = {
                str(check["name"])
                for check in inspect(engine).get_check_constraints("asset_schedule_manifests")
                if check.get("name")
            }
            schedule_checks = {
                str(check["name"])
                for check in inspect(engine).get_check_constraints("asset_signal_schedules")
                if check.get("name")
            }
            assert "ck_asset_schedule_manifest_scope" in manifest_checks
            assert "ck_asset_schedule_manifest_owner" in schedule_checks
            run_checks = {
                str(check["name"])
                for check in inspect(engine).get_check_constraints("asset_signal_runs")
                if check.get("name")
            }
            run_foreign_keys = {
                str(foreign_key["name"])
                for foreign_key in inspect(engine).get_foreign_keys("asset_signal_runs")
                if foreign_key.get("name")
            }
            assert "ck_asset_run_prediction_terminal" in run_checks
            assert "fk_asset_signal_runs_prediction" in run_foreign_keys
            outcome_checks = {
                str(check["name"])
                for check in inspect(engine).get_check_constraints("asset_signal_outcomes")
                if check.get("name")
            }
            assert "ck_asset_outcome_maturity_reason" in outcome_checks
            prediction_columns = {
                str(column["name"])
                for column in inspect(engine).get_columns("asset_signal_predictions")
            }
            assert {
                "position_context_snapshot_as_of_at",
                "position_context_snapshot_available_at",
                "position_context_snapshot_expires_at",
            } <= prediction_columns
            context_unique_constraints = {
                str(constraint["name"])
                for constraint in inspect(engine).get_unique_constraints(
                    "asset_position_context_snapshots"
                )
                if constraint.get("name")
            }
            assert {
                "uq_asset_position_context_prediction_binding",
                "uq_asset_position_context_prediction_window",
            } <= context_unique_constraints
            prediction_checks = {
                str(check["name"])
                for check in inspect(engine).get_check_constraints("asset_signal_predictions")
                if check.get("name")
            }
            assert "ck_asset_option_long_context_window" in prediction_checks
            prediction_foreign_keys = {
                str(foreign_key["name"])
                for foreign_key in inspect(engine).get_foreign_keys("asset_signal_predictions")
                if foreign_key.get("name")
            }
            assert {
                "fk_asset_prediction_position_context_binding",
                "fk_asset_prediction_position_context_window",
            } <= prediction_foreign_keys
            trigger_count = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.TRIGGERS
                    WHERE TRIGGER_SCHEMA = DATABASE()
                      AND TRIGGER_NAME LIKE 'trg_asset_%'
                    """
                )
            ).scalar_one()
            assert trigger_count == 0

            # Metadata probes above autobegin a read transaction under
            # SQLAlchemy 2.0; end it before the rollback-only fixture scope.
            connection.rollback()
            transaction = connection.begin()
            try:
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_instruments (
                            id, canonical_id, asset_type, identity_level, identity_json,
                            metadata_version, lifecycle_status, valid_from, created_at
                        ) VALUES (
                            :id, :canonical_id, 'futures', 'CONTRACT', JSON_OBJECT(),
                            'fixture-v1', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {"id": instrument_id, "canonical_id": canonical_id},
                )
                _assert_rejected(
                    connection,
                    """
                    INSERT INTO asset_signal_schedules (
                        id, owner_scope, instrument_id, asset_type, canonical_id, identity_version,
                        horizon_code, horizon_spec_json, position_context, cron_expression, timezone,
                        cutoff_policy, cutoff_policy_version, misfire_policy, schedule_version, enabled,
                        created_at, updated_at
                    ) VALUES (
                        :id, 'ADMIN_EVAL', :instrument_id, 'futures', :canonical_id, 'fixture-v1',
                        'fixture-horizon', JSON_OBJECT(), 'UNKNOWN', '0 19 * * *', 'UTC',
                        'fixture-policy', 'fixture-v1', 'SKIP', 1, 0,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """,
                    {
                        "id": f"{fixture_prefix}-no-manifest",
                        "instrument_id": instrument_id,
                        "canonical_id": canonical_id,
                    },
                    "ck_asset_schedule_manifest_owner",
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_source_snapshots (
                            id, instrument_id, asset_type, canonical_id, identity_version, cutoff_at,
                            raw_schema_version, raw_fields_json, source_manifest_json, content_hash,
                            license_tags_json, created_at
                        ) VALUES (
                            :id, :instrument_id, 'futures', :canonical_id, 'fixture-v1', CURRENT_TIMESTAMP,
                            'fixture-v1', JSON_OBJECT(), JSON_OBJECT(), :content_hash,
                            JSON_ARRAY(), CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "id": snapshot_id,
                        "instrument_id": instrument_id,
                        "canonical_id": canonical_id,
                        "content_hash": "a" * 64,
                    },
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_schedule_manifests (
                            id, manifest_key, manifest_version, owner_scope, approval_reference,
                            evidence_uri, evidence_content_hash, content_hash, approved_by, approved_at,
                            status, retirement_reason_codes_json, created_at
                        ) VALUES (
                            :id, 'mysql-contract', 'fixture-v1', 'ADMIN_EVAL', 'TEST-ONLY',
                            'evidence://test/mysql-contract', :evidence_hash, :content_hash,
                            'fixture-admin', CURRENT_TIMESTAMP, 'ACTIVE', JSON_ARRAY(), CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "id": manifest_id,
                        "evidence_hash": "f" * 64,
                        "content_hash": "a" * 64,
                    },
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_signal_schedules (
                            id, owner_scope, approved_manifest_id, manifest_entry_key,
                            manifest_content_hash, instrument_id, asset_type, canonical_id, identity_version,
                            horizon_code, horizon_spec_json, position_context, cron_expression, timezone,
                            cutoff_policy, cutoff_policy_version, misfire_policy, schedule_version, enabled,
                            created_at, updated_at
                        ) VALUES (
                            :id, 'ADMIN_EVAL', :manifest_id, 'mysql-contract-entry', :manifest_content_hash,
                            :instrument_id, 'futures', :canonical_id, 'fixture-v1',
                            'fixture-horizon', JSON_OBJECT(), 'UNKNOWN', '0 19 * * *', 'UTC',
                            'fixture-policy', 'fixture-v1', 'SKIP', 1, 0,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "id": schedule_id,
                        "manifest_id": manifest_id,
                        "manifest_content_hash": "a" * 64,
                        "instrument_id": instrument_id,
                        "canonical_id": canonical_id,
                    },
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_signal_runs (
                            id, run_key, schedule_id, schedule_version, schedule_config_json,
                            cutoff_policy_version, owner_scope, run_type, asset_type, as_of_at, cutoff_at,
                            policy_version, status, counts_json, created_at
                        ) VALUES (
                            :id, :run_key, :schedule_id, 1, JSON_OBJECT(),
                            'fixture-v1', 'ADMIN_EVAL', 'MANUAL', 'futures', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                            'fixture-v1', 'RUNNING', JSON_OBJECT(), CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {"id": run_id, "run_key": "b" * 64, "schedule_id": schedule_id},
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_signal_predictions (
                            id, prediction_key, decision_input_hash, owner_scope, instrument_id, asset_type,
                            canonical_id, identity_version, as_of_at, horizon_code, horizon_spec_json,
                            position_context, candidate_decision_json, published_decision_json, actionability,
                            quality_status, quality_json, snapshot_id, head_spec_set_hash, feature_version,
                            policy_version, model_version, calibration_version, capability_version,
                            compliance_policy_version, cutoff_policy_version, cost_snapshot_json, created_at
                        ) VALUES (
                            :id, :prediction_key, :decision_input_hash, 'ADMIN_EVAL', :instrument_id, 'futures',
                            :canonical_id, 'fixture-v1', CURRENT_TIMESTAMP, 'fixture-horizon', JSON_OBJECT(),
                            'UNKNOWN', JSON_OBJECT(), JSON_OBJECT(), 'RESEARCH_ONLY', 'ELIGIBLE',
                            JSON_OBJECT(), :snapshot_id, :head_spec_set_hash, 'fixture-v1', 'fixture-v1',
                            'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1',
                            JSON_OBJECT(), CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "id": prediction_id,
                        "prediction_key": "c" * 64,
                        "decision_input_hash": "d" * 64,
                        "instrument_id": instrument_id,
                        "canonical_id": canonical_id,
                        "snapshot_id": snapshot_id,
                        "head_spec_set_hash": "e" * 64,
                    },
                )

                _assert_rejected(
                    connection,
                    """
                    INSERT INTO asset_signal_outcomes (
                        id, prediction_id, outcome_kind, head_spec_hash, horizon_code,
                        evaluator_version, status, maturity_reason, metrics_json, risk_json,
                        reason_codes_json
                    ) VALUES (
                        :id, :prediction_id, 'futures.contract_pnl', :head_spec_hash,
                        'fixture-horizon', 'fixture-v1', 'PENDING', 'MATURED',
                        JSON_OBJECT(), JSON_OBJECT(), JSON_ARRAY()
                    )
                    """,
                    {
                        "id": f"{fixture_prefix}-bad-maturity",
                        "prediction_id": prediction_id,
                        "head_spec_hash": "f" * 64,
                    },
                    "ck_asset_outcome_maturity_reason",
                )

                _assert_rejected(
                    connection,
                    "UPDATE asset_signal_runs SET status = 'SUCCEEDED' WHERE id = :run_id",
                    {"run_id": run_id},
                    "ck_asset_run_prediction_terminal",
                )
                connection.execute(
                    text(
                        """
                        UPDATE asset_signal_runs
                        SET prediction_id = :prediction_id,
                            prediction_link_role = 'CREATED',
                            status = 'SUCCEEDED'
                        WHERE id = :run_id
                        """
                    ),
                    {"run_id": run_id, "prediction_id": prediction_id},
                )
                _assert_rejected(
                    connection,
                    "UPDATE asset_signal_runs SET prediction_id = NULL WHERE id = :run_id",
                    {"run_id": run_id},
                    "ck_asset_run_prediction_terminal",
                )
                _assert_rejected(
                    connection,
                    "DELETE FROM asset_signal_predictions WHERE id = :prediction_id",
                    {"prediction_id": prediction_id},
                    "foreign key",
                )

                # The option contract is intentionally verified with raw SQL.
                # This proves that a caller bypassing the service cannot turn a
                # foreign/expired context into a SELL+CLOSE authorization.
                connection.execute(
                    text(
                        """
                        INSERT INTO users (id, username, email, hashed_password)
                        VALUES
                            (:owner_id, :owner_username, :owner_email, 'hash'),
                            (:foreign_owner_id, :foreign_username, :foreign_email, 'hash')
                        """
                    ),
                    {
                        "owner_id": option_owner_id,
                        "owner_username": f"{fixture_prefix}_opt_owner",
                        "owner_email": f"{fixture_prefix}-opt-owner@example.test",
                        "foreign_owner_id": option_foreign_owner_id,
                        "foreign_username": f"{fixture_prefix}_opt_foreign",
                        "foreign_email": f"{fixture_prefix}-opt-foreign@example.test",
                    },
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_instruments (
                            id, canonical_id, asset_type, identity_level, identity_json,
                            metadata_version, lifecycle_status, valid_from, created_at
                        ) VALUES
                            (:option_instrument_id, :option_canonical_id, 'option', 'CONTRACT',
                             JSON_OBJECT(), 'fixture-v1', 'ACTIVE', :context_as_of_at,
                             :context_as_of_at),
                            (:option_foreign_instrument_id, :option_foreign_canonical_id, 'option',
                             'CONTRACT', JSON_OBJECT(), 'fixture-v1', 'ACTIVE', :context_as_of_at,
                             :context_as_of_at)
                        """
                    ),
                    {
                        "option_instrument_id": option_instrument_id,
                        "option_canonical_id": option_canonical_id,
                        "option_foreign_instrument_id": option_foreign_instrument_id,
                        "option_foreign_canonical_id": option_foreign_canonical_id,
                        "context_as_of_at": context_as_of_at,
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
                            :id, :instrument_id, 'option', :canonical_id, 'fixture-v1',
                            :prediction_as_of_at, 'fixture-v1', JSON_OBJECT(), JSON_OBJECT(),
                            :content_hash, JSON_ARRAY(), :prediction_as_of_at
                        )
                        """
                    ),
                    {
                        "id": option_source_id,
                        "instrument_id": option_instrument_id,
                        "canonical_id": option_canonical_id,
                        "prediction_as_of_at": prediction_as_of_at,
                        "content_hash": "g" * 64,
                    },
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_position_context_snapshots (
                            id, owner_scope, user_id, instrument_id, asset_type, canonical_id,
                            identity_version, position_context, long_quantity, short_quantity,
                            as_of_at, available_at, expires_at, source_type, source_manifest_json,
                            content_hash, created_at
                        ) VALUES
                            (:foreign_context_id, 'USER', :foreign_owner_id,
                             :foreign_instrument_id, 'option', :foreign_canonical_id,
                             'fixture-v1', 'LONG', 1, 0, :context_as_of_at, :context_as_of_at,
                             :context_valid_expires_at, 'USER_DECLARED', JSON_OBJECT(),
                             :foreign_context_hash, :context_as_of_at),
                            (:expired_context_id, 'USER', :owner_id, :option_instrument_id,
                             'option', :option_canonical_id, 'fixture-v1', 'LONG', 1, 0,
                             :context_as_of_at, :context_as_of_at, :context_expired_at,
                             'USER_DECLARED', JSON_OBJECT(), :expired_context_hash,
                             :context_as_of_at),
                            (:valid_context_id, 'USER', :owner_id, :option_instrument_id,
                             'option', :option_canonical_id, 'fixture-v1', 'LONG', 1, 0,
                             :context_as_of_at, :context_as_of_at, :context_valid_expires_at,
                             'USER_DECLARED', JSON_OBJECT(), :valid_context_hash,
                             :context_as_of_at)
                        """
                    ),
                    {
                        "foreign_context_id": option_foreign_context_id,
                        "foreign_owner_id": option_foreign_owner_id,
                        "foreign_instrument_id": option_foreign_instrument_id,
                        "foreign_canonical_id": option_foreign_canonical_id,
                        "expired_context_id": option_expired_context_id,
                        "valid_context_id": option_valid_context_id,
                        "owner_id": option_owner_id,
                        "option_instrument_id": option_instrument_id,
                        "option_canonical_id": option_canonical_id,
                        "context_as_of_at": context_as_of_at,
                        "context_expired_at": context_expired_at,
                        "context_valid_expires_at": context_valid_expires_at,
                        "foreign_context_hash": "h" * 64,
                        "expired_context_hash": "i" * 64,
                        "valid_context_hash": "j" * 64,
                    },
                )
                _assert_rejected(
                    connection,
                    """
                    INSERT INTO asset_signal_predictions (
                        id, prediction_key, decision_input_hash, owner_scope, user_id, instrument_id,
                        asset_type, canonical_id, identity_version, as_of_at, horizon_code,
                        horizon_spec_json, position_context, position_context_snapshot_id,
                        position_context_snapshot_as_of_at,
                        position_context_snapshot_available_at,
                        position_context_snapshot_expires_at, candidate_decision_json,
                        published_decision_json, actionability, quality_status, quality_json,
                        snapshot_id, head_spec_set_hash, feature_version, policy_version, model_version,
                        calibration_version, capability_version, compliance_policy_version,
                        cutoff_policy_version, cost_snapshot_json, created_at
                    ) VALUES (
                        :id, :prediction_key, :decision_input_hash, 'USER', :owner_id,
                        :option_instrument_id, 'option', :option_canonical_id, 'fixture-v1',
                        :prediction_as_of_at, 'fixture-horizon', JSON_OBJECT(), 'LONG',
                        :foreign_context_id, :context_as_of_at, :context_as_of_at,
                        :context_valid_expires_at, JSON_OBJECT(), JSON_OBJECT(), 'RESEARCH_ONLY',
                        'ELIGIBLE', JSON_OBJECT(), :option_source_id, :head_spec_set_hash,
                        'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1',
                        'fixture-v1', 'fixture-v1', JSON_OBJECT(), :prediction_as_of_at
                    )
                    """,
                    {
                        "id": option_foreign_prediction_id,
                        "prediction_key": "k" * 64,
                        "decision_input_hash": "l" * 64,
                        "owner_id": option_owner_id,
                        "option_instrument_id": option_instrument_id,
                        "option_canonical_id": option_canonical_id,
                        "prediction_as_of_at": prediction_as_of_at,
                        "foreign_context_id": option_foreign_context_id,
                        "context_as_of_at": context_as_of_at,
                        "context_valid_expires_at": context_valid_expires_at,
                        "option_source_id": option_source_id,
                        "head_spec_set_hash": "m" * 64,
                    },
                    "foreign key",
                )
                _assert_rejected(
                    connection,
                    """
                    INSERT INTO asset_signal_predictions (
                        id, prediction_key, decision_input_hash, owner_scope, user_id, instrument_id,
                        asset_type, canonical_id, identity_version, as_of_at, horizon_code,
                        horizon_spec_json, position_context, position_context_snapshot_id,
                        position_context_snapshot_as_of_at,
                        position_context_snapshot_available_at,
                        position_context_snapshot_expires_at, candidate_decision_json,
                        published_decision_json, actionability, quality_status, quality_json,
                        snapshot_id, head_spec_set_hash, feature_version, policy_version, model_version,
                        calibration_version, capability_version, compliance_policy_version,
                        cutoff_policy_version, cost_snapshot_json, created_at
                    ) VALUES (
                        :id, :prediction_key, :decision_input_hash, 'USER', :owner_id,
                        :option_instrument_id, 'option', :option_canonical_id, 'fixture-v1',
                        :prediction_as_of_at, 'fixture-horizon', JSON_OBJECT(), 'LONG',
                        :expired_context_id, :context_as_of_at, :context_as_of_at,
                        :context_expired_at, JSON_OBJECT(), JSON_OBJECT(), 'RESEARCH_ONLY',
                        'ELIGIBLE', JSON_OBJECT(), :option_source_id, :head_spec_set_hash,
                        'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1',
                        'fixture-v1', 'fixture-v1', JSON_OBJECT(), :prediction_as_of_at
                    )
                    """,
                    {
                        "id": option_expired_prediction_id,
                        "prediction_key": "n" * 64,
                        "decision_input_hash": "o" * 64,
                        "owner_id": option_owner_id,
                        "option_instrument_id": option_instrument_id,
                        "option_canonical_id": option_canonical_id,
                        "prediction_as_of_at": prediction_as_of_at,
                        "expired_context_id": option_expired_context_id,
                        "context_as_of_at": context_as_of_at,
                        "context_expired_at": context_expired_at,
                        "option_source_id": option_source_id,
                        "head_spec_set_hash": "p" * 64,
                    },
                    "ck_asset_option_long_context_window",
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_signal_predictions (
                            id, prediction_key, decision_input_hash, owner_scope, user_id, instrument_id,
                            asset_type, canonical_id, identity_version, as_of_at, horizon_code,
                            horizon_spec_json, position_context, position_context_snapshot_id,
                            position_context_snapshot_as_of_at,
                            position_context_snapshot_available_at,
                            position_context_snapshot_expires_at, candidate_decision_json,
                            published_decision_json, actionability, quality_status, quality_json,
                            snapshot_id, head_spec_set_hash, feature_version, policy_version, model_version,
                            calibration_version, capability_version, compliance_policy_version,
                            cutoff_policy_version, cost_snapshot_json, created_at
                        ) VALUES (
                            :id, :prediction_key, :decision_input_hash, 'USER', :owner_id,
                            :option_instrument_id, 'option', :option_canonical_id, 'fixture-v1',
                            :prediction_as_of_at, 'fixture-horizon', JSON_OBJECT(), 'LONG',
                            :valid_context_id, :context_as_of_at, :context_as_of_at,
                            :context_valid_expires_at, JSON_OBJECT(), JSON_OBJECT(), 'RESEARCH_ONLY',
                            'ELIGIBLE', JSON_OBJECT(), :option_source_id, :head_spec_set_hash,
                            'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1', 'fixture-v1',
                            'fixture-v1', 'fixture-v1', JSON_OBJECT(), :prediction_as_of_at
                        )
                        """
                    ),
                    {
                        "id": option_valid_prediction_id,
                        "prediction_key": "q" * 64,
                        "decision_input_hash": "r" * 64,
                        "owner_id": option_owner_id,
                        "option_instrument_id": option_instrument_id,
                        "option_canonical_id": option_canonical_id,
                        "prediction_as_of_at": prediction_as_of_at,
                        "valid_context_id": option_valid_context_id,
                        "context_as_of_at": context_as_of_at,
                        "context_valid_expires_at": context_valid_expires_at,
                        "option_source_id": option_source_id,
                        "head_spec_set_hash": "s" * 64,
                    },
                )
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
