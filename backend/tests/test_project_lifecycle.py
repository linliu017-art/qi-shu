import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.database import Base
from app.membership import add_member, initialize_project_owner
from app.models import Project, ProjectLifecycleEvent, UserAccount
from app.project_lifecycle import LifecycleError, current_state, transition


def test_archive_trash_restore_and_owner_permission(tmp_path):
    path = tmp_path / 'project.sqlite3'
    engine = create_engine(f'sqlite:///{path}')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = UserAccount(username='owner', password_hash='test', active=True, is_admin=False)
        member = UserAccount(username='member', password_hash='test', active=True, is_admin=False)
        db.add_all([owner, member])
        db.flush()
        project = Project(name='虚构项目', background='')
        initialize_project_owner(db, project, owner.id)
        db.commit()
        add_member(db, project.id, owner.id, member.id)
        with pytest.raises(PermissionError):
            transition(db, project.id, member.id, 'archive', 0)
        with pytest.raises(LifecycleError):
            transition(db, project.id, owner.id, 'trash', 0)
        transition(db, project.id, owner.id, 'archive', 0)
        with pytest.raises(LifecycleError):
            transition(db, project.id, owner.id, 'trash', 0, True)
        transition(db, project.id, owner.id, 'trash', 1, True)
        transition(db, project.id, owner.id, 'restore', 2)
        project_id = project.id
        assert current_state(db, project_id) == ('archived', 3)
        assert [e.action for e in db.scalars(select(ProjectLifecycleEvent)).all()] == ['archive', 'trash', 'restore']
    engine.dispose()
    engine = create_engine(f'sqlite:///{path}')
    with Session(engine) as db:
        assert current_state(db, project_id) == ('archived', 3)
        assert db.get(Project, project_id).name == '虚构项目'
    engine.dispose()
