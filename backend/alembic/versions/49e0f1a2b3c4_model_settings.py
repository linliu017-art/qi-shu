"""Administrator model settings and non-secret audit events."""
from alembic import op
import sqlalchemy as sa

revision = '49e0f1a2b3c4'
down_revision = '38d9e0f1a2b3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('model_settings', sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('allowed_models', sa.Text(), nullable=False),
                    sa.Column('max_requests', sa.Integer(), nullable=False))
    op.create_table('model_settings_events', sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('actor_id', sa.String(36), sa.ForeignKey('user_accounts.id'), nullable=False),
                    sa.Column('action', sa.String(30), nullable=False), sa.Column('details', sa.Text(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('model_settings_events')
    op.drop_table('model_settings')
