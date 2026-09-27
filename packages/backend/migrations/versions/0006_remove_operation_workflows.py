"""Remove the retired operation workflow tables.

Revision ID: 0006_remove_workflows
Revises: 0005_run_artifacts

Keep the historical revisions so existing installations can still upgrade.
Downgrade restores the schema only, not deleted workflow records.
"""

from alembic import op
from alembic.script import ScriptDirectory

revision = "0006_remove_workflows"
down_revision = "0005_run_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("operation_workflow_events")
    op.drop_table("operation_workflow_steps")
    op.drop_table("operation_workflows")


def downgrade() -> None:
    scripts = ScriptDirectory.from_config(op.get_context().config)
    original = scripts.get_revision("0004_operation_workflows")
    assert original is not None
    original.module.upgrade()
