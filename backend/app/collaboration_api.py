"""Account and membership HTTP routes, deliberately unmounted until access is enforced everywhere."""
from fastapi import APIRouter, Depends, Request, Response
from uuid import uuid4, UUID
from decimal import Decimal
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import DATA_DIR, SessionLocal
from .backup import BackupError, create_backup, restore_safe_copy
from .identity import authenticate, create_account, disable_account, enable_account, login_throttled, logout, reset_password
from .credentials import hash_password
from .membership import MembershipError, add_member, admin_handoff_disabled_owner, assign_legacy_project, member_role, remove_member, transfer_owner
from .models import AnalysisTask, Project, ProjectLifecycle, ProjectMember, ProposalDraft, SectionEdit, ConsistencyCheck, ProposalPricing, PurgeJob, QueueSettings, QueuedJob, TaskAttempt, TaskPricing, UserAccount
from .project_lifecycle import LifecycleError, current_state, transition
from .project_purge import PurgeError, cleanup, impact, purge
from .task_queue import cancel_queued, set_limit
from .model_settings import model_key, model_settings, save_settings

router = APIRouter(prefix='/api/v1')


class CollaborationError(Exception):
    def __init__(self, code: str, message: str, status: int):
        self.code, self.message, self.status = code, message, status


def db_session():
    with SessionLocal() as db:
        yield db


def current_user(request: Request, db: Session = Depends(db_session)) -> UserAccount:
    token = request.cookies.get('qishu_session', '')
    user = authenticate(db, token)
    if not user:
        raise CollaborationError('UNAUTHENTICATED', '请先登录。', 401)
    return user


def admin(user: UserAccount = Depends(current_user)) -> UserAccount:
    if not user.is_admin:
        raise CollaborationError('FORBIDDEN', '没有账号管理权限。', 403)
    return user


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class PasswordReset(BaseModel):
    password: str = Field(min_length=12, max_length=256)


class AccountOutput(BaseModel):
    id: str
    username: str
    active: bool
    is_admin: bool


class MembershipInput(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)


class TransferInput(MembershipInput):
    reason: str = Field(min_length=1, max_length=1000)


class MemberOutput(BaseModel):
    user_id: str
    username: str
    active: bool
    role: str


class QueueLimitInput(BaseModel):
    max_running: int | None = Field(default=None, ge=1, le=1000)


class QueueLimitOutput(BaseModel):
    max_running: int | None


class JobOutput(BaseModel):
    id: str
    kind: str
    target_id: str
    status: str
    can_cancel: bool


class LifecycleInput(BaseModel):
    version: int = Field(ge=0)
    confirm: bool = False


class LifecycleOutput(BaseModel):
    state: str
    version: int


class BackupOutput(BaseModel):
    id: str


class SetupStatus(BaseModel):
    setup_required: bool


class PurgeImpact(BaseModel):
    project_id: str
    name: str
    materials: int
    requirements: int
    proposals: int
    product_work: int
    product_requirements: int


class PurgeInput(BaseModel):
    confirmed_name: str = Field(min_length=1, max_length=200)
    confirm: bool = False


class PurgeOutput(BaseModel):
    id: str
    status: str
    backup_id: str


class HandoffOutput(BaseModel):
    project_id: str
    name: str
    previous_owner: str
    candidates: list[MemberOutput]


class LegacyProjectOutput(BaseModel):
    project_id: str
    name: str


class ModelSettingsInput(BaseModel):
    allowed_models: list[str] = Field(min_length=1, max_length=20)
    max_requests: int = Field(ge=1, le=1000)


class ModelSettingsOutput(ModelSettingsInput):
    key_configured: bool


class UsageOutput(BaseModel):
    actor_name: str
    calls: int
    known_prompt_tokens: int
    known_completion_tokens: int
    usage_complete: bool
    estimated_cost_usd: float | None


def backup_root():
    root = DATA_DIR / 'backups' / 'manual'
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise CollaborationError('BACKUP_FAILED', '备份目录不可用。', 500)
    return root


