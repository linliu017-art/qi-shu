import hashlib
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.backup import BackupError, create_backup, restore_to_new_directory, verify_backup
from app.database import Base
from app.models import Material, MaterialOriginal, Project


def test_backup_restores_originals_and_rejects_corruption(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'materials').mkdir()
    engine = create_engine(f'sqlite:///{data / "qishu.sqlite3"}')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        project = Project(name='虚构项目', background='')
        db.add(project)
        db.flush()
        content = '虚构资料'.encode()
        material = Material(project_id=project.id, filename='资料.txt', text=content.decode())
        db.add(material)
        db.flush()
        (data / 'materials' / material.id).write_bytes(content)
        db.add(MaterialOriginal(material_id=material.id, filename_on_disk=material.id,
                                byte_size=len(content), sha256=hashlib.sha256(content).hexdigest()))
        material_id = material.id
        db.commit()
    (data / 'secret.env').write_text('private', encoding='utf-8')
    backup = tmp_path / 'backup'
    create_backup(data, backup)
    assert not (backup / 'secret.env').exists()
    restored = tmp_path / 'restored'
    restore_to_new_directory(backup, restored)
    assert (restored / 'materials' / material_id).read_bytes() == content
    with pytest.raises(FileExistsError):
        restore_to_new_directory(backup, restored)
    (backup / 'materials' / material_id).write_text('damaged', encoding='utf-8')
    with pytest.raises(BackupError):
        verify_backup(backup)
    engine.dispose()

def test_safe_restore_rejects_permission_changes_and_clears_sessions(tmp_path):
    from datetime import datetime, timedelta, timezone
    import sqlite3
    from app.backup import restore_safe_copy
    from app.membership import initialize_project_owner
    from app.models import UserAccount, UserSession, ProjectMember
    data=tmp_path/'data';data.mkdir();(data/'materials').mkdir()
    engine=create_engine(f'sqlite:///{data / "qishu.sqlite3"}')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin=UserAccount(username='admin',password_hash='test-hash',is_admin=True,active=True)
        member=UserAccount(username='member',password_hash='test-hash',is_admin=False,active=True)
        db.add_all([admin,member]);db.flush()
        project=Project(name='虚构项目',background='');initialize_project_owner(db,project,admin.id);db.flush()
        db.add(ProjectMember(project_id=project.id,user_id=member.id,role='member'))
        db.add(UserSession(token_hash='fake-token-hash',user_id=admin.id,expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
        db.commit();member_id=member.id
    backup=tmp_path/'backup';create_backup(data,backup)
    destination=tmp_path/'safe-copy';restore_safe_copy(backup,destination,data)
    with sqlite3.connect(destination/'qishu.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM user_sessions').fetchone()[0]==0
    with Session(engine) as db:
        member=db.get(UserAccount,member_id);member.active=False;db.commit()
    with pytest.raises(BackupError):restore_safe_copy(backup,tmp_path/'refused-copy',data)
    assert not (tmp_path/'refused-copy').exists()
    engine.dispose()
