"""MCP service kinds

为 mcp_servers 增加能力路由辅助字段（additive，旧应用可忽略）：

- service_kind：diagnosis | control | generic
- is_default_for_kind：同一 kind 多服务时的默认项

不改变已有路由行为；多匹配且无默认项时 API 返回 MCP_CAPABILITY_AMBIGUOUS。

Revision ID: 0003_mcp_service_kinds
Revises: 0002_run_recovery_fields
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_mcp_service_kinds"
down_revision: Union[str, None] = "0002_run_recovery_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("mcp_servers", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("service_kind", sa.String(length=20), nullable=False, server_default="generic")
        )
        batch_op.add_column(
            sa.Column("is_default_for_kind", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("mcp_servers", schema=None) as batch_op:
        batch_op.drop_column("is_default_for_kind")
        batch_op.drop_column("service_kind")
