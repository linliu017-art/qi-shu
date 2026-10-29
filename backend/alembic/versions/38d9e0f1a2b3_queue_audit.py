"""Audit changes to the administrator's task concurrency setting."""
from alembic import op
import sqlalchemy as sa

revision = '38d9e0f1a2b3'
down_revision = '27c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('queue_settings_events', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('actor_id', sa.String(36), sa.ForeignKey('user_accounts.id'), nullable=False),
        sa.Column('old_limit', sa.Integer(), nullable=True), sa.Column('new_limit', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('queue_settings_events')
