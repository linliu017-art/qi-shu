"""Keep account administration history without storing passwords."""
from alembic import op
import sqlalchemy as sa

revision = 'c1d2e3f4a5b6'
down_revision = 'b0c1d2e3f4a5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('account_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('actor_id', sa.String(36), sa.ForeignKey('user_accounts.id'), nullable=False),
        sa.Column('target_id', sa.String(36), sa.ForeignKey('user_accounts.id'), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('account_events')
