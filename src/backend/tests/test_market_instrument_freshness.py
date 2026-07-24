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
