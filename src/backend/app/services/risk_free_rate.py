from __future__ import annotations

import time
from collections.abc import Awaitable, Callable


class RiskFreeRateService:
    def __init__(
        self,
        *,
        default_rate: float = 0.03,
        fetcher: Callable[[str], Awaitable[float]] | None = None,
        ttl_seconds: int = 3600,
    ) -> None:
        self.default_rate = default_rate
        self.fetcher = fetcher
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, float]] = {}
        self._series_mapping = {"USD": "DGS10", "CNY": "RISK_FREE_RATE_DEFAULT", "EUR": "ECB10Y"}

    async def get_rate(self, currency: str = "CNY") -> float:
        now = time.time()
        cached = self._cache.get(currency)
        if cached and now - cached[1] <= self.ttl_seconds:
            return cached[0]
        series_id = self._series_mapping.get(currency, currency)
        if self.fetcher is None:
            self._cache[currency] = (self.default_rate, now)
            return self.default_rate
        try:
            value = float(await self.fetcher(series_id))
        except Exception:
            value = self.default_rate
        self._cache[currency] = (value, now)
        return value
