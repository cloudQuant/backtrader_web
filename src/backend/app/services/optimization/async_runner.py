import asyncio
import threading
from collections.abc import Coroutine
from typing import Any

_async_runner_lock = threading.Lock()
_async_runner_loop: asyncio.AbstractEventLoop | None = None
_async_runner_thread: threading.Thread | None = None


def _ensure_async_runner_loop() -> asyncio.AbstractEventLoop:
    global _async_runner_loop, _async_runner_thread

    with _async_runner_lock:
        if _async_runner_loop is not None and _async_runner_loop.is_running():
            return _async_runner_loop

        ready = threading.Event()
        holder: dict[str, asyncio.AbstractEventLoop] = {}

        def _run_loop() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            holder["loop"] = loop
            ready.set()
            loop.run_forever()

        thread = threading.Thread(target=_run_loop, name="param-opt-async-runner", daemon=True)
        thread.start()
        ready.wait()
        _async_runner_thread = thread
        _async_runner_loop = holder["loop"]
        return _async_runner_loop


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    future = asyncio.run_coroutine_threadsafe(coro, _ensure_async_runner_loop())
    return future.result()
