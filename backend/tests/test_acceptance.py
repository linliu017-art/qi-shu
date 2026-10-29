from contextlib import contextmanager
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import app.main as main
from app.database import Base
from app.membership import initialize_project_owner, add_member, remove_member
from app.models import Project, UserAccount, ProductWorkRevision
from app.security_context import actor_id, multiuser
from sqlalchemy import select

@contextmanager
def identity(user):
    a=actor_id.set(user); m=multiuser.set(True)
    try: yield
    finally: multiuser.reset(m); actor_id.reset(a)

def test_acceptance_permission_readiness_and_retest_history():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        owner=UserAccount(username='owner',password_hash='test',active=True)
        member=UserAccount(username='member',password_hash='test',active=True)
        db.add_all([owner,member]); db.flush()
        project=Project(name='虚构项目',background=''); initialize_project_owner(db,project,owner.id); db.commit()
        add_member(db,project.id,owner.id,member.id)
        with identity(owner.id):
            standard=main.create_acceptance(main.AcceptanceCreate(kind='acceptance_standard',title='标准',project_id=project.id),db)
            with pytest.raises(main.ApiError): main.edit_acceptance_standard(standard['id'],main.StandardEdit(version=1,title='标准',ready=True),db)
            standard=main.edit_acceptance_standard(standard['id'],main.StandardEdit(version=1,title='标准',prerequisite='登录',action='点击',expected='成功',ready=True),db)
            record=main.create_acceptance(main.AcceptanceCreate(kind='acceptance_test',title='检查',project_id=project.id),db)
            record=main.add_acceptance_item(record['id'],main.AcceptanceItemInput(version=1,title='打开',expected='成功'),db)
            item=record['data']['items'][0]['id']
            with pytest.raises(main.ApiError) as reason: main.conclude_acceptance(record['id'],main.AcceptanceDecisionInput(version=2),db)
            assert reason.value.code=='REASON_REQUIRED'
            record=main.add_acceptance_attempt(record['id'],item,main.AcceptanceAttemptInput(version=2,state='failed',actual='失败',issue='缺陷'),db)
            record=main.conclude_acceptance(record['id'],main.AcceptanceDecisionInput(version=3,reason='后期优化'),db)
            record=main.add_acceptance_attempt(record['id'],item,main.AcceptanceAttemptInput(version=4,state='passed',actual='成功'),db)
            assert [a['state'] for a in record['data']['items'][0]['attempts']]==['failed','passed']
            assert record['data']['decisions'][0]['items'][0]['state']=='failed'
            assert record['data']['decisions'][0]['reason']=='后期优化'
            with pytest.raises(main.ApiError) as stale: main.conclude_acceptance(record['id'],main.AcceptanceDecisionInput(version=4),db)
            assert stale.value.status==409
            assert len(db.scalars(select(ProductWorkRevision).where(ProductWorkRevision.work_id==record['id'])).all())==4
        with identity(member.id):
            assert main.get_acceptance(record['id'],db)['editable'] is False
            with pytest.raises(main.ApiError) as denied: main.add_acceptance_item(record['id'],main.AcceptanceItemInput(version=5,title='越权'),db)
            assert denied.value.status==403
        remove_member(db,project.id,owner.id,member.id)
        with identity(member.id):
            with pytest.raises(main.ApiError) as denied: main.get_acceptance(record['id'],db)
            assert denied.value.status==404
    engine.dispose()

def test_acceptance_source_scope_and_changed_version():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        with identity('local-user'):
            record=main.create_acceptance(main.AcceptanceCreate(kind='acceptance_standard',title='标准'),db)
            prd=main.create_product_work(main.ProductWorkCreate(kind='prd',title='PRD'),db)
            record=main.add_acceptance_link(record['id'],main.AcceptanceLinkInput(target_type='prd',target_id=prd.id,version=1),db)
            assert main.acceptance_links(record['id'],db)[0]['state']=='available'
            main.edit_product_work(prd.id,main.ProductWorkEdit(title='PRD',content='改动',version=1),db)
            assert main.acceptance_links(record['id'],db)[0]['state']=='changed'
        with identity('other-user'):
            other=main.create_acceptance(main.AcceptanceCreate(kind='acceptance_standard',title='其他人标准'),db)
            with pytest.raises(main.ApiError) as denied:
                main.add_acceptance_link(other['id'],main.AcceptanceLinkInput(target_type='prd',target_id=prd.id,version=1),db)
            assert denied.value.status==404
    engine.dispose()

def test_acceptance_can_link_standard_and_iteration_without_cross_scope():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        with identity('local-user'):
            standard=main.create_acceptance(main.AcceptanceCreate(kind='acceptance_standard',title='标准'),db)
            record=main.create_acceptance(main.AcceptanceCreate(kind='acceptance_test',title='测试'),db)
            iteration=main.create_iteration(main.IterationCreate(title='迭代'),db)
            record=main.add_acceptance_link(record['id'],main.AcceptanceLinkInput(target_type='acceptance_standard',target_id=standard['id'],version=1),db)
            record=main.add_acceptance_link(record['id'],main.AcceptanceLinkInput(target_type='iteration',target_id=iteration['id'],version=2),db)
            assert len(main.acceptance_links(record['id'],db))==2
            with pytest.raises(main.ApiError):main.add_acceptance_link(standard['id'],main.AcceptanceLinkInput(target_type='iteration',target_id=iteration['id'],version=1),db)
        with identity('other-user'):
            other=main.create_acceptance(main.AcceptanceCreate(kind='acceptance_test',title='他人测试'),db)
            with pytest.raises(main.ApiError) as denied:main.add_acceptance_link(other['id'],main.AcceptanceLinkInput(target_type='acceptance_standard',target_id=standard['id'],version=1),db)
            assert denied.value.status==404
    engine.dispose()

