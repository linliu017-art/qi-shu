"""Assign durable per-project material group numbers without changing originals."""
from alembic import op
import sqlalchemy as sa

revision = 'f0d1e2f3a4b5'
down_revision = 'e9c0d1e2f3a4'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('material_labels',
        sa.Column('group_id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.UniqueConstraint('project_id', 'number', name='uq_material_label_number'))
    op.create_index('ix_material_labels_project_id', 'material_labels', ['project_id'])
    conn = op.get_bind()
    rows = conn.execute(sa.text('SELECT m.project_id, COALESCE(v.group_id, m.id) AS group_id, MIN(m.created_at) AS created FROM materials m LEFT JOIN material_versions v ON v.material_id=m.id GROUP BY m.project_id, COALESCE(v.group_id, m.id) ORDER BY m.project_id, created, group_id')).fetchall()
    counts = {}
    for project, group, _ in rows:
        counts[project] = counts.get(project, 0) + 1
        conn.execute(sa.text('INSERT INTO material_labels (group_id, project_id, number) VALUES (:group_id,:project_id,:number)'), {'group_id': group, 'project_id': project, 'number': counts[project]})

def downgrade():
    raise RuntimeError('资料编号包含用户引用，不支持自动降级。')
