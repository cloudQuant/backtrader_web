"""Benchmark data service for risk analytics."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from app.schemas.risk_analytics import BenchmarkReturnsResult
from app.services.realtime_data_service import RealTimeDataService

BenchmarkFetcher = Callable[[str, str, str], Awaitable[list[dict[str, Any]]]]

BENCHMARK_SYMBOLS: dict[str, str] = {
    "hs300": "000300.SH",
    "csi500": "000905.SH",
    "csi800": "000906.SH",
    "spx": "SPX",
    "btc": "BTC/USDT",
}


class BenchmarkService:
    """Fetch benchmark prices and derive return series."""

    def __init__(self, data_fetcher: BenchmarkFetcher | None = None) -> None:
        self.data_fetcher = data_fetcher or self._default_fetcher

    async def get_benchmark_returns(
        self,
        benchmark_id: str,
        start_date: str,
        end_date: str,
    ) -> BenchmarkReturnsResult:
        """Fetch benchmark data and calculate close-to-close returns."""
        symbol = BENCHMARK_SYMBOLS.get(benchmark_id)
        if symbol is None:
            return BenchmarkReturnsResult(
                status="degraded",
                benchmark_id=benchmark_id,
                start_date=start_date,
                end_date=end_date,
                reason="unknown_benchmark",
            )

        records = await self.data_fetcher(symbol, start_date, end_date)
        dates: list[str] = []
        closes: list[float] = []
        for record in records:
            close = record.get("close")
            date = record.get("date")
            if close is None or date is None:
                continue
            dates.append(str(date)[:10])
            closes.append(float(close))

        if len(closes) < 2:
            return BenchmarkReturnsResult(
                status="degraded",
                benchmark_id=benchmark_id,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                observation_count=len(closes),
                dates=dates,
                reason="insufficient_history",
            )

        returns = [
            round((current - previous) / previous, 6)
            for previous, current in zip(closes, closes[1:], strict=False)
            if previous > 0
        ]
        return BenchmarkReturnsResult(
            status="ok",
            benchmark_id=benchmark_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            observation_count=len(closes),
            dates=dates,
            returns=returns,
        )

    @staticmethod
    async def _default_fetcher(symbol: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        service = RealTimeDataService()
        return await service.get_historical_data(
            "system",
            "benchmark",
            symbol,
            datetime.fromisoformat(start_date),
            datetime.fromisoformat(end_date),
            "1d",
        )
