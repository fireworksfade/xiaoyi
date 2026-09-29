"""Track which memories an action actually adopted (spec §5.3/§7.6)."""

import sqlalchemy as sa
from alembic import op

revision = "0009_action_applied_memory"
down_revision = "0008_remove_legacy_imports"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "memory_action_links",
        sa.Column("applied_memory_ids", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade():
    op.drop_column("memory_action_links", "applied_memory_ids")
