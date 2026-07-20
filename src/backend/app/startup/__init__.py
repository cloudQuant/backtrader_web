from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI

from app.startup import (
    ai_log_sink,
    audit_sink,
    database,
    orchestration,
    paper_runtime,
    reconcile,
    security_check,
)

StartupHook = Callable[[FastAPI, Any], Awaitable[None]]

STARTUP_HOOKS: tuple[StartupHook, ...] = (
    database.register,
    reconcile.register,
    audit_sink.register,
    ai_log_sink.register,
    security_check.register,
    orchestration.register,
    paper_runtime.register,
)

SHUTDOWN_HOOKS: tuple[StartupHook, ...] = (
    orchestration.shutdown,
    paper_runtime.shutdown,
    reconcile.shutdown,
    audit_sink.shutdown,
    ai_log_sink.shutdown,
)


async def run_startup(app: FastAPI, settings: Any) -> None:
    for hook in STARTUP_HOOKS:
        await hook(app, settings)


async def run_shutdown(app: FastAPI, settings: Any) -> None:
    for hook in SHUTDOWN_HOOKS:
        await hook(app, settings)
