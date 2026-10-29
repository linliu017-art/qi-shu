"""Bind proposal inputs to authorized project template and case versions."""
from alembic import op
import sqlalchemy as sa
revision='e9c0d1e2f3a4'
down_revision='d8b9c0d1e2f3'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('proposal_input_sources',sa.Column('id',sa.String(36),primary_key=True),sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id'),nullable=False),sa.Column('draft_id',sa.String(36),sa.ForeignKey('proposal_drafts.id'),nullable=False),sa.Column('material_id',sa.String(36),sa.ForeignKey('materials.id'),nullable=False),sa.Column('kind',sa.String(20),nullable=False),sa.Column('version',sa.Integer(),nullable=False),sa.Column('state_version',sa.Integer(),nullable=False),sa.Column('file_hash',sa.String(64),nullable=False),sa.Column('text_hash',sa.String(64),nullable=False),sa.UniqueConstraint('draft_id','material_id','kind',name='uq_proposal_input_source'))
    op.create_index('ix_proposal_input_sources_project_id','proposal_input_sources',['project_id'])
    op.create_index('ix_proposal_input_sources_draft_id','proposal_input_sources',['draft_id'])

def downgrade():
    raise RuntimeError('方案输入依据包含用户数据，不支持自动降级。')
