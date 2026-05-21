"""
Enhanced logging configuration with structured logging support.

Features:
- Structured JSON logging for production environments
- Request ID tracking for distributed tracing
- Sensitive data filtering
- Log level filtering per module
- File rotation with compression
- Separate logs for different components
- Error tracking integration ready
"""

import json
import logging
import sys
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import get_settings


class InterceptHandler(logging.Handler):
    """Route stdlib logging calls to loguru.

    This handler intercepts all standard library ``logging`` calls (used by
    ~40 modules in the codebase) and forwards them to loguru so that every
    log line benefits from loguru's formatting, rotation and structured output.

    Install once via ``setup_logger()`` — no per-file changes required.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Map stdlib level name to loguru level
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk the call stack to find the *real* caller (skip logging internals)
        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# Sensitive data patterns to filter from logs
SENSITIVE_PATTERNS = [
    "password",
    "secret",
    "token",
    "api_key",
    "access_token",
    "refresh_token",
    "authorization",
    "credential",
]


class LogLevel(str, Enum):
    """Log level enumeration."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogContext:
    """Context manager for adding contextual information to logs."""

    def __init__(self, **kwargs):
        """Initialize log context.

        Args:
            **kwargs: Key-value pairs to include in log context.
        """
        self.context = kwargs
        self.bind_vars = {}

    def __enter__(self):
        """Enter context, bind variables to logger."""
        self.bind_vars = logger.bind(**self.context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context, unbind variables.

        Note: loguru context is automatically managed, no explicit cleanup needed.
        """
        pass


def _filter_sensitive_data(data: dict[str, Any]) -> dict[str, Any]:
    """Filter sensitive data from log entries.

    Args:
        data: Original data dictionary.

    Returns:
        Data with sensitive values masked.
    """
    if not isinstance(data, dict):
        return data

    filtered = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(pattern in key_lower for pattern in SENSITIVE_PATTERNS):
            # Mask sensitive values
            if isinstance(value, str) and len(value) > 4:
                filtered[key] = value[:2] + "****" + value[-2:]
            else:
                filtered[key] = "****"
        elif isinstance(value, dict):
            filtered[key] = _filter_sensitive_data(value)
        elif isinstance(value, list):
            filtered[key] = [
                _filter_sensitive_data(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            filtered[key] = value
    return filtered


def _serialize_log(record: dict[str, Any]) -> str:
    """Serialize log record to JSON format for structured logging.

    Produces a single-line JSON object with required fields:
    - timestamp: ISO 8601 with millisecond precision
    - level: DEBUG/INFO/WARNING/ERROR/CRITICAL
    - message: log message text (truncated to 10000 chars)
    - module: producing module name
    - request_id: current request context ID or "N/A"

    Args:
        record: Log record dictionary.

    Returns:
        JSON string representation.
    """
    # Timestamp with millisecond precision in ISO 8601 format
    ts = record["time"]
    timestamp = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}" + ts.strftime(
        "%z"
    )
    # Insert colon in timezone offset for strict ISO 8601 (e.g. +0800 → +08:00)
    if len(timestamp) > 5 and timestamp[-5] in ("+", "-") and ":" not in timestamp[-5:]:
        timestamp = timestamp[:-2] + ":" + timestamp[-2:]

    # Determine module name from record
    name = record.get("name") or ""
    extra_name = record["extra"].get("name", "")
    module_source = extra_name or name
    module = module_source.split(".")[-1] if "." in module_source else (module_source or "root")

    # Truncate message to 10000 characters
    message = record["message"]
    if len(message) > 10000:
        message = message[:10000]

    # Build required fields
    log_entry: dict[str, Any] = {
        "timestamp": timestamp,
        "level": record["level"].name,
        "message": message,
        "module": module,
        "request_id": record["extra"].get("request_id", "N/A"),
    }

    # Add exception info if present
    if record["exception"]:
        log_entry["exception"] = {
            "type": record["exception"].type.__name__,
            "message": str(record["exception"].value),
            "traceback": record["exception"].traceback
            if not record["exception"].type.__name__ == "KeyboardInterrupt"
            else " interrupted",
        }

    # Add extra context if present (excluding tracked fields)
    if record["extra"]:
        extra = {
            k: v
            for k, v in record["extra"].items()
            if k not in {"request_id", "user_id", "task_id", "name"}
        }
        if extra:
            extra_filtered = _filter_sensitive_data(extra)
            log_entry["context"] = extra_filtered

    # Add optional tracking fields
    if "user_id" in record["extra"] and record["extra"]["user_id"]:
        log_entry["user_id"] = record["extra"]["user_id"]
    if "task_id" in record["extra"] and record["extra"]["task_id"]:
        log_entry["task_id"] = record["extra"]["task_id"]

    return json.dumps(log_entry, ensure_ascii=False)


def _patch_record(record: dict[str, Any]) -> dict[str, Any]:
    """Ensure record has default values for optional fields."""
    if "request_id" not in record["extra"]:
        record["extra"]["request_id"] = "N/A"
    return record


_PLAIN_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss} | "
    "{level: <8} | "
    "{name}:{function}:{line} | "
    "{extra[request_id]:<12} | "
    "{message}"
)


def _json_console_sink(message) -> None:
    """Sink that writes JSON-serialized log records to stdout.

    Used in production to enable structured log ingestion by ELK/Loki/CloudWatch.
    """
    record = message.record
    sys.stdout.write(_serialize_log(record) + "\n")
    sys.stdout.flush()


def _add_console_handler(level: str, use_color: bool) -> None:
    """Add coloured (debug/text) or JSON (production) console handler."""
    if use_color:
        fmt = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "{extra[request_id]:<12} | "
            "<level>{message}</level>"
        )
        logger.add(
            sys.stdout, format=fmt, level=level, colorize=True, catch=True, filter=_patch_record
        )
    else:
        # Production: structured JSON output for log aggregation systems
        logger.add(
            _json_console_sink, level=level, colorize=False, catch=True, filter=_patch_record
        )


def _add_file_handler(
    logs_path: Path,
    filename: str,
    use_json: bool,
    *,
    level: str = "INFO",
    retention: str = "30 days",
    fmt_override: str | None = None,
    tag_filter: str | None = None,
    backtrace: bool = False,
) -> None:
    """Add a rotating file handler with common defaults."""
    filt = (
        (lambda record, t=tag_filter: t in record["extra"].get("tags", []))
        if tag_filter
        else _patch_record
    )

    if use_json:
        # For JSON output, use "{message}" as format and serialize in a custom
        # format function. Loguru applies .format_map() on the returned string,
        # so we must avoid raw braces. Instead, we use the `serialize` parameter
        # which writes the record as-is without format interpolation.
        logger.add(
            logs_path / filename,
            rotation="00:00",
            retention=retention,
            compression="zip",
            format="{message}",
            level=level,
            enqueue=True,
            catch=True,
            filter=filt,
            backtrace=backtrace,
            diagnose=backtrace,
            serialize=True,
        )
    else:
        fmt = fmt_override or _PLAIN_FORMAT
        logger.add(
            logs_path / filename,
            rotation="00:00",
            retention=retention,
            compression="zip",
            format=fmt,
            level=level,
            enqueue=True,
            catch=True,
            filter=filt,
            backtrace=backtrace,
            diagnose=backtrace,
        )


def _resolve_log_format(settings) -> tuple[bool, bool]:
    """Resolve whether to use JSON output and whether to use colored text.

    Fallback logic:
    - LOG_FORMAT=json → JSON output
    - LOG_FORMAT=text → plain text output
    - LOG_FORMAT unset/empty:
        - DEBUG=true → colored text
        - DEBUG=false → JSON output

    Returns:
        Tuple of (use_json, use_color).
    """
    log_format = getattr(settings, "LOG_FORMAT", "").strip().lower()

    if log_format == "json":
        return True, False
    elif log_format == "text":
        return False, False

    # Fallback based on DEBUG
    if settings.DEBUG:
        return False, True
    else:
        return True, False


def setup_logger(
    name: str | None = None,
    log_level: str | None = None,
    json_logs: bool | None = None,
    log_dir: str | None = None,
) -> Any:
    """Configure and return an enhanced logger instance.

    Args:
        name: Optional logger name (for compatibility, loguru uses global logger).
        log_level: Override log level from config.
        json_logs: Force JSON logging format.
        log_dir: Override log directory from config.

    Returns:
        The configured logger instance.
    """
    settings = get_settings()

    level = log_level or ("DEBUG" if settings.DEBUG else "INFO")

    # Determine format: explicit json_logs param takes precedence, then LOG_FORMAT env var
    if json_logs is not None:
        use_json = json_logs
        use_color = not json_logs and settings.DEBUG
    else:
        use_json, use_color = _resolve_log_format(settings)

    logs_path = Path(log_dir or "logs")
    logs_path.mkdir(parents=True, exist_ok=True)

    logger.remove()

    # Intercept stdlib logging → loguru so that modules using
    # ``logging.getLogger(__name__)`` are automatically routed through loguru.
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    _add_console_handler(level, use_color)

    _add_file_handler(logs_path, "app_{time:YYYY-MM-DD}.log", use_json, retention="30 days")

    _add_file_handler(
        logs_path,
        "errors_{time:YYYY-MM-DD}.log",
        use_json,
        level="ERROR",
        retention="90 days",
        fmt_override=_PLAIN_FORMAT + "\n{exception}",
        backtrace=True,
    )

    _add_file_handler(
        logs_path,
        "audit_{time:YYYY-MM-DD}.log",
        use_json,
        retention="365 days",
        fmt_override=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} | user:{extra[user_id]:<12} | {message}"
        ),
        tag_filter="audit",
    )

    _add_file_handler(
        logs_path,
        "backtest_{time:YYYY-MM-DD}.log",
        use_json,
        retention="60 days",
        fmt_override=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "task:{extra[task_id]:<12} | user:{extra[user_id]:<12} | {message}"
        ),
        tag_filter="backtest",
    )

    return logger


def get_logger(name: str | None = None) -> Any:
    """Get a logger instance with the given name.

    Args:
        name: Logger name (for module identification).

    Returns:
        Logger instance bound with the module name.

    Example:
        >>> from app.utils.logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing started")
    """
    if name:
        return logger.bind(name=name)
    return logger


def log_with_context(message: str, level: str = "INFO", **context) -> None:
    """Log a message with additional context.

    Args:
        message: Log message.
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        **context: Additional key-value pairs to include in log entry.

    Example:
        >>> log_with_context("User logged in", level="INFO", user_id="123", ip="192.168.1.1")
    """
    context_filtered = _filter_sensitive_data(context)
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message, **context_filtered)


class AuditLogger:
    """Specialized logger for security and audit events."""

    def __init__(self):
        """Initialize audit logger."""
        self.logger = logger.bind(tags=["audit"])

    def log_login(
        self,
        user_id: str,
        success: bool,
        ip: str | None = None,
        details: str | None = None,
    ) -> None:
        """Log login attempt.

        Args:
            user_id: User identifier.
            success: Whether login was successful.
            ip: Client IP address.
            details: Additional details.
        """
        status = "SUCCESS" if success else "FAILED"
        message = f"Login {status}: {user_id}"
        if details:
            message += f" - {details}"
        if ip:
            message += f" from {ip}"

        if success:
            self.logger.info(message, user_id=user_id, event="login_success", ip=ip)
        else:
            self.logger.warning(message, user_id=user_id, event="login_failed", ip=ip)

    def log_logout(self, user_id: str) -> None:
        """Log logout event.

        Args:
            user_id: User identifier.
        """
        self.logger.info(f"User logged out: {user_id}", user_id=user_id, event="logout")

    def log_permission_denied(self, user_id: str, resource: str, action: str) -> None:
        """Log permission denied event.

        Args:
            user_id: User identifier.
            resource: Resource being accessed.
            action: Action being attempted.
        """
        self.logger.warning(
            f"Permission denied: user={user_id}, resource={resource}, action={action}",
            user_id=user_id,
            event="permission_denied",
            resource=resource,
            action=action,
        )

    def log_strategy_access(self, user_id: str, strategy_id: str, action: str) -> None:
        """Log strategy access event.

        Args:
            user_id: User identifier.
            strategy_id: Strategy identifier.
            action: Action performed (view, create, update, delete).
        """
        self.logger.info(
            f"Strategy {action}: {strategy_id} by {user_id}",
            user_id=user_id,
            event="strategy_access",
            strategy_id=strategy_id,
            action=action,
        )

    def log_backtest_start(self, user_id: str, task_id: str, strategy_id: str) -> None:
        """Log backtest start event.

        Args:
            user_id: User identifier.
            task_id: Task identifier.
            strategy_id: Strategy identifier.
        """
        self.logger.info(
            f"Backtest started: task={task_id}, strategy={strategy_id}",
            user_id=user_id,
            event="backtest_start",
            task_id=task_id,
            strategy_id=strategy_id,
        )

    def log_backtest_complete(
        self, user_id: str, task_id: str, duration: float, success: bool
    ) -> None:
        """Log backtest completion event.

        Args:
            user_id: User identifier.
            task_id: Task identifier.
            duration: Execution duration in seconds.
            success: Whether backtest completed successfully.
        """
        status = "SUCCESS" if success else "FAILED"
        self.logger.info(
            f"Backtest {status}: task={task_id}, duration={duration:.2f}s",
            user_id=user_id,
            event="backtest_complete",
            task_id=task_id,
            duration=duration,
            success=success,
        )


# Global audit logger instance
audit_logger = AuditLogger()


def bind_request_context(request_id: str, user_id: str = None, **extra) -> logger:
    """Bind request context to logger for all subsequent logs in the request.

    Args:
        request_id: Unique request identifier.
        user_id: Optional user identifier.
        **extra: Additional context to bind.

    Returns:
        Logger with bound context.

    Example:
        >>> logger = bind_request_context("req-123", user_id="user-456")
        >>> logger.info("Processing request")  # Will include request_id and user_id
    """
    context = {"request_id": request_id}
    if user_id:
        context["user_id"] = user_id
    context.update(extra)
    return logger.bind(**context)


def bind_task_context(task_id: str, user_id: str = None, task_type: str = None) -> logger:
    """Bind task context to logger for task-related logs.

    Args:
        task_id: Unique task identifier.
        user_id: Optional user identifier.
        task_type: Optional task type (backtest, optimization, etc.).

    Returns:
        Logger with bound task context.

    Example:
        >>> logger = bind_task_context("task-123", user_id="user-456", task_type="backtest")
        >>> logger.info("Starting task")  # Will include task_id and user_id
    """
    context = {"task_id": task_id, "tags": []}
    if user_id:
        context["user_id"] = user_id
    if task_type:
        context["tags"].append(task_type)
    return logger.bind(**context)
