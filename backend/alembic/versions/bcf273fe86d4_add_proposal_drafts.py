"""add proposal drafts

Revision ID: bcf273fe86d4
Revises: 43bb95fe5cdd
Create Date: 2026-10-27 21:11:40.389525

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bcf273fe86d4'
down_revision: Union[str, Sequence[str], None] = '43bb95fe5cdd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('proposal_drafts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('owner_id', sa.String(36), nullable=False),
        sa.Column('baseline_id', sa.String(36), sa.ForeignKey('baselines.id'), nullable=False),
        sa.Column('template_id', sa.String(50), nullable=False),
        sa.Column('template_snapshot', sa.Text(), nullable=False),
        sa.Column('input_snapshot', sa.Text(), nullable=False),
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('error', sa.String(500), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('calls', sa.Integer(), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('elapsed_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_proposal_drafts_project_id', 'proposal_drafts', ['project_id'])
    op.create_table('proposal_revisions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('draft_id', sa.String(36), sa.ForeignKey('proposal_drafts.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_proposal_revisions_draft_id', 'proposal_revisions', ['draft_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_proposal_revisions_draft_id', table_name='proposal_revisions')
    op.drop_table('proposal_revisions')
    op.drop_index('ix_proposal_drafts_project_id', table_name='proposal_drafts')
    op.drop_table('proposal_drafts')
