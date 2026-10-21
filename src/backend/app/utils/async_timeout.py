"""Python 3.10-compatible replacement for :func:`asyncio.timeout`."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


@asynccontextmanager
async def timeout_after(seconds: float) -> AsyncIterator[None]:
    """Cancel the current task after ``seconds`` and raise ``TimeoutError``.

    ``asyncio.timeout`` only exists from Python 3.11. The timer-triggered
    cancellation is converted locally so an outer cancellation still
    propagates unchanged.
    """

    task = asyncio.current_task()
    if task is None:
        raise RuntimeError("timeout_after() requires a running task")
    timed_out = False

    def _on_deadline() -> None:
        nonlocal timed_out
        timed_out = True
        task.cancel()

    handle = asyncio.get_running_loop().call_later(seconds, _on_deadline)
    try:
        yield
    except asyncio.CancelledError:
        if not timed_out:
            raise
        raise TimeoutError from None
    finally:
        handle.cancel()
