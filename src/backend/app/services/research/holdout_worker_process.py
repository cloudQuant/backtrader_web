"""Deployment-only bootstrap for the independent sealed-holdout worker."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import math
import signal
import string
from collections.abc import Callable
from typing import Any

from app.config import get_settings
from app.services.research.holdout_worker import HoldoutEvaluationWorker
from app.utils.logger import setup_logger

_DEPLOYMENT_NAMESPACE = "app.research_deployments."
logger = setup_logger(__name__)

WorkerFactory = Callable[[], Any]
WorkerFactoryResolver = Callable[[str], WorkerFactory]


def resolve_holdout_worker_factory(
    reference: str,
    *,
    importer: Callable[[str], Any] = importlib.import_module,
) -> WorkerFactory:
    """Resolve one image-local reviewed factory, never an API-selected import."""

    normalized = str(reference or "").strip()
    if not normalized:
        raise ValueError("HOLDOUT_WORKER_FACTORY_REFERENCE_REQUIRED")
    if normalized.count(":") != 1:
        raise ValueError("HOLDOUT_WORKER_FACTORY_REFERENCE_INVALID")
    module_name, attribute_name = normalized.split(":", maxsplit=1)
    if not _valid_reference(module_name, attribute_name):
        raise ValueError("HOLDOUT_WORKER_FACTORY_REFERENCE_INVALID")
    if not module_name.startswith(_DEPLOYMENT_NAMESPACE):
        raise ValueError("HOLDOUT_WORKER_FACTORY_NAMESPACE_DENIED")
    try:
        module = importer(module_name)
    except Exception:
        raise ValueError("HOLDOUT_WORKER_FACTORY_IMPORT_FAILED") from None
    factory = getattr(module, attribute_name, None)
    if not callable(factory):
        raise ValueError("HOLDOUT_WORKER_FACTORY_NOT_CALLABLE")
    return factory


async def run_deployment_holdout_worker(
    *,
    settings: Any | None = None,
    stop_event: asyncio.Event | None = None,
    factory_resolver: WorkerFactoryResolver = resolve_holdout_worker_factory,
) -> bool:
    """Poll the dedicated worker only after all static composition succeeds."""

    active_settings = settings or get_settings()
    if not bool(getattr(active_settings, "AI_RESEARCH_PROTOCOL_V2_ENABLED", False)):
        logger.info("Sealed holdout worker remains disabled: protocol flag is off")
        return False
    if not bool(getattr(active_settings, "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_ENABLED", False)):
        logger.info("Sealed holdout worker remains disabled: worker flag is off")
        return False
    poll_seconds = _poll_seconds(
        getattr(active_settings, "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_POLL_SECONDS", None)
    )
    reference = str(
        getattr(active_settings, "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_FACTORY", "")
    ).strip()
    factory = factory_resolver(reference)
    worker = await _create_worker(factory)

    stop = stop_event or asyncio.Event()
    cleanup = _install_stop_signal_handlers(stop)
    try:
        while not stop.is_set():
            await worker.run_once(limit=10)
            if stop.is_set():
                break
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass
    finally:
        cleanup()
    return True


async def _create_worker(factory: WorkerFactory) -> HoldoutEvaluationWorker:
    try:
        candidate = factory()
        if inspect.isawaitable(candidate):
            candidate = await candidate
    except Exception:
        raise ValueError("HOLDOUT_WORKER_FACTORY_FAILED") from None
    if not isinstance(candidate, HoldoutEvaluationWorker):
        raise ValueError("HOLDOUT_WORKER_FACTORY_RETURN_INVALID")
    return candidate


def _poll_seconds(value: object) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or not 0.1 <= value <= 3600:
        raise ValueError("HOLDOUT_WORKER_POLL_INTERVAL_INVALID")
    return float(value)


def _valid_reference(module_name: str, attribute_name: str) -> bool:
    return bool(
        module_name
        and attribute_name
        and all(_identifier(part) for part in module_name.split("."))
        and _identifier(attribute_name)
    )


def _identifier(value: str) -> bool:
    if not value or value[0] not in f"{string.ascii_letters}_":
        return False
    allowed = f"{string.ascii_letters}{string.digits}_"
    return all(character in allowed for character in value)


def _install_stop_signal_handlers(stop_event: asyncio.Event) -> Callable[[], None]:
    loop = asyncio.get_running_loop()
    registered: list[signal.Signals] = []
    for name in ("SIGTERM", "SIGINT"):
        candidate = getattr(signal, name, None)
        if candidate is None:
            continue
        try:
            loop.add_signal_handler(candidate, stop_event.set)
        except (NotImplementedError, RuntimeError):
            continue
        registered.append(candidate)

    def cleanup() -> None:
        for registered_signal in registered:
            loop.remove_signal_handler(registered_signal)

    return cleanup
