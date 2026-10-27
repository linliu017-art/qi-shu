"""proposal review and export

Revision ID: 2e4bfb0b1673
Revises: bcf273fe86d4
Create Date: 2026-10-28 00:17:40.058376

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e4bfb0b1673'
down_revision: Union[str, Sequence[str], None] = 'bcf273fe86d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('proposal_review_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('draft_id', sa.String(36), sa.ForeignKey('proposal_drafts.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('decisions', sa.Text(), nullable=False),
        sa.Column('sources', sa.Text(), nullable=False),
        sa.Column('actor', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_proposal_review_events_project_id', 'proposal_review_events', ['project_id'])
    op.create_index('ix_proposal_review_events_draft_id', 'proposal_review_events', ['draft_id'])
    op.create_table('proposal_export_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('draft_id', sa.String(36), sa.ForeignKey('proposal_drafts.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('actor', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_proposal_export_events_project_id', 'proposal_export_events', ['project_id'])
    op.create_index('ix_proposal_export_events_draft_id', 'proposal_export_events', ['draft_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_proposal_export_events_draft_id', table_name='proposal_export_events')
    op.drop_index('ix_proposal_export_events_project_id', table_name='proposal_export_events')
    op.drop_table('proposal_export_events')
    op.drop_index('ix_proposal_review_events_draft_id', table_name='proposal_review_events')
    op.drop_index('ix_proposal_review_events_project_id', table_name='proposal_review_events')
    op.drop_table('proposal_review_events')
