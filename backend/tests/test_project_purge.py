import hashlib
import sqlite3
from pathlib import Path
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app.backup import verify_backup
from app.database import Base
from app.membership import initialize_project_owner
from app.models import (AdditionalCitation, AnalysisTask, Baseline, BaselineFacts, BaselineQuestions,
    ExtractedFact, FactReview, FactReviewEvent, Material, MaterialOriginal, MaterialVersion, MaterialStateEvent, ManualRequirement, ManualRequirementEvent, RequirementRevisionSuggestion, ModelConsent, OpenQuestion,
    Project, ProposalDraft, ProposalInputSource, ProposalOutline, ProposalOutlineLink, ProposalExportEvent, ProposalPricing, ProposalReviewEvent, ProposalRevision, PurgeJob,
    QuestionDecision, QueuedJob, Requirement, RequirementDecision, TaskAttempt, TaskAttemptTiming,
    TaskConfig, TaskModelChange, TaskPricing, TaskSegment, UserAccount)
from app.project_lifecycle import transition
from app.project_purge import PurgeError, cleanup, impact, purge


def test_confirmed_purge_keeps_other_project_and_verified_backup(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'materials').mkdir()
    engine = create_engine(f'sqlite:///{data / "qishu.sqlite3"}')
    @event.listens_for(engine, 'connect')
    def foreign_keys(conn, _record):
        conn.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        admin = UserAccount(username='admin', password_hash='test', is_admin=True, active=True)
        db.add(admin); db.flush()
        project = Project(name='虚构项目', background='')
        other = Project(name='保留项目', background='')
        initialize_project_owner(db, project, admin.id)
        initialize_project_owner(db, other, admin.id)
        db.commit()
        material = Material(project_id=project.id, filename='虚构.txt', text='虚构资料')
        db.add(material); db.flush()
        content = '虚构资料'.encode()
        (data / 'materials' / material.id).write_bytes(content)
        db.add(MaterialOriginal(material_id=material.id, filename_on_disk=material.id,
                                byte_size=len(content), sha256=hashlib.sha256(content).hexdigest()))
        db.add(MaterialVersion(material_id=material.id,project_id=project.id,group_id=material.id,version=1,state='active',state_version=0))
        db.add(MaterialStateEvent(material_id=material.id,project_id=project.id,actor=admin.id,action='restore',reason='测试'))
        manual=ManualRequirement(project_id=project.id,text='人工需求',original_text='人工需求',status='confirmed',version=1,created_by=admin.id)
        db.add(manual);db.flush()
        db.add(ManualRequirementEvent(requirement_id=manual.id,from_version=1,old_text='人工需求',new_text='人工需求',old_status='pending',new_status='confirmed',actor=admin.id))
        db.add(RequirementRevisionSuggestion(project_id=project.id,requirement_id=manual.id,base_version=1,original_text='人工需求',proposed_text='人工修订',status='pending',created_by=admin.id))
        task = AnalysisTask(project_id=project.id, material_ids='[]', status='completed')
        db.add(task); db.flush()
        segment = TaskSegment(task_id=task.id, material_id=material.id, position=0, start=0, end=4, status='completed')
        db.add(segment); db.flush()
        attempt = TaskAttempt(task_id=task.id, segment_id=segment.id, status='completed')
        db.add(attempt); db.flush()
        requirement = Requirement(project_id=project.id, task_id=task.id, text='需求', original_text='需求', material_id=material.id, quote='虚构', status='confirmed')
        question = OpenQuestion(project_id=project.id, task_id=task.id, material_id=material.id, text='问题', quote='虚构')
        fact = ExtractedFact(project_id=project.id, task_id=task.id, material_id=material.id, text='事实', quote='虚构')
        baseline = Baseline(project_id=project.id, snapshot='[]')
        db.add_all([requirement, question, fact, baseline]); db.flush()
        draft = ProposalDraft(project_id=project.id, baseline_id=baseline.id, template_id='demo', template_snapshot='模板', input_snapshot='{}', model_name='test', status='completed')
        db.add(draft); db.flush()
        outline=ProposalOutline(project_id=project.id,baseline_id=baseline.id,template_id='demo',version=1,chapters='[]',created_by=admin.id)
        db.add(outline);db.flush()
        db.add(ProposalOutlineLink(draft_id=draft.id,outline_id=outline.id,snapshot='[]'))
        db.add(ProposalInputSource(project_id=project.id,draft_id=draft.id,material_id=material.id,kind='template',version=1,state_version=0,file_hash=hashlib.sha256(content).hexdigest(),text_hash=hashlib.sha256(material.text.encode()).hexdigest()))
        db.add_all([
            TaskAttemptTiming(attempt_id=attempt.id, elapsed_ms=1), TaskConfig(task_id=task.id, model_name='test'),
            TaskPricing(task_id=task.id, input_per_million='0', output_per_million='0', pricing_date='2026-01-01', pricing_reference='test'),
            ModelConsent(task_id=task.id, action='start'),
            TaskModelChange(task_id=task.id, actor_id=admin.id, previous_model='deepseek-flash', new_model='deepseek-chat'),
            RequirementDecision(requirement_id=requirement.id, from_version=1, old_text='需求', new_text='需求', old_status='pending', new_status='confirmed'),
            QuestionDecision(question_id=question.id, action='answered'), FactReview(fact_id=fact.id),
            FactReviewEvent(fact_id=fact.id, old_status='pending', new_status='reviewed'),
            AdditionalCitation(project_id=project.id, item_type='fact', item_id=fact.id, material_id=material.id, quote='虚构'),
            BaselineFacts(baseline_id=baseline.id, snapshot='[]'), BaselineQuestions(baseline_id=baseline.id, snapshot='[]'),
            ProposalRevision(draft_id=draft.id, version=1, content='正文'),
            ProposalPricing(draft_id=draft.id, input_per_million='0.30', output_per_million='1.20', pricing_date='2026-10-27'),
            ProposalReviewEvent(project_id=project.id, draft_id=draft.id, version=1, action='submitted'),
            ProposalExportEvent(project_id=project.id, draft_id=draft.id, version=1, kind='draft'),
            QueuedJob(project_id=project.id, user_id=admin.id, kind='requirements', target_id=task.id, status='completed'),
        ])
        db.commit()
        project_id, other_id, material_id = project.id, other.id, material.id
        transition(db, project_id, admin.id, 'trash', 0, True)
        assert impact(db, admin.id, project_id)['materials'] == 1
        with pytest.raises(PurgeError):
            purge(db, data, data / 'backups' / 'manual', admin.id, project_id, '错误名称')
        assert db.get(Project, project_id) is not None
        job_id = purge(db, data, data / 'backups' / 'manual', admin.id, project_id, '虚构项目')
        db.expire_all()
        job = db.get(PurgeJob, job_id)
        assert job.status == 'completed'
        assert db.get(Project, project_id) is None
        assert db.get(Project, other_id).name == '保留项目'
        assert not (data / 'materials' / material_id).exists()
        backup_dir=data / 'backups' / 'manual' / job.backup_id
        verify_backup(backup_dir)
        with sqlite3.connect(backup_dir / 'qishu.sqlite3') as backup_db:
            assert backup_db.execute('SELECT COUNT(*) FROM proposal_outlines').fetchone()[0] == 1
            assert backup_db.execute('SELECT COUNT(*) FROM proposal_outline_links').fetchone()[0] == 1
            assert backup_db.execute('SELECT COUNT(*) FROM proposal_input_sources').fetchone()[0] == 1
            assert backup_db.execute('SELECT COUNT(*) FROM material_versions').fetchone()[0] == 1
            assert backup_db.execute('SELECT COUNT(*) FROM manual_requirements').fetchone()[0] == 1
            assert backup_db.execute('SELECT COUNT(*) FROM requirement_revision_suggestions').fetchone()[0] == 1
    engine.dispose()


