"""User-scoped, expiring Desktop plugin connections."""

import sqlalchemy as sa
from alembic import op

revision = "0010_harness_connections"
down_revision = "0009_action_applied_memory"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "harness_connections",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("instance_id", sa.String(80), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("harness_connections")
