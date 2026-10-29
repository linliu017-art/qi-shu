"""Password and session-token primitives for the forthcoming multi-user mode.

These helpers are not wired into the existing single-user service yet.
"""
import base64
import hashlib
import hmac
import secrets

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 5


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 256:
        raise ValueError('密码长度须为 12 至 256 个字符。')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return 'scrypt-v2$' + base64.urlsafe_b64encode(salt + digest).decode('ascii')


def verify_password(password: str, encoded: str) -> bool:
    if len(password) > 256 or not encoded.startswith(('scrypt-v1$', 'scrypt-v2$')):
        return False
    try:
        raw = base64.b64decode(encoded[len('scrypt-v1$'):], altchars=b'-_', validate=True)
        if len(raw) != 48:
            return False
        parallelism = 1 if encoded.startswith('scrypt-v1$') else _SCRYPT_P
        actual = hashlib.scrypt(password.encode('utf-8'), salt=raw[:16], n=_SCRYPT_N, r=_SCRYPT_R, p=parallelism, dklen=32)
        return hmac.compare_digest(actual, raw[16:])
    except (ValueError, UnicodeError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()
