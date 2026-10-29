from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.collaboration_api import CollaborationError, db_session, router
from app.credentials import hash_password
from app.database import Base
from app.membership import initialize_project_owner
from app.models import Project, UserAccount


def test_collaboration_routes_require_identity_and_membership():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = UserAccount(username='owner', password_hash=hash_password('一个足够长的负责人测试密码'), is_admin=True, active=True)
        member = UserAccount(username='member', password_hash=hash_password('一个足够长的成员测试密码'), is_admin=False, active=True)
        db.add_all([owner, member])
        db.flush()
        project = Project(name='虚构项目', background='')
        initialize_project_owner(db, project, owner.id)
        db.commit()
        project_id, member_id = project.id, member.id
    app = FastAPI()
    app.include_router(router)

    @app.exception_handler(CollaborationError)
    async def error(_request: Request, exc: CollaborationError):
        return JSONResponse(status_code=exc.status, content={'error': {'code': exc.code, 'message': exc.message}})

    def test_db():
        with Session(engine, expire_on_commit=False) as db:
            yield db
    app.dependency_overrides[db_session] = test_db
    with TestClient(app, base_url='https://testserver') as admin, TestClient(app, base_url='https://testserver') as other:
        assert other.get('/api/v1/auth/me').status_code == 401
        assert admin.post('/api/v1/auth/login', json={'username': 'owner', 'password': '错误'}).status_code == 401
        response = admin.post('/api/v1/auth/login', json={'username': 'owner', 'password': '一个足够长的负责人测试密码'})
        assert response.status_code == 200
        assert 'HttpOnly' in response.headers['set-cookie'] and 'Secure' in response.headers['set-cookie']
        assert other.post('/api/v1/auth/login', json={'username': 'member', 'password': '一个足够长的成员测试密码'}).status_code == 200
        path = f'/api/v1/projects/{project_id}/members'
        assert other.get(path).status_code == 404
        assert other.get('/api/v1/accounts').status_code == 403
        assert admin.post(path, json={'user_id': member_id}).status_code == 204
        assert other.get(path).status_code == 200
        assert other.post(path, json={'user_id': member_id}).status_code == 409
        assert admin.delete(path + '/' + member_id).status_code == 204
        assert other.get(path).status_code == 404
        assert admin.post(f'/api/v1/accounts/{member_id}/disable').status_code == 204
        assert other.get('/api/v1/auth/me').status_code == 401
    engine.dispose()
