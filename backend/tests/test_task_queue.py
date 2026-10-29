from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.membership import initialize_project_owner
from app.models import Project, QueuedJob, UserAccount
from app.task_queue import cancel_queued, claim_next, enqueue, finish, interrupt_after_shutdown, set_limit


def test_queue_limit_cancel_revocation_and_recovery(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "queue.sqlite3"}')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = UserAccount(username='owner', password_hash='test', active=True, is_admin=True)
        db.add(owner)
        db.flush()
        project = Project(name='虚构项目', background='')
        initialize_project_owner(db, project, owner.id)
        db.commit()
        set_limit(db, owner.id, 1)
        one = enqueue(db, project.id, owner.id, 'requirements', 'one')
        two = enqueue(db, project.id, owner.id, 'proposal', 'two')
        db.commit()
        first_id, second_id = one.id, two.id
        project_id, owner_id = project.id, owner.id
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: claim_next(engine), range(2)))
    claimed = [c for c in claims if c]
    assert len(claimed) == 1
    with Session(engine, expire_on_commit=False) as db:
        waiting = second_id if claimed[0][0] == first_id else first_id
        assert cancel_queued(db, project_id, owner_id, waiting)
        assert not cancel_queued(db, project_id, owner_id, claimed[0][0])
        assert finish(db, claimed[0][0], True)
        assert db.get(QueuedJob, waiting).status == 'cancelled'
        third = enqueue(db, project_id, owner_id, 'requirements', 'three')
        db.commit()
        third_id = third.id
        owner = db.get(UserAccount, owner_id)
        owner.active = False
        db.commit()
    assert claim_next(engine) is None
    engine.dispose()
    engine = create_engine(f'sqlite:///{tmp_path / "queue.sqlite3"}')
    with Session(engine) as db:
        assert db.get(QueuedJob, third_id).status == 'cancelled'
        assert db.get(QueuedJob, claimed[0][0]).status == 'completed'
    engine.dispose()


def test_restart_requires_explicit_interrupted_task_handling(tmp_path):
    path = tmp_path / 'recovery.sqlite3'
    engine = create_engine(f'sqlite:///{path}')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = UserAccount(username='owner', password_hash='test', active=True, is_admin=True)
        db.add(user)
        db.flush()
        project = Project(name='虚构项目', background='')
        initialize_project_owner(db, project, user.id)
        db.commit()
        job = enqueue(db, project.id, user.id, 'requirements', 'recovery')
        db.commit()
        job_id = job.id
    assert claim_next(engine)[0] == job_id
    engine.dispose()
    engine = create_engine(f'sqlite:///{path}')
    with Session(engine) as db:
        assert interrupt_after_shutdown(db) == 1
        assert db.get(QueuedJob, job_id).status == 'interrupted'
        assert not finish(db, job_id, True)
    assert claim_next(engine) is None
    engine.dispose()
