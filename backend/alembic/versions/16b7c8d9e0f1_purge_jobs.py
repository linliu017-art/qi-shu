"""Persist confirmed purge operations until original-file cleanup completes."""
from alembic import op
import sqlalchemy as sa

revision = '16b7c8d9e0f1'
down_revision = '05a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('purge_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), nullable=False),
        sa.Column('actor_id', sa.String(36), nullable=False),
        sa.Column('backup_id', sa.String(36), nullable=False),
        sa.Column('files', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('purge_jobs')
