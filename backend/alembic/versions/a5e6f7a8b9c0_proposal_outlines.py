"""Persist immutable proposal outlines and bind new drafts to their selected outline."""
from alembic import op
import sqlalchemy as sa
revision='a5e6f7a8b9c0'
down_revision='94d5e6f7a8b9'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('proposal_outlines',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id'),nullable=False),
        sa.Column('baseline_id',sa.String(36),sa.ForeignKey('baselines.id'),nullable=False),
        sa.Column('template_id',sa.String(50),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('chapters',sa.Text(),nullable=False),sa.Column('created_by',sa.String(36)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('project_id','baseline_id','version',name='uq_outline_project_baseline_version'))
    op.create_index('ix_proposal_outlines_project_id','proposal_outlines',['project_id'])
    op.create_table('proposal_outline_links',
        sa.Column('draft_id',sa.String(36),sa.ForeignKey('proposal_drafts.id'),primary_key=True),
        sa.Column('outline_id',sa.String(36),sa.ForeignKey('proposal_outlines.id'),nullable=False),
        sa.Column('snapshot',sa.Text(),nullable=False))


def downgrade():
    raise RuntimeError('提纲版本和方案关联包含用户数据，不能自动降级。')
