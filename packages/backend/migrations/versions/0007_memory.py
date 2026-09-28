"""Memory schema v1."""
import sqlalchemy as sa
from alembic import op

revision = "0007_memory"
down_revision = "0006_remove_workflows"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('memories',
        sa.Column('kind', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('title', sa.String(length=160), nullable=False, primary_key=False),
        sa.Column('current_revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('active_revision', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('source_type', sa.String(length=30), nullable=False, primary_key=False),
        sa.Column('event_key', sa.String(length=250), nullable=True, primary_key=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('use_count', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('owner_user_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint('owner_user_id', 'event_key'),
    )
    op.create_index('ix_memories_owner_user_id', 'memories', ['owner_user_id'], unique=False)
    op.create_index('ix_memory_owner_kind_status', 'memories', ['owner_user_id', 'kind', 'status', 'updated_at'], unique=False)
    op.create_table('memory_action_links',
        sa.Column('run_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('conversation_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('mcp_server_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('correlation_key', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('parameters_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('arguments', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('tool_name', sa.String(length=80), nullable=False, primary_key=False),
        sa.Column('proposal_id', sa.String(length=120), nullable=True, primary_key=False),
        sa.Column('command_id', sa.String(length=120), nullable=True, primary_key=False),
        sa.Column('diagnosis_id', sa.String(length=120), nullable=True, primary_key=False),
        sa.Column('reservation', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('result', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('result_hash', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('outcome', sa.String(length=30), nullable=False, primary_key=False),
        sa.Column('rediagnosis', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('next_poll_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('tracking_until', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('owner_user_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint('correlation_key'),
    )
    op.create_index('ix_memory_action_links_command_id', 'memory_action_links', ['command_id'], unique=False)
    op.create_index('ix_memory_action_links_owner_user_id', 'memory_action_links', ['owner_user_id'], unique=False)
    op.create_index('ix_memory_action_links_proposal_id', 'memory_action_links', ['proposal_id'], unique=False)
    op.create_index('ix_memory_action_links_run_id', 'memory_action_links', ['run_id'], unique=False)
    op.create_table('memory_feedback',
        sa.Column('memory_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('command_id', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('outcome', sa.String(length=30), nullable=False, primary_key=False),
        sa.Column('evidence', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('owner_user_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint('owner_user_id', 'memory_id', 'command_id'),
    )
    op.create_index('ix_memory_feedback_owner_user_id', 'memory_feedback', ['owner_user_id'], unique=False)
    op.create_table('memory_index_state',
        sa.Column('memory_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('model_fingerprint', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('error_code', sa.String(length=100), nullable=True, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint('memory_id', 'revision', 'model_fingerprint'),
    )
    op.create_table('memory_jobs',
        sa.Column('job_key', sa.String(length=250), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('payload', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('attempts', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('lease_token', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('error_code', sa.String(length=100), nullable=True, primary_key=False),
        sa.Column('owner_user_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint('owner_user_id', 'job_key'),
    )
    op.create_index('ix_memory_jobs_owner_user_id', 'memory_jobs', ['owner_user_id'], unique=False)
    op.create_index('ix_memory_jobs_status', 'memory_jobs', ['status'], unique=False)
    op.create_table('memory_legacy_imports',
        sa.Column('mcp_server_id', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('fault_id', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('source_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('original', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('batch_id', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('assigned_user_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('assigned_by', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('memory_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('error_code', sa.String(length=100), nullable=True, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint('mcp_server_id', 'fault_id'),
    )
    op.create_index('ix_memory_legacy_imports_batch_id', 'memory_legacy_imports', ['batch_id'], unique=False)
    op.create_table('memory_sources',
        sa.Column('source_key', sa.String(length=250), nullable=False, primary_key=False),
        sa.Column('source_type', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('source_id', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('run_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('conversation_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('mcp_server_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('diagnosis_id', sa.String(length=120), nullable=True, primary_key=False),
        sa.Column('command_id', sa.String(length=120), nullable=True, primary_key=False),
        sa.Column('tool_call_id', sa.String(length=120), nullable=True, primary_key=False),
        sa.Column('excerpt', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('access_state', sa.String(length=30), nullable=False, primary_key=False),
        sa.Column('owner_user_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint('owner_user_id', 'source_key'),
    )
    op.create_index('ix_memory_sources_conversation_id', 'memory_sources', ['conversation_id'], unique=False)
    op.create_index('ix_memory_sources_diagnosis_id', 'memory_sources', ['diagnosis_id'], unique=False)
    op.create_index('ix_memory_sources_owner_user_id', 'memory_sources', ['owner_user_id'], unique=False)
    op.create_index('ix_memory_sources_run_id', 'memory_sources', ['run_id'], unique=False)
    op.create_table('memory_tombstones',
        sa.Column('scope', sa.String(length=30), nullable=False, primary_key=False),
        sa.Column('target_id', sa.String(length=250), nullable=False, primary_key=False),
        sa.Column('content_hash', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('owner_user_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint('owner_user_id', 'scope', 'target_id'),
    )
    op.create_index('ix_memory_tombstones_owner_user_id', 'memory_tombstones', ['owner_user_id'], unique=False)
    op.create_table('memory_usage',
        sa.Column('memory_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('run_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('diagnosis_id', sa.String(length=120), nullable=True, primary_key=False),
        sa.Column('stage', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('owner_user_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
    )
    op.create_index('ix_memory_usage_owner_user_id', 'memory_usage', ['owner_user_id'], unique=False)
    op.create_table('memory_vector_outbox',
        sa.Column('memory_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('operation', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('model_fingerprint', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('collection', sa.String(length=160), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('owner_user_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
    )
    op.create_index('ix_memory_vector_outbox_memory_id', 'memory_vector_outbox', ['memory_id'], unique=False)
    op.create_index('ix_memory_vector_outbox_owner_user_id', 'memory_vector_outbox', ['owner_user_id'], unique=False)
    op.create_table('working_memories',
        sa.Column('conversation_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('run_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('facts', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('owner_user_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint('owner_user_id', 'conversation_id'),
    )
    op.create_index('ix_working_memories_conversation_id', 'working_memories', ['conversation_id'], unique=False)
    op.create_index('ix_working_memories_owner_user_id', 'working_memories', ['owner_user_id'], unique=False)
    op.create_table('memory_evidence_links',
        sa.Column('memory_id', sa.String(length=36), sa.ForeignKey('memories.id'), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('source_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('episode_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('episode_revision', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('relation', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('owner_user_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
    )
    op.create_index('ix_memory_evidence_links_episode_id', 'memory_evidence_links', ['episode_id'], unique=False)
    op.create_index('ix_memory_evidence_links_memory_id', 'memory_evidence_links', ['memory_id'], unique=False)
    op.create_index('ix_memory_evidence_links_owner_user_id', 'memory_evidence_links', ['owner_user_id'], unique=False)
    op.create_index('ix_memory_evidence_links_source_id', 'memory_evidence_links', ['source_id'], unique=False)
    op.create_table('memory_revisions',
        sa.Column('memory_id', sa.String(length=36), sa.ForeignKey('memories.id'), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('title', sa.String(length=160), nullable=False, primary_key=False),
        sa.Column('summary', sa.Text(), nullable=False, primary_key=False),
        sa.Column('content_json', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('applicability_json', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('search_text', sa.Text(), nullable=False, primary_key=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('review_state', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('reviewed_by', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('change_reason', sa.Text(), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('extractor_version', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('policy_version', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('model_id', sa.String(length=120), nullable=True, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint('memory_id', 'revision'),
    )
    op.create_index('ix_memory_revisions_memory_id', 'memory_revisions', ['memory_id'], unique=False)


def downgrade():
    op.drop_table('memory_revisions')
    op.drop_table('memory_evidence_links')
    op.drop_table('working_memories')
    op.drop_table('memory_vector_outbox')
    op.drop_table('memory_usage')
    op.drop_table('memory_tombstones')
    op.drop_table('memory_sources')
    op.drop_table('memory_legacy_imports')
    op.drop_table('memory_jobs')
    op.drop_table('memory_index_state')
    op.drop_table('memory_feedback')
    op.drop_table('memory_action_links')
    op.drop_table('memories')
