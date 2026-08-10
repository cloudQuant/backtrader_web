"""Create the expandable, non-stock multi-asset research foundation.

Revision ID: 20260802_asset_research_foundation
Revises: 20260801_stock_signal_predictions
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260802_asset_research_foundation"
down_revision = "20260801_stock_signal_predictions"
branch_labels = None
depends_on = None

_OWNER_SCOPE_CHECK = (
    "(owner_scope = 'USER' AND user_id IS NOT NULL) OR "
    "(owner_scope IN ('PUBLIC_SHADOW', 'ADMIN_EVAL') AND user_id IS NULL)"
)
_ASSET_TYPE_CHECK = "asset_type IN ('stock', 'bond', 'fund', 'futures', 'option', 'fx', 'crypto')"
def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


class _SchemaAwareOperations:
    """Keep upgrades compatible with historical ORM ``create_all`` databases."""

    def __init__(self, operations: Any) -> None:
        self._operations = operations

    def __getattr__(self, name: str) -> Any:
        return getattr(self._operations, name)

    def create_table(self, table_name: str, *columns: Any, **kwargs: Any) -> Any:
        if _table_exists(table_name):
            return None
        return self._operations.create_table(table_name, *columns, **kwargs)

    def create_index(self, index_name: str, table_name: str, columns: list[str], **kwargs: Any) -> Any:
        if _index_exists(table_name, index_name):
            return None
        return self._operations.create_index(index_name, table_name, columns, **kwargs)


def _retention_columns() -> list[sa.Column[Any]]:
    """Columns shared by every table in this bounded context."""
    return [
        sa.Column("retention_class", sa.String(length=32), nullable=False, server_default="research-v1"),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tombstoned_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    global op
    op = _SchemaAwareOperations(op)

    op.create_table(
        "asset_instruments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("canonical_id", sa.String(length=512), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("identity_level", sa.String(length=16), nullable=False),
        sa.Column("venue", sa.String(length=128), nullable=True),
        sa.Column("currency", sa.String(length=32), nullable=True),
        sa.Column("product_type", sa.String(length=64), nullable=True),
        sa.Column("identity_json", sa.JSON(), nullable=False),
        sa.Column("metadata_version", sa.String(length=64), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *_retention_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_id", "metadata_version", name="uq_asset_instrument_version"),
    )
    op.create_index(
        "ix_asset_instruments_type_canonical", "asset_instruments", ["asset_type", "canonical_id"]
    )

    op.create_table(
        "asset_data_source_registry",
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("asset_types", sa.JSON(), nullable=False),
        sa.Column("jurisdictions", sa.JSON(), nullable=False),
        sa.Column("license_status", sa.String(length=32), nullable=False),
        sa.Column("allowed_uses", sa.JSON(), nullable=False),
        sa.Column("attribution_text", sa.Text(), nullable=True),
        sa.Column("redistribution_policy", sa.String(length=64), nullable=False),
        sa.Column("derived_data_policy", sa.String(length=64), nullable=False),
        sa.Column("retention_policy", sa.String(length=64), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("freshness_sla", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *_retention_columns(),
        sa.PrimaryKeyConstraint("source_id"),
    )

    op.create_table(
        "asset_position_context_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_scope", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("canonical_id", sa.String(length=512), nullable=False),
        sa.Column("identity_version", sa.String(length=64), nullable=False),
        sa.Column("position_context", sa.String(length=16), nullable=False),
        sa.Column("long_quantity", sa.Numeric(precision=30, scale=10), nullable=False),
        sa.Column("short_quantity", sa.Numeric(precision=30, scale=10), nullable=False),
        sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_manifest_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("idempotency_request_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *_retention_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["instrument_id"], ["asset_instruments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            _OWNER_SCOPE_CHECK,
            name="ck_asset_position_context_owner",
        ),
        sa.CheckConstraint(
            "position_context IN ('FLAT', 'LONG', 'SHORT', 'UNKNOWN')",
            name="ck_asset_position_context_value",
        ),
        sa.CheckConstraint(
            "(position_context IN ('FLAT', 'UNKNOWN') AND long_quantity = 0 AND short_quantity = 0) "
            "OR (position_context = 'LONG' AND long_quantity > 0 AND short_quantity = 0) "
            "OR (position_context = 'SHORT' AND short_quantity > 0 AND long_quantity = 0)",
            name="ck_asset_position_context_quantities",
        ),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_asset_position_context_user_idempotency",
        ),
    )
    op.create_index(
        "ix_asset_position_context_owner_identity_asof",
        "asset_position_context_snapshots",
        ["owner_scope", "user_id", "canonical_id", "as_of_at"],
    )
    op.create_index(
        "ix_asset_position_context_expires_at", "asset_position_context_snapshots", ["expires_at"]
    )

    op.create_table(
        "asset_source_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("canonical_id", sa.String(length=512), nullable=False),
        sa.Column("identity_version", sa.String(length=64), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_schema_version", sa.String(length=64), nullable=False),
        sa.Column("raw_fields_json", sa.JSON(), nullable=False),
        sa.Column("raw_payload_uri", sa.String(length=2048), nullable=True),
        sa.Column("source_manifest_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("license_tags_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *_retention_columns(),
        sa.ForeignKeyConstraint(["instrument_id"], ["asset_instruments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_asset_source_snapshot_identity_cutoff",
        "asset_source_snapshots",
        ["canonical_id", "cutoff_at"],
    )
    op.create_index("ix_asset_source_snapshots_content_hash", "asset_source_snapshots", ["content_hash"])

    op.create_table(
        "asset_analysis_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("owner_scope", sa.String(length=32), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("canonical_id", sa.String(length=512), nullable=False),
        sa.Column("identity_version", sa.String(length=64), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("position_context", sa.String(length=16), nullable=False),
        sa.Column("position_context_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("horizon_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("retry_of_task_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("idempotency_request_hash", sa.String(length=64), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_retention_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["instrument_id"], ["asset_instruments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["position_context_snapshot_id"],
            ["asset_position_context_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["retry_of_task_id"], ["asset_analysis_tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_asset_task_user_idempotency"),
        sa.CheckConstraint("owner_scope = 'USER'", name="ck_asset_task_owner"),
        sa.CheckConstraint(_ASSET_TYPE_CHECK, name="ck_asset_task_asset_type"),
        sa.CheckConstraint(
            "position_context IN ('FLAT', 'LONG', 'SHORT', 'UNKNOWN')",
            name="ck_asset_task_position_context",
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_asset_task_status",
        ),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_asset_task_progress"),
    )
    op.create_index(
        "ix_asset_task_user_status_created", "asset_analysis_tasks", ["user_id", "status", "created_at"]
    )
    op.create_index("ix_asset_analysis_tasks_trace_id", "asset_analysis_tasks", ["trace_id"])

    op.create_table(
        "asset_signal_schedules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_scope", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("canonical_id", sa.String(length=512), nullable=False),
        sa.Column("identity_version", sa.String(length=64), nullable=False),
        sa.Column("horizon_code", sa.String(length=64), nullable=False),
        sa.Column("horizon_spec_json", sa.JSON(), nullable=False),
        sa.Column("position_context", sa.String(length=16), nullable=False),
        sa.Column("position_context_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("cron_expression", sa.String(length=128), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("cutoff_policy", sa.String(length=128), nullable=False),
        sa.Column("cutoff_policy_version", sa.String(length=64), nullable=False),
        sa.Column("misfire_policy", sa.String(length=32), nullable=False),
        sa.Column("schedule_version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("idempotency_request_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *_retention_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["instrument_id"], ["asset_instruments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["position_context_snapshot_id"],
            ["asset_position_context_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_asset_schedule_user_idempotency"),
        sa.CheckConstraint(_OWNER_SCOPE_CHECK, name="ck_asset_schedule_owner"),
        sa.CheckConstraint(_ASSET_TYPE_CHECK, name="ck_asset_schedule_asset_type"),
        sa.CheckConstraint(
            "position_context = 'UNKNOWN' AND position_context_snapshot_id IS NULL",
            name="ck_asset_schedule_no_position_context",
        ),
        sa.CheckConstraint("schedule_version >= 1", name="ck_asset_schedule_version"),
        sa.CheckConstraint(
            "misfire_policy IN ('SKIP', 'RUN_ONCE', 'BACKFILL')",
            name="ck_asset_schedule_misfire_policy",
        ),
    )
    op.create_index("ix_asset_schedule_enabled_next_run", "asset_signal_schedules", ["enabled", "next_run_at"])

    op.create_table(
        "asset_signal_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_key", sa.String(length=64), nullable=False),
        sa.Column("schedule_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("schedule_version", sa.Integer(), nullable=True),
        sa.Column("schedule_config_json", sa.JSON(), nullable=True),
        sa.Column("cutoff_policy_version", sa.String(length=64), nullable=False),
        sa.Column("owner_scope", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("counts_json", sa.JSON(), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_retention_columns(),
        sa.ForeignKeyConstraint(["schedule_id"], ["asset_signal_schedules.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["asset_analysis_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key", name="uq_asset_signal_runs_run_key"),
        sa.CheckConstraint(_OWNER_SCOPE_CHECK, name="ck_asset_run_owner"),
        sa.CheckConstraint(_ASSET_TYPE_CHECK, name="ck_asset_run_asset_type"),
        sa.CheckConstraint(
            "(task_id IS NOT NULL AND schedule_id IS NULL AND schedule_version IS NULL "
            "AND schedule_config_json IS NULL) OR "
            "(task_id IS NULL AND schedule_id IS NOT NULL AND schedule_version IS NOT NULL "
            "AND schedule_config_json IS NOT NULL)",
            name="ck_asset_run_exactly_one_source",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_asset_run_status",
        ),
    )
    op.create_index(
        "ix_asset_run_owner_status_asof", "asset_signal_runs", ["owner_scope", "user_id", "status", "as_of_at"]
    )
    op.create_index(
        "ix_asset_run_schedule_status_asof", "asset_signal_runs", ["schedule_id", "status", "as_of_at"]
    )
    op.create_index("ix_asset_signal_runs_trace_id", "asset_signal_runs", ["trace_id"])

    op.create_table(
        "asset_signal_predictions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("prediction_key", sa.String(length=64), nullable=False),
        sa.Column("decision_input_hash", sa.String(length=64), nullable=False),
        sa.Column("owner_scope", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("canonical_id", sa.String(length=512), nullable=False),
        sa.Column("identity_version", sa.String(length=64), nullable=False),
        sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_code", sa.String(length=64), nullable=False),
        sa.Column("horizon_spec_json", sa.JSON(), nullable=False),
        sa.Column("position_context", sa.String(length=16), nullable=False),
        sa.Column("position_context_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("candidate_decision_json", sa.JSON(), nullable=False),
        sa.Column("published_decision_json", sa.JSON(), nullable=False),
        sa.Column("actionability", sa.String(length=32), nullable=False),
        sa.Column("quality_status", sa.String(length=16), nullable=False),
        sa.Column("quality_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("mapped_contract_id", sa.String(length=36), nullable=True),
        sa.Column("head_spec_set_hash", sa.String(length=64), nullable=False),
        sa.Column("feature_version", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("calibration_version", sa.String(length=64), nullable=False),
        sa.Column("capability_version", sa.String(length=64), nullable=False),
        sa.Column("compliance_policy_version", sa.String(length=64), nullable=False),
        sa.Column("cutoff_policy_version", sa.String(length=64), nullable=False),
        sa.Column("cost_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *_retention_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["instrument_id"], ["asset_instruments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["position_context_snapshot_id"],
            ["asset_position_context_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["snapshot_id"], ["asset_source_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["mapped_contract_id"], ["asset_instruments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prediction_key", name="uq_asset_signal_predictions_prediction_key"),
        sa.CheckConstraint(_OWNER_SCOPE_CHECK, name="ck_asset_prediction_owner"),
        sa.CheckConstraint(_ASSET_TYPE_CHECK, name="ck_asset_prediction_asset_type"),
        sa.CheckConstraint(
            "position_context IN ('FLAT', 'LONG', 'SHORT', 'UNKNOWN')",
            name="ck_asset_prediction_position_context",
        ),
        sa.CheckConstraint(
            "quality_status IN ('ELIGIBLE', 'DEGRADED', 'REJECTED')",
            name="ck_asset_prediction_quality_status",
        ),
        sa.CheckConstraint(
            "actionability IN ('ACTIONABLE', 'RESEARCH_ONLY', 'INSUFFICIENT_DATA', "
            "'REGION_RESTRICTED')",
            name="ck_asset_prediction_actionability",
        ),
        sa.CheckConstraint(
            "asset_type != 'option' OR position_context != 'LONG' "
            "OR position_context_snapshot_id IS NOT NULL",
            name="ck_asset_option_long_context_snapshot",
        ),
    )
    op.create_index("ix_asset_signal_predictions_decision_input_hash", "asset_signal_predictions", ["decision_input_hash"])
    op.create_index("ix_asset_prediction_identity_asof", "asset_signal_predictions", ["asset_type", "canonical_id", "as_of_at"])
    op.create_index("ix_asset_prediction_owner_asof", "asset_signal_predictions", ["owner_scope", "user_id", "as_of_at"])
    op.create_index("ix_asset_prediction_owner_identity_asof", "asset_signal_predictions", ["owner_scope", "canonical_id", "as_of_at"])
    op.create_index("ix_asset_prediction_actionability_quality_asof", "asset_signal_predictions", ["actionability", "quality_status", "as_of_at"])
    op.create_index("ix_asset_prediction_versions", "asset_signal_predictions", ["model_version", "policy_version", "horizon_code"])

    op.create_table(
        "asset_signal_run_predictions",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("prediction_id", sa.String(length=36), nullable=False),
        sa.Column("link_role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *_retention_columns(),
        sa.ForeignKeyConstraint(["run_id"], ["asset_signal_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["prediction_id"], ["asset_signal_predictions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("run_id"),
        sa.CheckConstraint("link_role IN ('CREATED', 'REUSED')", name="ck_asset_run_prediction_role"),
    )
    op.create_index(
        "ix_asset_run_prediction_prediction_created",
        "asset_signal_run_predictions",
        ["prediction_id", "created_at"],
    )

    op.create_table(
        "asset_signal_outcomes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("prediction_id", sa.String(length=36), nullable=False),
        sa.Column("outcome_kind", sa.String(length=128), nullable=False),
        sa.Column("head_spec_hash", sa.String(length=64), nullable=False),
        sa.Column("horizon_code", sa.String(length=64), nullable=False),
        sa.Column("evaluator_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("maturity_reason", sa.String(length=32), nullable=True),
        sa.Column("maturity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entry_price", sa.Numeric(precision=30, scale=10), nullable=True),
        sa.Column("entry_price_basis", sa.String(length=64), nullable=True),
        sa.Column("exit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_price", sa.Numeric(precision=30, scale=10), nullable=True),
        sa.Column("exit_price_basis", sa.String(length=64), nullable=True),
        sa.Column("currency", sa.String(length=32), nullable=True),
        sa.Column("gross_return", sa.Numeric(precision=30, scale=10), nullable=True),
        sa.Column("net_return", sa.Numeric(precision=30, scale=10), nullable=True),
        sa.Column("total_cost", sa.Numeric(precision=30, scale=10), nullable=True),
        sa.Column("benchmark_return", sa.Numeric(precision=30, scale=10), nullable=True),
        sa.Column("success_label", sa.Boolean(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("risk_json", sa.JSON(), nullable=False),
        sa.Column("reason_codes_json", sa.JSON(), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
        *_retention_columns(),
        sa.ForeignKeyConstraint(["prediction_id"], ["asset_signal_predictions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "prediction_id", "horizon_code", "outcome_kind", "evaluator_version", name="uq_asset_outcome_evaluator"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PARTIAL', 'SCORED', 'UNSCORABLE')",
            name="ck_asset_outcome_status",
        ),
    )
    op.create_index("ix_asset_outcome_status_maturity", "asset_signal_outcomes", ["status", "maturity_at"])
    op.create_index("ix_asset_outcome_head_status_scored", "asset_signal_outcomes", ["outcome_kind", "head_spec_hash", "status", "scored_at"])
    op.create_index("ix_asset_outcome_prediction_horizon", "asset_signal_outcomes", ["prediction_id", "horizon_code"])

    op.create_table(
        "asset_analysis_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("prediction_id", sa.String(length=36), nullable=True),
        sa.Column("report_version", sa.String(length=64), nullable=False),
        sa.Column("sections_json", sa.JSON(), nullable=False),
        sa.Column("rendered_markdown", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *_retention_columns(),
        sa.ForeignKeyConstraint(["task_id"], ["asset_analysis_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["prediction_id"], ["asset_signal_predictions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "report_version", name="uq_asset_report_task_version"),
    )
    op.create_index("ix_asset_analysis_reports_task_id", "asset_analysis_reports", ["task_id"])
    op.create_index("ix_asset_analysis_reports_prediction_id", "asset_analysis_reports", ["prediction_id"])

    op.create_table(
        "asset_analysis_exports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("storage_uri", sa.String(length=2048), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("requested_by", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("idempotency_request_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_retention_columns(),
        sa.ForeignKeyConstraint(["report_id"], ["asset_analysis_reports.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("requested_by", "idempotency_key", name="uq_asset_export_user_idempotency"),
    )
    op.create_index("ix_asset_analysis_exports_report_id", "asset_analysis_exports", ["report_id"])

    op.create_table(
        "asset_report_publications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_ref", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("external_ref", sa.String(length=512), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("requested_by", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("idempotency_request_hash", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_retention_columns(),
        sa.ForeignKeyConstraint(["report_id"], ["asset_analysis_reports.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "requested_by",
            "idempotency_key",
            name="uq_asset_publication_user_idempotency",
        ),
    )
    op.create_index("ix_asset_report_publications_report_id", "asset_report_publications", ["report_id"])

    op.create_table(
        "asset_model_registry",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("promotion_scope_key", sa.String(length=64), nullable=False),
        sa.Column("promotion_scope_type", sa.String(length=32), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("instrument_class", sa.String(length=128), nullable=False),
        sa.Column("canonical_id_scope", sa.String(length=512), nullable=True),
        sa.Column("venue_scope", sa.String(length=128), nullable=True),
        sa.Column("product_type_scope", sa.String(length=64), nullable=True),
        sa.Column("scope_parameters_json", sa.JSON(), nullable=False),
        sa.Column("signal_head", sa.String(length=128), nullable=False),
        sa.Column("horizon_code", sa.String(length=64), nullable=False),
        sa.Column("head_spec_hash", sa.String(length=64), nullable=False),
        sa.Column("target_spec_version", sa.String(length=64), nullable=False),
        sa.Column("scoreability_rule_version", sa.String(length=64), nullable=False),
        sa.Column("baseline_version", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("probability_artifact_hash", sa.String(length=64), nullable=False),
        sa.Column("calibration_version", sa.String(length=64), nullable=False),
        sa.Column("calibration_artifact_hash", sa.String(length=64), nullable=False),
        sa.Column("training_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("approval_set_json", sa.JSON(), nullable=False),
        sa.Column("evidence_uri", sa.String(length=2048), nullable=True),
        sa.Column("evidence_content_hash", sa.String(length=64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *_retention_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "promotion_scope_key", "signal_head", "horizon_code", "head_spec_hash", "policy_version", "model_version", "calibration_version", name="uq_asset_model_registry_scope_version"
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'SHADOW', 'PROMOTED', 'SUSPENDED', 'RETIRED')",
            name="ck_asset_model_registry_status",
        ),
    )
    op.create_index(
        "ix_asset_model_registry_scope_status",
        "asset_model_registry",
        ["asset_type", "instrument_class", "signal_head", "horizon_code", "status"],
    )

    op.create_table(
        "asset_model_status_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("model_registry_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=False),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("reason_codes_json", sa.JSON(), nullable=False),
        sa.Column("metrics_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("evidence_uri", sa.String(length=2048), nullable=True),
        sa.Column("evidence_content_hash", sa.String(length=64), nullable=True),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *_retention_columns(),
        sa.ForeignKeyConstraint(["model_registry_id"], ["asset_model_registry.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_asset_model_status_events_registry_id", "asset_model_status_events", ["model_registry_id"])


def downgrade() -> None:
    for table_name in (
        "asset_model_status_events",
        "asset_model_registry",
        "asset_report_publications",
        "asset_analysis_exports",
        "asset_analysis_reports",
        "asset_signal_outcomes",
        "asset_signal_run_predictions",
        "asset_signal_predictions",
        "asset_signal_runs",
        "asset_signal_schedules",
        "asset_analysis_tasks",
        "asset_source_snapshots",
        "asset_position_context_snapshots",
        "asset_data_source_registry",
        "asset_instruments",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
