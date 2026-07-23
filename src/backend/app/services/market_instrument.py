from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

import pandas as pd
from sqlalchemy import text

from app.db.akshare_data_database import _get_akshare_data_engine

MarketAssetType = Literal["stock", "futures", "bond", "fund", "option", "fx", "crypto"]

_WAREHOUSE_PROVIDER = "akshare_data"
_ONLINE_PROVIDER = "akshare"
_HISTORY_FRESHNESS_DAYS: dict[MarketAssetType, int] = {
    # These are calendar-day tolerances, deliberately wider than a single
    # session so normal weekends and provider publication delays do not force
    # an unnecessary online fetch. They are still narrow enough to prevent an
    # old warehouse fallback from being presented as current market data.
    "stock": 5,
    "futures": 5,
    "bond": 5,
    "fund": 5,
    "option": 5,
    "fx": 5,
    "crypto": 2,
}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _safe_int(value: Any) -> int | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    return int(numeric)


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    """Return the first present value, accepting both original and lower-case keys."""
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if not key:
            continue
        if key in row and row[key] is not None:
            return row[key]
        lowered_value = lowered.get(key.lower())
        if lowered_value is not None:
            return lowered_value
    return None


def _date_text(value: date | str | None, fallback: date) -> str:
    if value is None:
        return fallback.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return value.replace("-", "")


