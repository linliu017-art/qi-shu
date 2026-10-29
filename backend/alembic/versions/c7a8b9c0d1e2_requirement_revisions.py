"""Keep human-entered requirements and revision suggestions without rewriting old rows."""
from alembic import op
import sqlalchemy as sa
revision='c7a8b9c0d1e2'
down_revision='b6f7a8b9c0d1'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('manual_requirements', sa.Column('id', sa.String(36), primary_key=True), sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False), sa.Column('text', sa.Text(), nullable=False), sa.Column('original_text', sa.Text(), nullable=False), sa.Column('status', sa.String(20), nullable=False), sa.Column('version', sa.Integer(), nullable=False), sa.Column('created_by', sa.String(36), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_manual_requirements_project_id','manual_requirements',['project_id'])
    op.create_table('manual_requirement_events', sa.Column('id',sa.String(36),primary_key=True), sa.Column('requirement_id',sa.String(36),sa.ForeignKey('manual_requirements.id'),nullable=False), sa.Column('from_version',sa.Integer(),nullable=False), sa.Column('old_text',sa.Text(),nullable=False), sa.Column('new_text',sa.Text(),nullable=False), sa.Column('old_status',sa.String(20),nullable=False), sa.Column('new_status',sa.String(20),nullable=False), sa.Column('actor',sa.String(36),nullable=False), sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_manual_requirement_events_requirement_id','manual_requirement_events',['requirement_id'])
    op.create_table('requirement_revision_suggestions', sa.Column('id',sa.String(36),primary_key=True), sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id'),nullable=False), sa.Column('requirement_id',sa.String(36),nullable=False), sa.Column('base_version',sa.Integer(),nullable=False), sa.Column('original_text',sa.Text(),nullable=False), sa.Column('proposed_text',sa.Text(),nullable=False), sa.Column('status',sa.String(20),nullable=False), sa.Column('created_by',sa.String(36),nullable=False), sa.Column('created_at',sa.DateTime(timezone=True),nullable=False), sa.Column('decided_by',sa.String(36)), sa.Column('decided_at',sa.DateTime(timezone=True)))
    op.create_index('ix_requirement_revision_suggestions_project_id','requirement_revision_suggestions',['project_id'])
    op.create_index('ix_requirement_revision_suggestions_requirement_id','requirement_revision_suggestions',['requirement_id'])

def downgrade():
    raise RuntimeError('人工需求与修订建议包含用户数据，不支持自动降级。')
