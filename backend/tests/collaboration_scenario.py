"""Isolated subprocess scenario for the disabled-by-default experimental mode."""
from fastapi.testclient import TestClient
from sqlalchemy import select
from threading import Event
import time
import io
from reportlab.pdfgen import canvas
from app.credentials import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import AnalysisTask, OpenQuestion, Project, UserAccount
import app.queue_worker as queue_worker


def main():
    origin = {'origin': 'https://testserver'}
    started, release = Event(), Event()
    def fake_execution(task_id):
        started.set()
        release.wait(5)
        with SessionLocal() as db:
            task = db.get(AnalysisTask, task_id)
            task.status = 'completed'
            db.commit()
    queue_worker.execute_task = fake_execution
    member = TestClient(app, base_url='https://testserver', headers=origin)
    outsider = TestClient(app, base_url='https://testserver', headers=origin)
    with TestClient(app, base_url='https://testserver', headers=origin) as owner:
        assert owner.get('/api/v1/auth/setup-status').json()['setup_required']
        setup = {'username': 'owner', 'password': '这是用于本机测试的安全长密码'}
        assert owner.post('/api/v1/auth/setup', json=setup).status_code == 201
        assert owner.post('/api/v1/auth/setup', json=setup).status_code == 409
        assert not owner.get('/api/v1/auth/setup-status').json()['setup_required']
        with SessionLocal() as db:
            for username in ('member', 'outsider'):
                db.add(UserAccount(username=username, password_hash=hash_password('这是用于本机测试的安全长密码'), active=True, is_admin=username == 'owner'))
            legacy = Project(name='未分配的旧项目', background='')
            db.add(legacy)
            db.commit()
            legacy_id = legacy.id
            member_id = db.scalar(select(UserAccount).where(UserAccount.username == 'member')).id
        assert outsider.get('/api/v1/projects').status_code == 401
        assert owner.post('/api/v1/auth/login', headers={'origin': 'https://evil.example'}, json={'username': 'owner', 'password': '这是用于本机测试的安全长密码'}).status_code == 403
        for client, username in ((owner, 'owner'), (member, 'member'), (outsider, 'outsider')):
            assert client.post('/api/v1/auth/login', json={'username': username, 'password': '这是用于本机测试的安全长密码'}).status_code == 200
        config = owner.get('/api/v1/admin/model-settings')
        assert config.status_code == 200 and 'fake-for-test' not in config.text
        assert member.get('/api/v1/admin/model-settings').status_code == 403
        assert owner.put('/api/v1/admin/model-settings', json={'allowed_models':['sk-unsafe-example'],'max_requests':2}).status_code == 422
        assert owner.put('/api/v1/admin/model-settings', json={'allowed_models':['deepseek-flash'],'max_requests':2}).status_code == 200
        assert owner.get('/api/v1/config').json()['max_requests'] == 2
        assert owner.get(f'/api/v1/projects/{legacy_id}/materials').status_code == 404
        assert any(p['project_id'] == legacy_id for p in owner.get('/api/v1/admin/legacy-projects').json())
        assert owner.post(f'/api/v1/admin/projects/{legacy_id}/assign', json={'user_id': member_id, 'reason': '旧项目交接'}).status_code == 204
        assert member.get(f'/api/v1/projects/{legacy_id}/materials').status_code == 200
        assert owner.get(f'/api/v1/projects/{legacy_id}/materials').status_code == 404
        project_id = owner.post('/api/v1/projects', json={'name': '隔离测试项目'}).json()['id']
        project = f'/api/v1/projects/{project_id}'
        material = owner.post(project + '/materials', files={'file': ('sample.txt', b'example content', 'text/plain')}).json()
        pdf_data = io.BytesIO()
        pdf = canvas.Canvas(pdf_data)
        pdf.drawString(40, 700, 'Fictional PDF')
        pdf.save()
        pdf_material = owner.post(project + '/materials', files={'file': ('sample.pdf', pdf_data.getvalue(), 'application/pdf')}).json()
        pdf_path = project + '/materials/' + pdf_material['id'] + '/pdf-preview'
        assert owner.get(pdf_path).content == pdf_data.getvalue()
        assert outsider.get(pdf_path).status_code == 404
        assert member.get(pdf_path).status_code == 404
        assert outsider.get(project + '/materials').status_code == 404
        assert outsider.get(project + '/todo').status_code == 404
        assert outsider.get(project + '/usage').status_code == 404
        assert outsider.get(project + '/materials/' + material['id'] + '/original').status_code == 404
        assert member.get(project + '/materials').status_code == 404
        assert owner.post(project + '/members', json={'user_id': member_id}).status_code == 204
        assert member.get(project + '/materials').status_code == 200
        assert member.get(project + '/todo').status_code == 200
        assert outsider.get(project + '/activity').status_code == 404
        assert not any(x['project_id']==project_id for x in outsider.get('/api/v1/worklist').json())
        assert member.get(project + '/activity').status_code == 200
        assert member.get(pdf_path).content == pdf_data.getvalue()
        assert member.post(project + '/baselines').status_code == 403
        with SessionLocal() as db:
            seed_task = AnalysisTask(project_id=project_id, material_ids='[]', status='completed')
            db.add(seed_task)
            db.flush()
            question = OpenQuestion(project_id=project_id, task_id=seed_task.id, material_id=material['id'], text='虚构问题', quote='example', status='pending')
            db.add(question)
            db.commit()
            question_id = question.id
        question_path = project + '/questions/' + question_id
        assert member.patch(question_path, json={'status': 'answered', 'answer': '答复', 'version': 1}).status_code == 200
        assert member.patch(question_path, json={'status': 'answered', 'answer': '冲突', 'version': 1}).status_code == 409
        assert member.patch(question_path, json={'status': 'resolved', 'answer': '完成', 'version': 2}).status_code == 403
        assert owner.patch(question_path, json={'status': 'resolved', 'answer': '完成', 'version': 2}).status_code == 200
        assert member.patch(question_path, json={'status': 'pending', 'answer': '', 'version': 3}).status_code == 403
        assert owner.put('/api/v1/queue/settings', json={'max_running': 1}).status_code == 200
        try:
            task_body = {'material_ids': [material['id']], 'confirm_external_use': True}
            first = owner.post(project + '/requirement-tasks', json=task_body)
            assert first.status_code == 202
            assert started.wait(3)
            second = member.post(project + '/requirement-tasks', json=task_body)
            assert second.status_code == 202
            jobs = member.get(project + '/queue').json()
            second_job = next(j for j in jobs if j['target_id'] == second.json()['id'])
            assert second_job['status'] == 'queued'
            assert member.post(project + '/queue/' + second_job['id'] + '/cancel').status_code == 204
            assert member.get(project + '/requirement-tasks/' + second.json()['id']).json()['status'] == 'cancelled'
        finally:
            release.set()
        for _ in range(30):
            if owner.get(project + '/requirement-tasks/' + first.json()['id']).json()['status'] == 'completed':
                break
            time.sleep(0.1)
        assert owner.get(project + '/requirement-tasks/' + first.json()['id']).json()['status'] == 'completed'
        # Members may suggest changes, but only the owner can decide or withdraw sources.
        material_path = project + '/materials/' + material['id']
        assert member.post(material_path + '/withdraw', json={'state_version':0,'confirm':True}).status_code == 403
        manual = member.post(project + '/requirements/manual', json={'text':'虚构人工需求'}).json()
        req_path = project + '/requirements/' + manual['id']
        assert member.patch(req_path, json={'status':'confirmed','text':manual['text'],'version':1}).status_code == 403
        confirmed = owner.patch(req_path, json={'status':'confirmed','text':manual['text'],'version':1}).json()
        suggestion = member.post(req_path + '/revisions', json={'text':'虚构修订需求','version':confirmed['version']}).json()
        revision_path = project + '/requirement-revisions/' + suggestion['id'] + '/decision'
        assert member.post(revision_path, json={'decision':'accept'}).status_code == 403
        assert owner.post(revision_path, json={'decision':'accept'}).status_code == 200
        assert owner.post(material_path + '/withdraw', json={'state_version':0,'confirm':True}).status_code == 200
        assert member.post(project + '/requirement-tasks', json={'material_ids':[material['id']], 'confirm_external_use':True}).status_code == 409
        assert owner.post(material_path + '/restore', json={'state_version':1,'confirm':True}).status_code == 200
        assert owner.delete(project + '/members/' + member_id).status_code == 204
        assert member.get(project + '/materials').status_code == 404
        assert member.get(project + '/todo').status_code == 404
        assert member.get(pdf_path).status_code == 404
        disposal = owner.post('/api/v1/projects', json={'name':'可清理虚构项目'}).json()['id']
        disposal_path = f'/api/v1/projects/{disposal}'
        assert owner.post(disposal_path + '/trash', json={'version':0,'confirm':True}).status_code == 200
        assert owner.get(f'/api/v1/admin/projects/{disposal}/purge-impact').json()['name'] == '可清理虚构项目'
        assert owner.post(f'/api/v1/admin/projects/{disposal}/purge', json={'confirm':False,'confirmed_name':'可清理虚构项目'}).status_code == 400
        purged = owner.post(f'/api/v1/admin/projects/{disposal}/purge', json={'confirm':True,'confirmed_name':'可清理虚构项目'})
        assert purged.status_code == 200 and purged.json()['status'] == 'completed'
        assert owner.get(disposal_path + '/materials').status_code == 404
        backup_id = purged.json()['backup_id']
        assert owner.post(f'/api/v1/admin/backups/{backup_id}/restore-copy').status_code == 409
        current_backup=owner.post('/api/v1/admin/backups').json()['id']
        assert owner.post(f'/api/v1/admin/backups/{current_backup}/restore-copy').status_code == 201
    member.close()
    outsider.close()


if __name__ == '__main__':
    main()
