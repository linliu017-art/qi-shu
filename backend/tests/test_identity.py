from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.credentials import hash_password, session_token_hash
from app.database import Base
import pytest
from concurrent.futures import ThreadPoolExecutor

from app.identity import authenticate, create_account, disable_account, enable_account, login, login_throttled, logout, reset_password
from app.models import AccountEvent, UserAccount, UserSession


def test_login_expiry_logout_and_disabled_account():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = UserAccount(username='test-user', password_hash=hash_password('测试密码至少需要十二个字符'), active=True, is_admin=False)
        db.add(user)
        db.commit()
        assert login(db, user.username, 'wrong') is None
        token = login(db, user.username, '测试密码至少需要十二个字符')
        assert token and authenticate(db, token).id == user.id
        assert db.get(UserSession, token) is None
        session = db.get(UserSession, session_token_hash(token))
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        assert authenticate(db, token) is None
        token = login(db, user.username, '测试密码至少需要十二个字符')
        user.active = False
        db.commit()
        assert authenticate(db, token) is None
        assert login(db, user.username, '测试密码至少需要十二个字符') is None
        logout(db, token)
        assert db.get(UserSession, session_token_hash(token)) is None
    engine.dispose()


def test_concurrent_admin_disables_cannot_remove_last_admin(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "admins.sqlite3"}')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        one = UserAccount(username='one', password_hash='test', active=True, is_admin=True)
        two = UserAccount(username='two', password_hash='test', active=True, is_admin=True)
        db.add_all([one, two]); db.commit()
        ids = (one.id, two.id)
    def attempt(pair):
        with Session(engine) as db:
            try:
                disable_account(db, *pair)
            except (PermissionError, ValueError):
                db.rollback()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(attempt, [ids, ids[::-1]]))
    with Session(engine) as db:
        assert sum(db.get(UserAccount, uid).active for uid in ids) >= 1
    engine.dispose()


def test_login_limit_persists_and_admin_reset_unlocks(tmp_path):
    path = tmp_path / 'throttle.sqlite3'
    engine = create_engine(f'sqlite:///{path}')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        admin = UserAccount(username='admin', password_hash=hash_password('管理员使用的足够长的密码'), active=True, is_admin=True)
        member = UserAccount(username='member', password_hash=hash_password('成员使用的足够长的测试密码'), active=True, is_admin=False)
        db.add_all([admin, member]); db.commit()
        ids = admin.id, member.id
        for _ in range(5):
            assert login_throttled(db, 'member', 'wrong') is None
    engine.dispose()
    engine = create_engine(f'sqlite:///{path}')
    with Session(engine) as db:
        assert login_throttled(db, 'member', '成员使用的足够长的测试密码') is None
        reset_password(db, ids[0], ids[1], '另一个足够长的新测试密码')
        assert login_throttled(db, 'member', '另一个足够长的新测试密码')
    engine.dispose()


def test_admin_creates_reactivates_and_resets_account():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin = UserAccount(username='admin', password_hash=hash_password('管理员使用的足够长的密码'), active=True, is_admin=True)
        db.add(admin)
        db.commit()
        user = create_account(db, admin.id, 'new-user', '足够长的初始测试密码字符串')
        old_token = login(db, user.username, '足够长的初始测试密码字符串')
        with pytest.raises(PermissionError):
            create_account(db, user.id, 'not-allowed', '足够长的初始测试密码字符串')
        reset_password(db, admin.id, user.id, '另一个足够长的新测试密码')
        assert authenticate(db, old_token) is None
        assert login(db, user.username, '足够长的初始测试密码字符串') is None
        assert login(db, user.username, '另一个足够长的新测试密码')
        disable_account(db, admin.id, user.id)
        enable_account(db, admin.id, user.id)
        assert user.active
        actions = [event.action for event in db.query(AccountEvent).all()]
        assert actions == ['created', 'password_reset', 'disabled', 'enabled']
    engine.dispose()


def test_disabling_revokes_sessions_and_retains_an_admin():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin = UserAccount(username='admin', password_hash=hash_password('管理员使用的足够长的密码'), active=True, is_admin=True)
        member = UserAccount(username='member', password_hash=hash_password('成员使用的足够长的测试密码'), active=True, is_admin=False)
        db.add_all([admin, member])
        db.commit()
        token = login(db, member.username, '成员使用的足够长的测试密码')
        with pytest.raises(PermissionError):
            disable_account(db, member.id, admin.id)
        with pytest.raises(ValueError):
            disable_account(db, admin.id, admin.id)
        disable_account(db, admin.id, member.id)
        assert authenticate(db, token) is None
        member.active = True
        db.commit()
        assert authenticate(db, token) is None
    engine.dispose()
