import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import app.main as main
import app.product_research as research
import app.product_web_search as search
from app.database import Base
from app.models import ProductResearchTask

def test_web_search_requires_consent_scopes_sources_and_records_result(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
    def session():return Session(engine,expire_on_commit=False)
    def dep():
        with session() as db:yield db
    main.app.dependency_overrides[main.db_session]=dep
    monkeypatch.setattr(search,'SessionLocal',session);monkeypatch.setattr(research,'SessionLocal',session)
    monkeypatch.setattr(main,'model_key',lambda:'model-fake');monkeypatch.setattr(main,'model_settings',lambda db:(['test-model'],1))
    monkeypatch.setattr(research,'model_key',lambda:'model-fake');monkeypatch.setattr(research,'model_settings',lambda db:(['test-model'],1))
    monkeypatch.setenv('ALIYUN_SEARCH_API_KEY','search-fake');monkeypatch.setenv('ALIYUN_SEARCH_ENDPOINT','https://example.opensearch.aliyuncs.com')
    requests=[]
    class Reply:
        def __init__(self,data):self.data=data
        def raise_for_status(self):pass
        def json(self):return self.data
    def fake(url,**kwargs):
        requests.append((url,kwargs['json']))
        if 'opensearch' in url:return Reply({'result':{'search_result':[{'title':'网页一','link':'https://example.com/a','content':'仅选内容','snippet':'摘要'}, {'title':'网页二','link':'https://example.com/b','content':'未选内容'}, {'title':'恶意地址','link':'javascript:alert(1)','content':'坏内容'}]}})
        return Reply({'choices':[{'finish_reason':'stop','message':{'content':'{"report":"仅依据网页一；未自动实测竞品网站。"}'}}]})
    monkeypatch.setattr(search.httpx,'post',fake)
    try:
        c=TestClient(main.app);work=c.post('/api/v1/product-work',json={'kind':'competitor','title':'虚构对比'}).json();path='/api/v1/product-work/'+work['id']
        payload={'version':1,'query':'公开竞品 官网'}
        assert c.post(path+'/web-search',json=payload).status_code==400 and not requests
        payload['confirm_external_use']=True
        assert c.post(path+'/web-search',json=payload).status_code==202
        task=c.get(path+'/web-search').json()[0];assert task['status']=='completed'
        data=json.loads(task['result']);assert len(data['items'])==2
        assert requests[0][1]=={'query':'公开竞品 官网','query_rewrite':False,'top_k':5,'content_type':'mainText','way':'pro'}
        body={'version':1,'goal':'分析','model':'test-model','confirm_external_use':True,'web_results':[{'task_id':task['id'],'index':0}]}
        assert c.post(path+'/research',json=body).status_code==202
        model_task=c.get(path+'/research').json()[0]
        assert '仅选内容' in model_task['source_text'] and '未选内容' not in model_task['source_text']
        with session() as db:
            stored=db.get(ProductResearchTask,task['id']);stored.result='{}';db.commit()
        model_task=c.get(path+'/research').json()[0];assert model_task['result']=='' and model_task['source_text']==''
    finally:main.app.dependency_overrides.pop(main.db_session,None);engine.dispose()

def test_search_configuration_rejects_untrusted_endpoint(monkeypatch):
    monkeypatch.setenv('ALIYUN_SEARCH_API_KEY','fake')
    for endpoint in ('https://attacker.example','http://example.opensearch.aliyuncs.com','https://example.opensearch.aliyuncs.com:bad','https://example.opensearch.aliyuncs.com/unsafe'):
        monkeypatch.setenv('ALIYUN_SEARCH_ENDPOINT',endpoint);assert search.search_settings() is None

def test_benchmark_parses_providers_without_calling_real_services():
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[2]/'scripts'/'benchmark_web_search.py'
    spec=importlib.util.spec_from_file_location('benchmark_web_search',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    class Response:
        def __init__(self,data):self.data=data
        def raise_for_status(self):pass
        def json(self):return self.data
    class Client:
        def post(self,url,**kwargs):
            if 'opensearch' in url:return Response({'result':{'search_result':[{'title':'官方','link':'https://notion.so/test','content':'正文'}]}})
            return Response({'Response':{'Version':'standard','Pages':[json.dumps({'title':'官网','url':'https://notion.so/x','passage':'摘要'})]}})
    ali=module.run_case(Client(),'阿里云 Pro','Notion pricing official','notion.so',('fake','https://example.opensearch.aliyuncs.com','default'))
    tencent=module.run_case(Client(),'腾讯标准版','Notion pricing official','notion.so','fake')
    assert ali['official_hit'] and tencent['official_hit']
    assert ali['content_kind']=='网页正文' and tencent['content_kind']=='摘要'
    assert ali['results'][0]['returned_characters']==2
