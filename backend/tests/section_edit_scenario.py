"""End-to-end queue, revocation, and recovery test with mocked provider."""
import json
import time
from threading import Event
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.credentials import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import Baseline, ProposalDraft, UserAccount
import app.section_edit as edit


def main():
    started, release = Event(), Event()
    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {'usage':{'prompt_tokens':10,'completion_tokens':5},'choices':[{'message':{'content':json.dumps({'content':'新的正文','suggestions':[]},ensure_ascii=False)}}]}
    def fake_post(*args, **kwargs):
        started.set()
        assert release.wait(8)
        return Response()
    edit.httpx.post = fake_post
    origin={'origin':'https://testserver'}
    member=TestClient(app,base_url='https://testserver',headers=origin)
    with TestClient(app,base_url='https://testserver',headers=origin) as admin:
        assert admin.post('/api/v1/auth/setup',json={'username':'admin','password':'这是用于本机测试的安全长密码'}).status_code==201
        with SessionLocal() as db:
            user=UserAccount(username='member',password_hash=hash_password('这是用于本机测试的安全长密码'),active=True,is_admin=False)
            db.add(user);db.commit();uid=user.id
        assert admin.post('/api/v1/auth/login',json={'username':'admin','password':'这是用于本机测试的安全长密码'}).status_code==200
        assert member.post('/api/v1/auth/login',json={'username':'member','password':'这是用于本机测试的安全长密码'}).status_code==200
        pid=admin.post('/api/v1/projects',json={'name':'虚构项目'}).json()['id']
        base=f'/api/v1/projects/{pid}'
        assert admin.post(base+'/members',json={'user_id':uid}).status_code==204
        with SessionLocal() as db:
            baseline=Baseline(project_id=pid,snapshot='[]');db.add(baseline);db.flush()
            draft=ProposalDraft(project_id=pid,baseline_id=baseline.id,template_id='demo-v1',template_snapshot='',input_snapshot='{}',model_name='deepseek-flash',status='completed',content='# 标题\n\n## 内容\n旧内容\n');db.add(draft);db.commit();did=draft.id
        url=base+'/proposals/'+did
        section=member.get(url+'/sections').json()['sections'][1]
        result=member.post(url+'/section-edits',json={'version':1,'section_id':section['id'],'instruction':'改善表达','confirm_external_use':True})
        assert result.status_code==202
        task=result.json()['id']
        assert started.wait(8)
        assert any(x['target_id']==task and x['kind']=='section_edit' for x in admin.get(base+'/queue').json())
        assert admin.delete(base+'/members/'+uid).status_code==204
        assert member.get(url+'/section-edits').status_code==404
        release.set()
        for _ in range(60):
            item=admin.get(url+'/section-edits').json()[0]
            if item['status']=='cancelled': break
            time.sleep(.1)
        assert item['status']=='cancelled' and item['candidate']==''
        assert admin.post(base+'/members',json={'user_id':uid}).status_code==204
        assert member.get(url+'/section-edits').status_code==200
        assert admin.get(base+'/usage').json()[0]['calls']==1
    member.close()
    with TestClient(app,base_url='https://testserver',headers=origin) as restarted:
        assert restarted.post('/api/v1/auth/login',json={'username':'admin','password':'这是用于本机测试的安全长密码'}).status_code==200
        assert restarted.get(url+'/section-edits').json()[0]['status']=='cancelled'


if __name__ == '__main__': main()
