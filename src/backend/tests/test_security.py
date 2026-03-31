"""
Security utilities tests - JWT and password handling.
"""

from datetime import timedelta

from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    generate_refresh_token_id,
    get_password_hash,
    hash_token,
    validate_password_strength,
    verify_password,
    verify_token_hash,
)


class TestPasswordHash:
    """Password hashing tests."""

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


class TestPasswordStrength:
    """Password strength validation tests."""

    def test_valid_strong_password(self):
        is_valid, errors = validate_password_strength("SecurePass123!")
        assert is_valid is True
        assert errors == []

    def test_short_password(self):
        is_valid, errors = validate_password_strength("Short1!")
        assert is_valid is False
        assert any("8 characters" in e for e in errors)

    def test_long_password(self):
        long_pw = "A" * 129 + "1!a"
        is_valid, errors = validate_password_strength(long_pw)
        assert is_valid is False
        assert any("128 characters" in e for e in errors)

    def test_no_uppercase(self):
        is_valid, errors = validate_password_strength("lowercase123!")
        assert is_valid is False
        assert any("uppercase" in e for e in errors)

    def test_no_lowercase(self):
        is_valid, errors = validate_password_strength("UPPERCASE123!")
        assert is_valid is False
        assert any("lowercase" in e for e in errors)

    def test_no_digit(self):
        is_valid, errors = validate_password_strength("NoDigitsHere!")
        assert is_valid is False
        assert any("digit" in e for e in errors)

    def test_no_special(self):
        is_valid, errors = validate_password_strength("NoSpecial123")
        assert is_valid is False
        assert any("special character" in e for e in errors)

    def test_common_password(self):
        # Use a password that IS in the common_passwords set
        is_valid, errors = validate_password_strength("password123")
        assert is_valid is False
        # "password123" is in common_passwords set
        assert any("common" in e.lower() for e in errors)

    def test_multiple_errors(self):
        is_valid, errors = validate_password_strength("short")
        assert is_valid is False
        assert len(errors) >= 3  # short, no digit, no special, no upper/lower


class TestTokenHash:
    """Token hashing tests."""

    def test_hash_token(self):
        token = "test-token-12345"
        hashed = hash_token(token)
        assert hashed != token
        assert len(hashed) == 64  # SHA-256 hex digest

    def test_verify_token_hash(self):
        token = "test-token-12345"
        hashed = hash_token(token)
        assert verify_token_hash(token, hashed)

    def test_verify_wrong_token(self):
        hashed = hash_token("correct-token")
        assert not verify_token_hash("wrong-token", hashed)

    def test_consistent_hash(self):
        token = "same-token"
        h1 = hash_token(token)
        h2 = hash_token(token)
        assert h1 == h2


class TestJWT:
    """JWT token tests."""

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

    def test_token_type_access(self):
        data = {"sub": "user-123"}
        token = create_access_token(data)
        payload = decode_access_token(token)
        assert payload is not None
        assert payload.get("token_type") == "access"


class TestRefreshToken:
    """Refresh token tests."""

    def test_create_refresh_token(self):
        data = {"sub": "user-123"}
        token = create_refresh_token(data)
        assert token is not None
        assert isinstance(token, str)

    def test_decode_refresh_token(self):
        data = {"sub": "user-456"}
        token = create_refresh_token(data)
        payload = decode_refresh_token(token)
        assert payload is not None
        assert payload["sub"] == "user-456"
        assert payload.get("token_type") == "refresh"

    def test_decode_access_token_as_refresh_fails(self):
        data = {"sub": "user-789"}
        access_token = create_access_token(data)
        payload = decode_refresh_token(access_token)
        assert payload is None  # Wrong token type

    def test_invalid_refresh_token(self):
        payload = decode_refresh_token("invalid.refresh.token")
        assert payload is None

    def test_refresh_token_custom_expiry(self):
        data = {"sub": "user-123"}
        token = create_refresh_token(data, expires_delta=timedelta(days=7))
        payload = decode_refresh_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"


class TestRefreshTokenId:
    """Refresh token ID generation tests."""

    def test_generate_id(self):
        token_id = generate_refresh_token_id()
        assert token_id is not None
        assert isinstance(token_id, str)
        assert len(token_id) > 0

    def test_unique_ids(self):
        id1 = generate_refresh_token_id()
        id2 = generate_refresh_token_id()
        assert id1 != id2

    def test_id_length(self):
        token_id = generate_refresh_token_id()
        # token_urlsafe(32) produces 43 characters
        assert len(token_id) == 43


class TestTokenTypeSeparation:
    """Verify that access tokens cannot be used as refresh tokens and vice versa."""

    def test_refresh_token_decoded_as_access_has_refresh_type(self):
        """decode_access_token decodes any valid JWT; callers must check token_type."""
        data = {"sub": "user-123"}
        refresh_token = create_refresh_token(data)
        payload = decode_access_token(refresh_token)
        # decode_access_token doesn't validate token_type, so the token decodes
        # but the caller should check token_type == "access"
        assert payload is not None
        assert payload.get("token_type") == "refresh"

    def test_access_token_rejected_as_refresh(self):
        data = {"sub": "user-123"}
        access_token = create_access_token(data)
        payload = decode_refresh_token(access_token)
        assert payload is None

    def test_expired_refresh_token(self):
        data = {"sub": "user-123"}
        token = create_refresh_token(data, expires_delta=timedelta(seconds=-1))
        payload = decode_refresh_token(token)
        assert payload is None

    def test_empty_string_token(self):
        assert decode_access_token("") is None
        assert decode_refresh_token("") is None

    def test_none_like_token(self):
        assert decode_access_token("null") is None
        assert decode_refresh_token("undefined") is None


class TestPasswordEdgeCases:
    """Edge cases for password validation."""

    def test_empty_password(self):
        is_valid, errors = validate_password_strength("")
        assert is_valid is False
        assert len(errors) >= 1

    def test_unicode_password(self):
        """Unicode characters in password should be accepted if strong enough."""
        is_valid, errors = validate_password_strength("Ünïcödé1234!@")
        assert is_valid is True
        assert errors == []

    def test_password_only_special_chars(self):
        is_valid, errors = validate_password_strength("!@#$%^&*()")
        assert is_valid is False


class TestTokenHashEdgeCases:
    """Edge cases for token hashing."""

    def test_empty_token_hash(self):
        hashed = hash_token("")
        assert len(hashed) == 64
        assert not verify_token_hash("nonempty", hashed)

    def test_long_token_hash(self):
        long_token = "a" * 10000
        hashed = hash_token(long_token)
        assert verify_token_hash(long_token, hashed)
