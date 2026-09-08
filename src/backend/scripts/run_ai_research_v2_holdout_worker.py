"""Run the opt-in, separately deployed sealed-holdout worker process."""

from __future__ import annotations

import asyncio
import logging

from app.services.research.holdout_worker_process import run_deployment_holdout_worker

LOGGER = logging.getLogger("run_ai_research_v2_holdout_worker")


def run() -> int:
    """Return an orchestration-friendly exit code without printing secrets."""

    try:
        started = asyncio.run(run_deployment_holdout_worker())
    except ValueError as exc:
        LOGGER.error("Sealed holdout worker refused startup: %s", exc)
        return 2
    if started:
        LOGGER.info("Sealed holdout worker stopped cleanly")
    else:
        LOGGER.info("Sealed holdout worker remains disabled")
    return 0


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    raise SystemExit(run())


if __name__ == "__main__":  # pragma: no cover
    main()
