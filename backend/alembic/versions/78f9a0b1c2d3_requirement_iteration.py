"""Track current planned iteration without changing legacy text values."""
from alembic import op
import sqlalchemy as sa
revision='78f9a0b1c2d3'
down_revision='67e8f9a0b1c2'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('product_requirements',sa.Column('iteration_id',sa.String(36),nullable=True))

def downgrade():
    raise RuntimeError('迭代关联包含用户数据，不支持自动降级。')
