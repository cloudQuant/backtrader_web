"""
Global exception handler middleware for consistent API error responses.

This middleware catches all exceptions and converts them to standardized
JSON responses, preventing information leakage and providing consistent
error format to API consumers.
"""

import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.utils.exceptions import BaseAppError
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ErrorResponse:
    """Standard error response format."""

    def __init__(
        self,
        status_code: int,
        error: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        path: Optional[str] = None,
    ):
        """Initialize error response.

        Args:
            status_code: HTTP status code.
            error: Error code/category.
            message: Human-readable error message.
            details: Additional error details.
            request_id: Unique request identifier for tracing.
            path: Request path that caused the error.
        """
        self.status_code = status_code
        self.error = error
        self.message = message
        self.details = details
        self.request_id = request_id
        self.path = path

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response.

        Returns:
            Dictionary representation of the error.
        """
        result = {
            "error": self.error,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.request_id:
            result["request_id"] = self.request_id
        if self.path:
            result["path"] = self.path
        return result


async def handle_base_app_error(request: Request, exc: BaseAppError) -> JSONResponse:
    """Handle custom application exceptions.

    Args:
        request: The FastAPI request.
        exc: The caught BaseAppError exception.

    Returns:
        JSON response with error details.
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])

    # Log the error
    logger.warning(
        f"Application error: {exc.error_code} - {exc.message}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "error_code": exc.error_code,
        },
    )

    # Determine status code based on error type
    status_code_map = {
        "UserNotFoundError": status.HTTP_404_NOT_FOUND,
        "StrategyNotFoundError": status.HTTP_404_NOT_FOUND,
        "BacktestNotFoundError": status.HTTP_404_NOT_FOUND,
        "DataNotFoundError": status.HTTP_404_NOT_FOUND,
        "InvalidCredentialsError": status.HTTP_401_UNAUTHORIZED,
        "InvalidTokenError": status.HTTP_401_UNAUTHORIZED,
        "TokenExpiredError": status.HTTP_401_UNAUTHORIZED,
        "UserInactiveError": status.HTTP_403_FORBIDDEN,
        "InsufficientPermissionsError": status.HTTP_403_FORBIDDEN,
        "ValidationError": status.HTTP_400_BAD_REQUEST,
        "InvalidInputError": status.HTTP_400_BAD_REQUEST,
        "MissingFieldError": status.HTTP_400_BAD_REQUEST,
        "PasswordTooWeakError": status.HTTP_400_BAD_REQUEST,
        "ConfigurationError": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "ExternalServiceError": status.HTTP_503_SERVICE_UNAVAILABLE,
    }

    http_status = status_code_map.get(exc.error_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    error_response = ErrorResponse(
        status_code=http_status,
        error=exc.error_code,
        message=exc.message,
        details=exc.details if exc.details else None,
        request_id=request_id,
        path=request.url.path,
    )

    return JSONResponse(content=error_response.to_dict(), status_code=http_status)


def _build_validation_error_response(
    request: Request,
    exc: ValidationError | RequestValidationError,
) -> tuple[list[dict], str]:
    """Extract validation errors into a consistent format.

    Shared by both Pydantic ValidationError and FastAPI RequestValidationError handlers.

    Args:
        request: The FastAPI request.
        exc: The validation exception.

    Returns:
        Tuple of (errors list, request_id).
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])
    errors = []
    for err in exc.errors():
        loc = err.get("loc", [])
        field = ".".join(str(part) for part in (loc if isinstance(loc, (list, tuple)) else [loc]))
        errors.append(
            {
                "field": field,
                "message": err.get("msg", err.get("message", "Invalid value")),
                "type": err.get("type", "validation_error"),
            }
        )
    return errors, request_id


async def handle_validation_error(request: Request, exc: ValidationError) -> JSONResponse:
    """Handle Pydantic validation errors (e.g. model_validate failures)."""
    errors, request_id = _build_validation_error_response(request, exc)
    logger.info(
        "Validation error: %s field(s)",
        len(errors),
        extra={"request_id": request_id, "path": request.url.path},
    )
    return JSONResponse(
        content=ErrorResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error="VALIDATION_ERROR",
            message="Request validation failed",
            details={"fields": errors},
            request_id=request_id,
            path=request.url.path,
        ).to_dict(),
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle FastAPI request validation errors (422)."""
    errors, request_id = _build_validation_error_response(request, exc)
    logger.info(
        "Request validation error: %s field(s)",
        len(errors),
        extra={"request_id": request_id, "path": request.url.path},
    )
    return JSONResponse(
        content=ErrorResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error="VALIDATION_ERROR",
            message="Request validation failed",
            details={"fields": errors},
            request_id=request_id,
            path=request.url.path,
        ).to_dict(),
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


async def handle_http_exception(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Handle Starlette/FastAPI HTTPException."""
    status_code = exc.status_code
    detail = exc.detail
    error_code = f"HTTP_{status_code}"

    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])

    logger.error(
        "HTTP exception: %s - %s",
        status_code,
        detail,
        extra={
            "request_id": request_id,
            "path": request.url.path,
        },
    )

    message = detail if isinstance(detail, str) else "Request failed"
    details: Optional[Dict[str, Any]] = detail if isinstance(detail, dict) else None

    error_response = ErrorResponse(
        status_code=status_code,
        error=error_code,
        message=message,
        details=details,
        request_id=request_id,
        path=request.url.path,
    )

    return JSONResponse(content=error_response.to_dict(), status_code=status_code)


async def handle_generic_exception(request: Request, exc: Exception) -> JSONResponse:
    """Handle all other uncaught exceptions.

    Args:
        request: The FastAPI request.
        exc: The caught exception.

    Returns:
        JSON response with error details (no sensitive data leaked).
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])

    # Log the full exception for debugging
    logger.error(
        f"Unhandled exception: {type(exc).__name__} - {str(exc)}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
        },
        exc_info=True,
    )

    # Don't expose internal errors to clients
    error_response = ErrorResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred. Please contact support if the problem persists.",
        request_id=request_id,
        path=request.url.path,
    )

    return JSONResponse(
        content=error_response.to_dict(), status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers with the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """
    # Custom application exceptions
    app.add_exception_handler(BaseAppError, handle_base_app_error)

    # FastAPI request validation errors (422)
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)

    # Pydantic validation errors (usually internal model_validate failures)
    app.add_exception_handler(ValidationError, handle_validation_error)

    # HTTP exceptions (e.g. raise HTTPException(...))
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)

    # Generic exception handler (must be last)
    app.add_exception_handler(Exception, handle_generic_exception)

    logger.info("Exception handlers registered")
