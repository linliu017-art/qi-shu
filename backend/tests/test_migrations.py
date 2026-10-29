import importlib
import os
import sqlite3
import subprocess
from pathlib import Path
from fastapi.testclient import TestClient

def test_existing_database_is_backed_up_before_schema_upgrade(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, 'QISHU_DATA_DIR': str(tmp_path), 'DEEPSEEK_API_KEY': ''}
    subprocess.run([str(root / '.venv/bin/alembic'), 'upgrade', '45351aff2980'], cwd=root, env=env, check=True, capture_output=True)
    db_path = tmp_path / 'qishu.sqlite3'
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO projects (id, owner_id, name, background, created_at) VALUES ('kept', 'local-user', '原项目', '', '2026-10-27')")
    monkeypatch.setenv('QISHU_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('DEEPSEEK_API_KEY', '')
    import app.database as database
    import app.models as models
    import app.main as main
    importlib.reload(database)
    importlib.reload(models)
    importlib.reload(main)
    with TestClient(main.app) as client:
        assert client.get('/api/v1/projects').json()[0]['name'] == '原项目'
    with sqlite3.connect(db_path) as migrated:
        assert migrated.execute("SELECT name FROM projects WHERE id='kept'").fetchone() == ('原项目',)
        assert migrated.execute('SELECT COUNT(*) FROM project_members').fetchone() == (0,)
        assert migrated.execute('SELECT COUNT(*) FROM user_accounts').fetchone() == (0,)
    backups = list((tmp_path / 'backups').glob('*.sqlite3'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT name FROM projects WHERE id='kept'").fetchone() == ('原项目',)
    database.engine.dispose()

def test_material_migration_preserves_old_ids_original_and_version(tmp_path, monkeypatch):
    import hashlib
    root=Path(__file__).resolve().parents[1]
    env={**os.environ,'QISHU_DATA_DIR':str(tmp_path),'DEEPSEEK_API_KEY':''}
    subprocess.run([str(root/'.venv/bin/alembic'),'upgrade','a5e6f7a8b9c0'],cwd=root,env=env,check=True,capture_output=True)
    content=b'existing fictitious material'
    material_id='c1a10192-0628-4740-a3de-37e81cbd6ad5'
    (tmp_path/'materials').mkdir()
    (tmp_path/'materials'/material_id).write_bytes(content)
    with sqlite3.connect(tmp_path/'qishu.sqlite3') as db:
        db.execute("INSERT INTO projects (id, owner_id, name, background, created_at) VALUES ('p', 'local-user', '虚构项目', '', '2026-10-27')")
        db.execute("INSERT INTO materials (id, project_id, owner_id, filename, text, warning, created_at) VALUES (?, 'p', 'local-user', 'old.txt', ?, '', '2026-10-27')",(material_id,content.decode()))
        db.execute('INSERT INTO material_originals (material_id, filename_on_disk, byte_size, sha256) VALUES (?, ?, ?, ?)',(material_id,material_id,len(content),hashlib.sha256(content).hexdigest()))
    monkeypatch.setenv('QISHU_DATA_DIR',str(tmp_path));monkeypatch.setenv('DEEPSEEK_API_KEY','')
    import app.database as database
    import app.models as models
    import app.main as main
    importlib.reload(database);importlib.reload(models);importlib.reload(main)
    with TestClient(main.app) as client:
        material=client.get('/api/v1/projects/p/materials').json()[0]
        assert material['id']==material_id and material['version']==1 and material['state']=='active'
        assert client.get('/api/v1/projects/p/materials/'+material_id+'/original').content==content
    assert len(list((tmp_path/'backups').glob('*.sqlite3')))==1
    database.engine.dispose()
