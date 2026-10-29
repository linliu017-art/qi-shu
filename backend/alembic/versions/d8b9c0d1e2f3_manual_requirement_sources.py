"""Allow optional, verified source quotations on human-entered requirements."""
from alembic import op
import sqlalchemy as sa
revision='d8b9c0d1e2f3'
down_revision='c7a8b9c0d1e2'
branch_labels=None
depends_on=None

def upgrade():
    op.execute('ALTER TABLE manual_requirements ADD COLUMN material_id VARCHAR(36) REFERENCES materials(id)')
    op.execute('ALTER TABLE manual_requirements ADD COLUMN quote TEXT')

def downgrade():
    raise RuntimeError('人工需求来源包含用户数据，不支持自动降级。')
