"""
安全工具测试 - JWT 和密码处理
"""
from datetime import timedelta

from app.utils.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
)


class TestPasswordHash:
    """密码哈希测试"""

    def test_hash_and_verify(self):
        password = "TestPassword123"
        hashed = get_password_hash(password)
        assert hashed != password
        assert verify_password(password, hashed)

    def test_wrong_password(self):
        hashed = get_password_hash("correct_password")
        assert not verify_password("wrong_password", hashed)

    def test_different_hashes(self):
        h1 = get_password_hash("same_password")
        h2 = get_password_hash("same_password")
        assert h1 != h2  # bcrypt uses random salt


class TestJWT:
    """JWT 令牌测试"""

    def test_create_and_decode(self):
        data = {"sub": "user-123", "username": "testuser"}
        token = create_access_token(data)
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["username"] == "testuser"

    def test_custom_expiry(self):
        data = {"sub": "user-456"}
        token = create_access_token(data, expires_delta=timedelta(minutes=5))
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user-456"

    def test_invalid_token(self):
        payload = decode_access_token("invalid.token.string")
        assert payload is None

    def test_expired_token(self):
        data = {"sub": "user-789"}
        token = create_access_token(data, expires_delta=timedelta(seconds=-1))
        payload = decode_access_token(token)
        assert payload is None