def safe_backup_id(backup_id: str) -> str:
    try:
        if str(UUID(backup_id)) != backup_id:
            raise ValueError
        return backup_id
    except ValueError:
        raise CollaborationError('NOT_FOUND', '找不到备份。', 404) from None


@router.get('/auth/setup-status', response_model=SetupStatus)
def setup_status(request: Request, db: Session = Depends(db_session)):
    if not request.client or request.client.host not in ('127.0.0.1', '::1', 'testclient'):
        raise CollaborationError('FORBIDDEN', '初始化只允许在本机进行。', 403)
    return SetupStatus(setup_required=db.scalar(select(func.count()).select_from(UserAccount)) == 0)


@router.post('/auth/setup', response_model=AccountOutput, status_code=201)
def setup_admin(body: Credentials, request: Request, db: Session = Depends(db_session)):
    if not request.client or request.client.host not in ('127.0.0.1', '::1', 'testclient'):
        raise CollaborationError('FORBIDDEN', '初始化只允许在本机进行。', 403)
    if db.get_bind().dialect.name != 'sqlite':
        raise CollaborationError('INVALID_STATE', '此初始化方式仅支持本机数据库。', 409)
    try:
        name = body.username.strip()
        if not name or any(ord(c) < 32 for c in name):
            raise ValueError
        digest = hash_password(body.password)
        db.execute(text('BEGIN IMMEDIATE'))
        if db.scalar(select(func.count()).select_from(UserAccount)):
            db.rollback()
            raise CollaborationError('INVALID_STATE', '管理员已初始化。', 409)
        user = UserAccount(username=name, password_hash=digest, active=True, is_admin=True)
        db.add(user)
        db.commit()
        return AccountOutput(id=user.id, username=user.username, active=user.active, is_admin=user.is_admin)
    except (ValueError, IntegrityError):
        db.rollback()
        raise CollaborationError('INVALID_ACCOUNT', '请输入有效账号和至少 12 个字符的密码。', 422) from None


@router.post('/auth/login', response_model=AccountOutput)
def login_route(body: Credentials, response: Response, db: Session = Depends(db_session)):
    token = login_throttled(db, body.username.strip(), body.password)
    if not token:
        raise CollaborationError('LOGIN_FAILED', '账号或密码不正确。', 401)
    user = authenticate(db, token)
    response.set_cookie('qishu_session', token, httponly=True, samesite='strict', secure=True, max_age=43200, path='/')
    return AccountOutput(id=user.id, username=user.username, active=user.active, is_admin=user.is_admin)


@router.post('/auth/logout', status_code=204)
def logout_route(request: Request, response: Response, db: Session = Depends(db_session)):
    logout(db, request.cookies.get('qishu_session', ''))
    response.delete_cookie('qishu_session', path='/', secure=True, httponly=True, samesite='strict')


@router.get('/auth/me', response_model=AccountOutput)
def me(user: UserAccount = Depends(current_user)):
    return AccountOutput(id=user.id, username=user.username, active=user.active, is_admin=user.is_admin)


