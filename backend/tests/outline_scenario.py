"""Two-person immutable outline version and restart checks with synthetic inputs."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from fastapi.testclient import TestClient
from app.credentials import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import Baseline,UserAccount


def main():
    origin={'origin':'https://testserver'}
    member=TestClient(app,base_url='https://testserver',headers=origin)
    with TestClient(app,base_url='https://testserver',headers=origin) as owner:
        pw='这是用于本机测试的安全长密码'
        assert owner.post('/api/v1/auth/setup',json={'username':'测试管理员','password':pw}).status_code==201
        with SessionLocal() as db:
            user=UserAccount(username='测试成员',password_hash=hash_password(pw),active=True,is_admin=False);db.add(user);db.commit();uid=user.id
        for client,name in ((owner,'测试管理员'),(member,'测试成员')):
            assert client.post('/api/v1/auth/login',json={'username':name,'password':pw}).status_code==200
        pid=owner.post('/api/v1/projects',json={'name':'虚构并发提纲'}).json()['id'];base=f'/api/v1/projects/{pid}'
        assert owner.post(base+'/members',json={'user_id':uid}).status_code==204
        with SessionLocal() as db:
            b=Baseline(project_id=pid,snapshot=json.dumps([{'id':'req-1','text':'支持报修'}],ensure_ascii=False));db.add(b);db.commit();bid=b.id
        barrier=Barrier(2)
        def submit(client,title):
            barrier.wait(timeout=5)
            return client.post(base+'/outlines',json={'baseline_id':bid,'chapters':[{'id':'chapter','title':title,'instruction':'','requirement_ids':['req-1']}]})
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1=pool.submit(submit,owner,'管理员提纲');f2=pool.submit(submit,member,'成员提纲');results=[f1.result(),f2.result()]
        assert [r.status_code for r in results].count(201)==2,[(r.status_code,r.text) for r in results]
        items=owner.get(base+'/outlines',params={'baseline_id':bid}).json()['outlines']
        assert [x['version'] for x in items]==[2,1] and {x['chapters'][0]['title'] for x in items}=={'管理员提纲','成员提纲'}
        assert owner.delete(base+'/members/'+uid).status_code==204
        assert member.get(base+'/outlines',params={'baseline_id':bid}).status_code==404
    member.close()
    with TestClient(app,base_url='https://testserver',headers=origin) as again:
        assert again.post('/api/v1/auth/login',json={'username':'测试管理员','password':pw}).status_code==200
        assert len(again.get(base+'/outlines',params={'baseline_id':bid}).json()['outlines'])==2
if __name__=='__main__':main()
