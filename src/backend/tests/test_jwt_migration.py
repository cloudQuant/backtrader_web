"""Property-based tests for JWT token round-trip.

Feature: best-practices-improvement
Property 1: JWT Token Round-Trip

For any valid payload containing fields sub (string), username (string),
token_type ("access" or "refresh"), and exp (future timestamp), encoding
the payload with PyJWT using HS256 algorithm and a secret key, then decoding
the resulting token with the same key and algorithm, SHALL produce a payload
where sub, username, and token_type fields are identical to the original.

Validates: Requirements 4.2, 4.3, 4.4
"""

from datetime import timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)


class TestJWTRoundTripProperty:
    """Property 1: JWT Token Round-Trip."""

    @given(
        sub=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
        ),
        username=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        ),
    )
    @settings(max_examples=100)
    def test_access_token_roundtrip(self, sub: str, username: str) -> None:
        """Encoding then decoding an access token preserves sub and username."""
        data = {"sub": sub, "username": username}
        token = create_access_token(data, expires_delta=timedelta(hours=1))

        decoded = decode_access_token(token)
        assert decoded is not None
        assert decoded["sub"] == sub
        assert decoded["username"] == username
        assert decoded["token_type"] == "access"

    @given(
        sub=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
        ),
        username=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        ),
    )
    @settings(max_examples=100)
    def test_refresh_token_roundtrip(self, sub: str, username: str) -> None:
        """Encoding then decoding a refresh token preserves sub and username."""
        data = {"sub": sub, "username": username}
        token = create_refresh_token(data, expires_delta=timedelta(days=7))

        decoded = decode_refresh_token(token)
        assert decoded is not None
        assert decoded["sub"] == sub
        assert decoded["username"] == username
        assert decoded["token_type"] == "refresh"

    @given(
        sub=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S"),
                blacklist_characters="\x00",
            ),
        ),
    )
    @settings(max_examples=100)
    def test_token_sub_preserves_special_characters(self, sub: str) -> None:
        """Token encoding preserves special characters in sub field."""
        data = {"sub": sub, "username": "test"}
        token = create_access_token(data, expires_delta=timedelta(hours=1))

        decoded = decode_access_token(token)
        assert decoded is not None
        assert decoded["sub"] == sub
