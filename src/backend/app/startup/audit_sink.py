from typing import Any

from fastapi import FastAPI

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _get_logger(app: FastAPI):
    return getattr(app.state, "startup_logger", logger)


async def register(app: FastAPI, settings: Any) -> None:
    try:
        from app.api.audit import get_audit_service

        await get_audit_service().start()
    except Exception:
        _get_logger(app).exception("Failed to start audit async sink")


async def shutdown(app: FastAPI, settings: Any) -> None:
    try:
        from app.api.audit import get_audit_service

        await get_audit_service().shutdown()
    except Exception:
        _get_logger(app).exception("Failed to shutdown audit async sink")
