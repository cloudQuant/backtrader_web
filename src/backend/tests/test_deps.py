from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest


def make_request() -> StarletteRequest:
    """Create a minimal Starlette request for dependency tests."""
    return StarletteRequest(
        {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
        }
    )


def make_websocket(protocols: str = "", query_token: str | None = None) -> SimpleNamespace:
    """Create a minimal websocket-like object for dependency tests."""
    query_params = {}
    if query_token is not None:
        query_params["token"] = query_token

    return SimpleNamespace(
        headers={"sec-websocket-protocol": protocols},
        query_params=query_params,
    )


def test_extract_websocket_token_from_subprotocol():
    from app.api.deps import WEBSOCKET_TOKEN_PROTOCOL, _extract_websocket_token

    websocket = make_websocket(f"{WEBSOCKET_TOKEN_PROTOCOL}, token-123", query_token="legacy")

    assert _extract_websocket_token(websocket) == ("token-123", WEBSOCKET_TOKEN_PROTOCOL)


def test_extract_websocket_token_rejects_query_param_fallback():
    from app.api.deps import _extract_websocket_token

    websocket = make_websocket(query_token="legacy-token")

    assert _extract_websocket_token(websocket) == (None, None)


def test_get_websocket_current_user_requires_subprotocol_token(monkeypatch):
    from app.api.deps import get_websocket_current_user

    monkeypatch.setattr(
        "app.api.deps.decode_access_token",
        lambda _: {"sub": "user-ws", "username": "tester", "exp": 123},
        raising=True,
    )

    websocket = make_websocket(query_token="legacy-token")

    current_user, accepted_subprotocol = get_websocket_current_user(websocket)

    assert current_user is None
    assert accepted_subprotocol is None


@pytest.mark.asyncio
async def test_get_current_user_invalid_token_raises(monkeypatch):
    from app.api.deps import get_current_user

    monkeypatch.setattr("app.api.deps.decode_access_token", lambda _: None, raising=True)
    creds = SimpleNamespace(credentials="bad")

    with pytest.raises(HTTPException) as e:
        await get_current_user(request=make_request(), credentials=creds)
    assert e.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_optional_no_credentials_returns_none():
    from app.api.deps import get_current_user_optional

    assert await get_current_user_optional(request=make_request(), credentials=None) is None


@pytest.mark.asyncio
async def test_get_current_user_optional_invalid_token_returns_none(monkeypatch):
    from app.api.deps import get_current_user_optional

    monkeypatch.setattr("app.api.deps.decode_access_token", lambda _: None, raising=True)
    creds = SimpleNamespace(credentials="bad")
    assert await get_current_user_optional(request=make_request(), credentials=creds) is None


@pytest.mark.asyncio
async def test_get_current_user_optional_valid_token_returns_payload(monkeypatch):
    from app.api.deps import get_current_user_optional

    payload = {"sub": "u1", "username": "test", "exp": 123}
    monkeypatch.setattr("app.api.deps.decode_access_token", lambda _: payload, raising=True)
    creds = SimpleNamespace(credentials="ok")
    out = await get_current_user_optional(request=make_request(), credentials=creds)
    assert out.sub == "u1"
    assert out.username == "test"


@pytest.mark.asyncio
async def test_get_current_user_sets_user_id_in_request_state(monkeypatch):
    """Test that get_current_user writes user_id to request.state."""
    from app.api.deps import get_current_user

    payload = {"sub": "user123", "username": "test", "exp": 123}
    monkeypatch.setattr("app.api.deps.decode_access_token", lambda _: payload, raising=True)

    request = make_request()
    creds = SimpleNamespace(credentials="ok")
    result = await get_current_user(request=request, credentials=creds)

    assert hasattr(request.state, "user_id")
    assert request.state.user_id == "user123"
    assert result.sub == "user123"


@pytest.mark.asyncio
async def test_get_current_user_optional_sets_user_id_in_request_state(monkeypatch):
    """Test that get_current_user_optional writes user_id to request.state when authenticated."""
    from app.api.deps import get_current_user_optional

    payload = {"sub": "user456", "username": "test", "exp": 123}
    monkeypatch.setattr("app.api.deps.decode_access_token", lambda _: payload, raising=True)

    request = make_request()
    creds = SimpleNamespace(credentials="ok")
    result = await get_current_user_optional(request=request, credentials=creds)

    assert hasattr(request.state, "user_id")
    assert request.state.user_id == "user456"
    assert result.sub == "user456"
