import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from app.database import Base
from app.membership import initialize_project_owner
from app.models import AnalysisTask, Project, QueuedJob, UserAccount
import app.queue_worker as worker_module


def test_worker_recovers_running_jobs_and_excludes_second_worker(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "queue.sqlite3"}')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(worker_module, 'engine', engine)
    monkeypatch.setattr(worker_module, 'SessionLocal', factory)
    monkeypatch.setattr(worker_module, 'DATA_DIR', tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        user = UserAccount(username='owner', password_hash='test', active=True, is_admin=False)
        db.add(user); db.flush()
        project = Project(name='虚构项目', background='')
        initialize_project_owner(db, project, user.id); db.flush()
        task = AnalysisTask(project_id=project.id, material_ids='[]', status='running')
        db.add(task); db.flush()
        job = QueuedJob(project_id=project.id, user_id=user.id, kind='requirements', target_id=task.id, status='running')
        db.add(job); db.commit()
        task_id, job_id = task.id, job.id
    first, second = worker_module.LocalQueueWorker(), worker_module.LocalQueueWorker()
    first.acquire()
    try:
        first.recover()
        with pytest.raises(RuntimeError):
            second.acquire()
        with Session(engine) as db:
            assert db.get(QueuedJob, job_id).status == 'interrupted'
            assert db.get(AnalysisTask, task_id).status == 'interrupted'
    finally:
        first.close()
    engine.dispose()
