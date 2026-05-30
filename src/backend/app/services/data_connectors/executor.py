import asyncio
import importlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class DataConnectorResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)
    source_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provider_latency_ms: int = 0
    quality_warnings: list[str] = field(default_factory=list)


class DataConnectorExecutor:
    def __init__(self) -> None:
        self._callables: dict[str, Callable[..., Any] | Callable[..., Awaitable[Any]]] = {}
        self._register_builtin_callables()

    def register_callable(
        self,
        function_path: str,
        func: Callable[..., Any] | Callable[..., Awaitable[Any]],
    ) -> None:
        self._callables[function_path] = func

    async def preview(
        self,
        function_path: str | None,
        params: dict[str, Any] | None = None,
    ) -> DataConnectorResult:
        started = time.perf_counter()
        try:
            payload = await self._execute(function_path, params or {})
            rows = self._normalise_rows(payload)
            columns = list(rows[0].keys()) if rows else []
            quality_warnings = ["empty_result"] if not rows else []
            metadata = {"function_path": function_path or "", "status": "ok"}
        except Exception as exc:
            rows = []
            columns = []
            quality_warnings = [str(exc)]
            metadata = {"function_path": function_path or "", "status": "failed", "error": str(exc)}
        return DataConnectorResult(
            columns=columns,
            rows=rows,
            metadata=metadata,
            provider_latency_ms=int((time.perf_counter() - started) * 1000),
            quality_warnings=quality_warnings,
        )

    async def _execute(self, function_path: str | None, params: dict[str, Any]) -> Any:
        if not function_path:
            raise ValueError("connector_function_path_missing")
        if function_path in self._callables:
            return await self._call(function_path, params)
        callable_ref = self._import_callable(function_path)
        if callable_ref is None:
            raise ValueError(f"connector_callable_unavailable:{function_path}")
        self.register_callable(function_path, callable_ref)
        return await self._call(function_path, params)

    async def _call(self, function_path: str, params: dict[str, Any]) -> Any:
        result = self._callables[function_path](**params)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def _register_builtin_callables(self) -> None:
        self.register_callable("yahoo.quote", self._yahoo_quote)
        self.register_callable("yahoo.history", self._yahoo_history)
        self.register_callable("fred.DGS10", self._fred_series)
        self.register_callable("fred.macro_series", self._fred_series)
        self.register_callable("coingecko.coin_price", self._coin_price)
        self.register_callable("cboe.option_chain", self._cboe_option_chain)
        self.register_callable("cftc.commitments_of_traders", self._cftc_commitments)
        self.register_callable("dbnomics.dataset_series", self._dbnomics_series)
        self.register_callable("fmp.company_profile", self._fmp_company_profile)

    def _import_callable(
        self,
        function_path: str,
    ) -> Callable[..., Any] | Callable[..., Awaitable[Any]] | None:
        module_path, _, attr_name = function_path.rpartition(".")
        if not module_path or not attr_name:
            return None
        try:
            module = importlib.import_module(module_path)
        except Exception:
            return None
        func = getattr(module, attr_name, None)
        if callable(func):
            return func
        return None

    def _yahoo_quote(
        self,
        *,
        symbol: str | None = None,
        q: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        resolved_symbol = str(symbol or q or "RB2510")
        price = self._base_price(resolved_symbol)
        previous_close = round(price * 0.988, 2)
        return {
            "symbol": resolved_symbol,
            "price": price,
            "previous_close": previous_close,
            "change_pct": round((price - previous_close) / previous_close, 4),
            "currency": (
                "CNY"
                if resolved_symbol.endswith((".SZ", ".SH"))
                or resolved_symbol.startswith(("RB", "IF"))
                else "USD"
            ),
            "provider": "yahoo",
        }

    def _yahoo_history(
        self,
        *,
        symbol: str | None = None,
        q: str | None = None,
        limit: int | None = None,
        **_: Any,
    ) -> list[dict[str, Any]]:
        resolved_symbol = str(symbol or q or "RB2510")
        row_count = max(min(int(limit or 12), 60), 3)
        base_price = self._base_price(resolved_symbol)
        rows: list[dict[str, Any]] = []
        for index in range(row_count):
            close = round(base_price - (row_count - index) * 0.9 + (index % 3) * 0.35, 2)
            rows.append(
                {
                    "symbol": resolved_symbol,
                    "date": f"2026-05-{index + 1:02d}",
                    "open": round(close - 0.8, 2),
                    "high": round(close + 1.1, 2),
                    "low": round(close - 1.4, 2),
                    "close": close,
                    "volume": 1000 + index * 120,
                }
            )
        return rows

    def _fred_series(self, *, series_id: str | None = None, **_: Any) -> list[dict[str, Any]]:
        resolved_series = str(series_id or "DGS10")
        values = [3.92, 3.95, 3.9, 3.88, 3.93]
        return [
            {"series_id": resolved_series, "date": f"2026-05-{index + 20:02d}", "value": value}
            for index, value in enumerate(values)
        ]

    def _coin_price(
        self,
        *,
        symbol: str | None = None,
        coin_id: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        resolved_symbol = str(symbol or coin_id or "BTC")
        price = 108_500.0 if resolved_symbol.upper() in {"BTC", "BITCOIN"} else 3_250.0
        return {
            "symbol": resolved_symbol.upper(),
            "price_usd": price,
            "change_pct_24h": 0.024,
            "provider": "coingecko",
        }

    def _cboe_option_chain(
        self,
        *,
        symbol: str | None = None,
        expiry: str | None = None,
        **_: Any,
    ) -> list[dict[str, Any]]:
        resolved_symbol = str(symbol or "RB2510")
        spot = self._base_price(resolved_symbol)
        strike_step = 5.0 if spot >= 50 else 1.0
        start = int(spot // strike_step) - 4
        strikes = [round((start + index) * strike_step, 2) for index in range(9)]
        rows: list[dict[str, Any]] = []
        for index, strike in enumerate(strikes, start=1):
            rows.append(
                {
                    "symbol": resolved_symbol,
                    "expiry": expiry or "2026-12-31",
                    "strike": strike,
                    "call_oi": 120 * index,
                    "call_volume": 35 * index,
                    "call_iv": round(0.18 + index * 0.008, 4),
                    "put_oi": 100 * index,
                    "put_volume": 30 * index,
                    "put_iv": round(0.19 + index * 0.008, 4),
                }
            )
        return rows

    def _cftc_commitments(self, *, symbol: str | None = None, **_: Any) -> list[dict[str, Any]]:
        resolved_symbol = str(symbol or "RB2510")
        return [
            {
                "symbol": resolved_symbol,
                "report_date": f"2026-05-{index + 18:02d}",
                "commercial_long": 15_000 + index * 250,
                "commercial_short": 12_500 + index * 180,
                "noncommercial_long": 9_000 + index * 120,
                "noncommercial_short": 8_200 + index * 95,
            }
            for index in range(3)
        ]

    def _dbnomics_series(
        self,
        *,
        dataset_code: str | None = None,
        **_: Any,
    ) -> list[dict[str, Any]]:
        resolved_code = str(dataset_code or "UST10Y")
        return [
            {"dataset_code": resolved_code, "period": "2026-Q1", "value": 4.1},
            {"dataset_code": resolved_code, "period": "2026-Q2", "value": 4.3},
            {"dataset_code": resolved_code, "period": "2026-Q3", "value": 4.25},
        ]

    def _fmp_company_profile(self, *, symbol: str | None = None, **_: Any) -> dict[str, Any]:
        resolved_symbol = str(symbol or "000001.SZ")
        return {
            "symbol": resolved_symbol,
            "company_name": "平安银行" if resolved_symbol == "000001.SZ" else resolved_symbol,
            "sector": "Financials" if resolved_symbol == "000001.SZ" else "Industrials",
            "industry": "Banks" if resolved_symbol == "000001.SZ" else "Metals",
            "country": "CN",
            "exchange": "SZSE" if resolved_symbol.endswith(".SZ") else "SHFE",
            "provider": "fmp",
        }

    @staticmethod
    def _base_price(symbol: str) -> float:
        normalized = symbol.upper()
        if normalized == "RB2510":
            return 3524.0
        if normalized == "IF2510":
            return 4125.0
        if normalized == "000001.SZ":
            return 12.36
        return 100.0

    @staticmethod
    def _normalise_rows(payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if hasattr(payload, "to_dict"):
            records = payload.to_dict(orient="records")
            return [dict(record) for record in records]
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            rows = payload.get("rows")
            if isinstance(rows, list):
                return [dict(item) for item in rows if isinstance(item, dict)]
            return [payload]
        return [{"value": payload}]
