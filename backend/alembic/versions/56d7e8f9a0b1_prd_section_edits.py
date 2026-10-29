"""Persist PRD section edit target and conflict metadata."""
from alembic import op
import sqlalchemy as sa

revision = '56d7e8f9a0b1'
down_revision = '45c6d7e8f9a0'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('product_research_tasks', sa.Column('edit_spec', sa.Text(), nullable=False, server_default='{}'))

def downgrade():
    raise RuntimeError('章节修改任务包含用户数据，不支持自动降级。')
