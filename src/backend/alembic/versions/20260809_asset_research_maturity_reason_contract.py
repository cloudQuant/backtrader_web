"""Enforce the architecture-owned maturity-reason contract.

Revision ID: 20260809_asset_research_maturity_reason_contract
Revises: 20260808_asset_research_manifest_evidence_required

The public API distinguishes outcome status from the business event that made
the outcome mature.  Without a database constraint, direct writes could store
undefined values such as ``MATURED`` and corrupt that shared interpretation.
The migration refuses incompatible historical rows instead of silently
rewriting them.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260809_asset_research_maturity_reason_contract"
down_revision = "20260808_asset_research_manifest_evidence_required"
branch_labels = None
depends_on = None

_TABLE = "asset_signal_outcomes"
_CHECK = "ck_asset_outcome_maturity_reason"
_CHECK_SQL = (
    "maturity_reason IS NULL OR maturity_reason IN "
    "('HORIZON_REACHED', 'EXPIRY', 'MATURITY', 'CALL', 'REDEMPTION', "
    "'ROLL', 'DELISTING', 'LIQUIDATION', 'EXERCISE')"
)


def _assert_existing_maturity_reasons(bind: Any) -> None:
    invalid = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM asset_signal_outcomes
            WHERE maturity_reason IS NOT NULL
              AND maturity_reason NOT IN (
                  'HORIZON_REACHED', 'EXPIRY', 'MATURITY', 'CALL', 'REDEMPTION',
                  'ROLL', 'DELISTING', 'LIQUIDATION', 'EXERCISE'
              )
            """
        )
    ).scalar_one()
    if int(invalid) != 0:
        raise RuntimeError(
            "ASSET_OUTCOME_MATURITY_REASON_BACKFILL_REQUIRED: cannot enforce the "
            "maturity-reason contract while legacy outcomes use undefined values"
        )


def _check_names(bind: Any) -> set[str]:
    return {
        str(check["name"])
        for check in sa.inspect(bind).get_check_constraints(_TABLE)
        if check.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    _assert_existing_maturity_reasons(bind)
    checks = _check_names(bind)
    with op.batch_alter_table(_TABLE) as batch:
        if _CHECK in checks:
            batch.drop_constraint(_CHECK, type_="check")
        batch.create_check_constraint(_CHECK, _CHECK_SQL)


def downgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_constraint(_CHECK, type_="check")
