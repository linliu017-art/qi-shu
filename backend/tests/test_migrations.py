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
    backups = list((tmp_path / 'backups').glob('*.sqlite3'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT name FROM projects WHERE id='kept'").fetchone() == ('原项目',)
    database.engine.dispose()
