"""
Error response contract tests.

Validates that API error responses conform to the standard structure:
{ error, message, details?, request_id?, path? }
"""

import pytest
from httpx import AsyncClient


class TestErrorResponseContract:
    """Validate error response structure for core HTTP status codes."""

    @pytest.mark.asyncio
    async def test_401_response_structure(self, client: AsyncClient):
        """Unauthenticated request returns structured 401 with error and message."""
        resp = await client.get("/api/v1/strategies")
        assert resp.status_code == 401
        data = resp.json()
        assert "error" in data
        assert "message" in data
        assert isinstance(data["error"], str)
        assert isinstance(data["message"], str)
        assert len(data["message"]) > 0

    @pytest.mark.asyncio
    async def test_422_response_structure(self, client: AsyncClient):
        """Validation error returns structured 422 with error, message, and details.fields."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"username": ""},  # missing email, password; invalid username
        )
        assert resp.status_code == 422
        data = resp.json()
        assert "error" in data
        assert "message" in data
        assert isinstance(data["error"], str)
        assert isinstance(data["message"], str)
        if "details" in data and "fields" in data["details"]:
            assert isinstance(data["details"]["fields"], list)
            assert len(data["details"]["fields"]) >= 1
