"""Persisted IoT operation workflows.

Revision ID: 0004_operation_workflows
Revises: 0003_mcp_service_kinds
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_operation_workflows"
down_revision: Union[str, None] = "0003_mcp_service_kinds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operation_workflows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "workflow_type", sa.String(80), nullable=False, server_default="iot_remediation_v1"
        ),
        sa.Column("workflow_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("goal", sa.String(24), nullable=False, server_default="diagnosis"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("outcome", sa.String(80)),
        sa.Column("current_step", sa.String(40), nullable=False, server_default="diagnose"),
        sa.Column("device_id", sa.String(120)),
        sa.Column("diagnosis_id", sa.String(120)),
        sa.Column("proposal_id", sa.String(120)),
        sa.Column("command_id", sa.String(120)),
        sa.Column("case_id", sa.String(120)),
        sa.Column("state_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("agent_run_id", name="uq_operation_workflow_run"),
    )
    for column in (
        "agent_run_id",
        "conversation_id",
        "user_id",
        "status",
        "device_id",
        "diagnosis_id",
        "proposal_id",
        "command_id",
        "case_id",
    ):
        op.create_index(f"ix_operation_workflows_{column}", "operation_workflows", [column])
    op.create_table(
        "operation_workflow_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workflow_id", sa.String(36), sa.ForeignKey("operation_workflows.id"), nullable=False
        ),
        sa.Column("step_key", sa.String(40), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error_code", sa.String(120)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workflow_id", "step_key", name="uq_workflow_step_key"),
    )
    op.create_index(
        "ix_operation_workflow_steps_workflow_id", "operation_workflow_steps", ["workflow_id"]
    )
    op.create_table(
        "operation_workflow_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workflow_id", sa.String(36), sa.ForeignKey("operation_workflows.id"), nullable=False
        ),
        sa.Column("event_key", sa.String(255), nullable=False, unique=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_operation_workflow_events_workflow_id", "operation_workflow_events", ["workflow_id"]
    )
    op.create_index(
        "ix_operation_workflow_events_event_key",
        "operation_workflow_events",
        ["event_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("operation_workflow_events")
    op.drop_table("operation_workflow_steps")
    op.drop_table("operation_workflows")
