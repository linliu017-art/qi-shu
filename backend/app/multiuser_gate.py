"""Fail-closed request gate; callers must explicitly install it on an isolated app."""
import os
import re
from urllib.parse import urlsplit
from fastapi import Request
from fastapi.responses import JSONResponse
from .database import SessionLocal
from .identity import authenticate
from .membership import member_role
from .models import ProjectLifecycle
from .security_context import actor_id, multiuser


def _error(code: str, message: str, status: int):
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message}})


def install_gate(app):
    @app.middleware('http')
    async def multiuser_gate(request: Request, call_next):
        path = request.url.path
        if not path.startswith('/api/'):
            return await call_next(request)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin', '')
            allowed = {item.strip() for item in os.environ.get('QISHU_ALLOWED_ORIGINS',
                        'http://127.0.0.1:3000,http://127.0.0.1:13000').split(',') if item.strip()}
            if not origin or origin not in allowed or urlsplit(origin).path not in ('', '/'):
                return _error('INVALID_ORIGIN', '请求来源不允许。', 403)
        if path in ('/api/v1/auth/login', '/api/v1/auth/logout', '/api/v1/auth/setup', '/api/v1/auth/setup-status'):
            return await call_next(request)
        with SessionLocal() as db:
            user = authenticate(db, request.cookies.get('qishu_session', ''))
            if not user:
                return _error('UNAUTHENTICATED', '请先登录。', 401)
            user_id = user.id
            match = re.match(r'^/api/v1/projects/([^/]+)(?:/|$)', path)
            if match:
                project_id = match.group(1)
                role = member_role(db, project_id, user_id)
                special_transfer = user.is_admin and request.method == 'POST' and path == f'/api/v1/projects/{project_id}/transfer'
                if not role and not special_transfer:
                    return _error('NOT_FOUND', '找不到这个项目。', 404)
                state = db.get(ProjectLifecycle, project_id)
                if state and state.state == 'trash' and not path.endswith('/restore'):
                    return _error('NOT_FOUND', '找不到这个项目。', 404)
                if state and state.state == 'archived' and request.method not in ('GET', 'HEAD') and not special_transfer and not path.endswith(('/unarchive', '/trash')):
                    return _error('PROJECT_ARCHIVED', '项目已归档，请先恢复。', 409)
        actor_token = actor_id.set(user_id)
        mode_token = multiuser.set(True)
        try:
            return await call_next(request)
        finally:
            actor_id.reset(actor_token)
            multiuser.reset(mode_token)
