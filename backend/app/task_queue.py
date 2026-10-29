"""Persistent SQLite queue primitives. Not yet connected to task execution or the API."""
from sqlalchemy import Engine, exists, func, select, update
from sqlalchemy.orm import Session

from .authorization import can_access
from .membership import member_role
from .models import AnalysisTask, ProjectLifecycle, ProjectMember, ProposalDraft, SectionEdit, ConsistencyCheck, QueueSettings, QueueSettingsEvent, QueuedJob, UserAccount


def enqueue(db: Session, project_id: str, user_id: str, kind: str, target_id: str) -> QueuedJob:
    if kind not in ('requirements', 'proposal', 'section_edit', 'consistency') or not can_access(db, project_id, user_id, 'edit'):
        raise PermissionError('无权发起任务。')
    lifecycle = db.get(ProjectLifecycle, project_id)
    if lifecycle and lifecycle.state != 'active':
        raise PermissionError('项目已归档或移入回收站。')
    job = db.scalar(select(QueuedJob).where(QueuedJob.kind == kind, QueuedJob.target_id == target_id))
    if job:
        if job.project_id != project_id or job.status not in ('failed', 'interrupted', 'cancelled'):
            raise ValueError('该任务已在队列中或已完成。')
        job.user_id, job.status = user_id, 'queued'
    else:
        job = QueuedJob(project_id=project_id, user_id=user_id, kind=kind, target_id=target_id, status='queued')
        db.add(job)
    db.flush()
    return job


def set_limit(db: Session, actor_id: str, limit: int | None) -> None:
    actor = db.get(UserAccount, actor_id)
    if not actor or not actor.active or not actor.is_admin:
        raise PermissionError('无权修改任务并发设置。')
    if limit is not None and not 1 <= limit <= 1000:
        raise ValueError('并发上限必须为正整数。')
    config = db.get(QueueSettings, 1)
    old_limit = config.max_running if config else None
    if old_limit == limit:
        return
    if not config:
        config = QueueSettings(id=1, max_running=limit)
        db.add(config)
    else:
        config.max_running = limit
    db.add(QueueSettingsEvent(actor_id=actor_id, old_limit=old_limit, new_limit=limit))
    db.commit()


def claim_next(engine: Engine) -> tuple[str, str, str] | None:
    """Claim atomically across processes; SQLite only until another backend is validated."""
    if engine.dialect.name != 'sqlite':
        raise RuntimeError('此调度器仅支持本地 SQLite。')
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        try:
            active_member = exists(select(ProjectMember.id).join(UserAccount, UserAccount.id == ProjectMember.user_id)
                .where(ProjectMember.project_id == QueuedJob.project_id, ProjectMember.user_id == QueuedJob.user_id,
                       UserAccount.active.is_(True)))
            revoked = connection.execute(select(QueuedJob.kind, QueuedJob.target_id)
                                         .where(QueuedJob.status == 'queued', ~active_member)).all()
            for kind, target_id in revoked:
                model = {'requirements': AnalysisTask, 'proposal': ProposalDraft, 'section_edit': SectionEdit, 'consistency': ConsistencyCheck}[kind]
                connection.execute(update(model).where(model.id == target_id, model.status == 'pending')
                                   .values(status='interrupted', error='提交人已失去项目权限，任务未执行。'))
            connection.execute(update(QueuedJob).where(QueuedJob.status == 'queued', ~active_member).values(status='cancelled'))
            limit = connection.execute(select(QueueSettings.max_running).where(QueueSettings.id == 1)).scalar_one_or_none()
            running = connection.execute(select(func.count()).select_from(QueuedJob).where(QueuedJob.status == 'running')).scalar_one()
            if limit is not None and running >= limit:
                connection.commit()
                return None
            row = connection.execute(select(QueuedJob.id, QueuedJob.kind, QueuedJob.target_id)
                .where(QueuedJob.status == 'queued').order_by(QueuedJob.created_at, QueuedJob.id).limit(1)).first()
            if row:
                connection.execute(update(QueuedJob).where(QueuedJob.id == row.id, QueuedJob.status == 'queued').values(status='running'))
            connection.commit()
            return (row.id, row.kind, row.target_id) if row else None
        except Exception:
            connection.rollback()
            raise


def finish(db: Session, job_id: str, success: bool, cancelled: bool = False) -> bool:
    result = db.execute(update(QueuedJob).where(QueuedJob.id == job_id, QueuedJob.status == 'running')
                        .values(status='cancelled' if cancelled else 'completed' if success else 'failed'))
    db.commit()
    return result.rowcount == 1


def interrupt_after_shutdown(db: Session) -> int:
    """Mark abandoned work only when the caller knows all previous workers are stopped.

    Never silently re-send work that might already have reached the model provider.
    """
    result = db.execute(update(QueuedJob).where(QueuedJob.status == 'running').values(status='interrupted'))
    db.commit()
    return result.rowcount


def cancel_queued(db: Session, project_id: str, actor_id: str, job_id: str) -> bool:
    if not can_access(db, project_id, actor_id, 'edit'):
        raise PermissionError('无权取消任务。')
    job = db.get(QueuedJob, job_id)
    if not job or job.project_id != project_id or (job.user_id != actor_id and member_role(db, project_id, actor_id) != 'owner'):
        raise PermissionError('无权取消任务。')
    result = db.execute(update(QueuedJob).where(QueuedJob.id == job_id, QueuedJob.project_id == project_id,
                                                QueuedJob.status == 'queued').values(status='cancelled'))
    model = {'requirements': AnalysisTask, 'proposal': ProposalDraft, 'section_edit': SectionEdit, 'consistency': ConsistencyCheck}[job.kind]
    if result.rowcount == 1:
        db.execute(update(model).where(model.id == job.target_id, model.project_id == project_id, model.status == 'pending')
                   .values(status='cancelled', error='任务排队期间已取消。'))
    else:
        changed = db.execute(update(model).where(model.id == job.target_id, model.project_id == project_id,
                             model.status.in_(['pending', 'running']), select(QueuedJob.id).where(QueuedJob.id == job_id,
                             QueuedJob.status == 'running').exists())
                             .values(status='cancelled', error='已请求取消；已发出的请求可能产生费用。'))
        if changed.rowcount != 1:
            db.rollback()
            return False
    db.commit()
    return True
