"""Record linked research sources for permission and version checks."""
from alembic import op
import sqlalchemy as sa

revision = '45c6d7e8f9a0'
down_revision = '34b5c6d7e8f9'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('product_research_tasks', sa.Column('source_refs', sa.Text(), nullable=False, server_default='[]'))

def downgrade():
    raise RuntimeError('研究来源包含用户数据，不支持自动降级。')
