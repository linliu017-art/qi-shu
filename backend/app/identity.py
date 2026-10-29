"""Identity services; integration into the API is a separate, unfinished step."""
from datetime import datetime, timedelta, timezone
import base64
import hashlib

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.orm import aliased
from sqlalchemy.orm import Session

from .credentials import hash_password, new_session_token, session_token_hash, verify_password
from .models import AccountEvent, LoginThrottle, UserAccount, UserSession

SESSION_LIFETIME = timedelta(hours=12)
_DUMMY_HASH = 'scrypt-v2$' + base64.urlsafe_b64encode(bytes(48)).decode('ascii')


def _admin(db: Session, actor_id: str) -> UserAccount:
    actor = db.get(UserAccount, actor_id)
    if not actor or not actor.active or not actor.is_admin:
        raise PermissionError('无权管理账号。')
    return actor


def create_account(db: Session, actor_id: str, username: str, password: str) -> UserAccount:
    _admin(db, actor_id)
    name = username.strip()
    if not name or len(name) > 100 or any(ord(c) < 32 for c in name):
        raise ValueError('账号名称不正确。')
    user = UserAccount(username=name, password_hash=hash_password(password), active=True, is_admin=False)
    db.add(user)
    db.flush()
    db.add(AccountEvent(actor_id=actor_id, target_id=user.id, action='created'))
    db.commit()
    return user


def enable_account(db: Session, actor_id: str, target_id: str) -> None:
    _admin(db, actor_id)
    target = db.get(UserAccount, target_id)
    if not target:
        raise ValueError('账号不存在。')
    if target.active:
        return
    target.active = True
    db.add(AccountEvent(actor_id=actor_id, target_id=target_id, action='enabled'))
    db.commit()


def reset_password(db: Session, actor_id: str, target_id: str, password: str) -> None:
    _admin(db, actor_id)
    target = db.get(UserAccount, target_id)
    if not target:
        raise ValueError('账号不存在。')
    target.password_hash = hash_password(password)
    db.execute(delete(UserSession).where(UserSession.user_id == target_id))
    db.execute(delete(LoginThrottle).where(LoginThrottle.username_hash == hashlib.sha256(target.username.encode('utf-8')).hexdigest()))
    db.add(AccountEvent(actor_id=actor_id, target_id=target_id, action='password_reset'))
    db.commit()


def login(db: Session, username: str, password: str) -> str | None:
    user = db.scalar(select(UserAccount).where(UserAccount.username == username))
    if not user or not user.active or not verify_password(password, user.password_hash):
        return None
    if user.password_hash.startswith('scrypt-v1$'):
        user.password_hash = hash_password(password)
    token = new_session_token()
    db.add(UserSession(token_hash=session_token_hash(token), user_id=user.id,
                       expires_at=datetime.now(timezone.utc) + SESSION_LIFETIME))
    db.commit()
    return token


def login_throttled(db: Session, username: str, password: str) -> str | None:
    """Serialize attempts per local SQLite database; persist no password or raw login name."""
    if db.get_bind().dialect.name != 'sqlite':
        raise RuntimeError('本机登录限流仅支持 SQLite。')
    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(username.encode('utf-8')).hexdigest()
    db.execute(text('BEGIN IMMEDIATE'))
    record = db.get(LoginThrottle, digest)
    if record and record.locked_until:
        expiry = record.locked_until.replace(tzinfo=timezone.utc) if record.locked_until.tzinfo is None else record.locked_until
        if expiry > now:
            db.rollback()
            return None
    user = db.scalar(select(UserAccount).where(UserAccount.username == username))
    valid = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if user and user.active and valid:
        if user.password_hash.startswith('scrypt-v1$'):
            user.password_hash = hash_password(password)
        if record:
            db.delete(record)
        token = new_session_token()
        db.add(UserSession(token_hash=session_token_hash(token), user_id=user.id, expires_at=now + SESSION_LIFETIME))
        db.commit()
        return token
    if not record:
        record = LoginThrottle(username_hash=digest, failures=0, window_started_at=now)
        db.add(record)
    start = record.window_started_at
    start = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start
    if now - start >= timedelta(minutes=5) or (record.locked_until and expiry <= now):
        record.failures, record.window_started_at, record.locked_until = 0, now, None
    record.failures += 1
    if record.failures >= 5:
        record.locked_until = now + timedelta(minutes=5)
    db.commit()
    return None


def authenticate(db: Session, token: str) -> UserAccount | None:
    if not token or len(token) > 256:
        return None
    entry = db.get(UserSession, session_token_hash(token))
    if not entry:
        return None
    expiration = entry.expires_at
    if expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=timezone.utc)
    if expiration <= datetime.now(timezone.utc):
        return None
    user = db.get(UserAccount, entry.user_id)
    return user if user and user.active else None


def logout(db: Session, token: str) -> None:
    if token and len(token) <= 256:
        db.execute(delete(UserSession).where(UserSession.token_hash == session_token_hash(token)))
        db.commit()


def disable_account(db: Session, actor_id: str, target_id: str) -> None:
    """Disable an account and revoke all sessions in the same transaction."""
    actor = db.get(UserAccount, actor_id)
    target = db.get(UserAccount, target_id)
    if not actor or not actor.active or not actor.is_admin or not target:
        raise PermissionError('无权停用该账号。')
    if not target.active:
        return
    admin_copy = aliased(UserAccount)
    active_admins = select(func.count()).select_from(admin_copy).where(admin_copy.active.is_(True), admin_copy.is_admin.is_(True)).scalar_subquery()
    result = db.execute(update(UserAccount).where(UserAccount.id == target_id, UserAccount.active.is_(True),
                        or_(UserAccount.is_admin.is_(False), active_admins > 1)).values(active=False))
    if result.rowcount != 1:
        db.rollback()
        raise ValueError('至少保留一个启用的管理员。')
    db.execute(delete(UserSession).where(UserSession.user_id == target_id))
    db.add(AccountEvent(actor_id=actor_id, target_id=target_id, action='disabled'))
    db.commit()
