"""Run the separately deployed protocol-v2 trusted-research Explorer worker.

This is intentionally not an API startup hook.  Operators must ship a reviewed
factory under ``app.research_deployments`` and explicitly enable both
``AI_RESEARCH_PROTOCOL_V2_ENABLED`` and
``AI_RESEARCH_PROTOCOL_V2_WORKER_ENABLED``.  Invalid factory configuration
exits before any queued task is recovered or claimed.
"""

from __future__ import annotations

import asyncio
import logging

from app.services.research.worker_process import run_deployment_worker

LOGGER = logging.getLogger("run_ai_research_v2_worker")


def run() -> int:
    """Run the worker process and return a container-friendly exit status."""

    try:
        started = asyncio.run(run_deployment_worker())
    except ValueError as exc:
        LOGGER.error("Trusted AI-research Explorer worker refused startup: %s", exc)
        return 2
    if started:
        LOGGER.info("Trusted AI-research Explorer worker stopped cleanly")
    else:
        LOGGER.info("Trusted AI-research Explorer worker remains disabled")
    return 0


def main() -> None:
    """Configure CLI logging and exit with the worker bootstrap result."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    raise SystemExit(run())


if __name__ == "__main__":  # pragma: no cover
    main()
