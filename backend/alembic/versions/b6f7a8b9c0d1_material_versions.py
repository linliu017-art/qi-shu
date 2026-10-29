"""Track immutable material versions and reversible withdrawal."""
from alembic import op
import sqlalchemy as sa

revision = 'b6f7a8b9c0d1'
down_revision = 'a5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('material_versions',
        sa.Column('material_id', sa.String(36), sa.ForeignKey('materials.id'), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('group_id', sa.String(36), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('state', sa.String(20), nullable=False, server_default='active'),
        sa.Column('state_version', sa.Integer(), nullable=False, server_default='0'),
        sa.UniqueConstraint('project_id', 'group_id', 'version', name='uq_material_group_version'),
        sa.CheckConstraint("state IN ('active', 'withdrawn')", name='ck_material_state'))
    op.create_index('ix_material_versions_project_id', 'material_versions', ['project_id'])
    op.execute("INSERT INTO material_versions (material_id, project_id, group_id, version, state, state_version) SELECT id, project_id, id, 1, 'active', 0 FROM materials")
    op.create_table('material_state_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('material_id', sa.String(36), sa.ForeignKey('materials.id'), nullable=False),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('actor', sa.String(36), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    raise RuntimeError('资料版本和状态包含用户数据，不支持自动降级。')
