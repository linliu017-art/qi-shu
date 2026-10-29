"""Persist version-bound content checks and human issue decisions."""
from alembic import op
import sqlalchemy as sa
revision='94d5e6f7a8b9'
down_revision='83c4d5e6f7a8'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('consistency_checks',
      sa.Column('id',sa.String(36),primary_key=True),
      sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id'),nullable=False),
      sa.Column('draft_id',sa.String(36),sa.ForeignKey('proposal_drafts.id'),nullable=False),
      sa.Column('actor_id',sa.String(36),nullable=False),sa.Column('base_version',sa.Integer(),nullable=False),
      sa.Column('content',sa.Text(),nullable=False),sa.Column('context',sa.Text(),nullable=False),
      sa.Column('source_warning',sa.String(500),nullable=False),sa.Column('source_signature',sa.Text(),nullable=False),sa.Column('model_name',sa.String(100),nullable=False),
      sa.Column('status',sa.String(20),nullable=False),sa.Column('error',sa.String(500),nullable=False),
      sa.Column('calls',sa.Integer(),nullable=False),sa.Column('prompt_tokens',sa.Integer()),sa.Column('completion_tokens',sa.Integer()),
      sa.Column('elapsed_ms',sa.Integer()),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_consistency_checks_draft_id','consistency_checks',['draft_id'])
    op.create_table('consistency_issues',
      sa.Column('id',sa.String(36),primary_key=True),sa.Column('check_id',sa.String(36),sa.ForeignKey('consistency_checks.id'),nullable=False),
      sa.Column('category',sa.String(30),nullable=False),sa.Column('description',sa.Text(),nullable=False),
      sa.Column('location_quote',sa.Text(),nullable=False),sa.Column('evidence_quote',sa.Text(),nullable=False),
      sa.Column('status',sa.String(20),nullable=False),sa.Column('decision_note',sa.Text(),nullable=False),
      sa.Column('decision_actor_id',sa.String(36)),sa.Column('decided_at',sa.DateTime(timezone=True)),sa.Column('version',sa.Integer(),nullable=False))
    op.create_index('ix_consistency_issues_check_id','consistency_issues',['check_id'])
    with op.batch_alter_table('queued_jobs',recreate='always') as batch:
        batch.drop_constraint('ck_queued_jobs_kind_v2',type_='check')
        batch.create_check_constraint('ck_queued_jobs_kind_v3',"kind IN ('requirements', 'proposal', 'section_edit', 'consistency')")


def downgrade():
    raise RuntimeError('检查和人工处理记录包含用户数据，不能自动降级。')
