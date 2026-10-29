import json
import importlib
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('QISHU_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('DEEPSEEK_API_KEY','fake-for-test')
    import app.database as database
    import app.models as models
    import app.main as main
    importlib.reload(database);importlib.reload(models);importlib.reload(main)
    with TestClient(main.app) as c: yield c
    database.engine.dispose()

def test_navigation_requires_confirmation_and_uses_allowlisted_intent(client, monkeypatch):
    import app.navigation as nav
    requests=[]
    class Response:
        status_code=200
        def json(self):return {'usage':{'prompt_tokens':20,'completion_tokens':5},'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'intent':'materials','project_hint':'星河'})}}]}
    def post(url,**kwargs):requests.append(kwargs['json']);return Response()
    monkeypatch.setattr(nav.httpx,'post',post)
    route='/api/v1/navigation/interpret'
    assert client.post(route,json={'text':'去星河项目上传资料'}).status_code==400
    assert requests==[]
    r=client.post(route,json={'text':'去星河项目上传资料','confirm_external_use':True})
    assert r.status_code==200 and r.json()['intent']=='materials' and r.json()['project_hint']=='星河'
    assert r.json()['prompt_tokens']==20 and requests[0]['messages'][1]['content']=='去星河项目上传资料'
    assert set(requests[0]['messages'][1])=={'role','content'}

def test_navigation_rejects_invented_paths_and_does_not_accept_hallucinated_project(client, monkeypatch):
    import app.navigation as nav
    class Response:
        status_code=200
        def json(self):return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'intent':'materials','project_hint':'不在原文'})}}]}
    monkeypatch.setattr(nav.httpx,'post',lambda *a,**k:Response())
    route='/api/v1/navigation/interpret'
    r=client.post(route,json={'text':'我要查看资料','confirm_external_use':True})
    assert r.status_code==200 and r.json()['project_hint']==''
    class Bad(Response):
        def json(self):return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'intent':'materials','project_hint':'','url':'https://bad.example'})}}]}
    monkeypatch.setattr(nav.httpx,'post',lambda *a,**k:Bad())
    r=client.post(route,json={'text':'我要查看资料','confirm_external_use':True})
    assert r.status_code==503 and r.json()['error']['code']=='NAVIGATION_UNAVAILABLE'
