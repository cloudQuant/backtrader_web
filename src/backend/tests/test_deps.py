from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_get_current_user_invalid_token_raises(monkeypatch):
    from app.api.deps import get_current_user

    monkeypatch.setattr("app.api.deps.decode_access_token", lambda _: None, raising=True)
    creds = SimpleNamespace(credentials="bad")

    with pytest.raises(HTTPException) as e:
        await get_current_user(credentials=creds)
    assert e.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_optional_no_credentials_returns_none():
    from app.api.deps import get_current_user_optional

    assert await get_current_user_optional(credentials=None) is None


@pytest.mark.asyncio
async def test_get_current_user_optional_invalid_token_returns_none(monkeypatch):
    from app.api.deps import get_current_user_optional

    monkeypatch.setattr("app.api.deps.decode_access_token", lambda _: None, raising=True)
    creds = SimpleNamespace(credentials="bad")
    assert await get_current_user_optional(credentials=creds) is None


@pytest.mark.asyncio
async def test_get_current_user_optional_valid_token_returns_payload(monkeypatch):
    from app.api.deps import get_current_user_optional

    payload = {"sub": "u1", "username": "test", "exp": 123}
    monkeypatch.setattr("app.api.deps.decode_access_token", lambda _: payload, raising=True)
    creds = SimpleNamespace(credentials="ok")
    out = await get_current_user_optional(credentials=creds)
    assert out.sub == "u1"
    assert out.username == "test"

