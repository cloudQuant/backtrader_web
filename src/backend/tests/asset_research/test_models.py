"""Schema-level contracts for Iteration 191 persistence."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.db.database import Base
from app.models.asset_research import ASSET_RESEARCH_TABLES
from app.schemas.asset_research import OutcomeEvaluation


def test_all_asset_research_tables_have_lifecycle_columns() -> None:
    """Every persisted immutable/auditable fact participates in retention policy."""
    expected_tables = {
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

    assert ASSET_RESEARCH_TABLES == expected_tables
    assert expected_tables.issubset(Base.metadata.tables)
    for table_name in expected_tables:
        columns = set(Base.metadata.tables[table_name].c.keys())
        assert {"retention_class", "retention_expires_at", "legal_hold", "tombstoned_at"}.issubset(
            columns
        )


def test_prediction_and_run_relation_are_idempotent_audit_facts() -> None:
    """A successful run owns one direct immutable prediction relation."""
    prediction = Base.metadata.tables["asset_signal_predictions"]
    run = Base.metadata.tables["asset_signal_runs"]

    assert any(
        set(constraint.columns.keys()) == {"prediction_key"}
        for constraint in prediction.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )
    assert {"prediction_id", "prediction_link_role"} <= set(run.c.keys())
    assert any(
        constraint.name == "ck_asset_run_prediction_terminal"
        for constraint in run.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    )
    assert any(
        foreign_key.parent.name == "prediction_id"
        and foreign_key.column.table.name == "asset_signal_predictions"
        for foreign_key in run.foreign_keys
    )


def test_outcome_maturity_reason_uses_the_architecture_owned_enum() -> None:
    """Maturity causes are not ad-hoc outcome status strings."""
    payload = {
        "outcome_kind": "futures.contract_pnl",
        "head_spec_hash": "a" * 64,
        "horizon_code": "standard",
        "evaluator_version": "outcome-v1",
        "status": "SCORED",
        "maturity_at": datetime(2026, 8, 2, tzinfo=timezone.utc),
    }

    assert OutcomeEvaluation(maturity_reason="HORIZON_REACHED", **payload).maturity_reason == (
        "HORIZON_REACHED"
    )
    assert OutcomeEvaluation(maturity_reason="EXERCISE", **payload).maturity_reason == "EXERCISE"
    with pytest.raises(ValidationError, match="maturity_reason"):
        OutcomeEvaluation(maturity_reason="MATURED", **payload)


def test_outcome_table_enforces_the_same_maturity_reason_enum() -> None:
    """Direct SQL cannot bypass the API's OutcomeEvaluation contract."""
    outcome = Base.metadata.tables["asset_signal_outcomes"]

    assert any(
        constraint.name == "ck_asset_outcome_maturity_reason"
        for constraint in outcome.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    )
