"""Recoverable run artifacts and context snapshots.

Revision ID: 0005_run_artifacts
Revises: 0004_operation_workflows
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_run_artifacts"
down_revision: Union[str, None] = "0004_operation_workflows"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("storage_uri", sa.String(1000), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("redaction_version", sa.String(40), nullable=False, server_default="v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_run_artifacts_run_id", "run_artifacts", ["run_id"])
    op.create_table(
        "conversation_context_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column(
            "covers_through_message_id",
            sa.String(36),
            sa.ForeignKey("messages.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("summary_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "source_artifact_id", sa.String(36), sa.ForeignKey("run_artifacts.id"), nullable=False
        ),
        sa.Column("estimated_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_context_snapshots_conversation_id",
        "conversation_context_snapshots",
        ["conversation_id"],
    )
    op.create_index(
        "ix_context_snapshots_message_id",
        "conversation_context_snapshots",
        ["covers_through_message_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("conversation_context_snapshots")
    op.drop_table("run_artifacts")
