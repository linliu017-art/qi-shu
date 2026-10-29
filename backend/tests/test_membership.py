import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.authorization import can_access
from app.database import Base
from app.membership import MembershipError, add_member, admin_handoff_disabled_owner, initialize_project_owner, member_role, remove_member, transfer_owner
from app.models import MembershipEvent, Project, ProjectMember, UserAccount


def test_project_isolation_membership_and_handoff():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = UserAccount(username='owner', password_hash='test', active=True, is_admin=False)
        member = UserAccount(username='member', password_hash='test', active=True, is_admin=False)
        admin = UserAccount(username='admin', password_hash='test', active=True, is_admin=True)
        outsider = UserAccount(username='outsider', password_hash='test', active=True, is_admin=False)
        db.add_all([owner, member, admin, outsider])
        db.flush()
        project = Project(name='虚构项目', background='')
        initialize_project_owner(db, project, owner.id)
        db.commit()
        assert member_role(db, project.id, admin.id) is None
        assert member_role(db, project.id, outsider.id) is None
        with pytest.raises(MembershipError):
            add_member(db, project.id, outsider.id, member.id)
        add_member(db, project.id, owner.id, member.id)
        assert member_role(db, project.id, member.id) == 'member'
        assert can_access(db, project.id, member.id, 'read')
        assert can_access(db, project.id, member.id, 'edit')
        assert not can_access(db, project.id, member.id, 'confirm_requirement')
        assert not can_access(db, project.id, member.id, 'approve_review')
        assert not can_access(db, project.id, admin.id, 'read')
        assert can_access(db, project.id, owner.id, 'approve_review')
        with pytest.raises(MembershipError):
            remove_member(db, project.id, member.id, owner.id)
        with pytest.raises(MembershipError):
            transfer_owner(db, project.id, owner.id, outsider.id, '交接')
        transfer_owner(db, project.id, owner.id, member.id, '交接')
        assert member_role(db, project.id, member.id) == 'owner'
        assert member_role(db, project.id, owner.id) == 'member'
        events = db.scalars(select(MembershipEvent).where(MembershipEvent.project_id == project.id)).all()
        assert [event.action for event in events] == ['created', 'added', 'transferred']
        assert events[-1].previous_owner_id == owner.id
        remove_member(db, project.id, member.id, owner.id)
        assert member_role(db, project.id, owner.id) is None
        assert not can_access(db, project.id, owner.id, 'read')
        member.active = False
        db.commit()
        assert member_role(db, project.id, member.id) is None
    engine.dispose()


def test_database_rejects_second_owner():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = UserAccount(username='first', password_hash='test', active=True, is_admin=False)
        second = UserAccount(username='second', password_hash='test', active=True, is_admin=False)
        db.add_all([first, second])
        db.flush()
        project = Project(name='虚构项目', background='')
        initialize_project_owner(db, project, first.id)
        db.commit()
        db.add(ProjectMember(project_id=project.id, user_id=second.id, role='owner'))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    engine.dispose()


def test_admin_can_reassign_disabled_owner_without_getting_project_access():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = UserAccount(username='owner', password_hash='test', active=True, is_admin=False)
        admin = UserAccount(username='admin', password_hash='test', active=True, is_admin=True)
        next_owner = UserAccount(username='new', password_hash='test', active=True, is_admin=False)
        db.add_all([owner, admin, next_owner]); db.flush()
        project = Project(name='虚构项目', background='')
        initialize_project_owner(db, project, owner.id); db.commit()
        with pytest.raises(MembershipError):
            admin_handoff_disabled_owner(db, project.id, admin.id, next_owner.id, '交接')
        owner.active = False; db.commit()
        admin_handoff_disabled_owner(db, project.id, admin.id, next_owner.id, '原负责人已停用')
        assert member_role(db, project.id, next_owner.id) == 'owner'
        assert member_role(db, project.id, admin.id) is None
        assert not can_access(db, project.id, admin.id, 'read')
    engine.dispose()
