"""Store validated competitor screenshot attachments."""
from alembic import op
import sqlalchemy as sa
revision='a1c2d3e4f5a6'
down_revision='90b1c2d3e4f5'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('competitor_images',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('work_id',sa.String(36),sa.ForeignKey('product_work.id'),nullable=False),
        sa.Column('filename',sa.String(200),nullable=False),sa.Column('media_type',sa.String(30),nullable=False),
        sa.Column('image_bytes',sa.LargeBinary(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_competitor_images_work_id','competitor_images',['work_id'])

def downgrade():raise RuntimeError('竞品截图包含用户数据，不支持自动降级。')
