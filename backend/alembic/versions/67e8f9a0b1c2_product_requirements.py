"""Persist product requirements and their auditable changes."""
from alembic import op
import sqlalchemy as sa

revision = '67e8f9a0b1c2'
down_revision = '56d7e8f9a0b1'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('product_requirements',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id'),nullable=True),
        sa.Column('creator_id',sa.String(36),nullable=False),
        sa.Column('title',sa.String(200),nullable=False),sa.Column('description',sa.Text(),nullable=False),
        sa.Column('priority',sa.String(20),nullable=False),sa.Column('status',sa.String(20),nullable=False),
        sa.Column('assignee_id',sa.String(36),nullable=True),sa.Column('iteration',sa.String(200),nullable=False),
        sa.Column('blocked_reason',sa.Text(),nullable=False),sa.Column('source_type',sa.String(30),nullable=False),
        sa.Column('source_id',sa.String(36),nullable=True),sa.Column('source_version',sa.Integer(),nullable=True),
        sa.Column('source_snapshot',sa.Text(),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_product_requirements_project_id','product_requirements',['project_id'])
    op.create_index('ix_product_requirements_creator_id','product_requirements',['creator_id'])
    op.create_table('product_requirement_events',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('requirement_id',sa.String(36),sa.ForeignKey('product_requirements.id'),nullable=False),
        sa.Column('actor_id',sa.String(36),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('before',sa.Text(),nullable=False),sa.Column('after',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_product_requirement_events_requirement_id','product_requirement_events',['requirement_id'])

def downgrade():
    raise RuntimeError('产品需求包含用户数据，不支持自动降级。')
