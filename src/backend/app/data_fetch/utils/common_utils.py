"""
Common utility functions for data fetch
"""

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def setup_logging(logger_name: str, log_level: int = logging.INFO) -> logging.Logger:
    """设置日志记录器"""
    logger = logging.getLogger(logger_name)

    if logger.handlers:
        return logger

    logger.setLevel(log_level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def get_default_logger(name: str = "app") -> logging.Logger:
    """获取默认配置的日志记录器"""
    return setup_logging(name)


def retry_on_exception(
    max_retries: int = 3,
    retry_delay: int = 5,
    logger: logging.Logger | None = None,
    allowed_exceptions: tuple[type[BaseException], ...] = (Exception,),
    stop_exceptions: tuple[type[BaseException], ...] = (),
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """重试装饰器"""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            local_logger = logger
            if not local_logger and args and hasattr(args[0], "logger"):
                local_logger = args[0].logger

            if not local_logger:
                local_logger = get_default_logger(func.__name__)

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except allowed_exceptions as exc:
                    if stop_exceptions and isinstance(exc, stop_exceptions):
                        local_logger.error(f"{func.__name__} 执行失败，不再重试: {exc}")
                        raise
                    local_logger.warning(f"{func.__name__} 第 {attempt + 1} 次执行失败: {exc}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                    else:
                        local_logger.error(f"{func.__name__} 执行失败，达到最大重试次数")
                        raise
            raise RuntimeError(f"{func.__name__} retry loop exited unexpectedly")

        return wrapper

    return decorator
