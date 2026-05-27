import pytest


@pytest.mark.asyncio
async def test_risk_free_rate_uses_cache_and_fallback(monkeypatch):
    from app.services.risk_free_rate import RiskFreeRateService

    calls = 0

    async def fake_fetch(series_id: str) -> float:
        nonlocal calls
        calls += 1
        return 0.042

    service = RiskFreeRateService(default_rate=0.03, fetcher=fake_fetch, ttl_seconds=3600)

    assert await service.get_rate("USD") == pytest.approx(0.042)
    assert await service.get_rate("USD") == pytest.approx(0.042)
    assert calls == 1

    async def failing_fetch(series_id: str) -> float:
        raise RuntimeError("offline")

    fallback = RiskFreeRateService(default_rate=0.035, fetcher=failing_fetch, ttl_seconds=3600)
    assert await fallback.get_rate("USD") == pytest.approx(0.035)
