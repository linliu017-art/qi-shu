"""Local single-process scheduler; starts only in experimental multi-user mode."""
import fcntl
import os
import threading
from sqlalchemy import select, update
from .analysis import execute_task
from .database import DATA_DIR, SessionLocal, engine
from .models import AnalysisTask, ProposalDraft, SectionEdit, ConsistencyCheck, PurgeJob, QueuedJob
from .proposal import run_proposal
from .section_edit import run_section_edit
from .consistency import run_consistency_check
from .project_purge import cleanup
from .task_queue import claim_next, finish, interrupt_after_shutdown


class LocalQueueWorker:
    def __init__(self, data_dir=None, db_engine=None, session_factory=None):
        self.data_dir = data_dir or DATA_DIR
        self.engine = db_engine or engine
        self.session_factory = session_factory or SessionLocal
        self.stop = threading.Event()
        self.lock = None
        self.thread = None
        self.running = set()
        self.running_lock = threading.Lock()

    def acquire(self, shared=False):
        fd = os.open(self.data_dir / '.queue-worker.lock', os.O_RDWR | os.O_CREAT, 0o600)
        self.lock = os.fdopen(fd, 'w')
        try:
            fcntl.flock(self.lock.fileno(), (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            self.lock = None
            raise RuntimeError('已有本地任务调度器运行。') from None

    def recover(self):
        if not self.lock:
            raise RuntimeError('任务调度器尚未取得独占锁。')
        with self.session_factory() as db:
            pending_purges = list(db.scalars(select(PurgeJob.id).where(PurgeJob.status.in_(['pending', 'cleanup_failed']))))
            for job_id in pending_purges:
                cleanup(db, self.data_dir, job_id)
            abandoned = db.execute(select(QueuedJob.kind, QueuedJob.target_id).where(QueuedJob.status == 'running')).all()
            interrupt_after_shutdown(db)
            for kind, target_id in abandoned:
                model = {'requirements': AnalysisTask, 'proposal': ProposalDraft, 'section_edit': SectionEdit, 'consistency': ConsistencyCheck}[kind]
                db.execute(update(model).where(model.id == target_id, model.status.in_(['pending', 'running']))
                           .values(status='interrupted', error='服务中断，继续前请重新确认。'))
            db.commit()
    def start(self):
        if not self.lock:
            raise RuntimeError('任务调度器尚未取得独占锁。')
        self.thread = threading.Thread(target=self._loop, name='qishu-queue', daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.stop.is_set():
            try:
                item = claim_next(self.engine)
                if item:
                    thread = threading.Thread(target=self._run, args=item, daemon=True)
                    with self.running_lock:
                        self.running.add(thread)
                    thread.start()
                    continue
            except Exception:
                # Leave persisted queue untouched; retry without logging user data.
                pass
            self.stop.wait(0.5)

    def _run(self, job_id, kind, target_id):
        model = {'requirements': AnalysisTask, 'proposal': ProposalDraft, 'section_edit': SectionEdit, 'consistency': ConsistencyCheck}[kind]
        try:
            {'requirements': execute_task, 'proposal': run_proposal, 'section_edit': run_section_edit, 'consistency': run_consistency_check}[kind](target_id)
            with self.session_factory() as db:
                target = db.get(model, target_id)
                finish(db, job_id, bool(target and target.status == 'completed'), bool(target and target.status == 'cancelled'))
        except Exception:
            with self.session_factory() as db:
                db.execute(update(model).where(model.id == target_id, model.status.in_(['pending', 'running']))
                           .values(status='failed', error='任务执行失败，请重试。'))
                db.commit()
                finish(db, job_id, False)
        finally:
            with self.running_lock:
                self.running.discard(threading.current_thread())

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join()
        with self.running_lock:
            workers = list(self.running)
        for worker in workers:
            worker.join()
        if self.lock:
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_UN)
            self.lock.close()
