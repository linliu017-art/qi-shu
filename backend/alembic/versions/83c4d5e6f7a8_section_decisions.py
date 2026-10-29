"""Record who accepted or discarded a section candidate and when."""
from alembic import op
import sqlalchemy as sa
revision = '83c4d5e6f7a8'
down_revision = '72b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('section_edits', sa.Column('decision_actor_id', sa.String(36), nullable=True))
    op.add_column('section_edits', sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    raise RuntimeError('章节修改决定记录包含用户数据，不能自动降级。')
