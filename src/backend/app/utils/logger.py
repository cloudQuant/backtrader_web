"""
Logging configuration (loguru).
"""
import sys
from loguru import logger
from app.config import get_settings


def setup_logger(name: str = None):
    """Configure a logger instance.

    Args:
        name: Optional logger name (not used in loguru but kept for compatibility).

    Returns:
        The configured logger instance.
    """
    settings = get_settings()

    # Remove default handler
    logger.remove()

    # Add console output
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stdout,
        format=log_format,
        level="DEBUG" if settings.DEBUG else "INFO",
        colorize=True,
    )

    # Add file output
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="7 days",
        format=log_format,
        level="INFO",
    )

    return logger
