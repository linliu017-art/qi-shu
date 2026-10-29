"""Project membership operations. Not yet connected to HTTP routes."""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .models import MembershipEvent, Project, ProjectLifecycle, ProjectMember, UserAccount


class MembershipError(Exception):
    pass


def member_role(db: Session, project_id: str, user_id: str) -> str | None:
    return db.scalar(select(ProjectMember.role).join(UserAccount, ProjectMember.user_id == UserAccount.id)
                     .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id,
                            UserAccount.active.is_(True)))


def _require_owner(db: Session, project_id: str, actor_id: str) -> None:
    if member_role(db, project_id, actor_id) != 'owner':
        raise MembershipError('只有项目负责人可以管理成员。')


def add_member(db: Session, project_id: str, actor_id: str, target_id: str) -> None:
    _require_owner(db, project_id, actor_id)
    target = db.get(UserAccount, target_id)
    if not target or not target.active:
        raise MembershipError('请选择已启用账号。')
    if member_role(db, project_id, target_id):
        raise MembershipError('该账号已是项目成员。')
    db.add(ProjectMember(project_id=project_id, user_id=target_id, role='member'))
    db.add(MembershipEvent(project_id=project_id, actor_id=actor_id, target_id=target_id, action='added'))
    db.commit()


def remove_member(db: Session, project_id: str, actor_id: str, target_id: str) -> None:
    _require_owner(db, project_id, actor_id)
    row = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == target_id))
    if not row or row.role != 'member':
        raise MembershipError('只能移除普通成员。')
    db.delete(row)
    db.add(MembershipEvent(project_id=project_id, actor_id=actor_id, target_id=target_id, action='removed'))
    db.commit()


def transfer_owner(db: Session, project_id: str, actor_id: str, target_id: str, reason: str) -> None:
    actor = db.get(UserAccount, actor_id)
    old = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.role == 'owner'))
    target = db.scalar(select(ProjectMember).join(UserAccount, ProjectMember.user_id == UserAccount.id)
                       .where(ProjectMember.project_id == project_id, ProjectMember.user_id == target_id,
                              ProjectMember.role == 'member', UserAccount.active.is_(True)))
    if not actor or not actor.active or not old or not target or not reason.strip():
        raise MembershipError('请选择启用的项目成员并填写转交原因。')
    if old.user_id != actor_id and not actor.is_admin:
        raise MembershipError('只有负责人或管理员可以调整负责人。')
    previous = old.user_id
    changed = db.execute(update(ProjectMember).where(ProjectMember.id == old.id, ProjectMember.role == 'owner')
                         .values(role='member'))
    if changed.rowcount != 1:
        db.rollback()
        raise MembershipError('负责人已改变，请刷新。')
    db.flush()
    promoted = db.execute(update(ProjectMember).where(ProjectMember.id == target.id, ProjectMember.role == 'member',
                          ProjectMember.user_id.in_(select(UserAccount.id).where(UserAccount.active.is_(True))))
                          .values(role='owner'))
    if promoted.rowcount != 1:
        db.rollback()
        raise MembershipError('接任成员状态已改变，请刷新。')
    db.add(MembershipEvent(project_id=project_id, actor_id=actor_id, target_id=target_id,
                           previous_owner_id=previous, action='transferred', reason=reason.strip()))
    db.commit()


def initialize_project_owner(db: Session, project: Project, user_id: str) -> None:
    """Call in the same transaction that creates a new project; never assign old projects."""
    user = db.get(UserAccount, user_id)
    if not user or not user.active:
        raise MembershipError('账号不可用。')
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user_id, role='owner'))
    db.add(MembershipEvent(project_id=project.id, actor_id=user_id, target_id=user_id, action='created'))


def admin_handoff_disabled_owner(db: Session, project_id: str, actor_id: str, target_id: str, reason: str) -> None:
    actor, target = db.get(UserAccount, actor_id), db.get(UserAccount, target_id)
    old = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.role == 'owner'))
    old_account = db.get(UserAccount, old.user_id) if old else None
    lifecycle = db.get(ProjectLifecycle, project_id)
    if (not actor or not actor.active or not actor.is_admin or not target or not target.active
            or not old or not old_account or old_account.active or not reason.strip()
            or (lifecycle and lifecycle.state == 'trash')):
        raise MembershipError('无法执行待交接项目调整。')
    existing = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == target_id))
    if not existing:
        db.add(ProjectMember(project_id=project_id, user_id=target_id, role='member'))
        db.add(MembershipEvent(project_id=project_id, actor_id=actor_id, target_id=target_id, action='added', reason=reason.strip()))
        db.flush()
    transfer_owner(db, project_id, actor_id, target_id, reason)


def assign_legacy_project(db: Session, project_id: str, actor_id: str, target_id: str, reason: str) -> None:
    actor, target, project = db.get(UserAccount, actor_id), db.get(UserAccount, target_id), db.get(Project, project_id)
    existing = db.scalar(select(ProjectMember.id).where(ProjectMember.project_id == project_id).limit(1))
    if (not actor or not actor.active or not actor.is_admin or not target or not target.active
            or not project or existing or not reason.strip()):
        raise MembershipError('旧项目无法分配，请检查状态和账号。')
    db.add(ProjectMember(project_id=project_id, user_id=target_id, role='owner'))
    db.add(MembershipEvent(project_id=project_id, actor_id=actor_id, target_id=target_id, action='claimed', reason=reason.strip()))
    db.commit()
