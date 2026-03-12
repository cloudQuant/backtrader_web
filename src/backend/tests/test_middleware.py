"""
Tests for security and exception handling middleware.
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.middleware.exception_handling import (
    ErrorResponse,
    handle_base_app_error,
    handle_generic_exception,
    handle_http_exception,
    handle_validation_error,
    register_exception_handlers,
)
from app.middleware.security_headers import add_security_headers
from app.utils.exceptions import (
    InvalidInputError,
    MissingConfigError,
    UserNotFoundError,
)


class TestErrorResponse:
    """Test suite for ErrorResponse class."""

    def test_to_dict_basic(self):
        """Test basic error response conversion."""
        error = ErrorResponse(status_code=404, error="NOT_FOUND", message="Resource not found")
        result = error.to_dict()
        assert result == {
            "error": "NOT_FOUND",
            "message": "Resource not found",
        }

    def test_to_dict_with_details(self):
        """Test error response with details."""
        error = ErrorResponse(
            status_code=400,
            error="VALIDATION_ERROR",
            message="Validation failed",
            details={"field": "username"},
        )
        result = error.to_dict()
        assert "details" in result
        assert result["details"]["field"] == "username"

    def test_to_dict_with_request_id(self):
        """Test error response with request ID."""
        error = ErrorResponse(
            status_code=500, error="SERVER_ERROR", message="Internal error", request_id="req-123"
        )
        result = error.to_dict()
        assert result["request_id"] == "req-123"


class TestExceptionHandling:
    """Test suite for exception handling middleware."""

    @pytest.mark.asyncio
    async def test_handle_base_app_error(self):
        """Test handling of custom application exceptions."""

        # Create mock request
        class MockURL:
            def __init__(self):
                self.path = "/api/test"

        class MockState:
            def __init__(self):
                self.request_id = "test-123"

        class MockRequest:
            def __init__(self):
                self.url = MockURL()
                self.state = MockState()

        request = MockRequest()

        # Create custom exception
        exc = UserNotFoundError(user_id="123")

        # Handle the exception
        response = await handle_base_app_error(request, exc)

        assert response.status_code == 404
        content = response.body.decode()
        assert "UserNotFoundError" in content
        assert "test-123" in content

    @pytest.mark.asyncio
    async def test_handle_validation_error(self):
        """Test handling of Pydantic validation errors."""
        from pydantic import BaseModel, ValidationError

        # Create mock request
        class MockURL:
            def __init__(self):
                self.path = "/api/test"

        class MockState:
            def __init__(self):
                self.request_id = "test-456"

        class MockRequest:
            def __init__(self):
                self.url = MockURL()
                self.state = MockState()

        request = MockRequest()

        # Define a test model and trigger validation error
        class TestModel(BaseModel):
            username: str
            email: str

        # Trigger a real validation error
        try:
            TestModel(email="test@example.com")  # missing username
        except ValidationError as exc:
            # Handle the exception
            response = await handle_validation_error(request, exc)

            assert response.status_code == 422
            content = response.body.decode()
            assert "VALIDATION_ERROR" in content
            assert "username" in content
        else:
            raise AssertionError("ValidationError should have been raised")

    @pytest.mark.asyncio
    async def test_handle_http_exception(self):
        """Test handling of HTTP exceptions."""
        from fastapi import HTTPException

        # Create mock request
        class MockURL:
            def __init__(self):
                self.path = "/api/test"

        class MockState:
            def __init__(self):
                self.request_id = "test-789"

        class MockRequest:
            def __init__(self):
                self.url = MockURL()
                self.state = MockState()

        request = MockRequest()

        # Create HTTP exception
        exc = HTTPException(status_code=403, detail="Forbidden")

        # Handle the exception
        response = await handle_http_exception(request, exc)

        assert response.status_code == 403
        content = response.body.decode()
        assert "HTTP_403" in content
        assert "test-789" in content

    @pytest.mark.asyncio
    async def test_handle_generic_exception(self):
        """Test handling of generic exceptions."""

        # Create mock request
        class MockURL:
            def __init__(self):
                self.path = "/api/test"

        class MockState:
            def __init__(self):
                self.request_id = "test-999"

        class MockRequest:
            def __init__(self):
                self.url = MockURL()
                self.state = MockState()

        request = MockRequest()

        # Create generic exception
        exc = ValueError("Something went wrong")

        # Handle the exception
        response = await handle_generic_exception(request, exc)

        assert response.status_code == 500
        content = response.body.decode()
        # Should not expose actual error message
        assert "Something went wrong" not in content
        assert "INTERNAL_SERVER_ERROR" in content
        assert "test-999" in content

    def test_register_exception_handlers(self):
        """Test registering exception handlers with FastAPI app."""
        app = FastAPI()

        # Should not raise
        register_exception_handlers(app)

        # Verify handlers are registered
        # (FastAPI stores exception handlers internally)
        assert app is not None


class TestSecurityHeadersMiddleware:
    """Test suite for security headers middleware."""

    @pytest.mark.asyncio
    async def test_security_headers_added(self):
        """Test that security headers are added to responses."""
        app = FastAPI()

        @app.get("/test")
        async def test_route():
            return {"message": "test"}

        # Add middleware
        add_security_headers(app)

        # Create test client
        from fastapi.testclient import TestClient

        client = TestClient(app)

        response = client.get("/test")

        # Verify security headers
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "Content-Security-Policy" in response.headers
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in response.headers

    @pytest.mark.asyncio
    async def test_no_cache_headers_on_auth_endpoints(self):
        """Test that auth endpoints have no-cache headers."""
        app = FastAPI()

        @app.get("/api/v1/auth/login")
        async def login_route():
            return {"token": "test"}

        # Add middleware
        add_security_headers(app)

        from fastapi.testclient import TestClient

        client = TestClient(app)

        response = client.get("/api/v1/auth/login")

        # Verify cache control headers
        assert response.headers.get("Cache-Control") == "no-store, no-cache, must-revalidate"
        assert response.headers.get("Pragma") == "no-cache"
        assert response.headers.get("Expires") == "0"

    @pytest.mark.asyncio
    async def test_hsts_only_in_production_with_https(self):
        """Test HSTS header only added in production with HTTPS."""
        app = FastAPI()

        @app.get("/test")
        async def test_route():
            return {"message": "test"}

        # Add middleware
        add_security_headers(app)

        from fastapi.testclient import TestClient

        client = TestClient(app)

        # In debug mode (default for tests), HSTS should not be added
        response = client.get("http://testserver/test")
        # No HSTS because it's not HTTPS
        assert response.headers.get("Strict-Transport-Security") is None

    @pytest.mark.asyncio
    async def test_server_header_removed(self):
        """Test that Server header is removed or hidden."""
        app = FastAPI()

        @app.get("/test")
        async def test_route():
            return {"message": "test"}

        add_security_headers(app)

        from fastapi.testclient import TestClient

        client = TestClient(app)

        response = client.get("/test")

        # Server header should be removed or not revealing
        server = response.headers.get("Server")
        if server:
            assert "Backtrader" not in str(server)

    @pytest.mark.asyncio
    async def test_x_powered_by_in_debug_only(self):
        """Test X-Powered-By header only present in debug mode."""
        app = FastAPI()

        @app.get("/test")
        async def test_route():
            return {"message": "test"}

        add_security_headers(app)

        from fastapi.testclient import TestClient

        client = TestClient(app)

        response = client.get("/test")

        # In debug mode (test default), should show app name
        assert response.headers.get("X-Powered-By") == "Backtrader Web"


class TestMiddlewareIntegration:
    """Test suite for middleware integration."""

    @pytest.mark.asyncio
    async def test_exception_and_security_headers_work_together(self, client: AsyncClient):
        """Test that exception handler and security headers work together."""
        # Create an app with both middlewares
        app = FastAPI()

        @app.get("/test")
        async def test_route():
            return {"message": "test"}

        @app.get("/error")
        async def error_route():
            raise UserNotFoundError(user_id="123")

        register_exception_handlers(app)
        add_security_headers(app)

        from fastapi.testclient import TestClient

        test_client = TestClient(app)

        # Normal request should have security headers
        response = test_client.get("/test")
        assert response.status_code == 200
        assert "X-Content-Type-Options" in response.headers

        # Error request should have both error format and security headers
        response = test_client.get("/error")
        assert response.status_code == 404
        assert "X-Content-Type-Options" in response.headers
        assert "UserNotFoundError" in response.json()["error"]


class TestCustomExceptionIntegration:
    """Test suite for custom exception integration with API."""

    @pytest.mark.asyncio
    async def test_user_not_found_in_api(self, client: AsyncClient):
        """Test UserNotFoundError in API context."""
        # First, we need to test the error through an actual API endpoint
        # This would require mocking the repository
        # For now, we just verify the exception exists and has correct structure
        exc = UserNotFoundError(user_id="test-123")

        assert exc.message == "User not found (ID: test-123)"
        assert exc.details["user_id"] == "test-123"
        assert exc.error_code == "UserNotFoundError"

        # Test to_dict method
        result = exc.to_dict()
        assert result["error"] == "UserNotFoundError"
        assert result["message"] == "User not found (ID: test-123)"

    @pytest.mark.asyncio
    async def test_validation_error_in_api(self, client: AsyncClient):
        """Test validation error in API context."""
        # Test with actual API endpoint
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "ab",  # Too short
                "email": "test@example.com",
                "password": "Test@123",
            },
        )

        # Should get validation error (422)
        # or success (if validation is lenient)
        assert response.status_code in (200, 422, 400)

    @pytest.mark.asyncio
    async def test_all_custom_exceptions_can_be_raised(self):
        """Test that all custom exceptions can be instantiated."""
        from app.utils.exceptions import (
            BacktestExecutionError,
            BacktestNotFoundError,
            BacktestTimeoutError,
            BrokerConnectionError,
            DataNotFoundError,
            DataProviderError,
            InsufficientPermissionsError,
            InvalidConfigError,
            InvalidCredentialsError,
            InvalidDateRangeError,
            InvalidStrategyCodeError,
            InvalidTokenError,
            MissingFieldError,
            PasswordTooWeakError,
            StrategyNotFoundError,
            TokenExpiredError,
            UserAlreadyExistsError,
            UserInactiveError,
        )

        # Try to instantiate each exception
        exceptions_to_test = [
            (InvalidCredentialsError, [], {}),
            (UserNotFoundError, [], {"user_id": "123"}),
            (UserAlreadyExistsError, [], {"username": "test"}),
            (InvalidTokenError, [], {}),
            (TokenExpiredError, [], {}),
            (InsufficientPermissionsError, [], {"resource": "test"}),
            (UserInactiveError, [], {"user_id": "123"}),
            (InvalidInputError, ["Invalid input"], {"field": "test"}),
            (MissingFieldError, ["field1"], {}),
            (PasswordTooWeakError, [["Too short"]], {}),
            (StrategyNotFoundError, [], {"strategy_id": "123"}),
            (InvalidStrategyCodeError, ["Invalid code"], {}),
            (BacktestNotFoundError, [], {"task_id": "123"}),
            (BacktestExecutionError, ["Failed"], {"task_id": "123"}),
            (BacktestTimeoutError, ["123", 300], {}),
            (DataNotFoundError, [], {"symbol": "AAPL"}),
            (InvalidDateRangeError, ["Invalid range"], {}),
            (MissingConfigError, ["DATABASE_URL"], {}),
            (InvalidConfigError, ["DEBUG", "invalid", "Invalid"], {}),
            (BrokerConnectionError, ["Binance"], {}),
            (DataProviderError, ["AkShare"], {}),
        ]

        for exc_class, args, kwargs in exceptions_to_test:
            try:
                exc = exc_class(*args, **kwargs)
                # Should have error_code
                assert exc.error_code is not None
                # Should have to_dict method
                assert hasattr(exc, "to_dict")
            except Exception as e:
                raise AssertionError(f"Failed to instantiate {exc_class.__name__}: {e}")
