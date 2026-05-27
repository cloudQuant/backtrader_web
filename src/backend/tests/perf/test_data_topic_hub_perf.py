import asyncio
import math
import time
from typing import Any

import pytest

pytest.importorskip('pytest_benchmark')


def _p95_ms(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def _measure_ms(func: Any, *, rounds: int) -> list[float]:
    durations: list[float] = []
    for _ in range(rounds):
        started = time.perf_counter()
        func()
        durations.append((time.perf_counter() - started) * 1000)
    return durations


@pytest.mark.performance
def test_data_topic_hub_cached_peek_p95(benchmark: Any) -> None:
    from app.services.data_topic_hub import DataTopicHub, TopicPolicy

    loop = asyncio.new_event_loop()
    try:
        hub = DataTopicHub()
        hub.register_topic('market:quote:RB2510', TopicPolicy(ttl_ms=1_000))
        loop.run_until_complete(hub.push('market:quote:RB2510', {'price': 100.0}))

        def peek_once() -> dict[str, float]:
            return loop.run_until_complete(hub.peek('market:quote:RB2510'))

        assert peek_once()['price'] == 100.0
        benchmark.pedantic(peek_once, rounds=5, iterations=20)

        p95_ms = _p95_ms(_measure_ms(peek_once, rounds=200))
        assert p95_ms <= 5.0
    finally:
        loop.close()


@pytest.mark.performance
def test_data_topic_hub_fanout_p95_for_100_subscribers(benchmark: Any) -> None:
    from app.services.data_topic_hub import DataTopicHub, TopicPolicy

    loop = asyncio.new_event_loop()
    try:
        hub = DataTopicHub()
        hub.register_topic('market:quote:RB2510', TopicPolicy(ttl_ms=1_000))
        for index in range(100):
            hub.subscribe(f'client-{index}', 'market:quote:*', lambda topic, value: None)

        def push_once() -> int:
            return loop.run_until_complete(hub.push('market:quote:RB2510', {'price': 100.0}))

        assert push_once() == 100
        benchmark.pedantic(push_once, rounds=5, iterations=10)

        p95_ms = _p95_ms(_measure_ms(push_once, rounds=100))
        assert p95_ms <= 20.0
    finally:
        loop.close()