def _sql_date_text(value: date | str | None, fallback: date) -> str:
    if value is None:
        return fallback.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = value.strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _coerce_date(value: Any) -> date | None:
    """Return a date value without silently accepting an invalid timestamp."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _iso_date(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value)


def _normalize_plain_code(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if "." in normalized:
        left, right = normalized.split(".", 1)
        if left in {"SH", "SZ", "BJ"}:
            return right
        if right in {"SH", "SZ", "BJ"}:
            return left
        return left
    if normalized.startswith(("SH", "SZ", "BJ")) and len(normalized) > 2:
        return normalized[2:]
    return normalized


def _normalize_exchange_symbol(symbol: str, default_prefix: str = "sh") -> str:
    normalized = symbol.strip().lower()
    if "." in normalized:
        code, exchange = normalized.split(".", 1)
        if exchange in {"sh", "sz", "bj"}:
            return f"{exchange}{code}"
    if normalized.startswith(("sh", "sz", "bj")):
        return normalized
    return f"{default_prefix}{normalized}"


def _normalize_upper_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "")


def _coerce_cell(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _coerce_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _coerce_cell(value) for key, value in row.items()}


def _normalize_period(period: str) -> str:
    period_map = {
        "1d": "daily",
        "daily": "daily",
        "day": "daily",
        "1w": "weekly",
        "weekly": "weekly",
        "week": "weekly",
        "1m": "monthly",
        "1M": "monthly",
        "monthly": "monthly",
        "month": "monthly",
    }
    return period_map.get(period, "daily")


class MarketInstrumentService:
    """Aggregate quote snapshots and history for market data lookup pages."""

    async def list_instruments(
        self,
        *,
        asset_type: MarketAssetType,
        search: str = "",
        limit: int = 80,
    ) -> dict[str, Any]:
        """Return selectable instruments from the local market data warehouse."""
        normalized_limit = max(1, min(limit, 200))
        lookup_map = {
            "stock": self._list_stock_instruments,
            "futures": self._list_futures_instruments,
            "bond": self._list_bond_instruments,
            "fund": self._list_fund_instruments,
            "option": self._list_option_instruments,
            "fx": self._list_fx_instruments,
            "crypto": self._list_crypto_instruments,
        }
        lookup = lookup_map.get(asset_type)
        if lookup is None:
            raise ValueError(f"Unsupported asset type: {asset_type}")
        items = await lookup(search=search.strip(), limit=normalized_limit)
        cached_items = await self._list_cached_instruments(
            asset_type=asset_type,
            search=search.strip(),
            limit=normalized_limit,
        )
        items = self._normalize_instrument_options(
            [*items, *cached_items],
            asset_type,
            normalized_limit,
        )
        return {
            "asset_type": asset_type,
            "items": items,
            "total": len(items),
        }

    async def lookup(
        self,
        *,
        asset_type: MarketAssetType,
        symbol: str,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        period: str = "daily",
        market: str | None = None,
    ) -> dict[str, Any]:
        normalized_symbol = symbol.strip().upper()
        end = date.today()
        start = end - timedelta(days=90)
        normalized_period = _normalize_period(period)
        warnings: list[str] = []

        lookup_map = {
            "stock": self._lookup_stock,
            "futures": self._lookup_futures,
            "bond": self._lookup_bond,
            "fund": self._lookup_fund,
            "option": self._lookup_option,
            "fx": self._lookup_fx,
            "crypto": self._lookup_crypto,
        }
        lookup = lookup_map.get(asset_type)
        if lookup is None:
            raise ValueError(f"Unsupported asset type: {asset_type}")

        warehouse_payload = await self._lookup_warehouse(
            asset_type=asset_type,
            symbol=normalized_symbol,
            start_date=start_date or start,
            end_date=end_date or end,
            period=normalized_period,
            market=market,
            warnings=warnings,
        )
        if self._payload_has_data(warehouse_payload):
            if self._history_requires_refresh(
                asset_type=asset_type,
                rows=(warehouse_payload.get("history") or {}).get("rows") or [],
                start_date=start_date or start,
                end_date=end_date or end,
            ):
                warnings.append("本地历史数据未覆盖所选区间或已超过发布延迟，正在使用补齐来源")
                warehouse_payload = await self._fill_history_gap(
                    asset_type=asset_type,
                    warehouse_payload=warehouse_payload,
                    symbol=normalized_symbol,
                    start_date=start_date or start,
                    end_date=end_date or end,
                    period=normalized_period,
                    market=market,
                    warnings=warnings,
                )
            warehouse_payload["warnings"] = warnings
            warehouse_payload["indicators"] = self._build_indicators(
                warehouse_payload["history"]["rows"]
            )
            return warehouse_payload

        payload = lookup(
            symbol=normalized_symbol,
            start_date=start_date or start,
            end_date=end_date or end,
            period=normalized_period,
            market=market,
            warnings=warnings,
        )
        payload["warnings"] = warnings
        payload["indicators"] = self._build_indicators(payload["history"]["rows"])
        return payload

    async def _lookup_warehouse(
        self,
        *,
        asset_type: MarketAssetType,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        lookup_map = {
            "stock": self._lookup_stock_warehouse,
            "futures": self._lookup_futures_warehouse,
            "bond": self._lookup_bond_warehouse,
            "fund": self._lookup_fund_warehouse,
            "option": self._lookup_option_warehouse,
            "fx": self._lookup_fx_warehouse,
            "crypto": self._lookup_crypto_warehouse,
        }
        lookup = lookup_map[asset_type]
        try:
            return await lookup(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                period=period,
                market=market,
                warnings=warnings,
            )
        except RuntimeError as exc:
            warnings.append(f"akshare_data 数据仓库不可用: {exc}")
        except Exception as exc:
            warnings.append(f"akshare_data 查询失败: {exc}")
        return self._payload(
            asset_type=asset_type,
            symbol=symbol,
            name=symbol,
            market=market or self._default_market(asset_type),
            snapshot={},
            rows=[],
            period=period,
            provider=_WAREHOUSE_PROVIDER,
        )

    @staticmethod
    def _payload_has_data(payload: dict[str, Any]) -> bool:
        snapshot = payload.get("snapshot") or {}
        rows = (payload.get("history") or {}).get("rows") or []
        return any(value is not None for value in snapshot.values()) or bool(rows)

    @staticmethod
    def _history_requires_refresh(
        *,
        asset_type: MarketAssetType,
        rows: list[dict[str, Any]],
        start_date: date | str,
        end_date: date | str,
    ) -> bool:
        """Return whether rows cannot safely satisfy the requested market interval.

        A non-empty response is not sufficient evidence of usable market data:
        legacy fallbacks can contain a valid-looking 2024 row for a current
        request. Require the latest bar to be inside the requested interval and
        within the source-specific publication-lag tolerance.
        """
        requested_start = _coerce_date(start_date)
        requested_end = _coerce_date(end_date)
        dates = [parsed for row in rows if (parsed := _coerce_date(row.get("date"))) is not None]
        if not dates or requested_start is None or requested_end is None:
            return True

        earliest = min(dates)
        latest = max(dates)
        if earliest > requested_end or latest < requested_start or latest > requested_end:
            return True

        tolerance = timedelta(days=_HISTORY_FRESHNESS_DAYS[asset_type])
        return latest < requested_end - tolerance

    async def _fill_history_gap(
        self,
        *,
        asset_type: MarketAssetType,
        warehouse_payload: dict[str, Any],
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        cached_rows = await self._lookup_history_cache(
            asset_type=asset_type,
            symbol=warehouse_payload.get("symbol") or symbol,
            start_date=start_date,
            end_date=end_date,
            period=period,
        )
        if cached_rows and not self._history_requires_refresh(
            asset_type=asset_type,
            rows=cached_rows,
            start_date=start_date,
            end_date=end_date,
        ):
            warnings.append("akshare_data 缺少该资产本地历史数据，已使用补齐缓存")
            return self._merge_history_gap(
                warehouse_payload=warehouse_payload,
                rows=cached_rows,
                period=period,
                provider_suffix="cache",
            )
        if cached_rows:
            warnings.append("MARKET_INSTRUMENT_HISTORY_CACHE 已过期或未覆盖所选区间，跳过缓存")

        online_warnings: list[str] = []
        online_rows = self._lookup_history_online(
            asset_type=asset_type,
            symbol=warehouse_payload.get("symbol") or symbol,
            start_date=start_date,
            end_date=end_date,
            period=period,
            market=market,
            warnings=online_warnings,
        )
        if not online_rows:
            if not online_warnings:
                online_warnings.append("该资产暂无本地历史数据，在线历史接口也未返回可用记录")
            warnings.extend(online_warnings)
            return warehouse_payload

        if self._history_requires_refresh(
            asset_type=asset_type,
            rows=online_rows,
            start_date=start_date,
            end_date=end_date,
        ):
            warnings.extend(online_warnings)
            warnings.append("在线历史数据未覆盖所选区间，未替换现有仓库记录")
            return warehouse_payload

        cache_error = await self._store_history_cache(
            asset_type=asset_type,
            symbol=warehouse_payload.get("symbol") or symbol,
            name=warehouse_payload.get("name") or symbol,
            market=warehouse_payload.get("market") or market or self._default_market(asset_type),
            period=period,
            rows=online_rows,
        )
        warnings.append("akshare_data 缺少该资产本地历史数据，已使用 AkShare 在线历史行情补齐")
        if cache_error:
            warnings.append(f"在线历史已返回，但写入补齐缓存失败: {cache_error}")
        else:
            warnings.append("在线历史已写入 MARKET_INSTRUMENT_HISTORY_CACHE 补齐缓存")

        return self._merge_history_gap(
            warehouse_payload=warehouse_payload,
            rows=online_rows,
            period=period,
            provider_suffix=_ONLINE_PROVIDER,
        )

    def _merge_history_gap(
        self,
        *,
        warehouse_payload: dict[str, Any],
        rows: list[dict[str, Any]],
        period: str,
        provider_suffix: str,
    ) -> dict[str, Any]:
        merged = {**warehouse_payload}
        merged["history"] = {
            "period": period,
            "rows": rows,
            "total": len(rows),
        }
        merged["provider"] = (
            f"{warehouse_payload.get('provider') or _WAREHOUSE_PROVIDER}+{provider_suffix}"
        )
        snapshot_values = {
            key: value
            for key, value in (merged.get("snapshot") or {}).items()
            if key != "data_source_table"
        }
        if not any(value is not None for value in snapshot_values.values()):
            merged["snapshot"] = self._snapshot_from_latest_history(
                merged.get("symbol") or "", rows
            )
        return merged

    def _lookup_history_online(
        self,
        *,
        asset_type: MarketAssetType,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        if asset_type == "stock":
            return self._lookup_stock_history_online(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                period=period,
                warnings=warnings,
            )

        lookup_map = {
            "futures": self._lookup_futures,
            "bond": self._lookup_bond,
            "fund": self._lookup_fund,
            "option": self._lookup_option,
            "fx": self._lookup_fx,
            "crypto": self._lookup_crypto,
        }
        lookup = lookup_map.get(asset_type)
        if lookup is None:
            return []
        payload = lookup(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            period=period,
            market=market,
            warnings=warnings,
        )
        return (payload.get("history") or {}).get("rows") or []

    def _lookup_stock_history_online(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        import akshare as ak

        code = _normalize_plain_code(symbol)
        try:
            history_df = ak.stock_zh_a_hist(
                symbol=code,
                period=period,
                start_date=_date_text(start_date, date.today() - timedelta(days=90)),
                end_date=_date_text(end_date, date.today()),
                adjust="qfq",
                timeout=10,
            )
            return self._normalize_cn_ohlcv_history(history_df)
        except Exception as exc:
            warnings.append(f"A 股历史行情不可用: {exc}")
            return []

    async def _list_stock_instruments(self, *, search: str, limit: int) -> list[dict[str, Any]]:
        rows = await self._fetch_rows(
            """
            SELECT
                symbol,
                name,
                'CN' AS market,
                'STOCK_ZH_A_SPOT_EM' AS source_table,
                MAX(latest_date) AS latest_date,
                1 AS has_snapshot,
                0 AS has_history,
                0 AS history_rows,
                MAX(sort_value) AS sort_value
            FROM (
                SELECT
                    COALESCE(NULLIF(symbol, ''), `代码`) AS symbol,
                    COALESCE(NULLIF(name, ''), `名称`, `代码`) AS name,
                    data_date AS latest_date,
                    `成交额` AS sort_value
                FROM STOCK_ZH_A_SPOT_EM
                WHERE (:search = ''
                    OR COALESCE(symbol, '') LIKE :pattern
                    OR COALESCE(name, '') LIKE :pattern
                    OR `代码` LIKE :pattern
                    OR `名称` LIKE :pattern)
            ) AS candidates
            WHERE symbol IS NOT NULL AND symbol <> ''
            GROUP BY symbol, name
            ORDER BY latest_date DESC, sort_value DESC, symbol ASC
            LIMIT :limit
            """,
            self._instrument_query_params(search, limit),
        )
        return self._normalize_instrument_options(rows, "stock", limit)

    async def _list_futures_instruments(self, *, search: str, limit: int) -> list[dict[str, Any]]:
        params = self._instrument_query_params(search, limit)
        if not search:
            latest = await self._fetch_one(
                "SELECT MAX(TRADE_DATE) AS latest_date FROM FUTURES_DAILY_MARKET"
            )
            latest_date = latest.get("latest_date") if latest else None
            if latest_date:
                rows = await self._fetch_rows(
                    """
                    SELECT
                        SYMBOL AS symbol,
                        CONCAT(
                            SYMBOL,
                            ' / ',
                            COALESCE(NULLIF(VARIETY, ''), COALESCE(MARKET, 'CN'))
                        ) AS name,
                        COALESCE(MARKET, 'CN') AS market,
                        'FUTURES_DAILY_MARKET' AS source_table,
                        MAX(TRADE_DATE) AS latest_date,
                        0 AS has_snapshot,
                        1 AS has_history,
                        COUNT(*) AS history_rows
                    FROM FUTURES_DAILY_MARKET
                    WHERE TRADE_DATE = :latest_date
                    GROUP BY SYMBOL, VARIETY, MARKET
                    ORDER BY history_rows DESC, SYMBOL ASC
                    LIMIT :limit
                    """,
                    {**params, "latest_date": latest_date},
                )
                return self._normalize_instrument_options(rows, "futures", limit)

        exact_rows = await self._fetch_rows(
            """
            SELECT
                SYMBOL AS symbol,
                CONCAT(
                    SYMBOL,
                    ' / ',
                    COALESCE(NULLIF(MAX(VARIETY), ''), COALESCE(MAX(MARKET), 'CN'))
                ) AS name,
                COALESCE(MAX(MARKET), 'CN') AS market,
                'FUTURES_DAILY_MARKET' AS source_table,
                MAX(TRADE_DATE) AS latest_date,
                0 AS has_snapshot,
                1 AS has_history,
                COUNT(*) AS history_rows
            FROM FUTURES_DAILY_MARKET
            WHERE SYMBOL IN (:search, :upper_search)
            GROUP BY SYMBOL
            ORDER BY latest_date DESC, history_rows DESC, SYMBOL ASC
            LIMIT :limit
            """,
            {**params, "upper_search": search.upper()},
        )
        if exact_rows:
            return self._normalize_instrument_options(exact_rows, "futures", limit)

        rows = await self._fetch_rows(
            """
            SELECT
                SYMBOL AS symbol,
                CONCAT(SYMBOL, ' / ', COALESCE(NULLIF(VARIETY, ''), COALESCE(MARKET, 'CN'))) AS name,
                COALESCE(MARKET, 'CN') AS market,
                'FUTURES_DAILY_MARKET' AS source_table,
                MAX(TRADE_DATE) AS latest_date,
                0 AS has_snapshot,
                1 AS has_history,
                COUNT(*) AS history_rows
            FROM FUTURES_DAILY_MARKET
            WHERE (SYMBOL LIKE :prefix_pattern
                OR COALESCE(VARIETY, '') LIKE :pattern
                OR COALESCE(MARKET, '') LIKE :pattern)
            GROUP BY SYMBOL, VARIETY, MARKET
            ORDER BY latest_date DESC, history_rows DESC, SYMBOL ASC
            LIMIT :limit
            """,
            {**params, "prefix_pattern": f"{search}%"},
        )
        return self._normalize_instrument_options(rows, "futures", limit)

    async def _list_bond_instruments(self, *, search: str, limit: int) -> list[dict[str, Any]]:
        params = self._instrument_query_params(search, limit)
        rows = await self._fetch_rows(
            """
            SELECT
                symbol,
                COALESCE(NULLIF(name, ''), code, symbol) AS name,
                'CN' AS market,
                'BOND_ZH_HS_COV_SPOT' AS source_table,
                MAX(data_date) AS latest_date,
                1 AS has_snapshot,
                0 AS has_history,
                0 AS history_rows
            FROM BOND_ZH_HS_COV_SPOT
            WHERE (:search = ''
                OR LOWER(symbol) LIKE LOWER(:pattern)
                OR code LIKE :pattern
                OR COALESCE(name, '') LIKE :pattern)
            GROUP BY symbol, name, code
            ORDER BY latest_date DESC, symbol ASC
            LIMIT :limit
            """,
            params,
        )
        rows.extend(
            await self._fetch_rows(
                """
                SELECT
                    symbol,
                    COALESCE(NULLIF(MAX(name), ''), symbol) AS name,
                    'CN' AS market,
                    'BOND_ZH_HS_COV_MIN' AS source_table,
                    MAX(data_date) AS latest_date,
                    0 AS has_snapshot,
                    1 AS has_history,
                    COUNT(*) AS history_rows
                FROM BOND_ZH_HS_COV_MIN
                WHERE (:search = ''
                    OR LOWER(symbol) LIKE LOWER(:pattern)
                    OR COALESCE(name, '') LIKE :pattern)
                GROUP BY symbol
                ORDER BY latest_date DESC, history_rows DESC, symbol ASC
                LIMIT :limit
                """,
                params,
            )
        )
        return self._normalize_instrument_options(rows, "bond", limit)

    async def _list_fund_instruments(self, *, search: str, limit: int) -> list[dict[str, Any]]:
        params = self._instrument_query_params(search, limit)
        rows = await self._fetch_rows(
            """
            SELECT
                ETF_CODE AS symbol,
                COALESCE(NULLIF(ETF_NAME, ''), ETF_CODE) AS name,
                'CN' AS market,
                'ETF_REALTIME_QUOTE_EM' AS source_table,
                MAX(QUOTE_DATE) AS latest_date,
                1 AS has_snapshot,
                0 AS has_history,
                0 AS history_rows
            FROM ETF_REALTIME_QUOTE_EM
            WHERE (:search = ''
                OR ETF_CODE LIKE :pattern
                OR COALESCE(ETF_NAME, '') LIKE :pattern)
            GROUP BY ETF_CODE, ETF_NAME
            ORDER BY latest_date DESC, symbol ASC
            LIMIT :limit
            """,
            params,
        )
        rows.extend(
            await self._fetch_rows(
                """
                SELECT
                    FUND_CODE AS symbol,
                    FUND_CODE AS name,
                    'CN' AS market,
                    'ETF_FUND_HIST_EM' AS source_table,
                    MAX(VALUE_DATE) AS latest_date,
                    0 AS has_snapshot,
                    1 AS has_history,
                    COUNT(*) AS history_rows
                FROM ETF_FUND_HIST_EM
                WHERE (:search = '' OR FUND_CODE LIKE :pattern)
                GROUP BY FUND_CODE
                ORDER BY latest_date DESC, history_rows DESC, FUND_CODE ASC
                LIMIT :limit
                """,
                params,
            )
        )
        return self._normalize_instrument_options(rows, "fund", limit)

    async def _list_option_instruments(self, *, search: str, limit: int) -> list[dict[str, Any]]:
        rows = await self._fetch_rows(
            """
            SELECT
                symbol,
                name,
                'CN' AS market,
                'OPTION_CURRENT_EM' AS source_table,
                MAX(latest_date) AS latest_date,
                1 AS has_snapshot,
                1 AS has_history,
                COUNT(*) AS history_rows
            FROM (
                SELECT
                    COALESCE(NULLIF(symbol, ''), `代码`) AS symbol,
                    COALESCE(NULLIF(name, ''), `名称`, `代码`) AS name,
                    data_date AS latest_date
                FROM OPTION_CURRENT_EM
                WHERE (:search = ''
                    OR COALESCE(symbol, '') LIKE :pattern
                    OR COALESCE(name, '') LIKE :pattern
                    OR `代码` LIKE :pattern
                    OR `名称` LIKE :pattern)
            ) AS candidates
            WHERE symbol IS NOT NULL AND symbol <> ''
            GROUP BY symbol, name
            ORDER BY latest_date DESC, history_rows DESC, symbol ASC
            LIMIT :limit
            """,
            self._instrument_query_params(search, limit),
        )
        return self._normalize_instrument_options(rows, "option", limit)

    async def _list_fx_instruments(self, *, search: str, limit: int) -> list[dict[str, Any]]:
        rows = await self._fetch_rows(
            """
            SELECT
                symbol,
                name,
                'FX' AS market,
                'FOREX_SPOT_EM' AS source_table,
                MAX(latest_date) AS latest_date,
                1 AS has_snapshot,
                1 AS has_history,
                COUNT(*) AS history_rows
            FROM (
                SELECT
                    COALESCE(NULLIF(symbol, ''), `代码`) AS symbol,
                    COALESCE(NULLIF(name, ''), `名称`, `代码`) AS name,
                    data_date AS latest_date
                FROM FOREX_SPOT_EM
                WHERE (:search = ''
                    OR COALESCE(symbol, '') LIKE :pattern
                    OR COALESCE(name, '') LIKE :pattern
                    OR `代码` LIKE :pattern
                    OR `名称` LIKE :pattern)
            ) AS candidates
            WHERE symbol IS NOT NULL AND symbol <> ''
            GROUP BY symbol, name
            ORDER BY latest_date DESC, symbol ASC
            LIMIT :limit
            """,
            self._instrument_query_params(search, limit),
        )
        return self._normalize_instrument_options(rows, "fx", limit)

    async def _list_crypto_instruments(self, *, search: str, limit: int) -> list[dict[str, Any]]:
        rows = await self._fetch_rows(
            """
            SELECT
                `交易品种` AS symbol,
                CONCAT(`交易品种`, ' / ', COALESCE(`市场`, 'CRYPTO')) AS name,
                COALESCE(`市场`, 'CRYPTO') AS market,
                'CRYPTO_JS_SPOT' AS source_table,
                MAX(data_date) AS latest_date,
                1 AS has_snapshot,
                1 AS has_history,
                COUNT(*) AS history_rows
            FROM CRYPTO_JS_SPOT
            WHERE (:search = ''
                OR `交易品种` LIKE :pattern
                OR COALESCE(`市场`, '') LIKE :pattern)
            GROUP BY `交易品种`, `市场`
            ORDER BY latest_date DESC, symbol ASC
            LIMIT :limit
            """,
            self._instrument_query_params(search, limit),
        )
        return self._normalize_instrument_options(rows, "crypto", limit)

    @staticmethod
    def _instrument_query_params(search: str, limit: int) -> dict[str, Any]:
        return {
            "search": search,
            "pattern": f"%{search}%",
            "limit": limit,
        }

    def _normalize_instrument_options(
        self,
        rows: list[dict[str, Any]],
        asset_type: MarketAssetType,
        limit: int,
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for row in rows:
            symbol = _safe_str(_first_value(row, "symbol"))
            if not symbol:
                continue
            key = symbol.upper()
            if key not in merged:
                merged[key] = {
                    "asset_type": asset_type,
                    "symbol": symbol,
                    "name": _safe_str(_first_value(row, "name")) or symbol,
                    "market": _safe_str(_first_value(row, "market"))
                    or self._default_market(asset_type),
                    "source_table": _safe_str(_first_value(row, "source_table")),
                    "latest_date": _safe_str(_first_value(row, "latest_date")),
                    "has_snapshot": bool(_safe_int(_first_value(row, "has_snapshot"))),
                    "has_history": bool(_safe_int(_first_value(row, "has_history"))),
                    "history_rows": _safe_int(_first_value(row, "history_rows")) or 0,
                }
                continue

            option = merged[key]
            option["has_snapshot"] = bool(
                option["has_snapshot"] or _safe_int(_first_value(row, "has_snapshot"))
            )
            option["has_history"] = bool(
                option["has_history"] or _safe_int(_first_value(row, "has_history"))
            )
            option["history_rows"] = int(option["history_rows"]) + (
                _safe_int(_first_value(row, "history_rows")) or 0
            )
            latest_date = _safe_str(_first_value(row, "latest_date"))
            if latest_date and (not option["latest_date"] or latest_date > option["latest_date"]):
                option["latest_date"] = latest_date
            source_table = _safe_str(_first_value(row, "source_table"))
            if source_table and source_table not in str(option["source_table"] or ""):
                option["source_table"] = (
                    f"{option['source_table']}/{source_table}"
                    if option["source_table"]
                    else source_table
                )
            name = _safe_str(_first_value(row, "name"))
            if name and option["name"] == option["symbol"]:
                option["name"] = name

        return sorted(
            merged.values(),
            key=lambda item: (
                item.get("latest_date") or "",
                bool(item.get("has_snapshot")),
                int(item.get("history_rows") or 0),
            ),
            reverse=True,
        )[:limit]

    async def _list_cached_instruments(
        self,
        *,
        asset_type: MarketAssetType,
        search: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        try:
            rows = await self._fetch_rows(
                """
                SELECT
                    symbol,
                    COALESCE(NULLIF(MAX(name), ''), symbol) AS name,
                    COALESCE(NULLIF(MAX(market), ''), :market) AS market,
                    'MARKET_INSTRUMENT_HISTORY_CACHE' AS source_table,
                    MAX(`date`) AS latest_date,
                    0 AS has_snapshot,
                    1 AS has_history,
                    COUNT(*) AS history_rows
                FROM MARKET_INSTRUMENT_HISTORY_CACHE
                WHERE asset_type = :asset_type
                  AND (:search = ''
                    OR symbol LIKE :pattern
                    OR COALESCE(name, '') LIKE :pattern
                    OR COALESCE(market, '') LIKE :pattern)
                GROUP BY symbol
                ORDER BY latest_date DESC, history_rows DESC, symbol ASC
                LIMIT :limit
                """,
                {
                    **self._instrument_query_params(search, limit),
                    "asset_type": asset_type,
                    "market": self._default_market(asset_type),
                },
            )
        except Exception:
            return []
        return rows

    async def _lookup_history_cache(
        self,
        *,
        asset_type: MarketAssetType,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
    ) -> list[dict[str, Any]]:
        try:
            rows = await self._fetch_rows(
                """
                SELECT
                    `date`,
                    name,
                    open,
                    high,
                    low,
                    close,
                    price,
                    volume,
                    turnover,
                    change_value,
                    change_pct,
                    turnover_rate,
                    open_interest,
                    settle,
                    strike,
                    days_to_expiry
                FROM MARKET_INSTRUMENT_HISTORY_CACHE
                WHERE asset_type = :asset_type
                  AND UPPER(symbol) = :symbol
                  AND period = :period
                  AND STR_TO_DATE(`date`, '%Y-%m-%d') BETWEEN :start AND :end
                ORDER BY STR_TO_DATE(`date`, '%Y-%m-%d') ASC
                LIMIT 260
                """,
                {
                    "asset_type": asset_type,
                    "symbol": symbol.upper(),
                    "period": period,
                    "start": _sql_date_text(start_date, date.today()),
                    "end": _sql_date_text(end_date, date.today()),
                },
            )
        except Exception:
            return []

        return [
            {
                "date": _iso_date(_first_value(row, "date")),
                "name": _safe_str(_first_value(row, "name")),
                "open": _safe_float(_first_value(row, "open")),
                "high": _safe_float(_first_value(row, "high")),
                "low": _safe_float(_first_value(row, "low")),
                "close": _safe_float(_first_value(row, "close")),
                "price": _safe_float(_first_value(row, "price")),
                "volume": _safe_int(_first_value(row, "volume")),
                "turnover": _safe_float(_first_value(row, "turnover")),
                "change": _safe_float(_first_value(row, "change_value")),
                "change_pct": _safe_float(_first_value(row, "change_pct")),
                "turnover_rate": _safe_float(_first_value(row, "turnover_rate")),
                "open_interest": _safe_int(_first_value(row, "open_interest")),
                "settle": _safe_float(_first_value(row, "settle")),
                "strike": _safe_float(_first_value(row, "strike")),
                "days_to_expiry": _safe_int(_first_value(row, "days_to_expiry")),
            }
            for row in rows
        ]

    async def _store_history_cache(
        self,
        *,
        asset_type: MarketAssetType,
        symbol: str,
        name: str,
        market: str,
        period: str,
        rows: list[dict[str, Any]],
    ) -> str | None:
        payloads = []
        normalized_symbol = symbol.upper()
        for row in rows:
            row_date = _safe_str(_first_value(row, "date"))
            if not row_date:
                continue
            payloads.append(
                {
                    "r_id": f"{asset_type}|{normalized_symbol}|{period}|{row_date}"[:191],
                    "asset_type": asset_type,
                    "symbol": normalized_symbol,
                    "name": _safe_str(_first_value(row, "name")) or name,
                    "market": market,
                    "period": period,
                    "date": row_date,
                    "open": _safe_float(_first_value(row, "open")),
                    "high": _safe_float(_first_value(row, "high")),
                    "low": _safe_float(_first_value(row, "low")),
                    "close": _safe_float(_first_value(row, "close")),
                    "price": _safe_float(_first_value(row, "price")),
                    "volume": _safe_int(_first_value(row, "volume")),
                    "turnover": _safe_float(_first_value(row, "turnover")),
                    "change_value": _safe_float(_first_value(row, "change")),
                    "change_pct": _safe_float(_first_value(row, "change_pct")),
                    "turnover_rate": _safe_float(_first_value(row, "turnover_rate")),
                    "open_interest": _safe_int(_first_value(row, "open_interest")),
                    "settle": _safe_float(_first_value(row, "settle")),
                    "strike": _safe_float(_first_value(row, "strike")),
                    "days_to_expiry": _safe_int(_first_value(row, "days_to_expiry")),
                    "provider": _ONLINE_PROVIDER,
                }
            )
        if not payloads:
            return None

        engine = _get_akshare_data_engine()
        if engine is None:
            return "AKSHARE_DATA_DATABASE_URL is not configured"

        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS MARKET_INSTRUMENT_HISTORY_CACHE (
                            R_ID VARCHAR(191) PRIMARY KEY,
                            asset_type VARCHAR(32) NOT NULL,
                            symbol VARCHAR(64) NOT NULL,
                            name VARCHAR(128) NULL,
                            market VARCHAR(32) NULL,
                            period VARCHAR(16) NOT NULL,
                            `date` VARCHAR(32) NOT NULL,
                            open DOUBLE NULL,
                            high DOUBLE NULL,
                            low DOUBLE NULL,
                            close DOUBLE NULL,
                            price DOUBLE NULL,
                            volume BIGINT NULL,
                            turnover DOUBLE NULL,
                            change_value DOUBLE NULL,
                            change_pct DOUBLE NULL,
                            turnover_rate DOUBLE NULL,
                            open_interest BIGINT NULL,
                            settle DOUBLE NULL,
                            strike DOUBLE NULL,
                            days_to_expiry INT NULL,
                            provider VARCHAR(64) NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            KEY idx_market_instrument_history_cache_lookup (
                                asset_type,
                                symbol,
                                period,
                                `date`
                            )
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                )
                await conn.execute(
                    text(
                        """
                        INSERT INTO MARKET_INSTRUMENT_HISTORY_CACHE (
                            R_ID,
                            asset_type,
                            symbol,
                            name,
                            market,
                            period,
                            `date`,
                            open,
                            high,
                            low,
                            close,
                            price,
                            volume,
                            turnover,
                            change_value,
                            change_pct,
                            turnover_rate,
                            open_interest,
                            settle,
                            strike,
                            days_to_expiry,
                            provider
                        ) VALUES (
                            :r_id,
                            :asset_type,
                            :symbol,
                            :name,
                            :market,
                            :period,
                            :date,
                            :open,
                            :high,
                            :low,
                            :close,
                            :price,
                            :volume,
                            :turnover,
                            :change_value,
                            :change_pct,
                            :turnover_rate,
                            :open_interest,
                            :settle,
                            :strike,
                            :days_to_expiry,
                            :provider
                        )
                        ON DUPLICATE KEY UPDATE
                            name = VALUES(name),
                            market = VALUES(market),
                            open = VALUES(open),
                            high = VALUES(high),
                            low = VALUES(low),
                            close = VALUES(close),
                            price = VALUES(price),
                            volume = VALUES(volume),
                            turnover = VALUES(turnover),
                            change_value = VALUES(change_value),
                            change_pct = VALUES(change_pct),
                            turnover_rate = VALUES(turnover_rate),
                            open_interest = VALUES(open_interest),
                            settle = VALUES(settle),
                            strike = VALUES(strike),
                            days_to_expiry = VALUES(days_to_expiry),
                            provider = VALUES(provider)
                        """
                    ),
                    payloads,
                )
        except Exception as exc:
            return str(exc)
        return None

    @staticmethod
    def _default_market(asset_type: MarketAssetType) -> str:
        return {
            "stock": "CN",
            "futures": "CN",
            "bond": "CN",
            "fund": "CN",
            "option": "CN",
            "fx": "FX",
            "crypto": "CRYPTO",
        }[asset_type]

    async def _fetch_rows(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        engine = _get_akshare_data_engine()
        if engine is None:
            raise RuntimeError("AKSHARE_DATA_DATABASE_URL is not configured")
        async with engine.connect() as conn:
            result = await conn.execute(text(sql), params or {})
            return [_coerce_row(dict(row)) for row in result.mappings().all()]

    async def _fetch_one(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        rows = await self._fetch_rows(sql, params)
        return rows[0] if rows else None

    async def _lookup_stock_warehouse(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        code = _normalize_plain_code(symbol)
        spot = await self._fetch_one(
            """
            SELECT *
            FROM STOCK_ZH_A_SPOT_EM
            WHERE symbol = :code OR `代码` = :code
            ORDER BY data_date DESC
            LIMIT 1
            """,
            {"code": code},
        )

        history_table = (
            "STOCK_ZH_A_HIST_TX"
            if code == "000001"
            else ("STOCK_ZH_A_DAILY" if code == "600000" else None)
        )
        history_rows: list[dict[str, Any]] = []
        if history_table:
            rows = await self._fetch_rows(
                f"""
                SELECT *
                FROM {history_table}
                WHERE STR_TO_DATE(`date`, '%Y-%m-%d') BETWEEN :start AND :end
                ORDER BY STR_TO_DATE(`date`, '%Y-%m-%d') ASC
                LIMIT 260
                """,
                {
                    "start": _sql_date_text(start_date, date.today()),
                    "end": _sql_date_text(end_date, date.today()),
                },
            )
            if not rows:
                rows = list(
                    reversed(
                        await self._fetch_rows(
                            f"""
                            SELECT *
                            FROM {history_table}
                            ORDER BY STR_TO_DATE(`date`, '%Y-%m-%d') DESC
                            LIMIT 120
                            """
                        )
                    )
                )
                if rows:
                    warnings.append("所选日期范围无股票历史数据，已展示 akshare_data 最近可用记录")
            history_rows = self._normalize_warehouse_history(
                rows,
                date_key="date",
                open_key="open",
                high_key="high",
                low_key="low",
                close_key="close",
                volume_key="volume",
                turnover_key="amount",
                turnover_rate_key="turnover",
            )

        if not history_rows:
            rows = await self._fetch_rows(
                """
                SELECT *
                FROM STOCK_ZH_A_HIST
                WHERE (symbol = :code OR `股票代码` = :code)
                  AND STR_TO_DATE(`日期`, '%Y-%m-%d') BETWEEN :start AND :end
                ORDER BY STR_TO_DATE(`日期`, '%Y-%m-%d') ASC
                LIMIT 260
                """,
                {
                    "code": code,
                    "start": _sql_date_text(start_date, date.today()),
                    "end": _sql_date_text(end_date, date.today()),
                },
            )
            history_rows = self._normalize_warehouse_history(
                rows,
                date_key="日期",
                open_key="开盘",
                high_key="最高",
                low_key="最低",
                close_key="收盘",
                volume_key="成交量",
                turnover_key="成交额",
                change_key="涨跌额",
                change_pct_key="涨跌幅",
                turnover_rate_key="换手率",
            )
            if history_rows:
                history_table = "STOCK_ZH_A_HIST"

        if spot is None and not history_rows:
            spot = await self._fetch_one(
                """
                SELECT *
                FROM STOCK_ZH_A_SPOT_EM
                WHERE `最新价` IS NOT NULL AND `最新价` <> 0
                ORDER BY data_date DESC, `成交额` DESC
                LIMIT 1
                """
            )
            if spot:
                code = _safe_str(_first_value(spot, "代码", "symbol")) or code
                warnings.append(f"akshare_data 未找到 {symbol}，已展示最新股票样例 {code}")

        snapshot = self._snapshot_from_cn_quote(spot or {}, symbol=code) if spot else {}
        snapshot = snapshot or self._snapshot_from_latest_history(code, history_rows)
        snapshot["data_source_table"] = (
            f"STOCK_ZH_A_SPOT_EM/{history_table}" if history_table else "STOCK_ZH_A_SPOT_EM"
        )
        return self._payload(
            asset_type="stock",
            symbol=code,
            name=snapshot.get("name") or code,
            market=market or "CN",
            snapshot=snapshot,
            rows=history_rows,
            period=period,
            provider=_WAREHOUSE_PROVIDER,
        )

    async def _lookup_futures_warehouse(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        requested = symbol.upper()
        rows = await self._fetch_rows(
            """
            SELECT *
            FROM FUTURES_DAILY_MARKET
            WHERE SYMBOL = :symbol
              AND TRADE_DATE BETWEEN :start AND :end
            ORDER BY TRADE_DATE ASC
            LIMIT 260
            """,
            {"symbol": requested, "start": start_date, "end": end_date},
        )
        if not rows:
            fallback = await self._fetch_one(
                """
                SELECT SYMBOL
                FROM FUTURES_DAILY_MARKET
                WHERE TRADE_DATE = (SELECT MAX(TRADE_DATE) FROM FUTURES_DAILY_MARKET)
                GROUP BY SYMBOL
                ORDER BY COUNT(*) DESC, SYMBOL ASC
                LIMIT 1
                """
            )
            if fallback:
                requested = str(fallback["SYMBOL"])
                warnings.append(f"akshare_data 未找到 {symbol}，已展示最新期货合约 {requested}")
                rows = await self._fetch_rows(
                    """
                    SELECT *
                    FROM FUTURES_DAILY_MARKET
                    WHERE SYMBOL = :symbol
                    ORDER BY TRADE_DATE ASC
                    LIMIT 260
                    """,
                    {"symbol": requested},
                )

        history_rows = self._normalize_warehouse_history(
            rows,
            date_key="TRADE_DATE",
            open_key="OPEN_PRICE",
            high_key="HIGH_PRICE",
            low_key="LOW_PRICE",
            close_key="CLOSE_PRICE",
            volume_key="VOLUME",
            turnover_key="TURNOVER",
            settle_key="SETTLE_PRICE",
            open_interest_key="OPEN_INTEREST",
        )
        snapshot = self._snapshot_from_latest_history(requested, history_rows)
        latest_raw = rows[-1] if rows else {}
        snapshot.update(
            {
                "name": requested,
                "settle": _safe_float(_first_value(latest_raw, "SETTLE_PRICE")),
                "previous_settle": _safe_float(_first_value(latest_raw, "PREV_SETTLE")),
                "open_interest": _safe_int(_first_value(latest_raw, "OPEN_INTEREST")),
                "turnover": _safe_float(_first_value(latest_raw, "TURNOVER")),
                "data_source_table": "FUTURES_DAILY_MARKET",
            }
        )
        return self._payload(
            asset_type="futures",
            symbol=requested,
            name=requested,
            market=market or _safe_str(_first_value(latest_raw, "MARKET")) or "CN",
            snapshot=snapshot,
            rows=history_rows,
            period=period,
            provider=_WAREHOUSE_PROVIDER,
        )

    async def _lookup_bond_warehouse(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        exchange_symbol = _normalize_exchange_symbol(symbol, default_prefix="sh")
        plain_code = exchange_symbol[2:]
        spot = await self._fetch_one(
            """
            SELECT *
            FROM BOND_ZH_HS_COV_SPOT
            WHERE LOWER(symbol) = :symbol OR code = :code
            ORDER BY data_date DESC
            LIMIT 1
            """,
            {"symbol": exchange_symbol.lower(), "code": plain_code},
        )
        rows = await self._fetch_rows(
            """
            SELECT *
            FROM BOND_ZH_HS_COV_MIN
            WHERE LOWER(symbol) = :symbol
            ORDER BY `时间` ASC
            LIMIT 260
            """,
            {"symbol": exchange_symbol.lower()},
        )
        if not rows and spot is None:
            fallback = await self._fetch_one(
                """
                SELECT symbol
                FROM BOND_ZH_HS_COV_MIN
                WHERE symbol IS NOT NULL
                GROUP BY symbol
                ORDER BY MAX(data_date) DESC, COUNT(*) DESC
                LIMIT 1
                """
            )
            if fallback:
                exchange_symbol = str(fallback["symbol"])
                plain_code = exchange_symbol[2:]
                warnings.append(
                    f"akshare_data 未找到 {symbol}，已展示最新可转债样例 {exchange_symbol}"
                )
                rows = await self._fetch_rows(
                    """
                    SELECT *
                    FROM BOND_ZH_HS_COV_MIN
                    WHERE LOWER(symbol) = :symbol
                    ORDER BY `时间` ASC
                    LIMIT 260
                    """,
                    {"symbol": exchange_symbol.lower()},
                )
        history_rows = self._normalize_warehouse_history(
            rows,
            date_key="时间",
            open_key="开盘",
            high_key="最高",
            low_key="最低",
            close_key="收盘",
            volume_key="成交量",
            turnover_key="成交额",
        )
        if spot:
            snapshot = {
                "symbol": exchange_symbol,
                "name": _safe_str(_first_value(spot, "name", "code")) or exchange_symbol,
                "price": _safe_float(_first_value(spot, "trade")),
                "change": _safe_float(_first_value(spot, "pricechange")),
                "change_pct": _safe_float(_first_value(spot, "changepercent")),
                "open": _safe_float(_first_value(spot, "open")),
                "high": _safe_float(_first_value(spot, "high")),
                "low": _safe_float(_first_value(spot, "low")),
                "previous_close": _safe_float(_first_value(spot, "settlement")),
                "bid": _safe_float(_first_value(spot, "buy")),
                "ask": _safe_float(_first_value(spot, "sell")),
                "volume": _safe_int(_first_value(spot, "volume")),
                "turnover": _safe_float(_first_value(spot, "amount")),
                "update_time": _safe_str(_first_value(spot, "ticktime", "data_date")),
                "data_source_table": "BOND_ZH_HS_COV_SPOT",
            }
        else:
            snapshot = self._snapshot_from_latest_history(exchange_symbol, history_rows)
            snapshot["data_source_table"] = "BOND_ZH_HS_COV_MIN"
        return self._payload(
            asset_type="bond",
            symbol=exchange_symbol,
            name=snapshot.get("name") or plain_code,
            market=market or "CN",
            snapshot=snapshot,
            rows=history_rows,
            period=period,
            provider=_WAREHOUSE_PROVIDER,
        )

    async def _lookup_fund_warehouse(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        code = _normalize_plain_code(symbol)
        spot = await self._fetch_one(
            """
            SELECT *
            FROM ETF_REALTIME_QUOTE_EM
            WHERE ETF_CODE = :code
            ORDER BY QUOTE_DATE DESC
            LIMIT 1
            """,
            {"code": code},
        )
        if spot is None:
            spot = await self._fetch_one(
                """
                SELECT *
                FROM ETF_REALTIME_QUOTE_EM
                WHERE LATEST_PRICE IS NOT NULL AND LATEST_PRICE <> 0
                ORDER BY QUOTE_DATE DESC, TURNOVER DESC
                LIMIT 1
                """
            )
            if spot:
                code = str(spot["ETF_CODE"])
                warnings.append(f"akshare_data 未找到 {symbol}，已展示最新 ETF 样例 {code}")

        rows: list[dict[str, Any]] = []
        if code == "510300":
            rows = await self._fetch_rows(
                """
                SELECT *
                FROM FUND_ETF_HIST_SINA
                WHERE STR_TO_DATE(`date`, '%Y-%m-%d') BETWEEN :start AND :end
                ORDER BY STR_TO_DATE(`date`, '%Y-%m-%d') ASC
                LIMIT 260
                """,
                {
                    "start": _sql_date_text(start_date, date.today()),
                    "end": _sql_date_text(end_date, date.today()),
                },
            )
            if not rows:
                rows = list(
                    reversed(
                        await self._fetch_rows(
                            """
                            SELECT *
                            FROM FUND_ETF_HIST_SINA
                            ORDER BY STR_TO_DATE(`date`, '%Y-%m-%d') DESC
                            LIMIT 120
                            """
                        )
                    )
                )
                if rows:
                    warnings.append("所选日期范围无基金历史数据，已展示 akshare_data 最近可用记录")
        else:
            nav_rows = await self._fetch_rows(
                """
                SELECT *
                FROM ETF_FUND_HIST_EM
                WHERE FUND_CODE = :code
                ORDER BY VALUE_DATE ASC
                LIMIT 260
                """,
                {"code": code},
            )
            rows = [
                {
                    "date": row.get("VALUE_DATE"),
                    "open": row.get("UNIT_NET_VALUE"),
                    "high": row.get("UNIT_NET_VALUE"),
                    "low": row.get("UNIT_NET_VALUE"),
                    "close": row.get("UNIT_NET_VALUE"),
                    "change_pct": row.get("DAILY_GROWTH_RATE"),
                }
                for row in nav_rows
            ]

        history_rows = self._normalize_warehouse_history(
            rows,
            date_key="date",
            open_key="open",
            high_key="high",
            low_key="low",
            close_key="close",
            volume_key="volume",
            turnover_key="amount",
        )
        if spot:
            snapshot = {
                "symbol": code,
                "name": _safe_str(_first_value(spot, "ETF_NAME")) or code,
                "price": _safe_float(_first_value(spot, "LATEST_PRICE")),
                "change": _safe_float(_first_value(spot, "CHANGE_AMOUNT")),
                "change_pct": _safe_float(_first_value(spot, "CHANGE_PERCENT")),
                "open": _safe_float(_first_value(spot, "OPEN_PRICE")),
                "high": _safe_float(_first_value(spot, "HIGH_PRICE")),
                "low": _safe_float(_first_value(spot, "LOW_PRICE")),
                "previous_close": _safe_float(_first_value(spot, "PREV_CLOSE")),
                "volume": _safe_int(_first_value(spot, "VOLUME")),
                "turnover": _safe_float(_first_value(spot, "TURNOVER")),
                "turnover_rate": _safe_float(_first_value(spot, "TURNOVER_RATE")),
                "market_cap": _safe_float(_first_value(spot, "TOTAL_MARKET_CAP")),
                "float_market_cap": _safe_float(_first_value(spot, "CIRC_MARKET_CAP")),
                "bid": _safe_float(_first_value(spot, "BID_PRICE")),
                "ask": _safe_float(_first_value(spot, "ASK_PRICE")),
                "update_time": _safe_str(_first_value(spot, "UPDATE_TIME", "QUOTE_DATE")),
                "data_source_table": "ETF_REALTIME_QUOTE_EM",
            }
        else:
            snapshot = self._snapshot_from_latest_history(code, history_rows)
        return self._payload(
            asset_type="fund",
            symbol=code,
            name=snapshot.get("name") or code,
            market=market or "CN",
            snapshot=snapshot,
            rows=history_rows,
            period=period,
            provider=_WAREHOUSE_PROVIDER,
        )

    async def _lookup_option_warehouse(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        normalized = symbol.upper()
        current = await self._fetch_one(
            """
            SELECT *
            FROM OPTION_CURRENT_EM
            WHERE UPPER(symbol) = :symbol OR UPPER(`代码`) = :symbol
            ORDER BY data_date DESC
            LIMIT 1
            """,
            {"symbol": normalized},
        )
        if current is None:
            current = await self._fetch_one(
                """
                SELECT *
                FROM OPTION_CURRENT_EM
                WHERE `最新价` IS NOT NULL
                ORDER BY data_date DESC, `成交量` DESC
                LIMIT 1
                """
            )
            if current:
                normalized = str(_first_value(current, "symbol", "代码") or normalized)
                warnings.append(f"akshare_data 未找到 {symbol}，已展示最新期权样例 {normalized}")

        latest_date_row = await self._fetch_one(
            "SELECT MAX(data_date) AS latest_date FROM OPTION_CURRENT_EM"
        )
        latest_date = latest_date_row.get("latest_date") if latest_date_row else None
        rows = (
            await self._fetch_rows(
                """
            SELECT *
            FROM OPTION_CURRENT_EM
            WHERE data_date = :latest_date
            ORDER BY `成交量` DESC, `持仓量` DESC
            LIMIT 80
            """,
                {"latest_date": latest_date},
            )
            if latest_date
            else []
        )
        history_rows = [
            {
                "date": _iso_date(_first_value(row, "data_date")),
                "name": _safe_str(_first_value(row, "名称", "name", "代码", "symbol")),
                "price": _safe_float(_first_value(row, "最新价")),
                "volume": _safe_int(_first_value(row, "成交量")),
                "turnover": _safe_float(_first_value(row, "成交额")),
                "open_interest": _safe_int(_first_value(row, "持仓量")),
                "change": _safe_float(_first_value(row, "涨跌额", "日增")),
                "change_pct": _safe_float(_first_value(row, "涨跌幅")),
                "strike": _safe_float(_first_value(row, "行权价")),
                "days_to_expiry": _safe_int(_first_value(row, "剩余日")),
            }
            for row in rows
        ]
        snapshot = {
            "symbol": normalized,
            "name": _safe_str(_first_value(current or {}, "名称", "name", "代码", "symbol"))
            or normalized,
            "price": _safe_float(_first_value(current or {}, "最新价")),
            "change": _safe_float(_first_value(current or {}, "涨跌额")),
            "change_pct": _safe_float(_first_value(current or {}, "涨跌幅")),
            "open": _safe_float(_first_value(current or {}, "今开")),
            "previous_settle": _safe_float(_first_value(current or {}, "昨结")),
            "volume": _safe_int(_first_value(current or {}, "成交量")),
            "turnover": _safe_float(_first_value(current or {}, "成交额")),
            "open_interest": _safe_int(_first_value(current or {}, "持仓量")),
            "strike": _safe_float(_first_value(current or {}, "行权价")),
            "days_to_expiry": _safe_int(_first_value(current or {}, "剩余日")),
            "update_time": _safe_str(_first_value(current or {}, "data_date")),
            "data_source_table": "OPTION_CURRENT_EM",
        }
        return self._payload(
            asset_type="option",
            symbol=normalized,
            name=snapshot.get("name") or normalized,
            market=market or "CN",
            snapshot=snapshot,
            rows=history_rows,
            period=period,
            provider=_WAREHOUSE_PROVIDER,
        )

    async def _lookup_fx_warehouse(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        normalized = symbol.upper()
        spot = await self._fetch_one(
            """
            SELECT *
            FROM FOREX_SPOT_EM
            WHERE UPPER(`代码`) = :symbol OR UPPER(symbol) = :symbol
            ORDER BY data_date DESC
            LIMIT 1
            """,
            {"symbol": normalized},
        )
        if spot is None:
            spot = await self._fetch_one(
                """
                SELECT *
                FROM FOREX_SPOT_EM
                WHERE `最新价` IS NOT NULL
                ORDER BY data_date DESC, ABS(`涨跌幅`) DESC
                LIMIT 1
                """
            )
            if spot:
                normalized = str(_first_value(spot, "代码", "symbol") or normalized)
                warnings.append(f"akshare_data 未找到 {symbol}，已展示最新外汇样例 {normalized}")

        currency_column = self._fx_history_column(normalized)
        rows = await self._fetch_rows(
            f"""
            SELECT `日期` AS date, `{currency_column}` AS close
            FROM CURRENCY_BOC_SAFE
            WHERE STR_TO_DATE(`日期`, '%Y-%m-%d') BETWEEN :start AND :end
            ORDER BY STR_TO_DATE(`日期`, '%Y-%m-%d') ASC
            LIMIT 260
            """,
            {
                "start": _sql_date_text(start_date, date.today()),
                "end": _sql_date_text(end_date, date.today()),
            },
        )
        if not rows:
            rows = list(
                reversed(
                    await self._fetch_rows(
                        f"""
                        SELECT `日期` AS date, `{currency_column}` AS close
                        FROM CURRENCY_BOC_SAFE
                        ORDER BY STR_TO_DATE(`日期`, '%Y-%m-%d') DESC
                        LIMIT 120
                        """
                    )
                )
            )
            if rows:
                warnings.append("所选日期范围无外汇历史数据，已展示 akshare_data 最近可用记录")
        history_rows = self._normalize_fx_history(rows)
        snapshot = {
            "symbol": normalized,
            "name": _safe_str(_first_value(spot or {}, "名称", "name", "代码")) or normalized,
            "price": _safe_float(_first_value(spot or {}, "最新价")),
            "change": _safe_float(_first_value(spot or {}, "涨跌额")),
            "change_pct": _safe_float(_first_value(spot or {}, "涨跌幅")),
            "open": _safe_float(_first_value(spot or {}, "今开")),
            "high": _safe_float(_first_value(spot or {}, "最高")),
            "low": _safe_float(_first_value(spot or {}, "最低")),
            "previous_close": _safe_float(_first_value(spot or {}, "昨收")),
            "update_time": _safe_str(_first_value(spot or {}, "data_date")),
            "history_currency": currency_column,
            "data_source_table": "FOREX_SPOT_EM/CURRENCY_BOC_SAFE",
        }
        snapshot = snapshot or self._snapshot_from_latest_history(normalized, history_rows)
        return self._payload(
            asset_type="fx",
            symbol=normalized,
            name=snapshot.get("name") or normalized,
            market=market or "FX",
            snapshot=snapshot,
            rows=history_rows,
            period=period,
            provider=_WAREHOUSE_PROVIDER,
        )

    async def _lookup_crypto_warehouse(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        normalized = symbol.upper()
        spot = await self._fetch_one(
            """
            SELECT *
            FROM CRYPTO_JS_SPOT
            WHERE UPPER(`交易品种`) = :symbol
            ORDER BY data_date DESC
            LIMIT 1
            """,
            {"symbol": normalized},
        )
        if spot is None:
            spot = await self._fetch_one(
                """
                SELECT *
                FROM CRYPTO_JS_SPOT
                WHERE `最近报价` IS NOT NULL AND `最近报价` <> 0
                ORDER BY data_date DESC, `24小时成交量` DESC
                LIMIT 1
                """
            )
            if spot:
                normalized = str(_first_value(spot, "交易品种") or normalized)
                warnings.append(
                    f"akshare_data 未找到 {symbol}，已展示最新数字货币样例 {normalized}"
                )

        latest_date_row = await self._fetch_one(
            "SELECT MAX(data_date) AS latest_date FROM CRYPTO_BITCOIN_CME"
        )
        latest_date = latest_date_row.get("latest_date") if latest_date_row else None
        cme_rows = (
            await self._fetch_rows(
                """
            SELECT *
            FROM CRYPTO_BITCOIN_CME
            WHERE data_date = :latest_date
            ORDER BY `未平仓合约` DESC
            LIMIT 20
            """,
                {"latest_date": latest_date},
            )
            if latest_date
            else []
        )
        history_rows = self._normalize_crypto_cme_rows(
            pd.DataFrame(cme_rows), latest_date or date.today()
        )
        snapshot = {
            "symbol": normalized,
            "name": _safe_str(_first_value(spot or {}, "交易品种")) or normalized,
            "price": _safe_float(_first_value(spot or {}, "最近报价")),
            "change": _safe_float(_first_value(spot or {}, "涨跌额")),
            "change_pct": _safe_float(_first_value(spot or {}, "涨跌幅")),
            "high": _safe_float(_first_value(spot or {}, "24小时最高")),
            "low": _safe_float(_first_value(spot or {}, "24小时最低")),
            "volume": _safe_float(_first_value(spot or {}, "24小时成交量")),
            "market": _safe_str(_first_value(spot or {}, "市场")),
            "update_time": _safe_str(_first_value(spot or {}, "更新时间", "data_date")),
            "data_source_table": "CRYPTO_JS_SPOT/CRYPTO_BITCOIN_CME",
        }
        return self._payload(
            asset_type="crypto",
            symbol=normalized,
            name=snapshot.get("name") or normalized,
            market=market or _safe_str(snapshot.get("market")) or "CRYPTO",
            snapshot=snapshot,
            rows=history_rows,
            period=period,
            provider=_WAREHOUSE_PROVIDER,
        )

    @staticmethod
    def _normalize_warehouse_history(
        rows: list[dict[str, Any]],
        *,
        date_key: str,
        open_key: str | None = None,
        high_key: str | None = None,
        low_key: str | None = None,
        close_key: str | None = None,
        volume_key: str | None = None,
        turnover_key: str | None = None,
        change_key: str | None = None,
        change_pct_key: str | None = None,
        turnover_rate_key: str | None = None,
        open_interest_key: str | None = None,
        settle_key: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_rows: list[dict[str, Any]] = []
        previous_close: float | None = None
        for row in rows:
            close_value = _safe_float(_first_value(row, close_key)) if close_key else None
            change_pct = _safe_float(_first_value(row, change_pct_key)) if change_pct_key else None
            if change_pct is None and previous_close and close_value is not None:
                change_pct = ((close_value / previous_close) - 1) * 100
            normalized_rows.append(
                {
                    "date": _iso_date(_first_value(row, date_key)),
                    "open": _safe_float(_first_value(row, open_key)) if open_key else close_value,
                    "high": _safe_float(_first_value(row, high_key)) if high_key else close_value,
                    "low": _safe_float(_first_value(row, low_key)) if low_key else close_value,
                    "close": close_value,
                    "volume": _safe_int(_first_value(row, volume_key)) if volume_key else None,
                    "turnover": _safe_float(_first_value(row, turnover_key))
                    if turnover_key
                    else None,
                    "change": _safe_float(_first_value(row, change_key)) if change_key else None,
                    "change_pct": change_pct,
                    "turnover_rate": _safe_float(_first_value(row, turnover_rate_key))
                    if turnover_rate_key
                    else None,
                    "open_interest": _safe_int(_first_value(row, open_interest_key))
                    if open_interest_key
                    else None,
                    "settle": _safe_float(_first_value(row, settle_key)) if settle_key else None,
                }
            )
            if close_value is not None:
                previous_close = close_value
        return normalized_rows

    @staticmethod
    def _normalize_fx_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_rows: list[dict[str, Any]] = []
        previous_close: float | None = None
        for row in rows:
            close_value = _safe_float(_first_value(row, "close"))
            change_pct = None
            if previous_close and close_value is not None:
                change_pct = ((close_value / previous_close) - 1) * 100
            normalized_rows.append(
                {
                    "date": _iso_date(_first_value(row, "date")),
                    "open": previous_close or close_value,
                    "high": close_value,
                    "low": close_value,
                    "close": close_value,
                    "change_pct": change_pct,
                }
            )
            if close_value is not None:
                previous_close = close_value
        return normalized_rows

    @staticmethod
    def _fx_history_column(symbol: str) -> str:
        upper_symbol = symbol.upper()
        column_by_currency = {
            "USD": "美元",
            "EUR": "欧元",
            "JPY": "日元",
            "HKD": "港元",
            "GBP": "英镑",
            "AUD": "澳元",
            "NZD": "新西兰元",
            "SGD": "新加坡元",
            "CHF": "瑞士法郎",
            "CAD": "加元",
        }
        for currency, column in column_by_currency.items():
            if upper_symbol.startswith(currency) or upper_symbol.endswith(currency):
                return column
        return "美元"

    def _lookup_stock(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        import akshare as ak

        code = _normalize_plain_code(symbol)
        snapshot: dict[str, Any] = {}
        history_rows: list[dict[str, Any]] = []

        try:
            spot_df = ak.stock_zh_a_spot_em()
            matched = spot_df[spot_df["代码"].astype(str) == code]
            if not matched.empty:
                snapshot = self._snapshot_from_cn_quote(matched.iloc[0].to_dict(), symbol=symbol)
            else:
                warnings.append(f"未在 A 股实时快照中找到 {symbol}")
        except Exception as exc:
            warnings.append(f"A 股实时快照不可用: {exc}")

        try:
            history_df = ak.stock_zh_a_hist(
                symbol=code,
                period=period,
                start_date=_date_text(start_date, date.today() - timedelta(days=90)),
                end_date=_date_text(end_date, date.today()),
                adjust="qfq",
                timeout=10,
            )
            history_rows = self._normalize_cn_ohlcv_history(history_df)
        except Exception as exc:
            warnings.append(f"A 股历史行情不可用: {exc}")

        snapshot = snapshot or self._snapshot_from_latest_history(symbol, history_rows)
        return self._payload(
            asset_type="stock",
            symbol=symbol,
            name=snapshot.get("name") or symbol,
            market=market or "CN",
            snapshot=snapshot,
            rows=history_rows,
            period=period,
        )

    def _lookup_futures(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        import akshare as ak

        normalized_market = (market or "CF").strip().upper()
        snapshot: dict[str, Any] = {}
        history_rows: list[dict[str, Any]] = []

        try:
            spot_df = ak.futures_zh_spot(symbol=symbol, market=normalized_market, adjust="0")
            if not spot_df.empty:
                row = spot_df.iloc[0].to_dict()
                snapshot = {
                    "symbol": symbol,
                    "name": _safe_str(row.get("symbol")) or symbol,
                    "price": _safe_float(row.get("current_price")),
                    "open": _safe_float(row.get("open")),
                    "high": _safe_float(row.get("high")),
                    "low": _safe_float(row.get("low")),
                    "previous_close": _safe_float(row.get("last_close")),
                    "settle": _safe_float(row.get("avg_price")),
                    "previous_settle": _safe_float(row.get("last_settle_price")),
                    "bid": _safe_float(row.get("bid_price")),
                    "ask": _safe_float(row.get("ask_price")),
                    "volume": _safe_int(row.get("volume")),
                    "open_interest": _safe_int(row.get("hold")),
                    "update_time": _safe_str(row.get("time")),
                }
        except Exception as exc:
            warnings.append(f"期货实时快照不可用: {exc}")

        try:
            history_df = ak.futures_zh_daily_sina(symbol=symbol)
            history_rows = self._normalize_generic_ohlcv_history(history_df, start_date, end_date)
        except Exception as exc:
            warnings.append(f"期货历史行情不可用: {exc}")

        snapshot = snapshot or self._snapshot_from_latest_history(symbol, history_rows)
        return self._payload(
            asset_type="futures",
            symbol=symbol,
            name=snapshot.get("name") or symbol,
            market=normalized_market,
            snapshot=snapshot,
            rows=history_rows,
            period=period,
        )

    def _lookup_bond(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        import akshare as ak

        exchange_symbol = _normalize_exchange_symbol(symbol)
        plain_code = exchange_symbol[2:]
        snapshot: dict[str, Any] = {}
        history_rows: list[dict[str, Any]] = []

        try:
            spot_df = ak.bond_zh_hs_cov_spot()
            matched = spot_df[
                (spot_df["symbol"].astype(str).str.lower() == exchange_symbol)
                | (spot_df["code"].astype(str) == plain_code)
            ]
            if not matched.empty:
                row = matched.iloc[0].to_dict()
                snapshot = {
                    "symbol": exchange_symbol,
                    "name": _safe_str(row.get("name")) or exchange_symbol,
                    "price": _safe_float(row.get("trade")),
                    "change": _safe_float(row.get("pricechange")),
                    "change_pct": _safe_float(row.get("changepercent")),
                    "open": _safe_float(row.get("open")),
                    "high": _safe_float(row.get("high")),
                    "low": _safe_float(row.get("low")),
                    "previous_close": _safe_float(row.get("settlement")),
                    "bid": _safe_float(row.get("buy")),
                    "ask": _safe_float(row.get("sell")),
                    "volume": _safe_int(row.get("volume")),
                    "turnover": _safe_float(row.get("amount")),
                    "update_time": _safe_str(row.get("ticktime")),
                }
            else:
                warnings.append(f"未在可转债实时快照中找到 {symbol}")
        except Exception as exc:
            warnings.append(f"债券实时快照不可用: {exc}")

        try:
            history_df = ak.bond_zh_hs_cov_daily(symbol=exchange_symbol)
            history_rows = self._normalize_generic_ohlcv_history(history_df, start_date, end_date)
        except Exception as exc:
            warnings.append(f"债券历史行情不可用: {exc}")

        snapshot = snapshot or self._snapshot_from_latest_history(exchange_symbol, history_rows)
        return self._payload(
            asset_type="bond",
            symbol=exchange_symbol,
            name=snapshot.get("name") or exchange_symbol,
            market=market or "CN",
            snapshot=snapshot,
            rows=history_rows,
            period=period,
        )

    def _lookup_fund(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        import akshare as ak

        code = _normalize_plain_code(symbol)
        snapshot: dict[str, Any] = {}
        history_rows: list[dict[str, Any]] = []

        try:
            spot_df = ak.fund_etf_spot_em()
            matched = spot_df[spot_df["代码"].astype(str) == code]
            if not matched.empty:
                snapshot = self._snapshot_from_cn_quote(matched.iloc[0].to_dict(), symbol=code)
            else:
                warnings.append(f"未在 ETF 实时快照中找到 {symbol}")
        except Exception as exc:
            warnings.append(f"基金实时快照不可用: {exc}")

        try:
            history_df = ak.fund_etf_hist_em(
                symbol=code,
                period=period,
                start_date=_date_text(start_date, date.today() - timedelta(days=90)),
                end_date=_date_text(end_date, date.today()),
                adjust="qfq",
            )
            history_rows = self._normalize_cn_ohlcv_history(history_df)
        except Exception as exc:
            warnings.append(f"基金历史行情不可用: {exc}")

        snapshot = snapshot or self._snapshot_from_latest_history(code, history_rows)
        return self._payload(
            asset_type="fund",
            symbol=code,
            name=snapshot.get("name") or code,
            market=market or "CN",
            snapshot=snapshot,
            rows=history_rows,
            period=period,
        )

    def _lookup_option(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        import akshare as ak

        history_rows: list[dict[str, Any]] = []
        try:
            if symbol.lower().startswith("io"):
                history_df = ak.option_cffex_hs300_daily_sina(symbol=symbol)
            else:
                history_df = ak.option_sse_daily_sina(symbol=symbol)
            history_rows = self._normalize_generic_ohlcv_history(history_df, start_date, end_date)
        except Exception as exc:
            warnings.append(f"期权历史行情不可用: {exc}")

        snapshot = self._snapshot_from_latest_history(symbol, history_rows)
        return self._payload(
            asset_type="option",
            symbol=symbol,
            name=symbol,
            market=market or "CN",
            snapshot=snapshot,
            rows=history_rows,
            period=period,
        )

    def _lookup_fx(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        import akshare as ak

        snapshot: dict[str, Any] = {}
        history_rows: list[dict[str, Any]] = []

        try:
            spot_df = ak.forex_spot_em()
            matched = self._match_any(spot_df, symbol, ["代码", "名称", "货币对", "symbol"])
            if not matched.empty:
                row = matched.iloc[0].to_dict()
                snapshot = {
                    "symbol": symbol,
                    "name": _safe_str(_first_present(row, "名称", "货币对", "代码")) or symbol,
                    "price": _safe_float(_first_present(row, "最新价", "最新", "price", "close")),
                    "change": _safe_float(_first_present(row, "涨跌额", "change")),
                    "change_pct": _safe_float(_first_present(row, "涨跌幅", "change_pct")),
                    "open": _safe_float(_first_present(row, "今开", "开盘", "open")),
                    "high": _safe_float(_first_present(row, "最高", "high")),
                    "low": _safe_float(_first_present(row, "最低", "low")),
                    "previous_close": _safe_float(_first_present(row, "昨收", "previous_close")),
                    "update_time": _safe_str(
                        _first_present(row, "更新时间", "时间", "update_time")
                    ),
                }
        except Exception as exc:
            warnings.append(f"外汇实时快照不可用: {exc}")

        try:
            history_df = ak.forex_hist_em(symbol=symbol)
            history_rows = self._normalize_generic_ohlcv_history(history_df, start_date, end_date)
        except Exception as exc:
            warnings.append(f"外汇历史行情不可用: {exc}")

        snapshot = snapshot or self._snapshot_from_latest_history(symbol, history_rows)
        return self._payload(
            asset_type="fx",
            symbol=symbol,
            name=snapshot.get("name") or symbol,
            market=market or "FX",
            snapshot=snapshot,
            rows=history_rows,
            period=period,
        )

    def _lookup_crypto(
        self,
        *,
        symbol: str,
        start_date: date | str,
        end_date: date | str,
        period: str,
        market: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        import akshare as ak

        snapshot: dict[str, Any] = {}
        history_rows: list[dict[str, Any]] = []

        try:
            spot_df = ak.crypto_js_spot()
            matched = self._match_any(spot_df, symbol, ["交易品种"])
            if not matched.empty:
                row = matched.iloc[0].to_dict()
                snapshot = {
                    "symbol": symbol,
                    "name": _safe_str(row.get("交易品种")) or symbol,
                    "price": _safe_float(row.get("最近报价")),
                    "change": _safe_float(row.get("涨跌额")),
                    "change_pct": _safe_float(row.get("涨跌幅")),
                    "high": _safe_float(row.get("24小时最高")),
                    "low": _safe_float(row.get("24小时最低")),
                    "volume": _safe_float(row.get("24小时成交量")),
                    "market": _safe_str(row.get("市场")),
                    "update_time": _safe_str(row.get("更新时间")),
                }
            else:
                warnings.append(f"未在数字货币实时快照中找到 {symbol}")
        except Exception as exc:
            warnings.append(f"数字货币实时快照不可用: {exc}")

        try:
            cme_df = ak.crypto_bitcoin_cme(date=_date_text(end_date, date.today()))
            history_rows = self._normalize_crypto_cme_rows(cme_df, end_date)
        except Exception as exc:
            warnings.append(f"数字货币 CME 持仓数据不可用: {exc}")

        return self._payload(
            asset_type="crypto",
            symbol=symbol,
            name=snapshot.get("name") or symbol,
            market=market or _safe_str(snapshot.get("market")) or "CRYPTO",
            snapshot=snapshot,
            rows=history_rows,
            period=period,
        )

    def _snapshot_from_cn_quote(self, row: dict[str, Any], *, symbol: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "name": _safe_str(_first_present(row, "名称", "name")) or symbol,
            "price": _safe_float(_first_present(row, "最新价", "收盘", "price")),
            "change": _safe_float(_first_present(row, "涨跌额", "change")),
            "change_pct": _safe_float(_first_present(row, "涨跌幅", "change_pct")),
            "open": _safe_float(_first_present(row, "今开", "开盘价", "开盘", "open")),
            "high": _safe_float(_first_present(row, "最高价", "最高", "high")),
            "low": _safe_float(_first_present(row, "最低价", "最低", "low")),
            "previous_close": _safe_float(_first_present(row, "昨收", "previous_close")),
            "volume": _safe_int(_first_present(row, "成交量", "volume")),
            "turnover": _safe_float(_first_present(row, "成交额", "turnover")),
            "market_cap": _safe_float(_first_present(row, "总市值")),
            "float_market_cap": _safe_float(_first_present(row, "流通市值")),
            "pe": _safe_float(_first_present(row, "市盈率-动态", "市盈率")),
            "pb": _safe_float(_first_present(row, "市净率")),
            "update_time": _safe_str(_first_present(row, "更新时间", "数据日期"))
            or datetime.now().isoformat(),
        }

    def _snapshot_from_latest_history(
        self,
        symbol: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not rows:
            return {"symbol": symbol, "name": symbol}
        latest = rows[-1]
        return {
            "symbol": symbol,
            "name": symbol,
            "price": latest.get("close"),
            "change_pct": latest.get("change_pct"),
            "open": latest.get("open"),
            "high": latest.get("high"),
            "low": latest.get("low"),
            "volume": latest.get("volume"),
            "turnover": latest.get("turnover"),
            "open_interest": latest.get("open_interest"),
            "settle": latest.get("settle"),
            "update_time": latest.get("date"),
        }

    def _payload(
        self,
        *,
        asset_type: MarketAssetType,
        symbol: str,
        name: str,
        market: str,
        snapshot: dict[str, Any],
        rows: list[dict[str, Any]],
        period: str,
        provider: str = _ONLINE_PROVIDER,
    ) -> dict[str, Any]:
        return {
            "asset_type": asset_type,
            "symbol": symbol,
            "name": name,
            "market": market,
            "provider": provider,
            "snapshot": snapshot,
            "history": {
                "period": period,
                "rows": rows,
                "total": len(rows),
            },
        }

    def _match_any(self, df: pd.DataFrame, symbol: str, columns: list[str]) -> pd.DataFrame:
        if df.empty:
            return df
        normalized = symbol.upper()
        mask = pd.Series(False, index=df.index)
        for column in columns:
            if column in df.columns:
                mask = mask | (df[column].astype(str).str.upper() == normalized)
        return df[mask]

    def _normalize_cn_ohlcv_history(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        return self._normalize_generic_ohlcv_history(
            df.rename(
                columns={
                    "日期": "date",
                    "开盘": "open",
                    "最高": "high",
                    "最低": "low",
                    "收盘": "close",
                    "成交量": "volume",
                    "成交额": "turnover",
                    "振幅": "amplitude",
                    "涨跌幅": "change_pct",
                    "涨跌额": "change",
                    "换手率": "turnover_rate",
                }
            ),
            start_date=None,
            end_date=None,
        )

    def _normalize_generic_ohlcv_history(
        self,
        df: pd.DataFrame,
        start_date: date | str | None,
        end_date: date | str | None,
    ) -> list[dict[str, Any]]:
        if df.empty:
            return []
        normalized = df.rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "turnover",
                "涨跌幅": "change_pct",
                "涨跌额": "change",
                "持仓": "open_interest",
                "hold": "open_interest",
                "settle": "settle",
            }
        ).copy()
        if "date" not in normalized.columns:
            return []
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        if start_date is not None:
            start = pd.to_datetime(_date_text(start_date, date.today() - timedelta(days=90)))
            normalized = normalized[normalized["date"] >= start]
        if end_date is not None:
            end = pd.to_datetime(_date_text(end_date, date.today()))
            normalized = normalized[normalized["date"] <= end]
        rows: list[dict[str, Any]] = []
        for _, row in normalized.iterrows():
            rows.append(
                {
                    "date": _iso_date(row.get("date")),
                    "open": _safe_float(row.get("open")),
                    "high": _safe_float(row.get("high")),
                    "low": _safe_float(row.get("low")),
                    "close": _safe_float(row.get("close")),
                    "volume": _safe_int(row.get("volume")),
                    "turnover": _safe_float(row.get("turnover")),
                    "change": _safe_float(row.get("change")),
                    "change_pct": _safe_float(row.get("change_pct")),
                    "turnover_rate": _safe_float(row.get("turnover_rate")),
                    "open_interest": _safe_int(row.get("open_interest")),
                    "settle": _safe_float(row.get("settle")),
                }
            )
        return rows

    def _normalize_crypto_cme_rows(
        self,
        df: pd.DataFrame,
        value_date: date | str,
    ) -> list[dict[str, Any]]:
        if df.empty:
            return []
        rows: list[dict[str, Any]] = []
        day = _iso_date(value_date)
        for _, row in df.iterrows():
            rows.append(
                {
                    "date": day,
                    "name": _safe_str(row.get("类型")) or _safe_str(row.get("商品")),
                    "volume": _safe_int(row.get("成交量")),
                    "open_interest": _safe_int(row.get("未平仓合约")),
                    "change": _safe_float(row.get("持仓变化")),
                }
            )
        return rows

    def _build_indicators(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        closes = [_safe_float(row.get("close")) for row in rows]
        closes = [value for value in closes if value is not None]
        volumes = [_safe_float(row.get("volume")) for row in rows]
        volumes = [value for value in volumes if value is not None]
        if not closes:
            return {
                "latest_close": None,
                "return_pct": None,
                "highest_close": None,
                "lowest_close": None,
                "avg_volume": sum(volumes) / len(volumes) if volumes else None,
                "observation_count": len(rows),
            }

        first_close = closes[0]
        latest_close = closes[-1]
        return_pct = ((latest_close / first_close) - 1) * 100 if first_close else None
        avg_volume = sum(volumes) / len(volumes) if volumes else None
        return {
            "latest_close": latest_close,
            "return_pct": return_pct,
            "highest_close": max(closes),
            "lowest_close": min(closes),
            "avg_volume": avg_volume,
            "observation_count": len(closes),
        }
