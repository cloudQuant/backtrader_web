"""Reserve the historical run-integrity revision in the unreleased chain.

Revision ID: 20260804_asset_research_run_integrity
Revises: 20260803_asset_research_schedule_reliability

The original unreleased implementation installed cross-table triggers here.
On MySQL with binary logging those triggers require global privileges that the
application migration account should not receive.  Revision ``20260806``
replaces the association-table design with a direct nullable foreign key and
a row-local CHECK on ``asset_signal_runs``.  This checkpoint deliberately
does no DDL so an ordinary schema-scoped MySQL account can reach that safe
representation.
"""

# revision identifiers, used by Alembic.
revision = "20260804_asset_research_run_integrity"
down_revision = "20260803_asset_research_schedule_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Keep the linear revision for databases created before the redesign."""


def downgrade() -> None:
    """The adjacent revisions contain all reversible schema operations."""
