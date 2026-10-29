"""Confirmed local purge with a verified prior backup and durable file cleanup."""
import json
from pathlib import Path
from uuid import UUID, uuid4
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .backup import create_backup
from .models import (AdditionalCitation, AnalysisTask, Baseline, BaselineFacts, BaselineQuestions,
    ExtractedFact, FactReview, FactReviewEvent, Material, MaterialOriginal, MaterialVersion, MaterialLabel, MaterialStateEvent, ManualRequirement, ManualRequirementEvent, RequirementRevisionSuggestion, MembershipEvent,
    ModelConsent, OpenQuestion, Project, ProductWork, ProductWorkRevision, ProductWorkStatusEvent, ProductWorkLink, ProductSectionLink, CompetitorImage, CompetitorComparison, CompetitorComparisonRevision, ProductResearchTask, ProductRequirement, ProductRequirementEvent, ProjectLifecycle, ProjectLifecycleEvent, ProjectMember,
    ProposalDraft, ProposalInputSource, ProposalOutline, ProposalOutlineLink, SectionEdit, ConsistencyCheck, ConsistencyIssue, ProposalExportEvent, ProposalPricing, ProposalReviewEvent, ProposalRevision, PurgeJob,
    QuestionDecision, QueuedJob, Requirement, RequirementDecision, TaskAttempt, TaskAttemptTiming,
    TaskConfig, TaskModelChange, TaskPricing, TaskSegment, UserAccount)


class PurgeError(Exception):
    pass


def _eligible(db: Session, actor_id: str, project_id: str) -> Project:
    actor, project, lifecycle = db.get(UserAccount, actor_id), db.get(Project, project_id), db.get(ProjectLifecycle, project_id)
    if not actor or not actor.active or not actor.is_admin or not project or not lifecycle or lifecycle.state != 'trash':
        raise PurgeError('仅管理员可清理已移入回收站的项目。')
    jobs = db.scalar(select(func.count()).select_from(QueuedJob).where(QueuedJob.project_id == project_id, QueuedJob.status.in_(['queued', 'running'])))
    tasks = db.scalar(select(func.count()).select_from(AnalysisTask).where(AnalysisTask.project_id == project_id, AnalysisTask.status.in_(['pending', 'running'])))
    drafts = db.scalar(select(func.count()).select_from(ProposalDraft).where(ProposalDraft.project_id == project_id, ProposalDraft.status.in_(['pending', 'running'])))
    research = db.scalar(select(func.count()).select_from(ProductResearchTask).where(ProductResearchTask.project_id == project_id, ProductResearchTask.status.in_(['pending', 'running'])))
    if jobs or tasks or drafts or research:
        raise PurgeError('项目仍有未结束任务。')
    return project


def impact(db: Session, actor_id: str, project_id: str) -> dict:
    project = _eligible(db, actor_id, project_id)
    return {'project_id': project.id, 'name': project.name,
            'materials': db.scalar(select(func.count()).select_from(Material).where(Material.project_id == project_id)),
            'requirements': db.scalar(select(func.count()).select_from(Requirement).where(Requirement.project_id == project_id)),
            'proposals': db.scalar(select(func.count()).select_from(ProposalDraft).where(ProposalDraft.project_id == project_id)),
            'product_work': db.scalar(select(func.count()).select_from(ProductWork).where(ProductWork.project_id == project_id)),
            'product_requirements': db.scalar(select(func.count()).select_from(ProductRequirement).where(ProductRequirement.project_id == project_id))}


