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
import re
import sys
import traceback
from collections.abc import Callable
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from types import FrameType
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from loguru import logger

from app.config import get_settings

_NOISY_THIRD_PARTY_LOGGERS = (
    "aiomysql",
    "aiomysql.connection",
    "aiosqlite",
    "aiosqlite.core",
    "asyncio",
    "faker",
    "faker.factory",
    "slowapi",
    "slowapi.extension",
)
_DATED_LOG_RE = re.compile(r"^(app|errors|audit|backtest)_(?P<date>\d{4}-\d{2}-\d{2})\.log$")
_STALE_LOG_ARCHIVE_MIN_AGE_SECONDS = 60


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
        frame: FrameType | None = sys._getframe(6)
        depth = 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _configure_third_party_log_levels() -> None:
    """Keep known noisy dependencies from flooding application log files."""
    for logger_name in _NOISY_THIRD_PARTY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _date_from_dated_log_name(filename: str) -> date | None:
    match = _DATED_LOG_RE.match(filename)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group("date"))
    except ValueError:
        return None


def _next_archive_path(log_file: Path) -> Path:
    archive_path = log_file.with_name(f"{log_file.name}.zip")
    if not archive_path.exists():
        return archive_path

    for index in range(1, 1000):
        candidate = log_file.with_name(f"{log_file.name}.{index}.zip")
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Could not find available archive path for {log_file}")


def _archive_stale_dated_logs(
    logs_path: Path,
    *,
    current_date: date | None = None,
    min_age_seconds: int = _STALE_LOG_ARCHIVE_MIN_AGE_SECONDS,
) -> list[Path]:
    """Compress inactive dated logs left behind before loguru could rotate them."""

    today = current_date or datetime.now().date()
    archived: list[Path] = []
    now_ts = datetime.now().timestamp()

    for log_file in sorted(logs_path.glob("*.log")):
        log_date = _date_from_dated_log_name(log_file.name)
        if log_date is None or log_date >= today:
            continue

        try:
            stat = log_file.stat()
        except OSError:
            continue

        if stat.st_size <= 0 or now_ts - stat.st_mtime < min_age_seconds:
            continue

        archive_path = _next_archive_path(log_file)
        try:
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
                archive.write(log_file, arcname=log_file.name)
            log_file.unlink()
            archived.append(archive_path)
        except OSError:
            archive_path.unlink(missing_ok=True)

    return archived


def _build_daily_or_size_rotation(max_bytes: int) -> str | Callable[[Any, Any], bool]:
    """Return a loguru rotation policy for daily files plus an optional size cap."""

    if max_bytes <= 0:
        return "00:00"

    def _should_rotate(message: Any, file: Any) -> bool:
        try:
            message_date = message.record["time"].date()
            file_date = _date_from_dated_log_name(Path(file.name).name)
            if file_date is not None and file_date < message_date:
                return True
        except Exception:
            pass

        try:
            file.seek(0, 2)
            message_size = len(str(message).encode("utf-8", errors="replace"))
            return file.tell() + message_size > max_bytes
        except Exception:
            return False

    return _should_rotate


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
_REDACTED_VALUE = "****"
_SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?ix)"
    r"(?:"
    r"(?P<label>"
    r"[\"']?\b(?:api[_ -]?key|access[_ -]?key|secret(?:[_ -]?key)?|"
    r"client[_ -]?secret|private[_ -]?key|password|passwd|authorization|"
    r"access[_ -]?token|refresh[_ -]?token|auth[_ -]?token|cookie|token)\b[\"']?"
    r"\s*(?:=|:)\s*"
    r")"
    r"(?:bearer\s+)?[^\s,;;&]+"
    r")"
    r"|(?P<bearer>\bbearer\s+)[A-Za-z0-9._~+/=-]+"
)


def _redact_sensitive_text(value: str) -> str:
    """Remove common credential forms from an otherwise unstructured string."""

    def _replace(match: re.Match[str]) -> str:
        if label := match.group("label"):
            return f"{label}{_REDACTED_VALUE}"
        return f"{match.group('bearer')}{_REDACTED_VALUE}"

    return _SENSITIVE_TEXT_PATTERN.sub(_replace, value)


def _redact_exception_record(exception: Any) -> Any:
    """Return an exception record whose rendered message cannot expose a credential."""
    try:
        redacted_message = _redact_sensitive_text(str(exception.value))
        if redacted_message == str(exception.value):
            return exception
        return exception._replace(value=RuntimeError(redacted_message))
    except Exception:
        # If an unusual exception record cannot be safely rewritten, omit it
        # instead of passing an untrusted value to a sink.
        return None


