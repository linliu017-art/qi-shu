"""Create and verify local database-and-originals snapshots; not yet exposed via HTTP."""
import hashlib
import json
import shutil
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path


class BackupError(Exception):
    pass


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _material_name(value: str) -> str:
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
        return value
    except (ValueError, AttributeError):
        raise BackupError('资料存储路径无效。') from None


def _originals(db_path: Path) -> list[tuple[str, str]]:
    with closing(sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise BackupError('数据库完整性检查未通过。')
        return [(_material_name(name), digest) for name, digest in
                db.execute('SELECT filename_on_disk, sha256 FROM material_originals')]


def create_backup(data_dir: Path, destination: Path) -> None:
    """Create a new destination; never overwrite an existing backup."""
    source_db = data_dir / 'qishu.sqlite3'
    if not source_db.is_file() or source_db.is_symlink():
        raise BackupError('找不到可备份的数据库。')
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        database = destination / 'qishu.sqlite3'
        with closing(sqlite3.connect(f'file:{source_db}?mode=ro', uri=True)) as source, closing(sqlite3.connect(database)) as target:
            source.backup(target)
        originals = _originals(database)
        material_dir = destination / 'materials'
        material_dir.mkdir(mode=0o700)
        records = {}
        for name, expected in originals:
            original = data_dir / 'materials' / name
            if not original.is_file() or original.is_symlink():
                raise BackupError('资料原件缺失或不是普通文件。')
            copied = material_dir / name
            shutil.copyfile(original, copied)
            if _digest(copied) != expected:
                raise BackupError('资料原件校验失败。')
            records[name] = expected
        manifest = {'version': 1, 'database_sha256': _digest(database), 'materials': records}
        (destination / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True), encoding='utf-8')
        verify_backup(destination)
    except Exception:
        shutil.rmtree(destination)
        raise


def verify_backup(source: Path) -> None:
    if source.is_symlink():
        raise BackupError('备份位置无效。')
    try:
        manifest_path, database = source / 'manifest.json', source / 'qishu.sqlite3'
        if manifest_path.is_symlink() or database.is_symlink() or (source / 'materials').is_symlink():
            raise BackupError('备份中不能包含符号链接。')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest['version'] != 1 or _digest(database) != manifest['database_sha256']:
            raise BackupError('备份数据库校验失败。')
        expected = dict(_originals(database))
        if manifest['materials'] != expected:
            raise BackupError('备份清单与数据库不一致。')
        for name, digest in expected.items():
            path = source / 'materials' / name
            if path.is_symlink() or not path.is_file() or _digest(path) != digest:
                raise BackupError('备份原件校验失败。')
    except (KeyError, ValueError, TypeError, OSError, sqlite3.Error):
        raise BackupError('备份无法读取或校验。') from None


def restore_to_new_directory(source: Path, destination: Path) -> None:
    """Restore only to a new directory; never overwrite live data."""
    verify_backup(source)
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        shutil.copyfile(source / 'qishu.sqlite3', destination / 'qishu.sqlite3')
        (destination / 'materials').mkdir(mode=0o700)
        if _digest(destination / 'qishu.sqlite3') != _digest(source / 'qishu.sqlite3'):
            raise BackupError('恢复数据库校验失败。')
        for name, digest in _originals(destination / 'qishu.sqlite3'):
            original = source / 'materials' / name
            if original.is_symlink():
                raise BackupError('备份原件不是普通文件。')
            shutil.copyfile(original, destination / 'materials' / name)
            if _digest(destination / 'materials' / name) != digest:
                raise BackupError('恢复资料校验失败。')
    except Exception:
        shutil.rmtree(destination)
        raise


def restore_safe_copy(source: Path, destination: Path, current_data: Path) -> None:
    """Restore only if no backed-up permission or deletion has since changed."""
    verify_backup(source)
    current_path = current_data / 'qishu.sqlite3'
    if not current_path.is_file() or current_path.is_symlink():
        raise BackupError('当前数据库不可用，无法核对权限。')
    checks = (
        ('user_accounts', 'id, active, is_admin, password_hash'),
        ('projects', 'id'),
        ('project_members', 'project_id, user_id, role'),
        ('materials', 'id, project_id'),
        ('project_lifecycle', 'project_id, state, version'),
        ('material_versions', 'material_id, state, state_version'),
    )
    try:
        with closing(sqlite3.connect(current_path, timeout=10)) as live, closing(sqlite3.connect(f'file:{source / "qishu.sqlite3"}?mode=ro', uri=True)) as backup:
            live.execute('BEGIN IMMEDIATE')
            try:
                for table, columns in checks:
                    before = set(backup.execute(f'SELECT {columns} FROM {table}'))
                    after = set(live.execute(f'SELECT {columns} FROM {table}'))
                    if not before.issubset(after):
                        raise BackupError('备份后的账号、项目权限或资料状态已变化，不能自动恢复，请人工核对。')
                restore_to_new_directory(source, destination)
                try:
                    with sqlite3.connect(destination / 'qishu.sqlite3') as restored:
                        restored.execute('DELETE FROM user_sessions')
                except (sqlite3.Error, OSError):
                    shutil.rmtree(destination, ignore_errors=True)
                    raise BackupError('无法清除副本中的旧会话，已取消恢复。') from None
            finally:
                live.rollback()
    except sqlite3.Error:
        raise BackupError('无法核对备份和当前权限，未执行恢复。') from None
