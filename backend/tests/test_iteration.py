from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import pytest
import app.main as main
from app.database import Base
from app.security_context import actor_id, multiuser

def test_independent_iteration_feedback_convert_once_and_conflict():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        a=actor_id.set('local-user');m=multiuser.set(False)
        try:
            work=main.create_iteration(main.IterationCreate(title='虚构迭代'),db)
            work=main.edit_iteration(work['id'],main.IterationEdit(version=1,title='虚构迭代',status='completed'),db)
            work=main.add_iteration_feedback(work['id'],main.IterationFeedbackInput(version=2,text='需要提醒',source='访谈'),db)
            feedback=work['data']['feedback'][0]
            row=main.convert_iteration_feedback(work['id'],feedback['id'],main.FeedbackConvertInput(version=3,title='提醒',description='发送提醒'),db)
            assert row.source_snapshot=='需要提醒' and row.source_state=='available'
            stored=main.get_iteration(work['id'],db)
            assert stored['data']['status']=='completed' and stored['data']['feedback'][0]['requirement_id']==row.id
            with pytest.raises(main.ApiError) as duplicate:
                main.convert_iteration_feedback(work['id'],feedback['id'],main.FeedbackConvertInput(version=4,title='提醒'),db)
            assert duplicate.value.status==409
            with pytest.raises(main.ApiError) as stale:
                main.edit_iteration(work['id'],main.IterationEdit(version=3,title='覆盖'),db)
            assert stale.value.status==409
        finally: multiuser.reset(m);actor_id.reset(a)
    engine.dispose()

def test_iteration_permission_and_status_does_not_change_requirements():
    from app.membership import initialize_project_owner, add_member, remove_member
    from app.models import Project, UserAccount
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        owner=UserAccount(username='owner',password_hash='test',active=True);member=UserAccount(username='member',password_hash='test',active=True)
        db.add_all([owner,member]);db.flush();project=Project(name='虚构项目',background='');initialize_project_owner(db,project,owner.id);db.commit();add_member(db,project.id,owner.id,member.id)
        a=actor_id.set(owner.id);m=multiuser.set(True)
        try:
            iteration=main.create_iteration(main.IterationCreate(title='迭代',project_id=project.id),db)
            requirement=main.create_product_requirement(main.ProductRequirementCreate(title='需求',project_id=project.id,status='doing'),db)
            main.edit_iteration(iteration['id'],main.IterationEdit(version=1,title='迭代',status='completed'),db)
            assert main.get_product_requirement(requirement.id,db).status=='doing'
            actor_id.set(member.id)
            assert main.get_iteration(iteration['id'],db)['editable'] is False
            with pytest.raises(main.ApiError) as denied:main.add_iteration_feedback(iteration['id'],main.IterationFeedbackInput(version=2,text='反馈'),db)
            assert denied.value.status==403
            actor_id.set(owner.id);remove_member(db,project.id,owner.id,member.id);actor_id.set(member.id)
            with pytest.raises(main.ApiError) as removed:main.get_iteration(iteration['id'],db)
            assert removed.value.status==404
        finally:multiuser.reset(m);actor_id.reset(a)
    engine.dispose()

def test_requirement_iteration_move_tracks_history_and_scope():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        a=actor_id.set('local-user');m=multiuser.set(False)
        try:
            first=main.create_iteration(main.IterationCreate(title='迭代一'),db)
            second=main.create_iteration(main.IterationCreate(title='迭代二'),db)
            row=main.create_product_requirement(main.ProductRequirementCreate(title='需求',iteration_id=first['id']),db)
            assert row.iteration=='迭代一' and row.iteration_id==first['id']
            row=main.edit_product_requirement(row.id,main.ProductRequirementEdit(title='需求',iteration_id=second['id'],version=1),db)
            assert row.iteration=='迭代二' and row.iteration_id==second['id']
            event=main.product_requirement_history(row.id,db)[0]
            assert event.before['iteration']=='迭代一' and event.after['iteration']=='迭代二'
            actor_id.set('other-user')
            with pytest.raises(main.ApiError) as denied:
                main.create_product_requirement(main.ProductRequirementCreate(title='越权',iteration_id=first['id']),db)
            assert denied.value.status==422
        finally:multiuser.reset(m);actor_id.reset(a)
    engine.dispose()

def test_feedback_status_changes_preserve_history():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        a=actor_id.set('local-user');m=multiuser.set(False)
        try:
            work=main.create_iteration(main.IterationCreate(title='迭代'),db)
            work=main.add_iteration_feedback(work['id'],main.IterationFeedbackInput(version=1,text='反馈'),db)
            work=main.set_iteration_feedback_status(work['id'],work['data']['feedback'][0]['id'],main.FeedbackStatusInput(version=2,status='deferred'),db)
            assert work['data']['feedback'][0]['status']=='deferred'
            assert db.scalar(main.select(main.ProductWorkRevision).where(main.ProductWorkRevision.work_id==work['id'],main.ProductWorkRevision.version==2)) is not None
        finally:multiuser.reset(m);actor_id.reset(a)
    engine.dispose()

def test_assign_personal_iteration_checks_visibility_and_linked_requirements():
    from app.models import Project
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        a=actor_id.set('local-user');m=multiuser.set(False)
        try:
            project=Project(name='虚构项目',background='');db.add(project);db.commit()
            work=main.create_iteration(main.IterationCreate(title='迭代'),db)
            with pytest.raises(main.ApiError):main.assign_iteration(work['id'],main.ProductWorkMove(project_id=project.id,version=1),db)
            row=main.create_product_requirement(main.ProductRequirementCreate(title='需求',iteration_id=work['id']),db)
            with pytest.raises(main.ApiError) as denied:main.assign_iteration(work['id'],main.ProductWorkMove(project_id=project.id,version=1,confirm_visibility=True),db)
            assert denied.value.code=='SOURCE_SCOPE'
            main.edit_product_requirement(row.id,main.ProductRequirementEdit(title='需求',iteration_id=None,version=1),db)
            moved=main.assign_iteration(work['id'],main.ProductWorkMove(project_id=project.id,version=1,confirm_visibility=True),db)
            assert moved['project_id']==project.id and moved['version']==2
        finally:multiuser.reset(m);actor_id.reset(a)
    engine.dispose()

def test_iteration_create_requirement_and_feedback_backtrace():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        a=actor_id.set('local-user');m=multiuser.set(False)
        try:
            iteration=main.create_iteration(main.IterationCreate(title='迭代'),db)
            direct=main.create_iteration_requirement(iteration['id'],main.IterationRequirementInput(title='需求',iteration_version=1),db)
            assert direct.iteration_id==iteration['id'] and direct.iteration=='迭代'
            iteration=main.add_iteration_feedback(iteration['id'],main.IterationFeedbackInput(version=1,text='原始反馈',source='访谈'),db)
            feedback=iteration['data']['feedback'][0]
            row=main.convert_iteration_feedback(iteration['id'],feedback['id'],main.FeedbackConvertInput(version=2,title='新需求'),db)
            found=main.get_requirement_feedback_source(row.id,db)
            assert found['text']=='原始反馈' and found['iteration_title']=='迭代' and found['source']=='访谈'
            actor_id.set('other')
            with pytest.raises(main.ApiError) as denied:main.get_requirement_feedback_source(row.id,db)
            assert denied.value.status==404
        finally:multiuser.reset(m);actor_id.reset(a)
    engine.dispose()
