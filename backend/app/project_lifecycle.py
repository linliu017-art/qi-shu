"""Reversible project lifecycle; not connected to the user interface yet."""
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .authorization import can_access
from .models import AnalysisTask, ProjectLifecycle, ProjectLifecycleEvent, ProposalDraft, QueuedJob


class LifecycleError(Exception):
    pass


def current_state(db: Session, project_id: str) -> tuple[str, int]:
    record = db.get(ProjectLifecycle, project_id)
    return (record.state, record.version) if record else ('active', 0)


def transition(db: Session, project_id: str, actor_id: str, action: str, version: int, confirm: bool = False) -> None:
    if not can_access(db, project_id, actor_id, 'archive'):
        raise PermissionError('只有负责人可以管理项目状态。')
    state, actual = current_state(db, project_id)
    if actual != version:
        raise LifecycleError('项目状态已改变，请刷新。')
    allowed = {('active', 'archive'): 'archived', ('archived', 'unarchive'): 'active',
               ('active', 'trash'): 'trash', ('archived', 'trash'): 'trash'}
    row = db.get(ProjectLifecycle, project_id)
    if action == 'restore' and state == 'trash' and row:
        new_state = row.before_trash or 'active'
    else:
        new_state = allowed.get((state, action))
    if not new_state or (action == 'trash' and not confirm):
        raise LifecycleError('当前状态不允许此操作，或尚未确认。')
    if action in ('archive', 'trash'):
        running = db.scalar(select(func.count()).select_from(QueuedJob).where(QueuedJob.project_id == project_id, QueuedJob.status.in_(['queued', 'running'])))
        running += db.scalar(select(func.count()).select_from(AnalysisTask).where(AnalysisTask.project_id == project_id, AnalysisTask.status.in_(['pending', 'running'])))
        running += db.scalar(select(func.count()).select_from(ProposalDraft).where(ProposalDraft.project_id == project_id, ProposalDraft.status.in_(['pending', 'running'])))
        if running:
            raise LifecycleError('项目仍有未结束任务，请先处理。')
    before = state if action == 'trash' else None
    try:
        if actual == 0:
            db.add(ProjectLifecycle(project_id=project_id, state=new_state, before_trash=before, version=1))
            db.flush()
        else:
            changed = db.execute(update(ProjectLifecycle).where(ProjectLifecycle.project_id == project_id,
                ProjectLifecycle.version == version).values(state=new_state, before_trash=before, version=version + 1))
            if changed.rowcount != 1:
                raise LifecycleError('项目状态已改变，请刷新。')
        db.add(ProjectLifecycleEvent(project_id=project_id, actor_id=actor_id, action=action))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise LifecycleError('项目状态已改变，请刷新。') from None
