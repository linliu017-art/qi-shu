"""Persist reviewed facts with a baseline; old baselines remain unchanged."""
from alembic import op
import sqlalchemy as sa

revision = '9b1c7d25f001'
down_revision = '2e4bfb0b1673'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('baseline_facts',
        sa.Column('baseline_id', sa.String(36), sa.ForeignKey('baselines.id'), primary_key=True),
        sa.Column('snapshot', sa.Text(), nullable=False))

def downgrade():
    op.drop_table('baseline_facts')
