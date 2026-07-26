from typing import Any

from fastapi import FastAPI

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _get_logger(app: FastAPI):
    return getattr(app.state, "startup_logger", logger)


async def register(app: FastAPI, settings: Any) -> None:
    try:
        from app.services.ai_observability.logger import get_ai_call_log_sink

        await get_ai_call_log_sink().start()
    except Exception:
        _get_logger(app).exception("Failed to start AI call log async sink")


async def shutdown(app: FastAPI, settings: Any) -> None:
    try:
        from app.services.ai_observability.logger import get_ai_call_log_sink

        await get_ai_call_log_sink().shutdown()
    except Exception:
        _get_logger(app).exception("Failed to shutdown AI call log async sink")
