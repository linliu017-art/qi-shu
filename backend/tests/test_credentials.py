import pytest

from app.credentials import hash_password, new_session_token, session_token_hash, verify_password


def test_password_salt_and_verification():
    password = '这是一个足够长的测试密码'
    first, second = hash_password(password), hash_password(password)
    assert first != second
    assert password not in first
    assert verify_password(password, first)
    assert not verify_password(password + '错', first)
    assert not verify_password(password, 'scrypt-v1$invalid')


def test_password_limits_and_session_tokens():
    with pytest.raises(ValueError):
        hash_password('short')
    with pytest.raises(ValueError):
        hash_password('x' * 257)
    first, second = new_session_token(), new_session_token()
    assert first != second
    assert session_token_hash(first) == session_token_hash(first)
    assert session_token_hash(first) != session_token_hash(second)
