"""Exercise real task code with a deliberately delayed, entirely fake model response."""
import json
import time
from threading import Event
from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models import Baseline, BaselineFacts, BaselineQuestions
import app.analysis as analysis


def main():
    started, release = Event(), Event()
    mode = ['requirements']
    material_id = ['']
    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            result = {'requirements':[{'text':'迟到结果','material_id':material_id[0],'quote':'虚构来源'}]} if mode[0] == 'requirements' else {'content':'迟到的方案'}
            return {'usage':{'prompt_tokens':10,'completion_tokens':20}, 'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result, ensure_ascii=False)}}]}
    def delayed(*args, **kwargs):
        started.set()
        release.wait(5)
        return Response()
    analysis.httpx.post = delayed
    headers = {'origin':'https://testserver'}
    with TestClient(app, base_url='https://testserver', headers=headers) as client:
        creds = {'username':'owner','password':'这是用于本机测试的安全长密码'}
        client.post('/api/v1/auth/setup', json=creds).raise_for_status()
        client.post('/api/v1/auth/login', json=creds).raise_for_status()
        project = client.post('/api/v1/projects', json={'name':'虚构取消测试'}).json()['id']
        path = f'/api/v1/projects/{project}'
        material_id[0] = client.post(path+'/materials', files={'file':('sample.txt','虚构来源'.encode(),'text/plain')}).json()['id']
        task = client.post(path+'/requirement-tasks', json={'material_ids':[material_id[0]],'confirm_external_use':True}).json()
        try:
            assert started.wait(3)
            job = next(j for j in client.get(path+'/queue').json() if j['target_id']==task['id'])
            assert client.post(path+'/queue/'+job['id']+'/cancel').status_code == 204
            assert client.get(path+'/requirement-tasks/'+task['id']).json()['status'] == 'cancelled'
            assert client.post(path+'/requirement-tasks/'+task['id']+'/resume', json={'confirm_external_use':True}).status_code == 409
        finally:
            release.set()
        for _ in range(50):
            job = next(j for j in client.get(path+'/queue').json() if j['target_id']==task['id'])
            if job['status']=='cancelled': break
            time.sleep(.1)
        assert job['status']=='cancelled'
        assert client.get(path+'/requirements').json() == []
        recorded = client.get(path+'/requirement-tasks/'+task['id']).json()
        assert recorded['prompt_tokens']==10 and recorded['completion_tokens']==20
        with SessionLocal() as db:
            baseline = Baseline(project_id=project, snapshot=json.dumps([{'text':'虚构需求','material_id':material_id[0],'quote':'虚构来源','related_sources':[]}], ensure_ascii=False))
            db.add(baseline); db.flush()
            db.add_all([BaselineFacts(baseline_id=baseline.id,snapshot='[]'),BaselineQuestions(baseline_id=baseline.id,snapshot='[]')])
            db.commit(); baseline_id=baseline.id
        mode[0]='proposal'; started.clear(); release.clear()
        draft = client.post(path+'/proposals',json={'baseline_id':baseline_id,'template_id':'demo-v1','confirm_external_use':True}).json()
        try:
            assert started.wait(3)
            job = next(j for j in client.get(path+'/queue').json() if j['target_id']==draft['id'])
            assert client.post(path+'/queue/'+job['id']+'/cancel').status_code == 204
        finally:
            release.set()
        for _ in range(50):
            job = next(j for j in client.get(path+'/queue').json() if j['target_id']==draft['id'])
            if job['status']=='cancelled': break
            time.sleep(.1)
        assert job['status']=='cancelled'
        draft = next(d for d in client.get(path+'/proposals').json() if d['id']==draft['id'])
        assert draft['status']=='cancelled' and draft['content']==''
        assert draft['prompt_tokens']==10 and draft['completion_tokens']==20
        usage = client.get(path+'/usage').json()
        assert len(usage)==1 and usage[0]['actor_name']=='owner'
        assert usage[0]['calls']==2 and usage[0]['known_prompt_tokens']==20 and usage[0]['known_completion_tokens']==40
        assert usage[0]['usage_complete'] and abs(usage[0]['estimated_cost_usd']-0.000054)<1e-9
        member_creds = {'username':'member','password':'这是用于本机测试的安全长密码'}
        member_id = client.post('/api/v1/accounts',json=member_creds).json()['id']
        assert client.post(path+'/members',json={'user_id':member_id}).status_code == 204
        member = TestClient(app, base_url='https://testserver', headers=headers)
        member.post('/api/v1/auth/login',json=member_creds).raise_for_status()
        mode[0]='requirements'; started.clear(); release.clear()
        task2 = member.post(path+'/requirement-tasks',json={'material_ids':[material_id[0]],'confirm_external_use':True}).json()
        try:
            assert started.wait(3)
            assert client.delete(path+'/members/'+member_id).status_code == 204
            assert member.get(path+'/materials').status_code == 404
        finally:
            release.set()
        for _ in range(50):
            job2 = next(j for j in client.get(path+'/queue').json() if j['target_id']==task2['id'])
            if job2['status']=='cancelled': break
            time.sleep(.1)
        assert job2['status']=='cancelled'
        assert client.get(path+'/requirements').json() == []
        assert client.get(path+'/requirement-tasks/'+task2['id']).json()['status'] == 'cancelled'
        assert any(u['actor_name']=='member' and u['calls']==1 for u in client.get(path+'/usage').json())
        member.close()


if __name__ == '__main__':
    main()
