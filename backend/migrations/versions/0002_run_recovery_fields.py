"""run recovery fields

为 agent_runs 增加运行生命周期字段（WP-03/WP-04）：

- queued_at/started_at/finished_at/last_progress_at：时间线
- attempt_count：执行次数
- interruption_reason：重启恢复时的中断原因（RUN_INTERRUPTED 等）
- status 索引：恢复扫描与 Dispatcher 周期轮询

纯 additive 变更：旧版本应用可忽略新列继续运行，可无损 downgrade。
已有数据回填：queued_at = created_at；已终态记录 attempt_count = 1。

Revision ID: 0002_run_recovery_fields
Revises: 0001_current_schema
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_run_recovery_fields"
down_revision: Union[str, None] = "0001_current_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("interruption_reason", sa.String(length=120), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_agent_runs_status"), ["status"], unique=False
        )
    op.execute("UPDATE agent_runs SET queued_at = created_at WHERE queued_at IS NULL")
    op.execute(
        "UPDATE agent_runs SET attempt_count = 1 "
        "WHERE status IN ('COMPLETED', 'FAILED') AND attempt_count = 0"
    )


def downgrade() -> None:
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_agent_runs_status"))
        batch_op.drop_column("interruption_reason")
        batch_op.drop_column("attempt_count")
        batch_op.drop_column("last_progress_at")
        batch_op.drop_column("finished_at")
        batch_op.drop_column("started_at")
        batch_op.drop_column("queued_at")