def test_ai_acceptance_candidate_requires_confirmation_and_source_stays_valid(monkeypatch):
    from fastapi.testclient import TestClient
    import app.product_research as research
    from app.database import Base as CurrentBase
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);CurrentBase.metadata.create_all(engine)
    def session():return Session(engine,expire_on_commit=False)
    def dependency():
        with session() as db:yield db
    monkeypatch.setattr(main,'model_key',lambda:'fake');monkeypatch.setattr(main,'model_settings',lambda db:(['test-model'],1))
    monkeypatch.setattr(research,'model_key',lambda:'fake');monkeypatch.setattr(research,'model_settings',lambda db:(['test-model'],1));monkeypatch.setattr(research,'SessionLocal',session)
    class Reply:
        def raise_for_status(self):pass
        def json(self):return {'choices':[{'finish_reason':'stop','message':{'content':'{"title":"提醒","prerequisite":"登录","action":"提交","expected":"显示提醒","quote":"提醒学生归还图书"}'}}]}
    monkeypatch.setattr(research.httpx,'post',lambda *a,**k:Reply());main.app.dependency_overrides[main.db_session]=dependency
    try:
        c=TestClient(main.app);prd=c.post('/api/v1/product-work',json={'kind':'prd','title':'PRD'}).json()
        c.put('/api/v1/product-work/'+prd['id'],json={'title':'PRD','content':'提醒学生归还图书','version':1})
        standard=c.post('/api/v1/acceptance',json={'kind':'acceptance_standard','title':'标准'}).json();path='/api/v1/acceptance/'+standard['id']
        standard=c.post(path+'/links',json={'target_type':'prd','target_id':prd['id'],'version':1}).json();link=c.get(path+'/links').json()[0]
        payload={'version':standard['version'],'link_id':link['id'],'model':'test-model'}
        assert c.post(path+'/candidates',json=payload).status_code==400
        payload['confirm_external_use']=True
        assert c.post(path+'/candidates',json=payload).status_code==202
        task=c.get(path+'/candidates').json()[0];assert task['status']=='completed' and '提醒学生' in task['result']
        assert c.get(path).json()['data']['action']==''
        body={'title':'提醒','prerequisite':'登录','action':'提交','expected':'显示提醒'}
        accepted=c.post(path+'/candidates/'+task['id']+'/accept',json=body)
        assert accepted.status_code==200 and accepted.json()['data']['ready'] is False
        assert c.post(path+'/candidates/'+task['id']+'/accept',json=body).status_code==409
        assert c.put('/api/v1/product-work/'+prd['id'],json={'title':'PRD','content':'新版本','version':2}).status_code==200
        hidden=c.get(path+'/candidates').json()[0];assert hidden['result']=='' and '依据已变更' in hidden['error']
    finally:main.app.dependency_overrides.pop(main.db_session,None);engine.dispose()

def test_acceptance_chapter_links_detect_changes_and_scope():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        with identity('local-user'):
            prd=main.create_product_work(main.ProductWorkCreate(kind='prd',title='虚构 PRD'),db)
            main.edit_product_work(prd.id,main.ProductWorkEdit(title='虚构 PRD',content='# 背景\n信息\n# 需求\n提醒',version=1),db)
            standard=main.create_acceptance(main.AcceptanceCreate(kind='acceptance_standard',title='标准'),db)
            standard=main.add_acceptance_section_link(standard['id'],main.AcceptanceSectionLinkInput(source_id=prd.id,source_version=2,section_index=1,version=1),db)
            link=main.list_acceptance_section_links(standard['id'],db)[0]
            assert '需求' in link['label'] and link['state']=='available'
            main.edit_product_work(prd.id,main.ProductWorkEdit(title='虚构 PRD',content='# 需求\n更改',version=2),db)
            assert main.list_acceptance_section_links(standard['id'],db)[0]['state']=='changed'
            with pytest.raises(main.ApiError) as stale:main.add_acceptance_section_link(standard['id'],main.AcceptanceSectionLinkInput(source_id=prd.id,source_version=2,section_index=0,version=2),db)
            assert stale.value.code=='SOURCE_CHANGED'
        with identity('other'):
            other=main.create_acceptance(main.AcceptanceCreate(kind='acceptance_standard',title='其他'),db)
            with pytest.raises(main.ApiError) as forbidden:main.add_acceptance_section_link(other['id'],main.AcceptanceSectionLinkInput(source_id=prd.id,source_version=3,section_index=0,version=1),db)
            assert forbidden.value.status==404
    engine.dispose()

def test_edit_check_item_preserves_previous_attempt_expectation():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        with identity('local-user'):
            work=main.create_acceptance(main.AcceptanceCreate(kind='acceptance_test',title='验收'),db)
            work=main.add_acceptance_item(work['id'],main.AcceptanceItemInput(version=1,title='提醒',expected='原预期'),db)
            item=work['data']['items'][0]['id']
            work=main.add_acceptance_attempt(work['id'],item,main.AcceptanceAttemptInput(version=2,state='failed',actual='失败'),db)
            work=main.edit_acceptance_item(work['id'],item,main.AcceptanceItemInput(version=3,title='提醒',expected='新预期'),db)
            assert work['data']['items'][0]['expected']=='新预期'
            assert work['data']['items'][0]['attempts'][0]['expected']=='原预期'
    engine.dispose()
