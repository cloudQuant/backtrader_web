"""
Security utilities for JWT and password handling.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()


# Token type constants
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# Refresh token expiration (30 days)
REFRESH_TOKEN_EXPIRE_DAYS = 30


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Args:
        plain_password: The plain text password.
        hashed_password: The bcrypt hashed password.

    Returns:
        True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def get_password_hash(password: str) -> str:
    """Generate a password hash.

    Args:
        password: The plain text password.

    Returns:
        The bcrypt hashed password as a string.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def validate_password_strength(password: str) -> tuple[bool, list[str]]:
    """Validate password strength according to security best practices.

    Args:
        password: The password to validate.

    Returns:
        A tuple of (is_valid, list_of_errors).
    """
    errors = []

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")

    if len(password) > 128:
        errors.append("Password must not exceed 128 characters")

    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)

    if not (has_upper and has_lower):
        errors.append("Password must contain both uppercase and lowercase letters")

    if not has_digit:
        errors.append("Password must contain at least one digit")

    if not has_special:
        errors.append("Password must contain at least one special character")

    # Check for common passwords
    common_passwords = {
        "password", "password123", "admin", "12345678",
        "qwerty", "abc123", "letmein", "welcome"
    }
    if password.lower() in common_passwords:
        errors.append("Password is too common")

    return len(errors) == 0, errors


def hash_token(token: str) -> str:
    """Hash a token using SHA-256.

    This is used for refresh tokens which can be longer than bcrypt's 72-byte limit.

    Args:
        token: The token to hash.

    Returns:
        The hex digest of the SHA-256 hash.
    """
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def verify_token_hash(token: str, token_hash: str) -> bool:
    """Verify a token against its hash.

    Args:
        token: The token to verify.
        token_hash: The stored hash to compare against.

    Returns:
        True if the token matches the hash, False otherwise.
    """
    return hash_token(token) == token_hash


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT access token.

    Args:
        data: The payload data to encode.
        expires_delta: Optional expiration time delta.

    Returns:
        The encoded JWT token.
    """
    to_encode = data.copy()
    to_encode.update({"token_type": TOKEN_TYPE_ACCESS})

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT refresh token.

    Refresh tokens have longer expiration and are used to obtain new access tokens.

    Args:
        data: The payload data to encode.
        expires_delta: Optional expiration time delta.

    Returns:
        The encoded JWT refresh token.
    """
    to_encode = data.copy()
    to_encode.update({"token_type": TOKEN_TYPE_REFRESH})

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def generate_refresh_token_id() -> str:
    """Generate a unique ID for refresh token storage.

    Returns:
        A cryptographically secure random token ID.
    """
    return secrets.token_urlsafe(32)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode a JWT token.

    Args:
        token: The JWT token to decode.

    Returns:
        The decoded payload, or None if decoding fails.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


def decode_refresh_token(token: str) -> Optional[dict]:
    """Decode and validate a refresh token.

    Args:
        token: The refresh token to decode.

    Returns:
        The decoded payload if valid and of type refresh, None otherwise.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        # Verify it's a refresh token
        if payload.get("token_type") != TOKEN_TYPE_REFRESH:
            return None
        return payload
    except JWTError:
        return None
