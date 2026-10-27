from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

def new_id():
    return str(uuid4())

def now():
    return datetime.now(timezone.utc)

class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(36), default='local-user')
    name: Mapped[str] = mapped_column(String(200))
    background: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Material(Base):
    __tablename__ = 'materials'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), default='local-user')
    filename: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    warning: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AnalysisTask(Base):
    __tablename__ = 'analysis_tasks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), default='local-user')
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

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

class ProposalDraft(Base):
    __tablename__ = 'proposal_drafts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), default='local-user')
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

class ProposalRevision(Base):
    __tablename__ = 'proposal_revisions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    draft_id: Mapped[str] = mapped_column(ForeignKey('proposal_drafts.id'), index=True)
    version: Mapped[int] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

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
