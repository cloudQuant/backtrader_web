"""Tests for optimization_async_runner module."""

import asyncio
import threading

from app.services.optimization_async_runner import (
    _ensure_async_runner_loop,
    _run_async,
)


class TestEnsureAsyncRunnerLoop:
    def test_returns_running_event_loop(self):
        loop = _ensure_async_runner_loop()
        assert isinstance(loop, asyncio.AbstractEventLoop)
        assert loop.is_running()

    def test_returns_same_loop_on_repeated_calls(self):
        loop1 = _ensure_async_runner_loop()
        loop2 = _ensure_async_runner_loop()
        assert loop1 is loop2


class TestRunAsync:
    def test_runs_coroutine_and_returns_result(self):
        async def add(a, b):
            return a + b

        result = _run_async(add(3, 4))
        assert result == 7

    def test_runs_async_sleep(self):
        async def quick_sleep():
            await asyncio.sleep(0.01)
            return "done"

        result = _run_async(quick_sleep())
        assert result == "done"

    def test_propagates_exception(self):
        async def fail():
            raise ValueError("boom")

        try:
            _run_async(fail())
            assert False, "Should have raised"
        except ValueError as e:
            assert "boom" in str(e)

    def test_works_from_non_main_thread(self):
        results = []

        def worker():
            async def compute():
                return 42

            results.append(_run_async(compute()))

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=5)
        assert results == [42]