def purge(db: Session, data_dir: Path, backup_root: Path, actor_id: str, project_id: str, confirmed_name: str) -> str:
    summary = impact(db, actor_id, project_id)
    if not confirmed_name or confirmed_name != summary['name']:
        raise PurgeError('项目名称不匹配，未执行清理。')
    backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if backup_root.is_symlink():
        raise PurgeError('备份目录无效。')
    backup_id = str(uuid4())
    create_backup(data_dir, backup_root / backup_id)
    db.rollback()
    try:
        db.execute(text('BEGIN IMMEDIATE'))
        summary_after = impact(db, actor_id, project_id)
        if summary != summary_after:
            raise PurgeError('项目内容已改变，请重新检查。')
        material_ids = select(Material.id).where(Material.project_id == project_id)
        task_ids = select(AnalysisTask.id).where(AnalysisTask.project_id == project_id)
        requirement_ids = select(Requirement.id).where(Requirement.project_id == project_id)
        question_ids = select(OpenQuestion.id).where(OpenQuestion.project_id == project_id)
        fact_ids = select(ExtractedFact.id).where(ExtractedFact.project_id == project_id)
        baseline_ids = select(Baseline.id).where(Baseline.project_id == project_id)
        draft_ids = select(ProposalDraft.id).where(ProposalDraft.project_id == project_id)
        work_ids = select(ProductWork.id).where(ProductWork.project_id == project_id)
        product_requirement_ids = select(ProductRequirement.id).where(ProductRequirement.project_id == project_id)
        attempt_ids = select(TaskAttempt.id).where(TaskAttempt.task_id.in_(task_ids))
        files = list(db.scalars(select(MaterialOriginal.filename_on_disk).where(MaterialOriginal.material_id.in_(material_ids))))
        for name in files:
            if str(UUID(name)) != name:
                raise PurgeError('资料路径无效，未执行清理。')
        job = PurgeJob(project_id=project_id, actor_id=actor_id, backup_id=backup_id, files=json.dumps(files), status='pending')
        db.add(job)
        db.flush()
        job_id = job.id
        for model, criterion in (
            (ProductResearchTask, ProductResearchTask.work_id.in_(work_ids)),
            (ProductWorkStatusEvent, ProductWorkStatusEvent.work_id.in_(work_ids)),
            (ProductWorkLink, ProductWorkLink.work_id.in_(work_ids)),
            (ProductSectionLink, ProductSectionLink.work_id.in_(work_ids)),
            (CompetitorImage, CompetitorImage.work_id.in_(work_ids)),
            (CompetitorComparisonRevision, CompetitorComparisonRevision.work_id.in_(work_ids)),
            (CompetitorComparison, CompetitorComparison.work_id.in_(work_ids)),
            (ProductRequirementEvent, ProductRequirementEvent.requirement_id.in_(product_requirement_ids)),
            (ProductRequirement, ProductRequirement.project_id == project_id),
            (ProductWorkRevision, ProductWorkRevision.work_id.in_(work_ids)),
            (ProductWork, ProductWork.project_id == project_id),
            (TaskAttemptTiming, TaskAttemptTiming.attempt_id.in_(attempt_ids)),
            (TaskAttempt, TaskAttempt.task_id.in_(task_ids)), (TaskSegment, TaskSegment.task_id.in_(task_ids)),
            (TaskConfig, TaskConfig.task_id.in_(task_ids)), (TaskPricing, TaskPricing.task_id.in_(task_ids)),
            (TaskModelChange, TaskModelChange.task_id.in_(task_ids)),
            (ModelConsent, ModelConsent.task_id.in_(task_ids)),
            (RequirementDecision, RequirementDecision.requirement_id.in_(requirement_ids)),
            (ManualRequirementEvent, ManualRequirementEvent.requirement_id.in_(select(ManualRequirement.id).where(ManualRequirement.project_id == project_id))),
            (RequirementRevisionSuggestion, RequirementRevisionSuggestion.project_id == project_id),
            (ManualRequirement, ManualRequirement.project_id == project_id),
            (QuestionDecision, QuestionDecision.question_id.in_(question_ids)),
            (FactReviewEvent, FactReviewEvent.fact_id.in_(fact_ids)), (FactReview, FactReview.fact_id.in_(fact_ids)),
            (AdditionalCitation, AdditionalCitation.project_id == project_id),
            (ProposalExportEvent, ProposalExportEvent.project_id == project_id),
            (ProposalReviewEvent, ProposalReviewEvent.project_id == project_id),
            (ConsistencyIssue, ConsistencyIssue.check_id.in_(select(ConsistencyCheck.id).where(ConsistencyCheck.project_id == project_id))),
            (ConsistencyCheck, ConsistencyCheck.project_id == project_id), (SectionEdit, SectionEdit.project_id == project_id), (ProposalInputSource, ProposalInputSource.project_id == project_id), (ProposalOutlineLink, ProposalOutlineLink.draft_id.in_(draft_ids)), (ProposalRevision, ProposalRevision.draft_id.in_(draft_ids)), (ProposalPricing, ProposalPricing.draft_id.in_(draft_ids)), (ProposalDraft, ProposalDraft.project_id == project_id), (ProposalOutline, ProposalOutline.project_id == project_id),
            (BaselineFacts, BaselineFacts.baseline_id.in_(baseline_ids)), (BaselineQuestions, BaselineQuestions.baseline_id.in_(baseline_ids)),
            (Baseline, Baseline.project_id == project_id), (Requirement, Requirement.project_id == project_id),
            (OpenQuestion, OpenQuestion.project_id == project_id), (ExtractedFact, ExtractedFact.project_id == project_id),
            (MaterialStateEvent, MaterialStateEvent.project_id == project_id), (MaterialVersion, MaterialVersion.project_id == project_id), (MaterialLabel, MaterialLabel.project_id == project_id), (MaterialOriginal, MaterialOriginal.material_id.in_(material_ids)), (Material, Material.project_id == project_id),
            (AnalysisTask, AnalysisTask.project_id == project_id), (QueuedJob, QueuedJob.project_id == project_id),
            (MembershipEvent, MembershipEvent.project_id == project_id), (ProjectMember, ProjectMember.project_id == project_id),
            (ProjectLifecycleEvent, ProjectLifecycleEvent.project_id == project_id), (ProjectLifecycle, ProjectLifecycle.project_id == project_id),
            (Project, Project.id == project_id)):
            db.execute(delete(model).where(criterion))
        db.commit()
    except Exception:
        db.rollback()
        raise
    cleanup(db, data_dir, job_id)
    return job_id


def cleanup(db: Session, data_dir: Path, job_id: str) -> bool:
    job = db.get(PurgeJob, job_id)
    if not job or job.status == 'completed':
        return bool(job)
    try:
        if (data_dir / 'materials').is_symlink():
            raise OSError('资料目录不允许是符号链接。')
        for name in json.loads(job.files):
            if str(UUID(name)) != name:
                raise ValueError
            (data_dir / 'materials' / name).unlink(missing_ok=True)
        job.status = 'completed'
    except (OSError, ValueError, TypeError):
        job.status = 'cleanup_failed'
    db.commit()
    return job.status == 'completed'
