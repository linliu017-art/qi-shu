"""Persist optional PRD chapter references."""
from alembic import op
import sqlalchemy as sa
revision='89a0b1c2d3e4'
down_revision='78f9a0b1c2d3'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('product_section_links',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('work_id',sa.String(36),sa.ForeignKey('product_work.id'),nullable=False),
        sa.Column('source_id',sa.String(36),nullable=False),
        sa.Column('source_version',sa.Integer(),nullable=False),sa.Column('section_index',sa.Integer(),nullable=False),
        sa.Column('section_title',sa.String(500),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('work_id','source_id','section_index',name='uq_product_section_link'))
    op.create_index('ix_product_section_links_work_id','product_section_links',['work_id'])

def downgrade():
    raise RuntimeError('章节关联包含用户数据，不支持自动降级。')
