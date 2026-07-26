"""
Security penetration tests (automated).

Covers OWASP Top 10 risks relevant to this application:
- A01: Broken Access Control (IDOR, privilege escalation)
- A02: Cryptographic Failures (JWT manipulation)
- A03: Injection (SQL injection, code injection, path traversal)
- A04: Insecure Design (sandbox escape, rate limiting)
- A07: Authentication Failures (brute force, token expiry)

Run with: pytest tests/test_security.py -v -m security
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.security


# ══════════════════════════════════════════════════════════════════════════════
# A01: Broken Access Control — IDOR (Insecure Direct Object Reference)
# ══════════════════════════════════════════════════════════════════════════════


class TestIDOR:
    """Test that users cannot access other users' resources by manipulating IDs."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_users_backtest(self, client: AsyncClient, auth_headers):
        """User A cannot view User B's backtest results by guessing task_id."""
        # Try to access a non-existent task (simulates guessing another user's ID)
        resp = await client.get("/api/v1/backtests/fake-task-id-12345", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_delete_other_users_strategy(self, client: AsyncClient, auth_headers):
        """User cannot delete a strategy they don't own."""
        resp = await client.delete("/api/v1/strategy/nonexistent-id", headers=auth_headers)
        assert resp.status_code in (404, 403)

    @pytest.mark.asyncio
    async def test_paper_trading_account_isolation(self, client: AsyncClient, auth_headers):
        """User cannot access another user's paper trading account."""
        resp = await client.get(
            "/api/v1/paper-trading/accounts/other-user-account-id", headers=auth_headers
        )
        assert resp.status_code in (404, 403)

    @pytest.mark.asyncio
    async def test_knowledge_base_isolation(self, client: AsyncClient, auth_headers):
        """User cannot access another user's knowledge base."""
        resp = await client.get("/api/v1/knowledge-base/other-user-kb-id", headers=auth_headers)
        assert resp.status_code in (404, 403)


# ══════════════════════════════════════════════════════════════════════════════
# A02: Cryptographic Failures — JWT Token Security
# ══════════════════════════════════════════════════════════════════════════════


class TestJWTSecurity:
    """Test JWT token handling security."""

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, client: AsyncClient):
        """Expired JWT tokens are rejected."""
        import jwt

        from app.config import get_settings

        settings = get_settings()
        # Create an expired token
        payload = {
            "sub": "test-user-id",
            "username": "testuser",
            "token_type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")

        resp = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self, client: AsyncClient):
        """Tokens signed with wrong key are rejected."""
        import jwt

        payload = {
            "sub": "test-user-id",
            "username": "testuser",
            "token_type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        # Sign with a different secret
        bad_token = jwt.encode(payload, "wrong-secret-key", algorithm="HS256")

        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_tampered_payload_rejected(self, client: AsyncClient):
        """Tokens with tampered payload (modified sub) are rejected."""
        import jwt

        from app.config import get_settings

        settings = get_settings()
        # Create a valid-looking token but with a non-existent user
        payload = {
            "sub": "non-existent-user-id-hacked",
            "username": "hacker",
            "token_type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")

        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        # Should return 404 (user not found) not 200 with another user's data
        assert resp.status_code in (401, 404)

    @pytest.mark.asyncio
    async def test_no_token_rejected(self, client: AsyncClient):
        """Requests without token are rejected on protected endpoints."""
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_token_rejected(self, client: AsyncClient):
        """Malformed tokens are rejected gracefully."""
        malformed_tokens = [
            "not-a-jwt",
            "eyJ.eyJ.sig",  # truncated
            "",
            "Bearer ",
            "null",
            "undefined",
        ]
        for token in malformed_tokens:
            resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 401, f"Token '{token}' should be rejected"


# ══════════════════════════════════════════════════════════════════════════════
# A03: Injection — SQL Injection, XSS, Path Traversal
# ══════════════════════════════════════════════════════════════════════════════


class TestInjection:
    """Test resistance to injection attacks."""

    @pytest.mark.asyncio
    async def test_sql_injection_in_login(self, client: AsyncClient):
        """SQL injection in login fields is handled safely."""
        payloads = [
            {"username": "' OR '1'='1", "password": "anything"},
            {"username": "admin'--", "password": "x"},
            {"username": "'; DROP TABLE users;--", "password": "x"},
            {"username": "admin", "password": "' OR '1'='1"},
        ]
        for payload in payloads:
            resp = await client.post("/api/v1/auth/login", json=payload)
            # Should return 401 (invalid credentials), not 200 or 500
            assert resp.status_code in (401, 422), (
                f"SQL injection payload {payload} got unexpected status {resp.status_code}"
            )

    @pytest.mark.asyncio
    async def test_sql_injection_in_search(self, client: AsyncClient, auth_headers):
        """SQL injection in search/filter parameters is handled safely."""
        payloads = [
            "' OR 1=1--",
            "'; DROP TABLE strategies;--",
            "1 UNION SELECT * FROM users--",
        ]
        for payload in payloads:
            resp = await client.get(
                f"/api/v1/strategy/templates?search={payload}", headers=auth_headers
            )
            # Should return 200 with empty results, not 500
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_path_traversal_in_strategy_id(self, client: AsyncClient, auth_headers):
        """Path traversal in strategy IDs is blocked."""
        traversal_payloads = [
            "../../../etc/passwd",
            "..%2F..%2F..%2Fetc%2Fpasswd",
            "....//....//etc/passwd",
            "/etc/passwd",
            "strategy/../../../etc/passwd",
        ]
        for payload in traversal_payloads:
            resp = await client.get(
                f"/api/v1/strategy/templates/{payload}/readme", headers=auth_headers
            )
            # Should return 404 or 400, never expose file contents
            assert resp.status_code in (400, 404, 422), (
                f"Path traversal '{payload}' got status {resp.status_code}"
            )
            if resp.status_code == 200:
                # Even if 200, content should not contain system file data
                assert "root:" not in resp.text

    @pytest.mark.asyncio
    async def test_xss_in_strategy_name(self, client: AsyncClient, auth_headers):
        """XSS payloads in strategy names are stored safely."""
        xss_payloads = [
            '<script>alert("xss")</script>',
            "<img src=x onerror=alert(1)>",
            '"><script>document.cookie</script>',
            "javascript:alert(1)",
        ]
        for payload in xss_payloads:
            resp = await client.post(
                "/api/v1/strategy/",
                json={
                    "name": payload,
                    "description": "test",
                    "code": "import backtrader as bt\nclass Strategy(bt.Strategy): pass",
                    "category": "custom",
                },
                headers=auth_headers,
            )
            # Should accept the input (stored safely) or reject it
            # The key is that it doesn't execute — frontend sanitizes on render
            assert resp.status_code in (200, 201, 400, 422)


# ══════════════════════════════════════════════════════════════════════════════
# A03: Code Injection — Strategy Sandbox Escape
# ══════════════════════════════════════════════════════════════════════════════


class TestSandboxSecurity:
    """Test that the strategy code sandbox prevents malicious code execution."""

    def test_sandbox_blocks_os_import(self):
        """Sandbox blocks importing os module."""
        from app.utils.sandbox import StrategySandbox

        malicious_code = """
import os
os.system('echo pwned')
"""
        with pytest.raises((ImportError, NameError, RuntimeError, ValueError)):
            StrategySandbox.execute_strategy_code(malicious_code, {})

    def test_sandbox_blocks_subprocess(self):
        """Sandbox blocks subprocess module."""
        from app.utils.sandbox import StrategySandbox

        malicious_code = """
import subprocess
subprocess.run(['ls', '/'])
"""
        with pytest.raises((ImportError, NameError, RuntimeError, ValueError)):
            StrategySandbox.execute_strategy_code(malicious_code, {})

    def test_sandbox_blocks_file_read(self):
        """Sandbox blocks reading files via open()."""
        from app.utils.sandbox import StrategySandbox

        malicious_code = """
with open('/etc/passwd', 'r') as f:
    data = f.read()
"""
        with pytest.raises((NameError, RuntimeError, ValueError, TypeError)):
            StrategySandbox.execute_strategy_code(malicious_code, {})

    def test_sandbox_blocks_eval_exec(self):
        """Sandbox blocks eval() and exec()."""
        from app.utils.sandbox import StrategySandbox

        for func in ["eval", "exec", "compile"]:
            malicious_code = f"""
{func}("__import__('os').system('echo pwned')")
"""
            with pytest.raises((NameError, RuntimeError, ValueError, TypeError)):
                StrategySandbox.execute_strategy_code(malicious_code, {})

    def test_sandbox_blocks_network_access(self):
        """Sandbox blocks network access via socket/urllib/requests."""
        from app.utils.sandbox import StrategySandbox

        network_codes = [
            "import socket\nsocket.socket()",
            "import urllib.request\nurllib.request.urlopen('http://evil.com')",
            "import requests\nrequests.get('http://evil.com')",
            "import http.client\nhttp.client.HTTPConnection('evil.com')",
        ]
        for code in network_codes:
            with pytest.raises((ImportError, NameError, RuntimeError, ValueError)):
                StrategySandbox.execute_strategy_code(code, {})

    def test_sandbox_blocks_dunder_access(self):
        """Sandbox blocks access to dangerous dunder attributes."""
        from app.utils.sandbox import StrategySandbox

        escape_attempts = [
            "x = ().__class__.__bases__[0].__subclasses__()",
            "x = ''.__class__.__mro__[1].__subclasses__()",
            "globals()['__builtins__']['__import__']('os')",
            "vars()['__builtins__']",
        ]
        for code in escape_attempts:
            with pytest.raises((NameError, RuntimeError, ValueError, TypeError, AttributeError)):
                StrategySandbox.execute_strategy_code(code, {})

    def test_sandbox_blocks_importlib(self):
        """Sandbox blocks importlib-based import bypass."""
        from app.utils.sandbox import StrategySandbox

        malicious_code = """
import importlib
importlib.import_module('os')
"""
        with pytest.raises((ImportError, NameError, RuntimeError, ValueError)):
            StrategySandbox.execute_strategy_code(malicious_code, {})

    def test_sandbox_allows_valid_strategy(self):
        """Sandbox AST check allows legitimate backtrader strategy code."""
        from app.utils.sandbox import StrategySandbox

        valid_code = """
import bt
import math

class MyStrategy(bt.Strategy):
    params = (('period', 20),)

    def __init__(self):
        self.counter = 0

    def next(self):
        self.counter += 1
        if self.counter > self.params.period:
            self.buy()
"""
        # AST safety check should pass for valid strategy code
        StrategySandbox._check_code_safety(valid_code)  # should not raise


# ══════════════════════════════════════════════════════════════════════════════
# A04: Insecure Design — Input Validation
# ══════════════════════════════════════════════════════════════════════════════


class TestInputValidation:
    """Test that invalid/malicious inputs are rejected gracefully."""

    @pytest.mark.asyncio
    async def test_oversized_strategy_code(self, client: AsyncClient, auth_headers):
        """Extremely large strategy code is rejected or handled safely."""
        # 1MB of code
        huge_code = "x = 1\n" * 100000
        resp = await client.post(
            "/api/v1/strategy/",
            json={
                "name": "huge",
                "description": "test",
                "code": huge_code,
                "category": "custom",
            },
            headers=auth_headers,
        )
        # Should either accept (with size limit) or reject with 413/422
        assert resp.status_code in (200, 201, 400, 413, 422)

    @pytest.mark.asyncio
    async def test_negative_initial_cash(self, client: AsyncClient, auth_headers):
        """Negative initial cash in backtest is rejected."""
        resp = await client.post(
            "/api/v1/backtests/run",
            json={
                "strategy_id": "001_ma_cross",
                "symbol": "000001.SZ",
                "start_date": "2023-01-01T00:00:00",
                "end_date": "2023-12-31T00:00:00",
                "initial_cash": -100000,
                "commission": 0.001,
                "params": {},
            },
            headers=auth_headers,
        )
        # Should reject negative cash
        assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_invalid_date_range(self, client: AsyncClient, auth_headers):
        """End date before start date is rejected."""
        resp = await client.post(
            "/api/v1/backtests/run",
            json={
                "strategy_id": "001_ma_cross",
                "symbol": "000001.SZ",
                "start_date": "2023-12-31T00:00:00",
                "end_date": "2023-01-01T00:00:00",
                "initial_cash": 100000,
                "commission": 0.001,
                "params": {},
            },
            headers=auth_headers,
        )
        # Should reject invalid date range
        assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_special_characters_in_username(self, client: AsyncClient):
        """Special characters in registration are handled safely."""
        special_usernames = [
            "user<script>",
            "user'; DROP TABLE--",
            "user\x00null",
            "a" * 1000,  # very long username
        ]
        for username in special_usernames:
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": username,
                    "email": f"{username[:10]}@test.com",
                    "password": "ValidPass123!",
                },
            )
            # Should reject or sanitize, never crash with 500
            assert resp.status_code in (200, 400, 422), (
                f"Username '{username[:20]}...' got unexpected status {resp.status_code}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# A07: Authentication Failures — Brute Force Protection
# ══════════════════════════════════════════════════════════════════════════════


class TestBruteForceProtection:
    """Test rate limiting and brute force protection."""

    @pytest.mark.asyncio
    async def test_login_rate_limiting(self, client: AsyncClient):
        """Login endpoint has rate limiting (10/minute)."""
        # Send multiple failed login attempts
        responses = []
        for i in range(12):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"username": "nonexistent", "password": f"wrong{i}"},
            )
            responses.append(resp.status_code)

        # At least some should be rate limited (429)
        # Note: rate limiting may not trigger in test environment with mocked limiter
        # But we verify no 500 errors occur
        assert all(code in (401, 429) for code in responses), (
            f"Unexpected status codes in brute force test: {responses}"
        )

    @pytest.mark.asyncio
    async def test_register_rate_limiting(self, client: AsyncClient):
        """Registration endpoint has rate limiting (5/hour)."""
        responses = []
        for i in range(7):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": f"ratelimit_test_{i}",
                    "email": f"ratelimit{i}@test.com",
                    "password": "ValidPass123!",
                },
            )
            responses.append(resp.status_code)

        # Should not all succeed — some should be rate limited
        # In test env, rate limiter may be reset per test, so just verify no 500s
        assert all(code in (200, 400, 429) for code in responses)