@router.get('/accounts', response_model=list[AccountOutput])
def accounts(_actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    return [AccountOutput(id=u.id, username=u.username, active=u.active, is_admin=u.is_admin)
            for u in db.scalars(select(UserAccount).order_by(UserAccount.username))]


@router.get('/directory', response_model=list[AccountOutput])
def directory(_actor: UserAccount = Depends(current_user), db: Session = Depends(db_session)):
    return [AccountOutput(id=u.id, username=u.username, active=u.active, is_admin=u.is_admin)
            for u in db.scalars(select(UserAccount).where(UserAccount.active.is_(True)).order_by(UserAccount.username))]


@router.post('/accounts', response_model=AccountOutput, status_code=201)
def create_account_route(body: Credentials, actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    try:
        u = create_account(db, actor.id, body.username, body.password)
        return AccountOutput(id=u.id, username=u.username, active=u.active, is_admin=u.is_admin)
    except (ValueError, IntegrityError):
        db.rollback()
        raise CollaborationError('INVALID_ACCOUNT', '账号无法创建，请检查名称及密码。', 422) from None


@router.post('/accounts/{user_id}/disable', status_code=204)
def disable_route(user_id: str, actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    try:
        disable_account(db, actor.id, user_id)
    except (ValueError, PermissionError):
        raise CollaborationError('INVALID_ACCOUNT', '账号无法停用。', 422) from None


@router.post('/accounts/{user_id}/enable', status_code=204)
def enable_route(user_id: str, actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    try:
        enable_account(db, actor.id, user_id)
    except ValueError:
        raise CollaborationError('INVALID_ACCOUNT', '账号无法启用。', 422) from None


@router.post('/accounts/{user_id}/password', status_code=204)
def password_route(user_id: str, body: PasswordReset, actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    try:
        reset_password(db, actor.id, user_id, body.password)
    except ValueError:
        raise CollaborationError('INVALID_ACCOUNT', '密码无法重设。', 422) from None


@router.get('/projects/{project_id}/members', response_model=list[MemberOutput])
def members(project_id: str, actor: UserAccount = Depends(current_user), db: Session = Depends(db_session)):
    if not member_role(db, project_id, actor.id):
        raise CollaborationError('NOT_FOUND', '找不到这个项目。', 404)
    pairs = db.execute(select(ProjectMember, UserAccount).join(UserAccount, UserAccount.id == ProjectMember.user_id)
                       .where(ProjectMember.project_id == project_id)).all()
    return [MemberOutput(user_id=u.id, username=u.username, active=u.active, role=m.role) for m, u in pairs]


@router.post('/projects/{project_id}/members', status_code=204)
def add_member_route(project_id: str, body: MembershipInput, actor: UserAccount = Depends(current_user), db: Session = Depends(db_session)):
    try:
        add_member(db, project_id, actor.id, body.user_id)
    except (MembershipError, IntegrityError):
        db.rollback()
        raise CollaborationError('MEMBERSHIP_ERROR', '无法添加成员，请检查权限与账号状态。', 409) from None


@router.delete('/projects/{project_id}/members/{user_id}', status_code=204)
def remove_member_route(project_id: str, user_id: str, actor: UserAccount = Depends(current_user), db: Session = Depends(db_session)):
    try:
        remove_member(db, project_id, actor.id, user_id)
    except MembershipError:
        db.rollback()
        raise CollaborationError('MEMBERSHIP_ERROR', '无法移除成员，请检查权限。', 409) from None


@router.post('/projects/{project_id}/transfer', status_code=204)
def transfer_route(project_id: str, body: TransferInput, actor: UserAccount = Depends(current_user), db: Session = Depends(db_session)):
    try:
        transfer_owner(db, project_id, actor.id, body.user_id, body.reason)
    except (MembershipError, IntegrityError):
        db.rollback()
        raise CollaborationError('MEMBERSHIP_ERROR', '无法转交负责人，请检查账号与项目状态。', 409) from None


@router.get('/queue/settings', response_model=QueueLimitOutput)
def queue_settings(_actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    settings = db.get(QueueSettings, 1)
    return QueueLimitOutput(max_running=settings.max_running if settings else None)


@router.put('/queue/settings', response_model=QueueLimitOutput)
def update_queue_settings(body: QueueLimitInput, actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    set_limit(db, actor.id, body.max_running)
    return QueueLimitOutput(max_running=body.max_running)


@router.get('/admin/model-settings', response_model=ModelSettingsOutput)
def get_model_settings(_actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    models, maximum = model_settings(db)
    return ModelSettingsOutput(allowed_models=models, max_requests=maximum, key_configured=bool(model_key()))


@router.put('/admin/model-settings', response_model=ModelSettingsOutput)
def update_model_settings(body: ModelSettingsInput, actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    try:
        save_settings(db, actor.id, body.allowed_models, body.max_requests)
        models, maximum = model_settings(db)
        return ModelSettingsOutput(allowed_models=models, max_requests=maximum, key_configured=bool(model_key()))
    except ValueError:
        db.rollback()
        raise CollaborationError('INVALID_INPUT', '模型名称或任务调用上限不正确。', 422) from None


@router.get('/projects/{project_id}/queue', response_model=list[JobOutput])
def project_queue(project_id: str, actor: UserAccount = Depends(current_user), db: Session = Depends(db_session)):
    role = member_role(db, project_id, actor.id)
    if not role:
        raise CollaborationError('NOT_FOUND', '找不到这个项目。', 404)
    result = []
    for j in db.scalars(select(QueuedJob).where(QueuedJob.project_id == project_id).order_by(QueuedJob.created_at.desc())):
        target = db.get({'requirements': AnalysisTask, 'proposal': ProposalDraft, 'section_edit': SectionEdit, 'consistency': ConsistencyCheck}[j.kind], j.target_id)
        status = 'cancel_requested' if j.status == 'running' and target and target.status == 'cancelled' else j.status
        result.append(JobOutput(id=j.id, kind=j.kind, target_id=j.target_id, status=status,
                                can_cancel=(role == 'owner' or j.user_id == actor.id) and status in ('queued', 'running')))
    return result


@router.get('/projects/{project_id}/usage', response_model=list[UsageOutput])
def project_usage(project_id: str, actor: UserAccount = Depends(current_user), db: Session = Depends(db_session)):
    if not member_role(db, project_id, actor.id):
        raise CollaborationError('NOT_FOUND', '找不到这个项目。', 404)
    groups: dict[str, dict] = {}
    def add(user_id, calls, prompt, completion, complete, prices):
        key = user_id or 'local-user'
        group = groups.setdefault(key, {'calls':0, 'prompt':0, 'completion':0, 'complete':True, 'price_complete':True, 'price':Decimal(0)})
        group['calls'] += calls
        group['prompt'] += prompt or 0
        group['completion'] += completion or 0
        group['complete'] = group['complete'] and complete
        if not complete or not prices:
            group['price_complete'] = False
        else:
            group['price'] += (Decimal(prompt) * Decimal(prices[0]) + Decimal(completion) * Decimal(prices[1])) / Decimal(1000000)
    attempts = db.execute(select(TaskAttempt, TaskPricing).join(AnalysisTask, AnalysisTask.id == TaskAttempt.task_id)
        .outerjoin(TaskPricing, TaskPricing.task_id == AnalysisTask.id).where(AnalysisTask.project_id == project_id)).all()
    for attempt, price in attempts:
        complete = attempt.prompt_tokens is not None and attempt.completion_tokens is not None
        prices = (price.input_per_million, price.output_per_million) if price and attempt.model_name == 'deepseek-flash' else None
        add(attempt.actor_id, 1, attempt.prompt_tokens, attempt.completion_tokens, complete, prices)
    drafts = db.execute(select(ProposalDraft, ProposalPricing).outerjoin(ProposalPricing, ProposalPricing.draft_id == ProposalDraft.id)
                        .where(ProposalDraft.project_id == project_id, ProposalDraft.calls > 0)).all()
    for draft, price in drafts:
        complete = draft.calls == 1 and draft.prompt_tokens is not None and draft.completion_tokens is not None
        prices = (price.input_per_million, price.output_per_million) if price and draft.model_name == 'deepseek-flash' else None
        add(draft.created_by, draft.calls, draft.prompt_tokens, draft.completion_tokens, complete, prices)
    for edit in db.scalars(select(SectionEdit).where(SectionEdit.project_id == project_id, SectionEdit.calls > 0)):
        complete = edit.calls == 1 and edit.prompt_tokens is not None and edit.completion_tokens is not None
        # No frozen price for these tasks; unknown instead of inventing a cost.
        add(edit.actor_id, edit.calls, edit.prompt_tokens, edit.completion_tokens, complete, None)
    for check in db.scalars(select(ConsistencyCheck).where(ConsistencyCheck.project_id == project_id, ConsistencyCheck.calls > 0)):
        complete = check.calls == 1 and check.prompt_tokens is not None and check.completion_tokens is not None
        add(check.actor_id, check.calls, check.prompt_tokens, check.completion_tokens, complete, None)
    result = []
    for user_id, group in groups.items():
        user = db.get(UserAccount, user_id)
        result.append(UsageOutput(actor_name=user.username if user else '历史本机操作', calls=group['calls'],
            known_prompt_tokens=group['prompt'], known_completion_tokens=group['completion'], usage_complete=group['complete'],
            estimated_cost_usd=float(group['price']) if group['price_complete'] else None))
    return result


@router.post('/projects/{project_id}/queue/{job_id}/cancel', status_code=204)
def cancel_queue_job(project_id: str, job_id: str, actor: UserAccount = Depends(current_user), db: Session = Depends(db_session)):
    try:
        if not cancel_queued(db, project_id, actor.id, job_id):
            raise CollaborationError('INVALID_STATE', '任务已结束或正在取消，无法再次取消。', 409)
    except PermissionError:
        raise CollaborationError('NOT_FOUND', '找不到这个任务。', 404) from None


@router.get('/projects/{project_id}/lifecycle', response_model=LifecycleOutput)
def lifecycle(project_id: str, actor: UserAccount = Depends(current_user), db: Session = Depends(db_session)):
    if not member_role(db, project_id, actor.id):
        raise CollaborationError('NOT_FOUND', '找不到这个项目。', 404)
    state, version = current_state(db, project_id)
    return LifecycleOutput(state=state, version=version)


@router.post('/projects/{project_id}/{action}', response_model=LifecycleOutput)
def project_transition(project_id: str, action: str, body: LifecycleInput, actor: UserAccount = Depends(current_user), db: Session = Depends(db_session)):
    if action not in ('archive', 'unarchive', 'trash', 'restore'):
        raise CollaborationError('NOT_FOUND', '找不到此操作。', 404)
    try:
        transition(db, project_id, actor.id, action, body.version, body.confirm)
        state, version = current_state(db, project_id)
        return LifecycleOutput(state=state, version=version)
    except PermissionError:
        raise CollaborationError('FORBIDDEN', '此操作需要项目负责人执行。', 403) from None
    except LifecycleError as exc:
        db.rollback()
        raise CollaborationError('INVALID_STATE', str(exc), 409) from None


@router.get('/admin/backups', response_model=list[BackupOutput])
def backups(_actor: UserAccount = Depends(admin)):
    root = backup_root()
    items = []
    for child in root.iterdir():
        try:
            if child.is_dir() and not child.is_symlink():
                safe_backup_id(child.name)
                items.append(BackupOutput(id=child.name))
        except CollaborationError:
            continue
    return items


@router.post('/admin/backups', response_model=BackupOutput, status_code=201)
def make_backup(_actor: UserAccount = Depends(admin)):
    backup_id = str(uuid4())
    try:
        create_backup(DATA_DIR, backup_root() / backup_id)
    except (BackupError, OSError):
        raise CollaborationError('BACKUP_FAILED', '备份失败，请检查资料和本机存储。', 500) from None
    return BackupOutput(id=backup_id)


@router.post('/admin/backups/{backup_id}/restore-copy', response_model=BackupOutput, status_code=201)
def restore_backup(backup_id: str, _actor: UserAccount = Depends(admin)):
    backup_id = safe_backup_id(backup_id)
    copies = DATA_DIR / 'restored-copies'
    copies.mkdir(mode=0o700, parents=True, exist_ok=True)
    if copies.is_symlink():
        raise CollaborationError('BACKUP_FAILED', '恢复目录不可用。', 500)
    copy_id = str(uuid4())
    try:
        restore_safe_copy(backup_root() / backup_id, copies / copy_id, DATA_DIR)
    except BackupError as exc:
        raise CollaborationError('BACKUP_REVIEW_REQUIRED', str(exc), 409) from None
    except OSError:
        raise CollaborationError('BACKUP_FAILED', '恢复副本失败，请检查备份。', 500) from None
    return BackupOutput(id=copy_id)


@router.get('/admin/trash', response_model=list[PurgeImpact])
def admin_trash(actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    ids = list(db.scalars(select(Project.id).join(ProjectLifecycle, ProjectLifecycle.project_id == Project.id)
                          .where(ProjectLifecycle.state == 'trash')))
    result = []
    for project_id in ids:
        try:
            result.append(PurgeImpact(**impact(db, actor.id, project_id)))
        except PurgeError:
            continue
    return result


@router.get('/admin/handoffs', response_model=list[HandoffOutput])
def handoffs(_actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    rows = db.execute(select(Project, UserAccount).join(ProjectMember, ProjectMember.project_id == Project.id)
                      .join(UserAccount, UserAccount.id == ProjectMember.user_id)
                      .where(ProjectMember.role == 'owner', UserAccount.active.is_(False))).all()
    result = []
    for project, previous in rows:
        lifecycle = db.get(ProjectLifecycle, project.id)
        if lifecycle and lifecycle.state == 'trash':
            continue
        candidates = db.scalars(select(UserAccount).where(UserAccount.active.is_(True)).order_by(UserAccount.username)).all()
        result.append(HandoffOutput(project_id=project.id, name=project.name, previous_owner=previous.username,
            candidates=[MemberOutput(user_id=u.id, username=u.username, active=u.active, role='member') for u in candidates]))
    return result


@router.get('/admin/legacy-projects', response_model=list[LegacyProjectOutput])
def legacy_projects(_actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    projects = db.scalars(select(Project).where(~select(ProjectMember.id).where(ProjectMember.project_id == Project.id).exists()))
    return [LegacyProjectOutput(project_id=p.id, name=p.name) for p in projects]


@router.post('/admin/projects/{project_id}/assign', status_code=204)
def assign_project(project_id: str, body: TransferInput, actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    try:
        assign_legacy_project(db, project_id, actor.id, body.user_id, body.reason)
    except (MembershipError, IntegrityError):
        db.rollback()
        raise CollaborationError('MEMBERSHIP_ERROR', '旧项目无法分配，请检查状态和账号。', 409) from None


@router.post('/admin/projects/{project_id}/handoff', status_code=204)
def admin_handoff(project_id: str, body: TransferInput, actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    try:
        admin_handoff_disabled_owner(db, project_id, actor.id, body.user_id, body.reason)
    except (MembershipError, IntegrityError):
        db.rollback()
        raise CollaborationError('MEMBERSHIP_ERROR', '无法调整负责人，请检查项目及账号状态。', 409) from None


@router.get('/admin/projects/{project_id}/purge-impact', response_model=PurgeImpact)
def purge_impact(project_id: str, actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    try:
        return PurgeImpact(**impact(db, actor.id, project_id))
    except PurgeError as exc:
        raise CollaborationError('INVALID_STATE', str(exc), 409) from None


@router.post('/admin/projects/{project_id}/purge', response_model=PurgeOutput)
def purge_route(project_id: str, body: PurgeInput, actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    if not body.confirm:
        raise CollaborationError('CONFIRMATION_REQUIRED', '请核对影响并确认清理。', 400)
    try:
        job_id = purge(db, DATA_DIR, backup_root(), actor.id, project_id, body.confirmed_name)
        job = db.get(PurgeJob, job_id)
        return PurgeOutput(id=job.id, status=job.status, backup_id=job.backup_id)
    except (PurgeError, BackupError, OSError, ValueError) as exc:
        db.rollback()
        raise CollaborationError('PURGE_FAILED', str(exc) if isinstance(exc, PurgeError) else '清理未完成，请检查本机存储。', 409) from None


@router.post('/admin/purges/{job_id}/retry', response_model=PurgeOutput)
def retry_purge(job_id: str, _actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    job = db.get(PurgeJob, job_id)
    if not job:
        raise CollaborationError('NOT_FOUND', '找不到清理记录。', 404)
    cleanup(db, DATA_DIR, job_id)
    db.refresh(job)
    return PurgeOutput(id=job.id, status=job.status, backup_id=job.backup_id)


@router.get('/admin/purges', response_model=list[PurgeOutput])
def pending_purges(_actor: UserAccount = Depends(admin), db: Session = Depends(db_session)):
    jobs = db.scalars(select(PurgeJob).where(PurgeJob.status.in_(['pending', 'cleanup_failed'])).order_by(PurgeJob.created_at.desc()))
    return [PurgeOutput(id=j.id, status=j.status, backup_id=j.backup_id) for j in jobs]
