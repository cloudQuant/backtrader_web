"""Deployment-only bootstrap for the protocol-v2 Explorer worker.

The HTTP application must never construct this process or supply a fallback
executor map.  A deployment image instead ships a reviewed factory under
``app.research_deployments`` and enables both protocol and worker flags.  The
factory is resolved before the first recover/claim operation, so a bad image
or incomplete executor map leaves queued user work untouched.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import signal
import string
from collections.abc import Callable
from typing import Any

from app.config import get_settings
from app.services.research.workflow_worker import (
    ResearchProtocolWorker,
    run_research_protocol_worker,
)
from app.utils.logger import setup_logger

_DEPLOYMENT_FACTORY_NAMESPACE = "app.research_deployments."
logger = setup_logger(__name__)

WorkerFactory = Callable[[], Any]
WorkerFactoryResolver = Callable[[str], WorkerFactory]


def resolve_worker_factory(
    reference: str,
    *,
    importer: Callable[[str], Any] = importlib.import_module,
) -> WorkerFactory:
    """Resolve only a reviewed, image-local Explorer worker factory.

    The setting names a callable in a dedicated deployment namespace rather
    than an arbitrary import.  Deployment configuration can select a reviewed
    factory bundled into the immutable worker image, but cannot turn a task
    payload into an import target.
    """

    normalized = str(reference or "").strip()
    if not normalized:
        raise ValueError("RESEARCH_WORKER_FACTORY_REFERENCE_REQUIRED")
    if normalized.count(":") != 1:
        raise ValueError("RESEARCH_WORKER_FACTORY_REFERENCE_INVALID")
    module_name, attribute_name = normalized.split(":", maxsplit=1)
    if not _is_factory_reference_valid(module_name, attribute_name):
        raise ValueError("RESEARCH_WORKER_FACTORY_REFERENCE_INVALID")
    if not module_name.startswith(_DEPLOYMENT_FACTORY_NAMESPACE):
        raise ValueError("RESEARCH_WORKER_FACTORY_NAMESPACE_DENIED")
    try:
        module = importer(module_name)
    except Exception as exc:
        raise ValueError("RESEARCH_WORKER_FACTORY_IMPORT_FAILED") from exc
    factory = getattr(module, attribute_name, None)
    if not callable(factory):
        raise ValueError("RESEARCH_WORKER_FACTORY_NOT_CALLABLE")
    return factory


async def run_deployment_worker(
    *,
    settings: Any | None = None,
    stop_event: asyncio.Event | None = None,
    factory_resolver: WorkerFactoryResolver = resolve_worker_factory,
) -> bool:
    """Run a separately deployed Explorer worker until a process stop signal.

    Returns ``False`` when either opt-in flag is disabled.  Otherwise errors
    are intentionally stable, fail closed, and occur before task recovery or
    claim.  The caller is a CLI process, never FastAPI lifecycle code.
    """

    active_settings = settings or get_settings()
    if not bool(getattr(active_settings, "AI_RESEARCH_PROTOCOL_V2_ENABLED", False)):
        logger.info("Trusted AI-research Explorer worker remains disabled: protocol flag is off")
        return False
    if not bool(getattr(active_settings, "AI_RESEARCH_PROTOCOL_V2_WORKER_ENABLED", False)):
        logger.info("Trusted AI-research Explorer worker remains disabled: worker flag is off")
        return False

    factory_reference = str(
        getattr(active_settings, "AI_RESEARCH_PROTOCOL_V2_WORKER_FACTORY", "")
    ).strip()
    factory = factory_resolver(factory_reference)
    worker = await _create_worker(factory)

    resolved_stop_event = stop_event or asyncio.Event()
    cleanup_signal_handlers = _install_stop_signal_handlers(resolved_stop_event)
    try:
        await run_research_protocol_worker(
            worker,
            stop_event=resolved_stop_event,
            poll_interval_seconds=float(
                getattr(active_settings, "AI_RESEARCH_PROTOCOL_V2_WORKER_POLL_SECONDS", 0)
            ),
        )
    finally:
        cleanup_signal_handlers()
    return True


async def _create_worker(factory: WorkerFactory) -> ResearchProtocolWorker:
    """Create a deployment-owned worker without exposing factory exceptions."""

    try:
        candidate = factory()
        if inspect.isawaitable(candidate):
            candidate = await candidate
    except Exception as exc:
        raise ValueError("RESEARCH_WORKER_FACTORY_FAILED") from exc
    if not isinstance(candidate, ResearchProtocolWorker):
        raise ValueError("RESEARCH_WORKER_FACTORY_RETURN_INVALID")
    return candidate


def _is_factory_reference_valid(module_name: str, attribute_name: str) -> bool:
    """Accept an ordinary dotted Python module and a single callable name."""

    module_parts = module_name.split(".")
    return bool(
        module_name
        and attribute_name
        and all(_matches_identifier(part) for part in module_parts)
        and _matches_identifier(attribute_name)
    )


def _matches_identifier(value: str) -> bool:
    """Accept an ASCII Python identifier and reject visually confusable names."""

    if not value or value[0] not in f"{string.ascii_letters}_":
        return False
    allowed = f"{string.ascii_letters}{string.digits}_"
    return all(character in allowed for character in value)


def _install_stop_signal_handlers(stop_event: asyncio.Event) -> Callable[[], None]:
    """Translate TERM/INT into a bounded stop-after-current-poll request."""

    loop = asyncio.get_running_loop()
    registered: list[signal.Signals] = []
    for signal_name in ("SIGTERM", "SIGINT"):
        candidate = getattr(signal, signal_name, None)
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
