from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import LargeBinary, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

def new_id():
    return str(uuid4())

def now():
    return datetime.now(timezone.utc)

class UserAccount(Base):
    __tablename__ = 'user_accounts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class UserSession(Base):
    __tablename__ = 'user_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('user_accounts.id'), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class LoginThrottle(Base):
    __tablename__ = 'login_throttles'
    username_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class AccountEvent(Base):
    __tablename__ = 'account_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey('user_accounts.id'), nullable=False)
    target_id: Mapped[str] = mapped_column(ForeignKey('user_accounts.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class ProjectMember(Base):
    __tablename__ = 'project_members'
    __table_args__ = (UniqueConstraint('project_id', 'user_id'), CheckConstraint("role IN ('owner', 'member')"),
                      Index('uq_project_one_owner', 'project_id', unique=True,
                            sqlite_where=text("role = 'owner'"), postgresql_where=text("role = 'owner'")))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey('user_accounts.id'), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class MembershipEvent(Base):
    __tablename__ = 'membership_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True, nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey('user_accounts.id'), nullable=False)
    target_id: Mapped[str] = mapped_column(ForeignKey('user_accounts.id'), nullable=False)
    previous_owner_id: Mapped[str | None] = mapped_column(ForeignKey('user_accounts.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default='', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class QueueSettings(Base):
    __tablename__ = 'queue_settings'
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    max_running: Mapped[int | None] = mapped_column(nullable=True)

class QueueSettingsEvent(Base):
    __tablename__ = 'queue_settings_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey('user_accounts.id'), nullable=False)
    old_limit: Mapped[int | None] = mapped_column(nullable=True)
    new_limit: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class ModelSettings(Base):
    __tablename__ = 'model_settings'
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    allowed_models: Mapped[str] = mapped_column(Text, nullable=False)
    max_requests: Mapped[int] = mapped_column(nullable=False)

class ModelSettingsEvent(Base):
    __tablename__ = 'model_settings_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey('user_accounts.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    details: Mapped[str] = mapped_column(Text, default='', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class QueuedJob(Base):
    __tablename__ = 'queued_jobs'
    __table_args__ = (UniqueConstraint('kind', 'target_id'),
                      CheckConstraint("kind IN ('requirements', 'proposal', 'section_edit', 'consistency')"),
                      CheckConstraint("status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted')"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey('user_accounts.id'), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='queued', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class ProjectLifecycle(Base):
    __tablename__ = 'project_lifecycle'
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), primary_key=True)
    state: Mapped[str] = mapped_column(String(20), default='active', nullable=False)
    before_trash: Mapped[str | None] = mapped_column(String(20), nullable=True)
    version: Mapped[int] = mapped_column(default=1, nullable=False)

class ProjectLifecycleEvent(Base):
    __tablename__ = 'project_lifecycle_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True, nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey('user_accounts.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class PurgeJob(Base):
    __tablename__ = 'purge_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    backup_id: Mapped[str] = mapped_column(String(36), nullable=False)
    files: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='pending', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(36), default='local-user')
    name: Mapped[str] = mapped_column(String(200))
    background: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ProductWork(Base):
    __tablename__ = 'product_work'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    creator_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey('projects.id'), index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default='draft', nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, default='', nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class ProductWorkRevision(Base):
    __tablename__ = 'product_work_revisions'
    __table_args__ = (UniqueConstraint('work_id', 'version', name='uq_product_work_revision'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_id: Mapped[str] = mapped_column(ForeignKey('product_work.id'), index=True, nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class ProductWorkStatusEvent(Base):
    __tablename__ = 'product_work_status_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_id: Mapped[str] = mapped_column(ForeignKey('product_work.id'), index=True, nullable=False)
    old_status: Mapped[str] = mapped_column(String(30), nullable=False)
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class ProductWorkLink(Base):
    __tablename__ = 'product_work_links'
    __table_args__ = (UniqueConstraint('work_id', 'target_type', 'target_id', name='uq_product_work_link'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_id: Mapped[str] = mapped_column(ForeignKey('product_work.id'), index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_version: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class CompetitorImage(Base):
    __tablename__ = 'competitor_images'
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=new_id)
    work_id: Mapped[str] = mapped_column(ForeignKey('product_work.id'),index=True,nullable=False)
    filename: Mapped[str] = mapped_column(String(200),nullable=False)
    media_type: Mapped[str] = mapped_column(String(30),nullable=False)
    image_bytes: Mapped[bytes] = mapped_column(LargeBinary,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now,nullable=False)

class CompetitorComparison(Base):
    __tablename__ = 'competitor_comparisons'
    work_id: Mapped[str] = mapped_column(ForeignKey('product_work.id'), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default='{}')

class CompetitorComparisonRevision(Base):
    __tablename__ = 'competitor_comparison_revisions'
    __table_args__ = (UniqueConstraint('work_id','version',name='uq_competitor_comparison_revision'),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=new_id)
    work_id: Mapped[str] = mapped_column(ForeignKey('product_work.id'),index=True,nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now,nullable=False)

class ProductSectionLink(Base):
    __tablename__ = 'product_section_links'
    __table_args__ = (UniqueConstraint('work_id', 'source_id', 'section_index', name='uq_product_section_link'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_id: Mapped[str] = mapped_column(ForeignKey('product_work.id'), index=True, nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_version: Mapped[int] = mapped_column(nullable=False)
    section_index: Mapped[int] = mapped_column(nullable=False)
    section_title: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class ProductRequirement(Base):
    __tablename__ = 'product_requirements'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(ForeignKey('projects.id'), index=True, nullable=True)
    creator_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default='', nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default='unset', nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='clarify', nullable=False)
    assignee_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    iteration: Mapped[str] = mapped_column(String(200), default='', nullable=False)
    iteration_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    blocked_reason: Mapped[str] = mapped_column(Text, default='', nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), default='manual', nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_version: Mapped[int | None] = mapped_column(nullable=True)
    source_snapshot: Mapped[str] = mapped_column(Text, default='', nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class ProductRequirementEvent(Base):
    __tablename__ = 'product_requirement_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(ForeignKey('product_requirements.id'), index=True, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    before: Mapped[str] = mapped_column(Text, nullable=False)
    after: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class ProductResearchTask(Base):
    __tablename__ = 'product_research_tasks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_id: Mapped[str] = mapped_column(ForeignKey('product_work.id'), index=True, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey('projects.id'), nullable=True)
    base_version: Mapped[int] = mapped_column(nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs: Mapped[str] = mapped_column(Text, default='[]', nullable=False)
    edit_spec: Mapped[str] = mapped_column(Text, default='{}', nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), default='product_research_v1', nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='pending', nullable=False)
    result: Mapped[str] = mapped_column(Text, default='', nullable=False)
    error: Mapped[str] = mapped_column(String(500), default='', nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class Material(Base):
    __tablename__ = 'materials'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), default='local-user')
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    warning: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class MaterialVersion(Base):
    __tablename__ = 'material_versions'
    __table_args__ = (UniqueConstraint('project_id', 'group_id', 'version', name='uq_material_group_version'),
                      CheckConstraint("state IN ('active', 'withdrawn')", name='ck_material_state'))
    material_id: Mapped[str] = mapped_column(ForeignKey('materials.id'), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    group_id: Mapped[str] = mapped_column(String(36))
    version: Mapped[int] = mapped_column()
    state: Mapped[str] = mapped_column(String(20), default='active')
    state_version: Mapped[int] = mapped_column(default=0)

class MaterialLabel(Base):
    __tablename__ = 'material_labels'
    __table_args__ = (UniqueConstraint('project_id', 'number', name='uq_material_label_number'),)
    group_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    number: Mapped[int] = mapped_column()

class MaterialStateEvent(Base):
    __tablename__ = 'material_state_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    material_id: Mapped[str] = mapped_column(ForeignKey('materials.id'))
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    actor: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AnalysisTask(Base):
    __tablename__ = 'analysis_tasks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), default='local-user')
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='pending')
    material_ids: Mapped[str] = mapped_column(Text)
    error: Mapped[str] = mapped_column(String(500), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Requirement(Base):
    __tablename__ = 'requirements'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('analysis_tasks.id'), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), default='local-user')
    text: Mapped[str] = mapped_column(Text)
    original_text: Mapped[str] = mapped_column(Text)
    material_id: Mapped[str] = mapped_column(ForeignKey('materials.id'))
    quote: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    version: Mapped[int] = mapped_column(default=1)

class Baseline(Base):
    __tablename__ = 'baselines'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), default='local-user')
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    snapshot: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class MaterialOriginal(Base):
    __tablename__ = 'material_originals'
    material_id: Mapped[str] = mapped_column(ForeignKey('materials.id'), primary_key=True)
    filename_on_disk: Mapped[str] = mapped_column(String(50), unique=True)
    byte_size: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))

class TaskSegment(Base):
    __tablename__ = 'task_segments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey('analysis_tasks.id'), index=True)
    material_id: Mapped[str] = mapped_column(ForeignKey('materials.id'))
    position: Mapped[int] = mapped_column()
    start: Mapped[int] = mapped_column()
    end: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default='pending')

class TaskAttempt(Base):
    __tablename__ = 'task_attempts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey('analysis_tasks.id'), index=True)
    segment_id: Mapped[str] = mapped_column(ForeignKey('task_segments.id'))
    status: Mapped[str] = mapped_column(String(20), default='started')
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class TaskModelChange(Base):
    __tablename__ = 'task_model_changes'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey('analysis_tasks.id'), index=True, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    previous_model: Mapped[str] = mapped_column(String(100), nullable=False)
    new_model: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class TaskConfig(Base):
    __tablename__ = 'task_configs'
    task_id: Mapped[str] = mapped_column(ForeignKey('analysis_tasks.id'), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40), default='requirements_v6')

class OpenQuestion(Base):
    __tablename__ = 'open_questions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('analysis_tasks.id'), index=True)
    material_id: Mapped[str] = mapped_column(ForeignKey('materials.id'))
    text: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    version: Mapped[int] = mapped_column(default=1, nullable=False)

class TaskPricing(Base):
    __tablename__ = 'task_pricing'
    task_id: Mapped[str] = mapped_column(ForeignKey('analysis_tasks.id'), primary_key=True)
    input_per_million: Mapped[str] = mapped_column(String(40))
    output_per_million: Mapped[str] = mapped_column(String(40))
    pricing_date: Mapped[str] = mapped_column(String(10))
    pricing_reference: Mapped[str] = mapped_column(String(300))

class QuestionDecision(Base):
    __tablename__ = 'question_decisions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    question_id: Mapped[str] = mapped_column(ForeignKey('open_questions.id'), index=True)
    action: Mapped[str] = mapped_column(String(20))
    answer: Mapped[str] = mapped_column(Text, default='')
    actor: Mapped[str] = mapped_column(String(36), default='local-user')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class RequirementDecision(Base):
    __tablename__ = 'requirement_decisions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(ForeignKey('requirements.id'), index=True)
    from_version: Mapped[int] = mapped_column()
    old_text: Mapped[str] = mapped_column(Text)
    new_text: Mapped[str] = mapped_column(Text)
    old_status: Mapped[str] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(36), default='local-user')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class BaselineQuestions(Base):
    __tablename__ = 'baseline_questions'
    baseline_id: Mapped[str] = mapped_column(ForeignKey('baselines.id'), primary_key=True)
    snapshot: Mapped[str] = mapped_column(Text)

class BaselineFacts(Base):
    __tablename__ = 'baseline_facts'
    baseline_id: Mapped[str] = mapped_column(ForeignKey('baselines.id'), primary_key=True)
    snapshot: Mapped[str] = mapped_column(Text)

class ModelConsent(Base):
    __tablename__ = 'model_consents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey('analysis_tasks.id'), index=True)
    action: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(36), default='local-user')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class TaskAttemptTiming(Base):
    __tablename__ = 'task_attempt_timings'
    attempt_id: Mapped[str] = mapped_column(ForeignKey('task_attempts.id'), primary_key=True)
    elapsed_ms: Mapped[int] = mapped_column()

class ExtractedFact(Base):
    __tablename__ = 'extracted_facts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('analysis_tasks.id'), index=True)
    material_id: Mapped[str] = mapped_column(ForeignKey('materials.id'))
    text: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text)

class AdditionalCitation(Base):
    __tablename__ = 'additional_citations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    item_type: Mapped[str] = mapped_column(String(20))
    item_id: Mapped[str] = mapped_column(String(36), index=True)
    material_id: Mapped[str] = mapped_column(ForeignKey('materials.id'))
    quote: Mapped[str] = mapped_column(Text)

class FactReview(Base):
    __tablename__ = 'fact_reviews'
    fact_id: Mapped[str] = mapped_column(ForeignKey('extracted_facts.id'), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    version: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class FactReviewEvent(Base):
    __tablename__ = 'fact_review_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    fact_id: Mapped[str] = mapped_column(ForeignKey('extracted_facts.id'), index=True)
    old_status: Mapped[str] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(36), default='local-user')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ProposalOutline(Base):
    __tablename__ = 'proposal_outlines'
    __table_args__ = (UniqueConstraint('project_id','baseline_id','version',name='uq_outline_project_baseline_version'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True, nullable=False)
    baseline_id: Mapped[str] = mapped_column(ForeignKey('baselines.id'), nullable=False)
    template_id: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    chapters: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class ProposalOutlineLink(Base):
    __tablename__ = 'proposal_outline_links'
    draft_id: Mapped[str] = mapped_column(ForeignKey('proposal_drafts.id'), primary_key=True)
    outline_id: Mapped[str] = mapped_column(ForeignKey('proposal_outlines.id'), nullable=False)
    snapshot: Mapped[str] = mapped_column(Text, nullable=False)

class ProposalDraft(Base):
    __tablename__ = 'proposal_drafts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), default='local-user')
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    baseline_id: Mapped[str] = mapped_column(ForeignKey('baselines.id'))
    template_id: Mapped[str] = mapped_column(String(50))
    template_snapshot: Mapped[str] = mapped_column(Text)
    input_snapshot: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default='pending')
    content: Mapped[str] = mapped_column(Text, default='')
    error: Mapped[str] = mapped_column(String(500), default='')
    version: Mapped[int] = mapped_column(default=1)
    calls: Mapped[int] = mapped_column(default=0)
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SectionEdit(Base):
    __tablename__ = 'section_edits'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), nullable=False)
    draft_id: Mapped[str] = mapped_column(ForeignKey('proposal_drafts.id'), index=True, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    base_version: Mapped[int] = mapped_column(nullable=False)
    section_id: Mapped[str] = mapped_column(String(100), nullable=False)
    section_title: Mapped[str] = mapped_column(String(500), nullable=False)
    section_level: Mapped[int] = mapped_column(nullable=False)
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)
    original: Mapped[str] = mapped_column(Text, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='pending', nullable=False)
    candidate: Mapped[str] = mapped_column(Text, default='', nullable=False)
    decision_actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suggestions: Mapped[str] = mapped_column(Text, default='[]', nullable=False)
    error: Mapped[str] = mapped_column(String(500), default='', nullable=False)
    calls: Mapped[int] = mapped_column(default=0, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class ConsistencyCheck(Base):
    __tablename__ = 'consistency_checks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), nullable=False)
    draft_id: Mapped[str] = mapped_column(ForeignKey('proposal_drafts.id'), index=True, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    base_version: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    source_warning: Mapped[str] = mapped_column(String(500), default='', nullable=False)
    source_signature: Mapped[str] = mapped_column(Text, default='', nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='pending', nullable=False)
    error: Mapped[str] = mapped_column(String(500), default='', nullable=False)
    calls: Mapped[int] = mapped_column(default=0, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class ConsistencyIssue(Base):
    __tablename__ = 'consistency_issues'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    check_id: Mapped[str] = mapped_column(ForeignKey('consistency_checks.id'), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location_quote: Mapped[str] = mapped_column(Text, default='', nullable=False)
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='pending', nullable=False)
    decision_note: Mapped[str] = mapped_column(Text, default='', nullable=False)
    decision_actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(default=1, nullable=False)

class ProposalRevision(Base):
    __tablename__ = 'proposal_revisions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    draft_id: Mapped[str] = mapped_column(ForeignKey('proposal_drafts.id'), index=True)
    version: Mapped[int] = mapped_column()
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ProposalPricing(Base):
    __tablename__ = 'proposal_pricing'
    draft_id: Mapped[str] = mapped_column(ForeignKey('proposal_drafts.id'), primary_key=True)
    input_per_million: Mapped[str] = mapped_column(String(40), nullable=False)
    output_per_million: Mapped[str] = mapped_column(String(40), nullable=False)
    pricing_date: Mapped[str] = mapped_column(String(10), nullable=False)

class ProposalReviewEvent(Base):
    __tablename__ = 'proposal_review_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey('proposal_drafts.id'), index=True)
    version: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text, default='')
    decisions: Mapped[str] = mapped_column(Text, default='[]')
    sources: Mapped[str] = mapped_column(Text, default='{}')
    actor: Mapped[str] = mapped_column(String(36), default='local-user')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ProposalExportEvent(Base):
    __tablename__ = 'proposal_export_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey('proposal_drafts.id'), index=True)
    version: Mapped[int] = mapped_column()
    kind: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(36), default='local-user')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ManualRequirement(Base):
    __tablename__ = 'manual_requirements'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    text: Mapped[str] = mapped_column(Text)
    original_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    material_id: Mapped[str | None] = mapped_column(ForeignKey('materials.id'), nullable=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)

class ManualRequirementEvent(Base):
    __tablename__ = 'manual_requirement_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(ForeignKey('manual_requirements.id'), index=True)
    from_version: Mapped[int] = mapped_column()
    old_text: Mapped[str] = mapped_column(Text)
    new_text: Mapped[str] = mapped_column(Text)
    old_status: Mapped[str] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class RequirementRevisionSuggestion(Base):
    __tablename__ = 'requirement_revision_suggestions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    requirement_id: Mapped[str] = mapped_column(String(36), index=True)
    base_version: Mapped[int] = mapped_column()
    original_text: Mapped[str] = mapped_column(Text)
    proposed_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    created_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class ProposalInputSource(Base):
    __tablename__ = 'proposal_input_sources'
    __table_args__ = (UniqueConstraint('draft_id','material_id','kind',name='uq_proposal_input_source'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey('proposal_drafts.id'), index=True)
    material_id: Mapped[str] = mapped_column(ForeignKey('materials.id'))
    kind: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column()
    state_version: Mapped[int] = mapped_column()
    file_hash: Mapped[str] = mapped_column(String(64))
    text_hash: Mapped[str] = mapped_column(String(64))
