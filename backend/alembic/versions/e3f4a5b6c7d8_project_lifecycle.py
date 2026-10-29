"""Keep reversible project state and audit records."""
from alembic import op
import sqlalchemy as sa

revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('project_lifecycle',
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), primary_key=True),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('before_trash', sa.String(20), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False))
    op.create_table('project_lifecycle_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('actor_id', sa.String(36), sa.ForeignKey('user_accounts.id'), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_project_lifecycle_events_project_id', 'project_lifecycle_events', ['project_id'])


def downgrade():
    op.drop_table('project_lifecycle_events')
    op.drop_table('project_lifecycle')
