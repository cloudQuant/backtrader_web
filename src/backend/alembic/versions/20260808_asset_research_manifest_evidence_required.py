"""Require durable approval evidence on every system schedule manifest.

Revision ID: 20260808_asset_research_manifest_evidence_required
Revises: 20260807_asset_research_schedule_manifests

The manifest control plane is only meaningful when its approval evidence is
durable at the database boundary.  API validation already required both
fields, but a direct write could previously leave both NULL.  This revision
refuses any such historical row instead of inventing evidence during upgrade.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260808_asset_research_manifest_evidence_required"
down_revision = "20260807_asset_research_schedule_manifests"
branch_labels = None
depends_on = None

_TABLE = "asset_schedule_manifests"
_CHECK = "ck_asset_schedule_manifest_evidence"
_OPTIONAL_EVIDENCE_CHECK = (
    "(evidence_uri IS NULL AND evidence_content_hash IS NULL) OR "
    "(evidence_uri IS NOT NULL AND evidence_content_hash IS NOT NULL)"
)
_REQUIRED_EVIDENCE_CHECK = "evidence_uri IS NOT NULL AND evidence_content_hash IS NOT NULL"


def _assert_existing_evidence(bind: Any) -> None:
    missing = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM asset_schedule_manifests
            WHERE evidence_uri IS NULL OR evidence_content_hash IS NULL
            """
        )
    ).scalar_one()
    if int(missing) != 0:
        raise RuntimeError(
            "ASSET_SCHEDULE_MANIFEST_EVIDENCE_BACKFILL_REQUIRED: "
            "cannot make approval evidence required while legacy manifest rows are incomplete"
        )


def _check_names(bind: Any) -> set[str]:
    return {
        str(check["name"])
        for check in sa.inspect(bind).get_check_constraints(_TABLE)
        if check.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    _assert_existing_evidence(bind)
    checks = _check_names(bind)
    with op.batch_alter_table(_TABLE) as batch:
        if _CHECK in checks:
            batch.drop_constraint(_CHECK, type_="check")
        batch.alter_column(
            "evidence_uri",
            existing_type=sa.String(length=2048),
            nullable=False,
        )
        batch.alter_column(
            "evidence_content_hash",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch.create_check_constraint(_CHECK, _REQUIRED_EVIDENCE_CHECK)


def downgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_constraint(_CHECK, type_="check")
        batch.alter_column(
            "evidence_content_hash",
            existing_type=sa.String(length=64),
            nullable=True,
        )
        batch.alter_column(
            "evidence_uri",
            existing_type=sa.String(length=2048),
            nullable=True,
        )
        batch.create_check_constraint(_CHECK, _OPTIONAL_EVIDENCE_CHECK)
