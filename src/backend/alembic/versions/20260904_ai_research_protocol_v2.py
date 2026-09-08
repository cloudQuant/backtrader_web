"""Add the authoritative protocol-v2 trusted research aggregates.

Revision ID: 20260904_ai_research_protocol_v2
Revises: 20260811_asset_research_task_leases

The legacy AI-research schema remains untouched and read-compatible.  These
tables are an expand-only authority for explicitly routed protocol-v2 runs;
the migration neither backfills historical OOS results nor converts them into
sealed evidence.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260904_ai_research_protocol_v2"
down_revision = "20260811_asset_research_task_leases"
branch_labels = None
depends_on = None


def _id() -> sa.Column:
    return sa.Column("id", sa.String(length=36), nullable=False)


def _timestamp(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    """Create protocol-v2 tables without altering legacy research records."""

    op.create_table(
        "ai_research_capability_profiles",
        _id(),
        sa.Column("profile_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("topology", sa.String(length=128), nullable=False),
        sa.Column("actor_mode", sa.String(length=32), nullable=False),
        sa.Column("db_engine", sa.String(length=64), nullable=True),
        sa.Column("service_identities", sa.JSON(), nullable=False),
        sa.Column("queue_capabilities", sa.JSON(), nullable=False),
        sa.Column("storage_boundaries", sa.JSON(), nullable=False),
        sa.Column("network_capabilities", sa.JSON(), nullable=False),
        sa.Column("sandbox_capabilities", sa.JSON(), nullable=False),
        sa.Column("approval_capabilities", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        _timestamp("verified_at"),
        _timestamp("expires_at"),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "version", name="uq_ai_research_capability_profile_version"),
    )
    op.create_index(
        "ix_ai_research_capability_profile_expiry",
        "ai_research_capability_profiles",
        ["profile_id", "expires_at"],
    )

    op.create_table(
        "ai_research_hypothesis_versions",
        _id(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("hypothesis_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column(
            "parent_version_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_hypothesis_versions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("canonical_payload", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "source_mandate_id",
            sa.String(length=36),
            sa.ForeignKey("investment_mandates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "confirmed_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        _timestamp("confirmed_at", nullable=True),
        _timestamp("created_at"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'CONFIRMED', 'SUPERSEDED')",
            name="ck_ai_research_hypothesis_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "hypothesis_id", "version_no", name="uq_ai_research_hypothesis_version"),
    )
    op.create_index("ix_ai_research_hypothesis_owner_status", "ai_research_hypothesis_versions", ["user_id", "status", "created_at"])
    op.create_index("ix_ai_research_hypothesis_versions_hypothesis_id", "ai_research_hypothesis_versions", ["hypothesis_id"])
    op.create_index("ix_ai_research_hypothesis_versions_workspace_id", "ai_research_hypothesis_versions", ["workspace_id"])
    op.create_index("ix_ai_research_hypothesis_versions_content_hash", "ai_research_hypothesis_versions", ["content_hash"])

    op.create_table(
        "ai_research_experiment_epochs",
        _id(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "hypothesis_version_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_hypothesis_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("family_hash", sa.String(length=64), nullable=False),
        sa.Column("search_budget", sa.JSON(), nullable=False),
        sa.Column("dataset_policy_version", sa.String(length=128), nullable=False),
        sa.Column("holdout_budget", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'OPEN'")),
        sa.Column("selected_candidate_id", sa.String(length=36), nullable=True),
        sa.Column(
            "parent_epoch_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        _timestamp("opened_at"),
        _timestamp("disclosed_at", nullable=True),
        _timestamp("closed_at", nullable=True),
        sa.CheckConstraint("status IN ('OPEN', 'SELECTED', 'DISCLOSED', 'CLOSED')", name="ck_ai_research_epoch_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("selected_candidate_id", name="uq_ai_research_epoch_selected_candidate"),
    )
    op.create_index("ix_ai_research_epoch_owner_status", "ai_research_experiment_epochs", ["user_id", "status", "opened_at"])
    op.create_index("ix_ai_research_epoch_family", "ai_research_experiment_epochs", ["user_id", "family_hash"])

    op.create_table(
        "ai_research_dataset_snapshots",
        _id(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("dataset_policy_version", sa.String(length=128), nullable=False),
        sa.Column("partition_kind", sa.String(length=32), nullable=False),
        sa.Column("instrument_manifest", sa.JSON(), nullable=False),
        sa.Column("split_manifest", sa.JSON(), nullable=False),
        sa.Column("source_manifest", sa.JSON(), nullable=False),
        sa.Column("execution_policy", sa.JSON(), nullable=False),
        _timestamp("point_in_time_cutoff"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=2048), nullable=True),
        sa.Column("license_tags", sa.JSON(), nullable=False),
        _timestamp("created_at"),
        sa.CheckConstraint(
            "partition_kind IN ('DISCOVERY', 'ITERATION_VALIDATION', 'SEALED_HOLDOUT', 'FORWARD_OBSERVATION')",
            name="ck_ai_research_dataset_partition",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_research_dataset_owner_partition", "ai_research_dataset_snapshots", ["user_id", "partition_kind", "created_at"])
    op.create_index("ix_ai_research_dataset_content_hash", "ai_research_dataset_snapshots", ["content_hash"])

    op.create_table(
        "ai_research_runs",
        _id(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column(
            "hypothesis_version_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_hypothesis_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "dataset_snapshot_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "experiment_epoch_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("protocol_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stage_cursor", sa.String(length=64), nullable=False),
        sa.Column("promotion_policy_version", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("capability_profile_id", sa.String(length=128), nullable=False),
        sa.Column("capability_profile_version", sa.String(length=128), nullable=False),
        sa.Column("capability_evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        _timestamp("created_at"),
        _timestamp("started_at", nullable=True),
        _timestamp("completed_at", nullable=True),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT')",
            name="ck_ai_research_run_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_research_run_owner_status", "ai_research_runs", ["user_id", "status", "created_at"])
    op.create_index("ix_ai_research_runs_workspace_id", "ai_research_runs", ["workspace_id"])
    op.create_index("ix_ai_research_runs_trace_id", "ai_research_runs", ["trace_id"])

    op.create_table(
        "ai_research_tasks",
        _id(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stage_cursor", sa.String(length=64), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("idempotency_request_hash", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("retry_of_task_id", sa.String(length=36), sa.ForeignKey("ai_research_tasks.id", ondelete="RESTRICT"), nullable=True),
        _timestamp("cancel_requested_at", nullable=True),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        _timestamp("lease_expires_at", nullable=True),
        _timestamp("lease_heartbeat_at", nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        _timestamp("created_at"),
        _timestamp("started_at", nullable=True),
        _timestamp("completed_at", nullable=True),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT')",
            name="ck_ai_research_task_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_ai_research_task_attempt_count"),
        sa.CheckConstraint(
            "(lease_token IS NULL AND lease_expires_at IS NULL AND lease_heartbeat_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND lease_heartbeat_at IS NOT NULL)",
            name="ck_ai_research_task_lease_pair",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_ai_research_task_idempotency"),
    )
    op.create_index("ix_ai_research_tasks_run_id", "ai_research_tasks", ["run_id"])
    op.create_index("ix_ai_research_task_owner_status", "ai_research_tasks", ["user_id", "status", "created_at"])
    op.create_index("ix_ai_research_task_claim", "ai_research_tasks", ["status", "lease_expires_at", "created_at"])
    op.create_index("ix_ai_research_tasks_trace_id", "ai_research_tasks", ["trace_id"])

    op.create_table(
        "ai_research_artifacts",
        _id(),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=2048), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("producer_identity", sa.String(length=128), nullable=False),
        sa.Column("container_image_digest", sa.String(length=256), nullable=True),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash", "kind", name="uq_ai_research_artifact_content_kind"),
    )
    op.create_index("ix_ai_research_artifact_producer", "ai_research_artifacts", ["producer_identity", "created_at"])

    op.create_table(
        "ai_research_candidates",
        _id(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("experiment_epoch_id", sa.String(length=36), sa.ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_version_id", sa.String(length=36), sa.ForeignKey("ai_strategy_research_versions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("dataset_snapshot_id", sa.String(length=36), sa.ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code_artifact_id", sa.String(length=36), sa.ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("dependency_artifact_id", sa.String(length=36), sa.ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("candidate_hash", sa.String(length=64), nullable=False),
        sa.Column("environment_hash", sa.String(length=64), nullable=False),
        sa.Column("cost_model_hash", sa.String(length=64), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("freeze_status", sa.String(length=16), nullable=False, server_default=sa.text("'MUTABLE'")),
        _timestamp("frozen_at", nullable=True),
        sa.Column("frozen_by", sa.String(length=128), nullable=True),
        _timestamp("created_at"),
        sa.CheckConstraint("freeze_status IN ('MUTABLE', 'FROZEN')", name="ck_ai_research_candidate_freeze"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_research_candidate_epoch_status", "ai_research_candidates", ["experiment_epoch_id", "freeze_status"])
    op.create_index("ix_ai_research_candidate_owner_hash", "ai_research_candidates", ["user_id", "candidate_hash"])

    op.create_table(
        "ai_research_trials",
        _id(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("parent_trial_id", sa.String(length=36), sa.ForeignKey("ai_research_trials.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("returns_artifact_id", sa.String(length=36), sa.ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("observed_market_performance", sa.Boolean(), nullable=False),
        sa.Column("counts_as_market_trial", sa.Boolean(), nullable=False),
        sa.Column("counting_reason", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        _timestamp("started_at", nullable=True),
        _timestamp("completed_at", nullable=True),
        _timestamp("created_at"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT', 'INVALID')",
            name="ck_ai_research_trial_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_ai_research_trial_ordinal"),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_ai_research_trial_idempotency"),
    )
    op.create_index("ix_ai_research_trial_candidate", "ai_research_trials", ["candidate_id", "created_at"])

    op.create_table(
        "ai_research_model_invocations",
        _id(),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("trial_id", sa.String(length=36), sa.ForeignKey("ai_research_trials.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("requested_model", sa.String(length=256), nullable=False),
        sa.Column("resolved_model", sa.String(length=256), nullable=False),
        sa.Column("provider_request_id", sa.String(length=256), nullable=True),
        sa.Column("prompt_template_version", sa.String(length=128), nullable=False),
        sa.Column("system_input_hash", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("sampling_params", sa.JSON(), nullable=False),
        sa.Column("tool_manifest", sa.JSON(), nullable=False),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("transformation_chain", sa.JSON(), nullable=False),
        sa.Column("fallback_chain", sa.JSON(), nullable=False),
        sa.Column("token_usage", sa.JSON(), nullable=False),
        sa.Column("cost", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        _timestamp("created_at"),
        _timestamp("completed_at", nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_research_invocation_run_created", "ai_research_model_invocations", ["run_id", "created_at"])

    op.create_table(
        "ai_research_holdout_authorizations",
        _id(),
        sa.Column("experiment_epoch_id", sa.String(length=36), sa.ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("evaluator_identity", sa.String(length=128), nullable=False),
        sa.Column("capability_profile_id", sa.String(length=128), nullable=False),
        sa.Column("capability_profile_version", sa.String(length=128), nullable=False),
        sa.Column("capability_evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_by", sa.String(length=128), nullable=True),
        _timestamp("issued_at"),
        _timestamp("consumed_at", nullable=True),
        _timestamp("expires_at", nullable=True),
        sa.CheckConstraint("status IN ('ISSUED', 'CONSUMED', 'EXPIRED', 'REVOKED')", name="ck_ai_research_holdout_authorization_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_ai_research_holdout_token_hash"),
        sa.UniqueConstraint(
            "experiment_epoch_id", "candidate_id", "dataset_snapshot_id", "policy_version",
            name="uq_ai_research_holdout_authorization_binding",
        ),
    )

    op.create_table(
        "ai_research_evaluations",
        _id(),
        sa.Column("experiment_epoch_id", sa.String(length=36), sa.ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_type", sa.String(length=32), nullable=False),
        sa.Column("evaluator_identity", sa.String(length=128), nullable=False),
        sa.Column("evaluator_version", sa.String(length=128), nullable=False),
        sa.Column("authorization_id", sa.String(length=36), sa.ForeignKey("ai_research_holdout_authorizations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("returns_artifact_id", sa.String(length=36), sa.ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("gate_inputs", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        _timestamp("started_at", nullable=True),
        _timestamp("completed_at", nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'PASSED', 'REJECTED', 'FAILED', 'EXPIRED')",
            name="ck_ai_research_evaluation_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "experiment_epoch_id", "dataset_snapshot_id", "policy_version", "evaluation_type",
            name="uq_ai_research_evaluation_budget",
        ),
    )

    op.create_table(
        "ai_research_gate_decisions",
        _id(),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_id", sa.String(length=36), sa.ForeignKey("ai_research_evaluations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("gate_code", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("input_evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("executor_version", sa.String(length=128), nullable=False),
        _timestamp("evaluated_at"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_research_gate_candidate", "ai_research_gate_decisions", ["candidate_id", "evaluated_at"])

    op.create_table(
        "ai_research_approval_requests",
        _id(),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("gate_input_evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_package_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        _timestamp("requested_at"),
        _timestamp("eligible_at"),
        _timestamp("expires_at"),
        _timestamp("decided_at", nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'DECIDED', 'EXPIRED', 'REVOKED')",
            name="ck_ai_research_approval_request_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            "idempotency_key",
            name="uq_ai_research_approval_request_idempotency",
        ),
    )

    op.create_table(
        "ai_research_human_decisions",
        _id(),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("domain_permissions", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("approval_mode", sa.String(length=32), nullable=False),
        sa.Column("single_actor", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("risk_acknowledgement", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("challenge_records", sa.JSON(), nullable=False),
        sa.Column("evidence_package_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        _timestamp("requested_at", nullable=True),
        _timestamp("eligible_at", nullable=True),
        _timestamp("decided_at"),
        _timestamp("expires_at", nullable=True),
        sa.CheckConstraint("decision IN ('APPROVED', 'REJECTED', 'REQUESTED_CHANGES')", name="ck_ai_research_human_decision"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "idempotency_key", name="uq_ai_research_human_decision_idempotency"),
    )

    op.create_table(
        "ai_research_governance_decisions",
        _id(),
        sa.Column("target_requirement_or_gate", sa.String(length=128), nullable=False),
        sa.Column("original_status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("risk", sa.Text(), nullable=False),
        sa.Column("compensating_controls", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        _timestamp("effective_at"),
        _timestamp("expires_at", nullable=True),
        _timestamp("revoked_at", nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ai_research_stage_attempts",
        _id(),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("ai_research_tasks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("output_artifact_id", sa.String(length=36), sa.ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        _timestamp("started_at"),
        _timestamp("completed_at", nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "stage", "attempt_no", name="uq_ai_research_stage_attempt"),
        sa.UniqueConstraint("task_id", "idempotency_key", name="uq_ai_research_stage_idempotency"),
    )

    op.create_table(
        "ai_research_quota_buckets",
        _id(),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        _timestamp("window_start"),
        _timestamp("window_end"),
        sa.Column("hard_limit", sa.Integer(), nullable=False),
        sa.Column("concurrency_limit", sa.Integer(), nullable=False),
        sa.Column("reserved_amount", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("settled_amount", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active_reservations", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("reconcile_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_fencing_token", sa.Integer(), nullable=False, server_default=sa.text("1")),
        _timestamp("updated_at"),
        sa.CheckConstraint("status IN ('ACTIVE', 'BLOCKED_UNKNOWN')", name="ck_ai_research_quota_bucket_status"),
        sa.CheckConstraint("reserved_amount >= 0 AND settled_amount >= 0", name="ck_ai_research_quota_amounts"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scope_type", "scope_id", "policy_version", "resource_type", "window_start", "window_end",
            name="uq_ai_research_quota_bucket_window",
        ),
    )

    op.create_table(
        "ai_research_quota_reservations",
        _id(),
        sa.Column("bucket_id", sa.String(length=36), sa.ForeignKey("ai_research_quota_buckets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("ai_research_tasks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("stage_attempt_id", sa.String(length=36), sa.ForeignKey("ai_research_stage_attempts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("reserved_amount", sa.Integer(), nullable=False),
        sa.Column("settled_amount", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'RESERVED'")),
        _timestamp("lease_expires_at", nullable=True),
        sa.Column("fencing_token", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("provider_operation_id", sa.String(length=256), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        _timestamp("created_at"),
        _timestamp("settled_at", nullable=True),
        _timestamp("released_at", nullable=True),
        sa.CheckConstraint(
            "status IN ('RESERVED', 'IN_FLIGHT', 'RECONCILING', 'SETTLED', 'RELEASED', 'EXPIRED', 'BLOCKED_UNKNOWN')",
            name="ck_ai_research_quota_reservation_status",
        ),
        sa.CheckConstraint("reserved_amount >= 0 AND settled_amount >= 0", name="ck_ai_research_quota_reservation_amounts"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bucket_id", "resource_type", "idempotency_key", name="uq_ai_research_quota_reservation"),
    )


def downgrade() -> None:
    """Remove v2 authority tables only; legacy AI-research records survive."""

    for table_name in (
        "ai_research_quota_reservations",
        "ai_research_quota_buckets",
        "ai_research_stage_attempts",
        "ai_research_governance_decisions",
        "ai_research_human_decisions",
        "ai_research_approval_requests",
        "ai_research_gate_decisions",
        "ai_research_evaluations",
        "ai_research_holdout_authorizations",
        "ai_research_model_invocations",
        "ai_research_trials",
        "ai_research_candidates",
        "ai_research_artifacts",
        "ai_research_tasks",
        "ai_research_runs",
        "ai_research_dataset_snapshots",
        "ai_research_experiment_epochs",
        "ai_research_hypothesis_versions",
        "ai_research_capability_profiles",
    ):
        op.drop_table(table_name)
