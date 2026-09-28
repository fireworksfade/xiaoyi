"""Remove the unused historical fault-case import staging table."""

import sqlalchemy as sa
from alembic import op

revision = "0008_remove_legacy_imports"
down_revision = "0007_memory"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_memory_legacy_imports_batch_id", table_name="memory_legacy_imports")
    op.drop_table("memory_legacy_imports")


def downgrade():
    # Restore only the old schema for migration roundtrips; removed rows stay deleted.
    op.create_table(
        "memory_legacy_imports",
        sa.Column("mcp_server_id", sa.String(120), nullable=False),
        sa.Column("fault_id", sa.String(120), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("original", sa.JSON(), nullable=False),
        sa.Column("batch_id", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("assigned_user_id", sa.String(36)),
        sa.Column("assigned_by", sa.String(36)),
        sa.Column("memory_id", sa.String(36)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("mcp_server_id", "fault_id"),
    )
    op.create_index("ix_memory_legacy_imports_batch_id", "memory_legacy_imports", ["batch_id"])
