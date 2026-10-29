"""Enforce one project owner and record membership changes."""
from alembic import op
import sqlalchemy as sa

revision = 'b0c1d2e3f4a5'
down_revision = 'a9b8c7d6e5f4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('project_members') as batch:
        batch.create_check_constraint('ck_project_member_role', "role IN ('owner', 'member')")
    op.create_index('uq_project_one_owner', 'project_members', ['project_id'], unique=True,
                    sqlite_where=sa.text("role = 'owner'"), postgresql_where=sa.text("role = 'owner'"))
    op.create_table('membership_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('actor_id', sa.String(36), sa.ForeignKey('user_accounts.id'), nullable=False),
        sa.Column('target_id', sa.String(36), sa.ForeignKey('user_accounts.id'), nullable=False),
        sa.Column('previous_owner_id', sa.String(36), sa.ForeignKey('user_accounts.id'), nullable=True),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_membership_events_project_id', 'membership_events', ['project_id'])


def downgrade():
    op.drop_table('membership_events')
    op.drop_index('uq_project_one_owner', table_name='project_members')
    with op.batch_alter_table('project_members') as batch:
        batch.drop_constraint('ck_project_member_role', type_='check')
