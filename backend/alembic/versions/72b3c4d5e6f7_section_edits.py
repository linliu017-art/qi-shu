"""Persist bounded proposal section edit jobs."""
from alembic import op
import sqlalchemy as sa

revision = '72b3c4d5e6f7'
down_revision = '61a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('section_edits',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('draft_id', sa.String(36), sa.ForeignKey('proposal_drafts.id'), nullable=False),
        sa.Column('actor_id', sa.String(36), nullable=False),
        sa.Column('base_version', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.String(100), nullable=False),
        sa.Column('section_title', sa.String(500), nullable=False),
        sa.Column('section_level', sa.Integer(), nullable=False),
        sa.Column('start_offset', sa.Integer(), nullable=False),
        sa.Column('end_offset', sa.Integer(), nullable=False),
        sa.Column('original', sa.Text(), nullable=False),
        sa.Column('instruction', sa.Text(), nullable=False),
        sa.Column('context', sa.Text(), nullable=False),
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('candidate', sa.Text(), nullable=False),
        sa.Column('suggestions', sa.Text(), nullable=False),
        sa.Column('error', sa.String(500), nullable=False),
        sa.Column('calls', sa.Integer(), nullable=False),
        sa.Column('prompt_tokens', sa.Integer()), sa.Column('completion_tokens', sa.Integer()),
        sa.Column('elapsed_ms', sa.Integer()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_section_edits_draft_id', 'section_edits', ['draft_id'])
    with op.batch_alter_table('queued_jobs', recreate='always') as batch:
        batch.create_check_constraint('ck_queued_jobs_kind_v2', "kind IN ('requirements', 'proposal', 'section_edit')")
        batch.create_check_constraint('ck_queued_jobs_status_v2', "status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted')")


def downgrade():
    raise RuntimeError('章节修改任务可能包含用户数据，不能自动降级。')