class LogLevel(str, Enum):
    """Log level enumeration."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogContext:
    """Context manager for adding contextual information to logs."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize log context.

        Args:
            **kwargs: Key-value pairs to include in log context.
        """
        self.context: dict[str, Any] = kwargs
        self.bind_vars: Any = {}

    def __enter__(self) -> "LogContext":
        """Enter context, bind variables to logger."""
        self.bind_vars = logger.bind(**self.context)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
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

    filtered: dict[str, Any] = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(pattern in key_lower for pattern in SENSITIVE_PATTERNS):
            filtered[key] = _REDACTED_VALUE
        elif isinstance(value, dict):
            filtered[key] = _filter_sensitive_data(value)
        elif isinstance(value, list):
            filtered[key] = [
                _filter_sensitive_data(item)
                if isinstance(item, dict)
                else _redact_sensitive_text(item)
                if isinstance(item, str)
                else item
                for item in value
            ]
        elif isinstance(value, str):
            filtered[key] = _redact_sensitive_text(value)
        else:
            filtered[key] = value
    return filtered


def _get_trace_context() -> dict[str, str]:
    """Return the active OTel trace/span IDs for log↔trace correlation.

    Returns ``{"trace_id": ..., "span_id": ...}`` (32-/16-hex, W3C format) when
    there is a valid *recording* span in context, otherwise an empty dict.

    This is the logs-correlation half of iteration 176 §H: structured log lines
    emitted inside an OTel span carry the same ``trace_id`` the trace backend
    (Jaeger/Tempo) uses, so an operator can pivot from a Loki/ELK log entry to
    the exact distributed trace. When OTel is disabled or not installed the
    helper is a cheap no-op (one import guard + one ``is_valid`` check).
    """
    try:
        from opentelemetry import trace as _otel_trace

        span = _otel_trace.get_current_span()
        ctx = span.get_span_context()
        if not ctx or not ctx.is_valid:
            return {}
        return {
            "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x"),
        }
    except Exception:
        return {}


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
    timestamp = (
        ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}" + ts.strftime("%z")
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
    message = _redact_sensitive_text(str(record["message"]))
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
        exception = record["exception"]
        log_entry["exception"] = {
            "type": exception.type.__name__,
            "message": _redact_sensitive_text(str(exception.value)),
            "traceback": " interrupted"
            if exception.type.__name__ == "KeyboardInterrupt"
            else _redact_sensitive_text(
                "".join(
                    traceback.format_exception(
                        exception.type,
                        exception.value,
                        exception.traceback,
                    )
                )
            ),
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

    # 176 §H — logs↔traces correlation: stamp the active OTel trace/span IDs so
    # operators can pivot from a structured log line to its distributed trace.
    trace_context = _get_trace_context()
    if trace_context:
        log_entry["trace_id"] = trace_context["trace_id"]
        log_entry["span_id"] = trace_context["span_id"]

    return json.dumps(log_entry, ensure_ascii=False)


def _patch_record(record: Any) -> bool:
    """Ensure record is redacted and has default values for optional fields."""
    record["message"] = _redact_sensitive_text(str(record.get("message", "")))
    extra = record.get("extra")
    if isinstance(extra, dict):
        record["extra"] = _filter_sensitive_data(extra)
    if record.get("exception"):
        record["exception"] = _redact_exception_record(record["exception"])
    if "request_id" not in record["extra"]:
        record["extra"]["request_id"] = "N/A"
    return True


def _sanitize_log_record(record: Any) -> None:
    """Apply record redaction through Loguru's global patcher contract."""
    _patch_record(record)


# Apply the same redaction to the default loguru sink and every bound logger,
# including messages emitted before setup_logger() installs application sinks.
logger = logger.patch(_sanitize_log_record)


_PLAIN_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss} | "
    "{level: <8} | "
    "{name}:{function}:{line} | "
    "{extra[request_id]:<12} | "
    "{message}"
)


def _json_console_sink(message: Any) -> None:
    """Sink that writes JSON-serialized log records to stdout.

    Used in production to enable structured log ingestion by ELK/Loki/CloudWatch.
    """
    record: dict[str, Any] = message.record
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
    rotation: str | Callable[[Any, Any], bool] = "00:00",
) -> None:
    """Add a rotating file handler with common defaults."""

    def _tag_filter(record: Any) -> bool:
        return _patch_record(record) and bool(
            tag_filter and tag_filter in record["extra"].get("tags", [])
        )

    filt: Callable[[Any], bool] = _tag_filter if tag_filter else _patch_record

    if use_json:
        # For JSON output, use "{message}" as format and serialize in a custom
        # format function. Loguru applies .format_map() on the returned string,
        # so we must avoid raw braces. Instead, we use the `serialize` parameter
        # which writes the record as-is without format interpolation.
        logger.add(
            logs_path / filename,
            rotation=rotation,
            retention=retention,
            compression="zip",
            format="{message}",
            level=level,
            enqueue=True,
            catch=True,
            filter=filt,
            backtrace=backtrace,
            diagnose=False,
            serialize=True,
        )
    else:
        fmt = fmt_override or _PLAIN_FORMAT
        logger.add(
            logs_path / filename,
            rotation=rotation,
            retention=retention,
            compression="zip",
            format=fmt,
            level=level,
            enqueue=True,
            catch=True,
            filter=filt,
            backtrace=backtrace,
            diagnose=False,
        )


