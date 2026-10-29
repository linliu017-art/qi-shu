"""Keep each attempt's actual model and operator when a task is resumed."""
from alembic import op
import sqlalchemy as sa

revision = '50f1a2b3c4d5'
down_revision = '49e0f1a2b3c4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('task_attempts', sa.Column('model_name', sa.String(100), nullable=True))
    op.add_column('task_attempts', sa.Column('actor_id', sa.String(36), nullable=True))
    op.create_table('task_model_changes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('task_id', sa.String(36), sa.ForeignKey('analysis_tasks.id'), nullable=False),
        sa.Column('actor_id', sa.String(36), nullable=False),
        sa.Column('previous_model', sa.String(100), nullable=False),
        sa.Column('new_model', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_task_model_changes_task_id', 'task_model_changes', ['task_id'])


def downgrade():
    op.drop_table('task_model_changes')
    op.drop_column('task_attempts', 'actor_id')
    op.drop_column('task_attempts', 'model_name')