def test_interrupted_file_cleanup_can_be_retried(tmp_path, monkeypatch):
    data = tmp_path / 'data'; data.mkdir(); (data / 'materials').mkdir()
    engine = create_engine(f'sqlite:///{data / "qishu.sqlite3"}')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        admin = UserAccount(username='admin', password_hash='test', is_admin=True, active=True)
        db.add(admin); db.flush()
        project = Project(name='待清理测试', background='')
        initialize_project_owner(db, project, admin.id); db.commit()
        material = Material(project_id=project.id, filename='x.txt', text='x')
        db.add(material); db.flush()
        path = data / 'materials' / material.id; path.write_bytes(b'x')
        db.add(MaterialOriginal(material_id=material.id, filename_on_disk=material.id, byte_size=1,
                                sha256=hashlib.sha256(b'x').hexdigest()))
        db.commit()
        transition(db, project.id, admin.id, 'trash', 0, True)
        original_unlink = Path.unlink
        def fail_original(self, *args, **kwargs):
            if self == path:
                raise OSError('synthetic failure')
            return original_unlink(self, *args, **kwargs)
        with monkeypatch.context() as m:
            m.setattr(Path, 'unlink', fail_original)
            job_id = purge(db, data, data / 'backups' / 'manual', admin.id, project.id, '待清理测试')
        assert db.get(PurgeJob, job_id).status == 'cleanup_failed'
        assert path.exists()
        assert cleanup(db, data, job_id)
        assert not path.exists()
        assert db.get(PurgeJob, job_id).status == 'completed'
    engine.dispose()
