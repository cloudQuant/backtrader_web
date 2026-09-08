"""Regression tests for market-history freshness gating."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.market_instrument import MarketInstrumentService


def test_history_refresh_rejects_legacy_rows_for_a_current_request():
    assert MarketInstrumentService._history_requires_refresh(
        asset_type="stock",
        rows=[{"date": "2024-12-31", "close": 10.0}],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 22),
    )


def test_history_refresh_accepts_a_valid_historical_request_range():
    assert not MarketInstrumentService._history_requires_refresh(
        asset_type="stock",
        rows=[{"date": "2024-12-30", "close": 10.0}, {"date": "2024-12-31", "close": 10.1}],
        start_date=date(2024, 12, 1),
        end_date=date(2024, 12, 31),
    )


@pytest.mark.asyncio
async def test_market_instrument_hides_warehouse_access_denied_details():
    """Warehouse ACL failures must not leak SQL errors into the UI."""
    warnings: list[str] = []

    class DeniedWarehouseService(MarketInstrumentService):
        async def _lookup_stock_warehouse(self, **_kwargs):
            raise RuntimeError("Access denied for user 'backtrader_web' to database 'akshare_data'")

    payload = await DeniedWarehouseService()._lookup_warehouse(
        asset_type="stock",
        symbol="000001",
        start_date="2026-06-01",
        end_date="2026-06-19",
        period="1d",
        market="CN",
        warnings=warnings,
    )

    assert payload["history"]["total"] == 0
    assert warnings == ["本地 MySQL 行情仓库不可用，请检查数据源访问权限。"]


@pytest.mark.asyncio
async def test_default_market_lookup_reads_only_the_mysql_warehouse():
    """Initial page loading must never trigger a network market-data request."""

    class LocalOnlyService(MarketInstrumentService):
        async def _lookup_warehouse(self, **_kwargs):
            return self._payload(
                asset_type="stock",
                symbol="000001",
                name="平安银行",
                market="CN",
                snapshot={"symbol": "000001", "price": 10.0},
                rows=[{"date": "2024-12-31", "close": 10.0}],
                period="daily",
                provider="akshare_data",
            )

        def _lookup_stock(self, **_kwargs):
            raise AssertionError("default lookup must not call AkShare")

    payload = await LocalOnlyService().lookup(
        asset_type="stock",
        symbol="000001",
        start_date="2026-06-01",
        end_date="2026-06-19",
        refresh_online=False,
    )

    assert payload["provider"] == "akshare_data"
    assert payload["history"]["total"] == 1


@pytest.mark.asyncio
async def test_user_requested_market_lookup_fetches_akshare_after_local_read():
    """Only an explicit query action may refresh data from AkShare."""

    calls: list[str] = []

    class UserRequestedRefreshService(MarketInstrumentService):
        async def _lookup_warehouse(self, **_kwargs):
            return self._payload(
                asset_type="stock",
                symbol="000001",
                name="平安银行",
                market="CN",
                snapshot={"symbol": "000001", "price": 10.0},
                rows=[{"date": "2026-06-18", "close": 10.0}],
                period="daily",
                provider="akshare_data",
            )

        def _lookup_stock(self, **kwargs):
            calls.append(kwargs["symbol"])
            return self._payload(
                asset_type="stock",
                symbol="000001",
                name="平安银行",
                market="CN",
                snapshot={"symbol": "000001", "price": 11.0},
                rows=[{"date": "2026-06-19", "close": 11.0}],
                period="daily",
                provider="akshare",
            )

    payload = await UserRequestedRefreshService().lookup(
        asset_type="stock",
        symbol="000001",
        start_date="2026-06-01",
        end_date="2026-06-19",
        refresh_online=True,
    )

    assert calls == ["000001"]
    assert payload["provider"] == "akshare"
    assert payload["snapshot"]["price"] == 11.0


@pytest.mark.asyncio
async def test_empty_akshare_response_keeps_the_mysql_market_data():
    """Identity-only AkShare responses must not replace a usable local result."""

    class EmptyOnlineRefreshService(MarketInstrumentService):
        async def _lookup_warehouse(self, **_kwargs):
            return self._payload(
                asset_type="stock",
                symbol="000001",
                name="平安银行",
                market="CN",
                snapshot={"symbol": "000001", "price": 10.0},
                rows=[{"date": "2026-06-18", "close": 10.0}],
                period="daily",
                provider="akshare_data",
            )

        def _lookup_stock(self, **_kwargs):
            return self._payload(
                asset_type="stock",
                symbol="000001",
                name="000001",
                market="CN",
                snapshot={"symbol": "000001", "name": "000001"},
                rows=[],
                period="daily",
                provider="akshare",
            )

    payload = await EmptyOnlineRefreshService().lookup(
        asset_type="stock",
        symbol="000001",
        start_date="2026-06-01",
        end_date="2026-06-19",
        refresh_online=True,
    )

    assert payload["provider"] == "akshare_data"
    assert payload["history"]["total"] == 1
    assert "AkShare 未返回可用数据，已保留本地 MySQL 数据。" in payload["warnings"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asset_type", "symbol", "unexpected_symbol"),
    [
        ("stock", "000001", "600519"),
        ("futures", "RB2510", "IF2510"),
        ("bond", "sh113527", "sh110074"),
        ("fund", "510300", "159915"),
        ("option", "10003889", "10003890"),
        ("fx", "USDCNH", "EURUSD"),
        ("crypto", "BTCJPY", "ETHJPY"),
    ],
)
async def test_local_lookup_discards_a_payload_for_a_different_instrument(
    asset_type: str,
    symbol: str,
    unexpected_symbol: str,
):
    """Legacy fallback must return an empty result instead of a nearby symbol."""

    class MismatchedWarehouseService(MarketInstrumentService):
        async def _lookup_warehouse(self, **kwargs):
            return self._payload(
                asset_type=kwargs["asset_type"],
                symbol=unexpected_symbol,
                name=unexpected_symbol,
                market=kwargs["market"] or "CN",
                snapshot={"symbol": unexpected_symbol, "price": 99.0},
                rows=[{"date": "2026-06-19", "close": 99.0}],
                period=kwargs["period"],
                provider="akshare_data",
            )

    payload = await MismatchedWarehouseService().lookup(
        asset_type=asset_type,  # type: ignore[arg-type]
        symbol=symbol,
        start_date="2026-06-01",
        end_date="2026-06-19",
        refresh_online=False,
    )

    assert payload["symbol"].upper() == symbol.upper()
    assert payload["snapshot"] == {}
    assert payload["history"]["total"] == 0
    assert payload["warnings"] == ["本地行情未返回所请求的精确标的，已忽略该结果。"]


@pytest.mark.asyncio
async def test_refresh_discards_an_online_payload_for_a_different_instrument():
    """An online refresh must not replace local data with another symbol's result."""

    class MismatchedOnlineService(MarketInstrumentService):
        async def _lookup_warehouse(self, **kwargs):
            return self._payload(
                asset_type="stock",
                symbol=kwargs["symbol"],
                name=kwargs["symbol"],
                market="CN",
                snapshot={},
                rows=[],
                period=kwargs["period"],
                provider="akshare_data",
            )

        def _lookup_stock(self, **kwargs):
            return self._payload(
                asset_type="stock",
                symbol="600519",
                name="600519",
                market="CN",
                snapshot={"symbol": "600519", "price": 99.0},
                rows=[{"date": "2026-06-19", "close": 99.0}],
                period=kwargs["period"],
                provider="akshare",
            )

    payload = await MismatchedOnlineService().lookup(
        asset_type="stock",
        symbol="000001",
        start_date="2026-06-01",
        end_date="2026-06-19",
        refresh_online=True,
    )

    assert payload["symbol"] == "000001"
    assert payload["snapshot"] == {}
    assert payload["history"]["total"] == 0
    assert "本地行情未找到所请求的精确标的。" in payload["warnings"]
    assert "AkShare 未返回所请求的精确标的，已忽略该结果。" in payload["warnings"]


@pytest.mark.asyncio
async def test_stock_warehouse_does_not_substitute_recent_rows_outside_the_requested_window():
    """A history miss must retain its requested time window instead of showing stale bars."""

    queries: list[str] = []

    class ExactWindowService(MarketInstrumentService):
        async def _fetch_one(self, *_args, **_kwargs):
            return None

        async def _fetch_rows(self, sql, *_args, **_kwargs):
            queries.append(sql)
            return []

    payload = await ExactWindowService()._lookup_stock_warehouse(
        symbol="000001",
        start_date="2026-06-01",
        end_date="2026-06-19",
        period="daily",
        market="CN",
        warnings=[],
    )

    assert payload["history"]["total"] == 0
    assert len(queries) == 2
    assert all("BETWEEN :start AND :end" in query for query in queries)
    assert not any("LIMIT 120" in query for query in queries)
