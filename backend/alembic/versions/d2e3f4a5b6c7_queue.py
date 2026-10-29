"""Persist scheduling configuration and task queue."""
from alembic import op
import sqlalchemy as sa

revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('queue_settings', sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('max_running', sa.Integer(), nullable=True))
    op.create_table('queued_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('user_accounts.id'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False), sa.Column('target_id', sa.String(36), nullable=False),
        sa.Column('status', sa.String(20), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('kind', 'target_id'), sa.CheckConstraint("kind IN ('requirements', 'proposal')"),
        sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted')"))
    op.create_index('ix_queued_jobs_project_id', 'queued_jobs', ['project_id'])


def downgrade():
    op.drop_table('queued_jobs')
    op.drop_table('queue_settings')
