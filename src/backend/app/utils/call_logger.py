"""
Function call logging decorator.

Provides a universal decorator that automatically records function invocation
time, execution duration, return value summary, and exception details.

Usage:
    from app.utils.call_logger import call_logger

    @call_logger()
    async def create_strategy(user_id: str, data: dict) -> Strategy:
        ...

    @call_logger(log_result=False, slow_threshold=5000)
    async def run_backtest(task_id: str, config: dict) -> BacktestResult:
        ...
"""

import functools
import inspect
import time
import traceback
from collections.abc import Callable
from typing import Any, ParamSpec

from app.utils.logger import get_logger

_VALID_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

_SENSITIVE_SUBSTRINGS = (
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "credential",
)
_SENSITIVE_MASK = "***"
_MAX_SANITIZE_DEPTH = 6

P = ParamSpec("P")


def _is_sensitive_key(key: Any) -> bool:
    """Return whether a mapping/parameter key is sensitive."""
    return any(s in str(key).lower() for s in _SENSITIVE_SUBSTRINGS)


def _sanitize_for_log(value: Any, *, key: Any | None = None, depth: int = 0) -> Any:
    """Return a log-safe representation with nested secrets masked."""
    if key is not None and _is_sensitive_key(key):
        return _SENSITIVE_MASK
    if depth >= _MAX_SANITIZE_DEPTH:
        return f"<{type(value).__name__}>"
    if isinstance(value, dict):
        return {
            item_key: _sanitize_for_log(item_value, key=item_key, depth=depth + 1)
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_for_log(item, depth=depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_for_log(item, depth=depth + 1) for item in value)
    if isinstance(value, (set, frozenset)):
        return type(value)(_sanitize_for_log(item, depth=depth + 1) for item in value)

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _sanitize_for_log(model_dump(), depth=depth + 1)
        except Exception:
            return f"<{type(value).__name__}>"

    return value


def _filter_args(args_dict: dict[str, Any]) -> dict[str, Any]:
    """Replace sensitive parameter values with '***'.

    Args:
        args_dict: Dictionary of parameter names to values.

    Returns:
        Filtered dictionary with sensitive values masked.
    """
    return {
        key: _sanitize_for_log(value, key=key)
        for key, value in args_dict.items()
        if key not in {"self", "cls"}
    }


def _truncate(value: Any, max_length: int = 200) -> str:
    """Truncate a value's string representation.

    Args:
        value: Value to represent as string.
        max_length: Maximum character length.

    Returns:
        Truncated string representation.
    """
    s = repr(_sanitize_for_log(value))
    if len(s) > max_length:
        return s[:max_length] + "..."
    return s


def call_logger(
    *,
    log_level: str = "INFO",
    log_result: bool = True,
    log_args: bool = True,
    slow_threshold: int = 1000,
) -> Callable[[Callable[P, Any]], Callable[P, Any]]:
    """Decorator that logs function calls with timing, args, result, and exceptions.

    Args:
        log_level: Log level for successful calls (DEBUG/INFO/WARNING/ERROR/CRITICAL).
        log_result: Whether to include return value in log output.
        log_args: Whether to include input arguments in log output.
        slow_threshold: Duration threshold in milliseconds for slow call warnings.

    Returns:
        Decorator function.

    Raises:
        ValueError: If log_level is not a valid Python logging level.
    """
    level_upper = log_level.upper()
    if level_upper not in _VALID_LEVELS:
        raise ValueError(
            f"Invalid log_level: '{log_level}'. Accepted values: {', '.join(sorted(_VALID_LEVELS))}"
        )

    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        logger = get_logger(func.__module__)
        func_name = func.__qualname__
        module_name = func.__module__

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                # Build args summary
                args_summary = ""
                if log_args:
                    sig = inspect.signature(func)
                    bound = sig.bind(*args, **kwargs)
                    bound.apply_defaults()
                    filtered = _filter_args(dict(bound.arguments))
                    args_summary = f" args={filtered}"

                log_func = getattr(logger, level_upper.lower(), logger.info)
                log_func(
                    f"CALL {module_name}.{func_name}{args_summary}",
                )

                start = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                except Exception as exc:
                    duration_ms = (time.perf_counter() - start) * 1000
                    tb = traceback.format_exc()
                    logger.error(
                        f"FAIL {module_name}.{func_name} "
                        f"duration={duration_ms:.1f}ms "
                        f"exception={type(exc).__name__}: {exc}\n{tb}",
                    )
                    raise
                else:
                    duration_ms = (time.perf_counter() - start) * 1000
                    result_summary = ""
                    if log_result:
                        result_summary = f" result={_truncate(result)}"
                    log_func(
                        f"OK   {module_name}.{func_name} "
                        f"duration={duration_ms:.1f}ms{result_summary}",
                    )
                    if duration_ms > slow_threshold:
                        logger.warning(
                            f"SLOW {module_name}.{func_name} "
                            f"duration={duration_ms:.1f}ms "
                            f"threshold={slow_threshold}ms",
                        )
                    return result

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                # Build args summary
                args_summary = ""
                if log_args:
                    sig = inspect.signature(func)
                    bound = sig.bind(*args, **kwargs)
                    bound.apply_defaults()
                    filtered = _filter_args(dict(bound.arguments))
                    args_summary = f" args={filtered}"

                log_func = getattr(logger, level_upper.lower(), logger.info)
                log_func(
                    f"CALL {module_name}.{func_name}{args_summary}",
                )

                start = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                except Exception as exc:
                    duration_ms = (time.perf_counter() - start) * 1000
                    tb = traceback.format_exc()
                    logger.error(
                        f"FAIL {module_name}.{func_name} "
                        f"duration={duration_ms:.1f}ms "
                        f"exception={type(exc).__name__}: {exc}\n{tb}",
                    )
                    raise
                else:
                    duration_ms = (time.perf_counter() - start) * 1000
                    result_summary = ""
                    if log_result:
                        result_summary = f" result={_truncate(result)}"
                    log_func(
                        f"OK   {module_name}.{func_name} "
                        f"duration={duration_ms:.1f}ms{result_summary}",
                    )
                    if duration_ms > slow_threshold:
                        logger.warning(
                            f"SLOW {module_name}.{func_name} "
                            f"duration={duration_ms:.1f}ms "
                            f"threshold={slow_threshold}ms",
                        )
                    return result

            return sync_wrapper

    return decorator