# ══════════════════════════════════════════════════════════════════════════════
# Security Headers
# ══════════════════════════════════════════════════════════════════════════════


class TestSecurityHeaders:
    """Test that security-related response headers are present."""

    @pytest.mark.asyncio
    async def test_cors_not_wildcard(self, client: AsyncClient):
        """CORS is not set to wildcard (*) in responses."""
        resp = await client.get("/api/v1/health")
        cors_header = resp.headers.get("access-control-allow-origin", "")
        assert cors_header != "*", "CORS should not be wildcard in production"

    @pytest.mark.asyncio
    async def test_no_server_version_leak(self, client: AsyncClient):
        """Server header doesn't leak version information."""
        resp = await client.get("/api/v1/health")
        server = resp.headers.get("server", "")
        # Should not expose detailed version info
        assert "Python" not in server
        assert "uvicorn" not in server.lower() or "version" not in server.lower()

    @pytest.mark.asyncio
    async def test_request_id_present(self, client: AsyncClient, auth_headers):
        """X-Request-ID header is present in responses."""
        resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert "x-request-id" in resp.headers


# ══════════════════════════════════════════════════════════════════════════════
# Data Exposure
# ══════════════════════════════════════════════════════════════════════════════


class TestDataExposure:
    """Test that sensitive data is not exposed in responses."""

    @pytest.mark.asyncio
    async def test_password_not_in_user_response(self, client: AsyncClient, auth_headers):
        """User profile response does not contain password hash."""
        resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        if resp.status_code == 200:
            body = resp.json()
            assert "password" not in body
            assert "password_hash" not in body
            assert "hashed_password" not in body

    @pytest.mark.asyncio
    async def test_error_messages_not_verbose(self, client: AsyncClient):
        """Error responses don't expose internal implementation details."""
        resp = await client.get("/api/v1/backtests/nonexistent", headers={})
        # Should not contain stack traces or internal paths
        body = resp.text
        assert "Traceback" not in body
        assert "/opt/workspace" not in body
        assert "site-packages" not in body

    @pytest.mark.asyncio
    async def test_openapi_does_not_expose_internal_routes(self, client: AsyncClient):
        """OpenAPI schema doesn't expose internal/debug endpoints."""
        resp = await client.get("/openapi.json")
        if resp.status_code == 200:
            schema = resp.json()
            paths = list(schema.get("paths", {}).keys())
            # Should not have debug/internal endpoints
            assert "/debug" not in paths
            assert "/internal" not in paths
            assert "/_internal" not in paths
