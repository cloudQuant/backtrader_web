"""Bind every dataset snapshot to its controlled storage reference.

Revision ID: 20260905_ai_research_dataset_storage_reference
Revises: 20260905_ai_research_holdout_candidate_hash

Dataset metadata content hashes intentionally omit the opaque object location
so that the location is never exposed through Explorer read models.  The
location still needs its own immutable digest: without it, a valid controlled
namespace could be switched to a different object after a snapshot was
created.  This migration backfills a partition-plus-reference digest and
refuses to manufacture a digest for an absent or invalid legacy reference.
"""

from __future__ import annotations

import json
from hashlib import sha256
from urllib.parse import urlsplit

import sqlalchemy as sa

from alembic import op

revision = "20260905_ai_research_dataset_storage_reference"
down_revision = "20260905_ai_research_holdout_candidate_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add and backfill the immutable digest for the opaque storage reference."""

    with op.batch_alter_table("ai_research_dataset_snapshots") as batch_op:
        batch_op.add_column(sa.Column("storage_reference_hash", sa.String(length=64), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, partition_kind, storage_uri "
            "FROM ai_research_dataset_snapshots"
        )
    ).mappings()
    for row in rows:
        storage_uri = row["storage_uri"]
        partition_kind = row["partition_kind"]
        if not isinstance(storage_uri, str) or not storage_uri.strip():
            raise RuntimeError("DATASET_STORAGE_REFERENCE_BACKFILL_REQUIRED")
        if not isinstance(partition_kind, str) or not _valid_reference(partition_kind, storage_uri):
            raise RuntimeError("DATASET_STORAGE_REFERENCE_INVALID")
        bind.execute(
            sa.text(
                "UPDATE ai_research_dataset_snapshots "
                "SET storage_reference_hash = :storage_reference_hash "
                "WHERE id = :id"
            ),
            {
                "id": row["id"],
                "storage_reference_hash": _storage_reference_hash(partition_kind, storage_uri),
            },
        )

    with op.batch_alter_table("ai_research_dataset_snapshots") as batch_op:
        batch_op.alter_column(
            "storage_reference_hash",
            existing_type=sa.String(length=64),
            nullable=False,
        )


def downgrade() -> None:
    """Remove only the supplemental opaque-reference digest."""

    with op.batch_alter_table("ai_research_dataset_snapshots") as batch_op:
        batch_op.drop_column("storage_reference_hash")


def _storage_reference_hash(partition_kind: str, storage_uri: str) -> str:
    payload = {"partition_kind": partition_kind, "storage_uri": storage_uri}
    return sha256(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()


def _valid_reference(partition_kind: str, storage_uri: str) -> bool:
    parsed = urlsplit(storage_uri)
    expected_scheme = "sealed" if partition_kind == "SEALED_HOLDOUT" else "controlled"
    path_parts = tuple(part for part in parsed.path.split("/") if part)
    return bool(
        parsed.scheme == expected_scheme
        and parsed.netloc
        and not parsed.query
        and not parsed.fragment
        and not any(part in {".", ".."} or "\\" in part for part in path_parts)
    )
