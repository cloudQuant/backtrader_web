import math
import time
from typing import Any

import pytest

pytest.importorskip("pytest_benchmark")


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
def test_option_single_strike_greeks_under_500ms(benchmark: Any) -> None:
    from app.services.options_chain import OptionsChainService

    service = OptionsChainService()

    def calculate_once() -> dict[str, float]:
        return service.calculate_greeks(100.0, 100.0, 0.22, True)

    result = calculate_once()
    assert result["delta"] is not None

    benchmark.pedantic(calculate_once, rounds=5, iterations=50)

    p95_ms = _p95_ms(_measure_ms(calculate_once, rounds=200))
    assert p95_ms <= 500.0
