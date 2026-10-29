"""Protect question decisions from concurrent overwrites."""
from alembic import op
import sqlalchemy as sa

revision = '05a6b7c8d9e0'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('open_questions', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))


def downgrade():
    op.drop_column('open_questions', 'version')
