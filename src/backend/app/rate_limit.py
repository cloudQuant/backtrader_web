"""Shared rate limiter configuration.

Supports Redis backend for distributed rate limiting when REDIS_URL is configured.
Falls back to in-memory storage when Redis is unavailable.
"""

import logging
from pathlib import Path

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

logger = logging.getLogger(__name__)

_SLOWAPI_CONFIG_FILE = Path(__file__).resolve().parents[1] / ".slowapi.env"


def _create_limiter() -> Limiter:
    """Create rate limiter with Redis backend if available, else in-memory."""
    settings = get_settings()
    storage_uri = None

    if settings.REDIS_URL:
        try:
            import redis  # noqa: F401

            storage_uri = settings.REDIS_URL
            logger.info("Rate limiter using Redis backend: %s", settings.REDIS_URL.split("@")[-1])
        except ImportError:
            logger.warning(
                "Redis URL configured but redis package not installed. "
                "Falling back to in-memory rate limiting."
            )

    if not storage_uri:
        logger.info("Rate limiter using in-memory backend (not suitable for multi-instance)")

    # `.slowapi.env` is an optional runtime override file (not tracked in git).
    # Only pass it to the Limiter when it actually exists; otherwise slowapi/
    # starlette emits a spurious "Config file not found" UserWarning on every
    # startup of a fresh clone.
    config_filename = str(_SLOWAPI_CONFIG_FILE) if _SLOWAPI_CONFIG_FILE.is_file() else None

    return Limiter(
        key_func=get_remote_address,
        storage_uri=storage_uri,
        config_filename=config_filename,
    )


limiter = _create_limiter()
