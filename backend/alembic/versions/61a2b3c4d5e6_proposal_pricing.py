"""Freeze proposal pricing assumptions for transparent usage estimates."""
from alembic import op
import sqlalchemy as sa

revision = '61a2b3c4d5e6'
down_revision = '50f1a2b3c4d5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('proposal_pricing', sa.Column('draft_id', sa.String(36), sa.ForeignKey('proposal_drafts.id'), primary_key=True),
        sa.Column('input_per_million', sa.String(40), nullable=False),
        sa.Column('output_per_million', sa.String(40), nullable=False), sa.Column('pricing_date', sa.String(10), nullable=False))


def downgrade():
    op.drop_table('proposal_pricing')
