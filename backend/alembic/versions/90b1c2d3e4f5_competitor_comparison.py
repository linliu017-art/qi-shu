"""Store structured competitor comparisons and revision history."""
from alembic import op
import sqlalchemy as sa
revision='90b1c2d3e4f5'
down_revision='89a0b1c2d3e4'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('competitor_comparisons',sa.Column('work_id',sa.String(36),sa.ForeignKey('product_work.id'),primary_key=True),sa.Column('content',sa.Text(),nullable=False))
    op.create_table('competitor_comparison_revisions',sa.Column('id',sa.String(36),primary_key=True),sa.Column('work_id',sa.String(36),sa.ForeignKey('product_work.id'),nullable=False),sa.Column('version',sa.Integer(),nullable=False),sa.Column('content',sa.Text(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint('work_id','version',name='uq_competitor_comparison_revision'))
    op.create_index('ix_competitor_comparison_revisions_work_id','competitor_comparison_revisions',['work_id'])

def downgrade():raise RuntimeError('竞品资料包含用户数据，不支持自动降级。')
