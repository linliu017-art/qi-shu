"""Persist user-confirmed competitor research tasks."""
from alembic import op
import sqlalchemy as sa

revision = '12f3a4b5c6d7'
down_revision = '01e2f3a4b5c6'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('product_research_tasks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('work_id', sa.String(36), sa.ForeignKey('product_work.id'), nullable=False),
        sa.Column('actor_id', sa.String(36), nullable=False),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('base_version', sa.Integer(), nullable=False),
        sa.Column('goal', sa.Text(), nullable=False),
        sa.Column('source_text', sa.Text(), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('prompt_version', sa.String(40), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('result', sa.Text(), nullable=False),
        sa.Column('error', sa.String(500), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('elapsed_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_product_research_tasks_work_id', 'product_research_tasks', ['work_id'])

def downgrade():
    raise RuntimeError('产品研究包含用户数据，不支持自动降级。')
