"""Persist product work and its revision history."""
from alembic import op
import sqlalchemy as sa

revision = '01e2f3a4b5c6'
down_revision = 'f0d1e2f3a4b5'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('product_work',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('creator_id', sa.String(36), nullable=False),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_product_work_creator_id', 'product_work', ['creator_id'])
    op.create_index('ix_product_work_project_id', 'product_work', ['project_id'])
    op.create_table('product_work_revisions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('work_id', sa.String(36), sa.ForeignKey('product_work.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('work_id', 'version', name='uq_product_work_revision'))
    op.create_index('ix_product_work_revisions_work_id', 'product_work_revisions', ['work_id'])

def downgrade():
    raise RuntimeError('产品工作包含用户数据，不支持自动降级。')
