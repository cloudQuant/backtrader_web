from typing import Any

from fastapi import FastAPI

from app.config import _DEFAULT_PASSWORDS, _DEFAULT_SECRETS
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _get_logger(app: FastAPI):
    return getattr(app.state, "startup_logger", logger)


async def register(app: FastAPI, settings: Any) -> None:
    startup_logger = _get_logger(app)
    if settings.SECRET_KEY in _DEFAULT_SECRETS or settings.JWT_SECRET_KEY in _DEFAULT_SECRETS:
        startup_logger.warning(
            "Using default security key. Set SECRET_KEY / JWT_SECRET_KEY in production."
        )
    if settings.ADMIN_PASSWORD.lower() in _DEFAULT_PASSWORDS:
        startup_logger.warning(
            "Default admin password detected. Change ADMIN_PASSWORD in production."
        )
