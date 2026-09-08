"""Add server-attested object identity to protocol-v2 dataset snapshots.

Revision ID: 20260905_ai_research_dataset_identity
Revises: 20260905_ai_research_generation_materialization

Existing snapshots receive only the explicit ``LEGACY_UNVERIFIED`` state.  This
migration deliberately does not synthesize an object receipt, version, digest,
byte count, attestation receipt, or snapshot identity from a legacy URI.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260905_ai_research_dataset_identity"
down_revision = "20260905_ai_research_generation_materialization"
branch_labels = None
depends_on = None

_TABLE = "ai_research_dataset_snapshots"
_STATUS_CONSTRAINT = "ck_ai_research_dataset_integrity_status"
_OWNER_OBJECT_INDEX = "ix_ai_research_dataset_owner_object_integrity"


def upgrade() -> None:
    """Add nullable trusted-object fields and mark all historical rows legacy."""

    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.add_column(sa.Column("object_receipt_id", sa.String(length=256), nullable=True))
        batch_op.add_column(sa.Column("object_logical_id", sa.String(length=256), nullable=True))
        batch_op.add_column(sa.Column("object_version", sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column("object_digest", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("object_size_bytes", sa.BigInteger(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "integrity_status",
                sa.String(length=32),
                nullable=False,
                server_default="LEGACY_UNVERIFIED",
            )
        )
        batch_op.add_column(
            sa.Column("integrity_checked_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("integrity_receipt_hash", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("snapshot_identity_hash", sa.String(length=64), nullable=True)
        )
        batch_op.create_check_constraint(
            _STATUS_CONSTRAINT,
            "integrity_status IN ('LEGACY_UNVERIFIED', 'VERIFIED', 'FAILED')",
        )
        batch_op.create_index(
            _OWNER_OBJECT_INDEX,
            ["user_id", "object_logical_id", "integrity_status"],
            unique=False,
        )


def downgrade() -> None:
    """Remove only the additive dataset object-attestation foundation."""

    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_index(_OWNER_OBJECT_INDEX)
        batch_op.drop_constraint(_STATUS_CONSTRAINT, type_="check")
        batch_op.drop_column("snapshot_identity_hash")
        batch_op.drop_column("integrity_receipt_hash")
        batch_op.drop_column("integrity_checked_at")
        batch_op.drop_column("integrity_status")
        batch_op.drop_column("object_size_bytes")
        batch_op.drop_column("object_digest")
        batch_op.drop_column("object_version")
        batch_op.drop_column("object_logical_id")
        batch_op.drop_column("object_receipt_id")
