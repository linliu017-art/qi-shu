"""Track new multi-user authors while leaving legacy history unassigned."""
from alembic import op
import sqlalchemy as sa

revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('materials', 'analysis_tasks', 'baselines', 'proposal_drafts'):
        op.add_column(table, sa.Column('created_by', sa.String(36), nullable=True))
    op.add_column('proposal_revisions', sa.Column('actor_id', sa.String(36), nullable=True))


def downgrade():
    op.drop_column('proposal_revisions', 'actor_id')
    for table in ('materials', 'analysis_tasks', 'baselines', 'proposal_drafts'):
        op.drop_column(table, 'created_by')
