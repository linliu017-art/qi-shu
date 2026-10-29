"""Two-account concurrent edit checks; model output is simulated in an isolated database."""
import json, os, sqlite3, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.credentials import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import Baseline, ProposalDraft, UserAccount
import app.section_edit as editing


def main():
    origin={'origin':'https://testserver'}
    owner=TestClient(app,base_url='https://testserver',headers=origin)
    member=TestClient(app,base_url='https://testserver',headers=origin)
    started, release=Event(),Event()
    mode={'block':True}
    class Response:
        status_code=200
        def raise_for_status(self): pass
        def json(self): return {'usage':{'prompt_tokens':10,'completion_tokens':5},'choices':[{'message':{'content':json.dumps({'content':'候选修改正文','suggestions':[]},ensure_ascii=False)}}]}
    def fake_post(*args,**kwargs):
        started.set()
        if mode['block'] and not release.wait(10): raise RuntimeError('test timeout')
        return Response()
    editing.httpx.post=fake_post
    with owner:
        if os.environ.get('QISHU_FIXED_TEST_ACCOUNTS')=='1':
            root=Path(__file__).resolve().parents[2]
            creds=dict(line.split('：',1) for line in (root/'data/多人验收/测试账号.txt').read_text().splitlines() if '：' in line)
            source=sqlite3.connect('file:'+str(root/'data/多人验收/qishu.sqlite3')+'?mode=ro',uri=True)
            records=[source.execute('select username,password_hash,is_admin,active from user_accounts where username=?',(creds[k],)).fetchone() for k in ('管理员账号','普通账号')]
            source.close(); assert all(row and row[3] for row in records)
            with SessionLocal() as db:
                for row in records: db.add(UserAccount(username=row[0],password_hash=row[1],is_admin=bool(row[2]),active=True))
                db.commit();member_id=db.scalar(select(UserAccount.id).where(UserAccount.username==creds['普通账号']))
            logins=[(owner,creds['管理员账号'],creds['管理员密码']),(member,creds['普通账号'],creds['普通密码'])]
        else:
            password='这是用于本机测试的安全长密码'
            assert owner.post('/api/v1/auth/setup',json={'username':'测试管理员','password':password}).status_code==201
            with SessionLocal() as db:
                account=UserAccount(username='测试成员',password_hash=hash_password(password),active=True,is_admin=False)
                db.add(account);db.commit();member_id=account.id
            logins=[(owner,'测试管理员',password),(member,'测试成员',password)]
        for client,username,password in logins:
            assert client.post('/api/v1/auth/login',json={'username':username,'password':password}).status_code==200
        pid=owner.post('/api/v1/projects',json={'name':'并发修改虚构测试'}).json()['id']
        base=f'/api/v1/projects/{pid}'
        assert owner.post(base+'/members',json={'user_id':member_id}).status_code==204
        original='# 方案\n\n## 目标\n原目标\n\n## 范围\n原范围\n'
        with SessionLocal() as db:
            baseline=Baseline(project_id=pid,snapshot='[]');db.add(baseline);db.flush()
            draft=ProposalDraft(project_id=pid,baseline_id=baseline.id,template_id='demo-v1',template_snapshot='',input_snapshot='{}',model_name='deepseek-flash',status='completed',content=original)
            db.add(draft);db.commit();did=draft.id
        path=base+'/proposals/'+did
        def proposal(): return next(x for x in owner.get(base+'/proposals').json() if x['id']==did)
        def create(client,version):
            target=next(x for x in client.get(path+'/sections').json()['sections'] if x['title']=='目标')
            r=client.post(path+'/section-edits',json={'version':version,'section_id':target['id'],'instruction':'调整目标描述','confirm_external_use':True})
            assert r.status_code==202,(r.status_code,r.text)
            return r.json()['id']
        def completed(task):
            for _ in range(100):
                item=next(x for x in member.get(path+'/section-edits').json() if x['id']==task)
                if item['status'] in ('completed','failed','cancelled'): return item
                time.sleep(.1)
            raise AssertionError('candidate timeout')
        task=create(member,1)
        assert started.wait(8)
        updated=original.replace('原目标','管理员修改的目标').replace('原范围','管理员修改的范围')
        assert owner.patch(path,json={'version':1,'content':updated}).status_code==200
        release.set();item=completed(task)
        assert item['status']=='completed' and item['candidate']=='候选修改正文'
        result=member.post(base+'/section-edits/'+task+'/accept',json={'version':1})
        assert result.status_code==409 and result.json()['error']['code']=='VERSION_CONFLICT'
        assert proposal()['content']==updated and proposal()['version']==2
        assert next(x for x in owner.get(path+'/section-edits').json() if x['id']==task)['candidate']=='候选修改正文'
        assert owner.get(path+'/revisions').json()[0]['content']==original
        print('生成期间他人修改：冲突被阻止，新内容和候选均保留。',flush=True)
        mode['block']=False
        first=create(owner,2);assert completed(first)['status']=='completed'
        second=create(member,2);assert completed(second)['status']=='completed'
        barrier=Barrier(2)
        def accept(client,candidate):
            barrier.wait(timeout=5)
            return client.post(base+'/section-edits/'+candidate+'/accept',json={'version':2})
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(accept,owner,first);b=pool.submit(accept,member,second)
            outcomes=[a.result(),b.result()]
        assert sorted(r.status_code for r in outcomes)==[200,409],[r.status_code for r in outcomes]
        final=proposal()
        assert final['version']==3 and '管理员修改的范围' in final['content']
        rows=owner.get(path+'/section-edits').json()
        assert sum(x['status']=='accepted' for x in rows)==1
        assert sum(x['status']=='completed' for x in rows)==2
        print('两人同时接受候选：恰好一次成功，另一项保留并提示冲突。',flush=True)
        assert owner.patch(path,json={'version':2,'content':updated+'迟到人工修改'}).status_code==409
        assert proposal()['content']==final['content']
        assert [r['version'] for r in owner.get(path+'/revisions').json()]==[2,1]
        print('迟到的手动保存：被阻止，现有方案及历史版本保留。',flush=True)
    member.close()
    with TestClient(app,base_url='https://testserver',headers=origin) as restarted:
        _,username,password=logins[0]
        assert restarted.post('/api/v1/auth/login',json={'username':username,'password':password}).status_code==200
        assert next(x for x in restarted.get(base+'/proposals').json() if x['id']==did)['content']==final['content']
        assert next(x for x in restarted.get(path+'/section-edits').json() if x['id']==task)['candidate']=='候选修改正文'
        assert len(restarted.get(path+'/revisions').json())==2
        print('应用生命周期重启后，方案、候选和旧版本仍可读取。',flush=True)


if __name__=='__main__':main()
