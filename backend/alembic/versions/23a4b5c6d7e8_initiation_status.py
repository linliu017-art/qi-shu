"""Record manually updated initiation status without changing existing work."""
from alembic import op
import sqlalchemy as sa

revision = '23a4b5c6d7e8'
down_revision = '12f3a4b5c6d7'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('product_work', sa.Column('status', sa.String(30), nullable=False, server_default='draft'))
    op.create_table('product_work_status_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('work_id', sa.String(36), sa.ForeignKey('product_work.id'), nullable=False),
        sa.Column('old_status', sa.String(30), nullable=False),
        sa.Column('new_status', sa.String(30), nullable=False),
        sa.Column('actor_id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_product_work_status_events_work_id', 'product_work_status_events', ['work_id'])

def downgrade():
    raise RuntimeError('立项状态包含用户数据，不支持自动降级。')
