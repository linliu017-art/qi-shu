"""Persist optional same-project initiation references."""
from alembic import op
import sqlalchemy as sa

revision = '34b5c6d7e8f9'
down_revision = '23a4b5c6d7e8'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('product_work_links',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('work_id', sa.String(36), sa.ForeignKey('product_work.id'), nullable=False),
        sa.Column('target_type', sa.String(20), nullable=False),
        sa.Column('target_id', sa.String(36), nullable=False),
        sa.Column('target_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('work_id', 'target_type', 'target_id', name='uq_product_work_link'))
    op.create_index('ix_product_work_links_work_id', 'product_work_links', ['work_id'])

def downgrade():
    raise RuntimeError('产品工作关联包含用户数据，不支持自动降级。')
