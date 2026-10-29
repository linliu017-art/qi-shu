"""Check queue cancellation and membership revoke with a simulated model."""
import json,time
from threading import Event
from fastapi.testclient import TestClient
from app.credentials import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import Baseline,ProposalDraft,UserAccount
import app.consistency as consistency

def main():
    started,release=Event(),Event()
    class Response:
        status_code=200
        def raise_for_status(self):pass
        def json(self):return {'usage':{'prompt_tokens':2,'completion_tokens':3},'choices':[{'message':{'content':json.dumps({'issues':[{'category':'名称','description':'名称不一致','location_quote':'甲系统','evidence_quote':'乙系统'}]},ensure_ascii=False)}}]}
    def fake(*args,**kw):
        started.set();assert release.wait(10);return Response()
    consistency.httpx.post=fake
    origin={'origin':'https://testserver'}
    member=TestClient(app,base_url='https://testserver',headers=origin)
    with TestClient(app,base_url='https://testserver',headers=origin) as owner:
        pw='这是用于本机测试的安全长密码'
        assert owner.post('/api/v1/auth/setup',json={'username':'测试管理员','password':pw}).status_code==201
        with SessionLocal() as db:
            user=UserAccount(username='测试成员',password_hash=hash_password(pw),active=True,is_admin=False)
            db.add(user);db.commit();uid=user.id
        for client,name in ((owner,'测试管理员'),(member,'测试成员')):
            assert client.post('/api/v1/auth/login',json={'username':name,'password':pw}).status_code==200
        pid=owner.post('/api/v1/projects',json={'name':'虚构检查测试'}).json()['id'];base='/api/v1/projects/'+pid
        assert owner.post(base+'/members',json={'user_id':uid}).status_code==204
        with SessionLocal() as db:
            b=Baseline(project_id=pid,snapshot='[]');db.add(b);db.flush()
            d=ProposalDraft(project_id=pid,baseline_id=b.id,template_id='demo-v1',template_snapshot='',input_snapshot='{}',model_name='deepseek-flash',status='completed',content='甲系统和乙系统');db.add(d);db.commit();did=d.id
        path=base+'/proposals/'+did
        r=member.post(path+'/consistency-checks',json={'version':1,'confirm_external_use':True});assert r.status_code==202
        cid=r.json()['id'];assert started.wait(8)
        assert any(x['kind']=='consistency' and x['target_id']==cid for x in owner.get(base+'/queue').json())
        assert owner.delete(base+'/members/'+uid).status_code==204
        assert member.get(path+'/consistency-checks').status_code==404
        release.set()
        for _ in range(80):
            row=owner.get(path+'/consistency-checks').json()[0]
            if row['status']=='cancelled':break
            time.sleep(.1)
        assert row['status']=='cancelled' and not row['issues']
        assert owner.post(base+'/members',json={'user_id':uid}).status_code==204
        assert member.get(path+'/consistency-checks').status_code==200
        assert owner.get(base+'/usage').json()[0]['calls']==1
    member.close()
    with TestClient(app,base_url='https://testserver',headers=origin) as again:
        assert again.post('/api/v1/auth/login',json={'username':'测试管理员','password':pw}).status_code==200
        assert again.get(path+'/consistency-checks').json()[0]['status']=='cancelled'
if __name__=='__main__':main()
