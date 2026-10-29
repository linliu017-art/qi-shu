"""Persist account-based login throttling across process restarts."""
from alembic import op
import sqlalchemy as sa

revision = '27c8d9e0f1a2'
down_revision = '16b7c8d9e0f1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('login_throttles',
        sa.Column('username_hash', sa.String(64), primary_key=True),
        sa.Column('failures', sa.Integer(), nullable=False),
        sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_table('login_throttles')
