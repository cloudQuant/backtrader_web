"""Persist the server-owned workflow version for every protocol-v2 run.

Existing rows retain the historical two-stage generation graph.  The default
also remains on the column so a write that omits the field cannot accidentally
create an unversioned run while mixed worker deployments exist.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260906_ai_research_workflow_version"
down_revision = "20260906_ai_research_search_allocation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_research_runs",
        sa.Column(
            "workflow_version",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'generation-v1'"),
        ),
    )


def downgrade() -> None:
    """Reject a lossy graph downgrade instead of reinterpreting persisted runs.

    A later re-upgrade would apply the server default to every row and turn a
    discovery (or future) graph into ``generation-v1``.  Operators that need
    to retire such data must first archive or explicitly convert it in a
    forward migration; this revision only permits a legacy-only rollback.
    """

    incompatible = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM ai_research_runs "
                "WHERE workflow_version IS NULL OR workflow_version <> :legacy_workflow "
                "LIMIT 1"
            ),
            {"legacy_workflow": "generation-v1"},
        )
        .scalar()
    )
    if incompatible is not None:
        raise RuntimeError("RESEARCH_WORKFLOW_VERSION_DOWNGRADE_BLOCKED")
    op.drop_column("ai_research_runs", "workflow_version")
