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
def test_ws_gateway_broadcast_p95_for_500_connections(benchmark: Any) -> None:
    from app.services.ws_gateway import WSGateway

    loop = asyncio.new_event_loop()
    try:
        gateway = WSGateway(token_validator=lambda token: token == 'ok')
        for index in range(500):
            client_id = f'client-{index}'
            assert loop.run_until_complete(gateway.connect(client_id, token='ok')) is True
            loop.run_until_complete(gateway.subscribe(client_id, ['market:quote:*']))

        def publish_once() -> int:
            delivered = loop.run_until_complete(gateway.publish('market:quote:RB2510', {'price': 100.0}))
            gateway._messages.clear()
            return delivered

        assert publish_once() == 500
        benchmark.pedantic(publish_once, rounds=3, iterations=5)

        p95_ms = _p95_ms(_measure_ms(publish_once, rounds=30))
        assert p95_ms <= 50.0
    finally:
        loop.close()
