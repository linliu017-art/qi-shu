"""Synthetic 50-account / 10-concurrent request scenario; no model calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.credentials import new_session_token, session_token_hash
from app.database import SessionLocal
from app.main import app
from app.membership import initialize_project_owner
from app.models import AnalysisTask, Material, Project, ProjectMember, Requirement, RequirementDecision, UserAccount, UserSession
from sqlalchemy import select


def main():
    headers = {'origin':'https://testserver'}
    with TestClient(app, base_url='https://testserver', headers=headers):
        with SessionLocal() as db:
            users = [UserAccount(username=f'虚构成员{i}', password_hash='not-used', active=True, is_admin=False) for i in range(50)]
            outsider = UserAccount(username='虚构非成员', password_hash='not-used', active=True, is_admin=False)
            db.add_all(users + [outsider]); db.flush()
            project = Project(name='并发虚构项目', background='')
            initialize_project_owner(db, project, users[0].id); db.flush()
            for user in users[1:]:
                db.add(ProjectMember(project_id=project.id, user_id=user.id, role='member'))
            material = Material(project_id=project.id, filename='test.txt', text='虚构来源')
            task = AnalysisTask(project_id=project.id, status='completed', material_ids='[]')
            db.add_all([material, task]); db.flush()
            requirement = Requirement(project_id=project.id, task_id=task.id, material_id=material.id, text='原需求', original_text='原需求', quote='虚构来源', status='pending')
            db.add(requirement); db.flush()
            project_id, requirement_id = project.id, requirement.id
            tokens = []
            for user in users + [outsider]:
                token = new_session_token(); tokens.append(token)
                db.add(UserSession(token_hash=session_token_hash(token), user_id=user.id, expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
            db.commit()
        def read(token):
            client = TestClient(app, base_url='https://testserver', headers=headers, cookies={'qishu_session':token})
            try:
                return client.get(f'/api/v1/projects/{project_id}/requirements').status_code
            finally:
                client.close()
        with ThreadPoolExecutor(max_workers=10) as pool:
            statuses = list(pool.map(read, tokens))
        assert statuses[:50] == [200] * 50 and statuses[50] == 404
        def edit(index):
            client = TestClient(app, base_url='https://testserver', headers=headers, cookies={'qishu_session':tokens[index]})
            try:
                return client.patch(f'/api/v1/projects/{project_id}/requirements/{requirement_id}',
                                    json={'status':'pending','text':f'第{index}人编辑','version':1}).status_code
            finally:
                client.close()
        with ThreadPoolExecutor(max_workers=10) as pool:
            statuses = list(pool.map(edit, range(1,11)))
        assert statuses.count(200) == 1 and statuses.count(409) == 9, statuses
        with SessionLocal() as db:
            assert len(list(db.scalars(select(RequirementDecision).where(RequirementDecision.requirement_id == requirement_id)))) == 1


if __name__ == '__main__':
    main()