def _resolve_log_format(settings: Any) -> tuple[bool, bool]:
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
    raw_log_format = getattr(settings, "LOG_FORMAT", "")
    log_format = raw_log_format.strip().lower() if isinstance(raw_log_format, str) else ""

    if log_format == "json":
        return True, False
    elif log_format == "text":
        return False, False

    # Fallback based on DEBUG
    if settings.DEBUG:
        return False, True
    else:
        return True, False


def _resolve_int_setting(settings: Any, name: str, default: int) -> int:
    value = getattr(settings, name, default)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def setup_logger(
    name: str | None = None,
    log_level: str | None = None,
    json_logs: bool | None = None,
    log_dir: str | None = None,
) -> Any:
    """Configure and return an enhanced logger instance.

    Log level policy:
    - LOG_LEVEL env var (highest priority): use specified level for all sinks
    - DEBUG=true (dev/test): console=DEBUG, file=DEBUG (output everything)
    - DEBUG=false (production): console=WARNING, file=INFO

    Args:
        name: Optional logger name (for compatibility, loguru uses global logger).
        log_level: Override log level from config.
        json_logs: Force JSON logging format.
        log_dir: Override log directory from config.

    Returns:
        The configured logger instance.
    """
    settings = get_settings()

    # Resolve log levels: explicit LOG_LEVEL > function param > environment-based default
    raw_explicit_level = getattr(settings, "LOG_LEVEL", "")
    explicit_level = (
        raw_explicit_level.strip().upper() if isinstance(raw_explicit_level, str) else ""
    )
    if log_level:
        console_level = log_level
        file_level = log_level
    elif explicit_level:
        console_level = explicit_level
        file_level = explicit_level
    elif settings.DEBUG:
        # Dev/test: output everything
        console_level = "DEBUG"
        file_level = "DEBUG"
    else:
        # Production: console only WARNING+, file keeps INFO+
        console_level = "WARNING"
        file_level = "INFO"

    # Determine format: explicit json_logs param takes precedence, then LOG_FORMAT env var
    if json_logs is not None:
        use_json = json_logs
        use_color = not json_logs and settings.DEBUG
    else:
        use_json, use_color = _resolve_log_format(settings)

    logs_path = Path(log_dir or getattr(settings, "LOG_DIR", "./logs") or "./logs")
    logs_path.mkdir(parents=True, exist_ok=True)

    logger.remove()
    _archive_stale_dated_logs(logs_path)

    # Intercept stdlib logging → loguru so that modules using
    # ``logging.getLogger(__name__)`` are automatically routed through loguru.
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    _configure_third_party_log_levels()

    _add_console_handler(console_level, use_color)

    # Resolve retention periods from config
    app_retention = f"{_resolve_int_setting(settings, 'LOG_RETENTION_APP_DAYS', 30)} days"
    error_retention = f"{_resolve_int_setting(settings, 'LOG_RETENTION_ERROR_DAYS', 90)} days"
    audit_retention = f"{_resolve_int_setting(settings, 'LOG_RETENTION_AUDIT_DAYS', 365)} days"
    max_log_file_mb = _resolve_int_setting(settings, "LOG_ROTATION_MAX_MB", 100)
    file_rotation = _build_daily_or_size_rotation(max_log_file_mb * 1024 * 1024)

    _add_file_handler(
        logs_path,
        "app_{time:YYYY-MM-DD}.log",
        use_json,
        level=file_level,
        retention=app_retention,
        rotation=file_rotation,
    )

    _add_file_handler(
        logs_path,
        "errors_{time:YYYY-MM-DD}.log",
        use_json,
        level="ERROR",
        retention=error_retention,
        fmt_override=_PLAIN_FORMAT + "\n{exception}",
        backtrace=True,
        rotation=file_rotation,
    )

    _add_file_handler(
        logs_path,
        "audit_{time:YYYY-MM-DD}.log",
        use_json,
        retention=audit_retention,
        level=file_level,
        fmt_override=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} | user:{extra[user_id]:<12} | {message}"
        ),
        tag_filter="audit",
        rotation=file_rotation,
    )

    _add_file_handler(
        logs_path,
        "backtest_{time:YYYY-MM-DD}.log",
        use_json,
        retention="60 days",
        level=file_level,
        fmt_override=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "task:{extra[task_id]:<12} | user:{extra[user_id]:<12} | {message}"
        ),
        tag_filter="backtest",
        rotation=file_rotation,
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


def log_with_context(message: str, level: str = "INFO", **context: Any) -> None:
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

    def __init__(self) -> None:
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


def bind_request_context(request_id: str, user_id: str | None = None, **extra: Any) -> Any:
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
    context: dict[str, Any] = {"request_id": request_id}
    if user_id:
        context["user_id"] = user_id
    context.update(extra)
    return logger.bind(**context)


def bind_task_context(
    task_id: str,
    user_id: str | None = None,
    task_type: str | None = None,
) -> Any:
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
    context: dict[str, Any] = {"task_id": task_id, "tags": []}
    if user_id:
        context["user_id"] = user_id
    if task_type:
        tags = context.setdefault("tags", [])
        if isinstance(tags, list):
            tags.append(task_type)
    return logger.bind(**context)
