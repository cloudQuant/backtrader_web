"""Backfill market history into the akshare_data warehouse.

This script is intentionally narrow and repeatable. It fills the history tables
used by the market data page without changing business database tables.
"""

from __future__ import annotations

import argparse
import logging
import math
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import mysql.connector

from app.data_fetch.configs.db_config import DB_CONFIG
from app.data_fetch.providers.akshare_to_mysql import FuncThread
from app.data_fetch.scripts.futures.weekly.daily_market_data import FuturesDailyMarket
from app.data_fetch.scripts.stocks.daily.stock_zh_a_hist import StockZhAHist
from app.services.market_instrument import MarketInstrumentService

LOGGER = logging.getLogger("backfill_market_history")


@dataclass(frozen=True)
class StockCandidate:
    symbol: str
    name: str
    history_rows: int
    latest_history_date: str | None


@dataclass(frozen=True)
class CacheCandidate:
    asset_type: str
    symbol: str
    name: str
    market: str
    history_rows: int
    latest_history_date: str | None


def _date_text(value: date) -> str:
    return value.strftime("%Y%m%d")


def _sql_date_text(value: str) -> str:
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _plain_code(value: str) -> str:
    text = str(value).strip().lower()
    if "." in text:
        left, right = text.split(".", 1)
        if left in {"sh", "sz", "bj"}:
            return right
        if right in {"sh", "sz", "bj"}:
            return left
    if text.startswith(("sh", "sz", "bj")) and len(text) > 2:
        return text[2:]
    return text


def _fund_sina_symbol(value: str) -> str:
    text = str(value).strip().lower()
    if text.startswith(("sh", "sz")):
        return text
    code = _plain_code(text)
    prefix = "sh" if code.startswith(("5", "6")) else "sz"
    return f"{prefix}{code}"


def _default_start_date(days: int) -> str:
    return _date_text(date.today() - timedelta(days=days))


def _default_end_date() -> str:
    return _date_text(date.today())


def _connect():
    return mysql.connector.connect(**DB_CONFIG)


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


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


def _ensure_stock_history_indexes(conn) -> None:
    """Ensure the history table has the unique key required for idempotent upsert."""
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'STOCK_ZH_A_HIST'
              AND INDEX_NAME = 'uk_symbol_date'
            """
        )
        if cursor.fetchone()[0] > 0:
            return
        cursor.execute(
            "ALTER TABLE STOCK_ZH_A_HIST ADD UNIQUE KEY uk_symbol_date (`symbol`, `data_date`)"
        )
    conn.commit()


def _ensure_history_cache_table(conn) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
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
    conn.commit()


def _fetch_stock_candidates(
    *,
    limit: int,
    min_rows: int,
    symbols: Iterable[str] | None,
    missing_only: bool,
) -> list[StockCandidate]:
    symbol_list = [str(symbol).strip() for symbol in (symbols or []) if str(symbol).strip()]
    conn = _connect()
    try:
        _ensure_stock_history_indexes(conn)
        params: list[object] = []
        where_clauses: list[str] = []
        if symbol_list:
            placeholders = ", ".join(["%s"] * len(symbol_list))
            where_clauses.append(f"s.code IN ({placeholders})")
            params.extend(symbol_list)

        if missing_only:
            where_clauses.append("COALESCE(h.history_rows, 0) < %s")
            params.append(min_rows)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        params.append(limit)
        sql = f"""
            SELECT
                s.code,
                COALESCE(s.name, s.code) AS name,
                COALESCE(h.history_rows, 0) AS history_rows,
                h.latest_history_date
            FROM (
                SELECT
                    raw.code,
                    MAX(raw.name) AS name,
                    MAX(raw.latest_date) AS latest_date,
                    MAX(raw.turnover) AS turnover
                FROM (
                    SELECT
                        COALESCE(NULLIF(symbol, ''), `代码`) AS code,
                        COALESCE(NULLIF(name, ''), `名称`) AS name,
                        data_date AS latest_date,
                        `成交额` AS turnover
                    FROM STOCK_ZH_A_SPOT_EM
                ) AS raw
                WHERE raw.code REGEXP '^[0-9]{{6}}$'
                GROUP BY raw.code
            ) AS s
            LEFT JOIN (
                SELECT
                    COALESCE(NULLIF(symbol, ''), `股票代码`) AS code,
                    COUNT(*) AS history_rows,
                    MAX(data_date) AS latest_history_date
                FROM STOCK_ZH_A_HIST
                GROUP BY code
            ) AS h ON h.code = s.code
            {where_sql}
            ORDER BY COALESCE(h.history_rows, 0) ASC, s.latest_date DESC, s.turnover DESC, s.code ASC
            LIMIT %s
        """
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [
            StockCandidate(
                symbol=str(row["code"]),
                name=str(row.get("name") or row["code"]),
                history_rows=int(row.get("history_rows") or 0),
                latest_history_date=(
                    row.get("latest_history_date").isoformat()
                    if hasattr(row.get("latest_history_date"), "isoformat")
                    else row.get("latest_history_date")
                ),
            )
            for row in rows
        ]
    finally:
        conn.close()


def _cache_source_sql(asset_type: str) -> str:
    if asset_type == "bond":
        return """
            SELECT
                raw.symbol,
                COALESCE(NULLIF(MAX(raw.name), ''), MAX(raw.code), raw.symbol) AS name,
                'CN' AS market,
                MAX(raw.latest_date) AS latest_date,
                MAX(raw.sort_value) AS sort_value
            FROM (
                SELECT
                    LOWER(symbol) AS symbol,
                    name,
                    code,
                    data_date AS latest_date,
                    trade AS sort_value
                FROM BOND_ZH_HS_COV_SPOT
                WHERE symbol IS NOT NULL AND symbol <> ''
            ) AS raw
            GROUP BY raw.symbol
        """
    if asset_type == "fund":
        return """
            SELECT
                raw.symbol,
                COALESCE(NULLIF(MAX(raw.name), ''), raw.symbol) AS name,
                'CN' AS market,
                MAX(raw.latest_date) AS latest_date,
                MAX(raw.sort_value) AS sort_value
            FROM (
                SELECT
                    ETF_CODE AS symbol,
                    ETF_NAME AS name,
                    QUOTE_DATE AS latest_date,
                    TURNOVER AS sort_value
                FROM ETF_REALTIME_QUOTE_EM
                WHERE ETF_CODE IS NOT NULL AND ETF_CODE <> ''
            ) AS raw
            GROUP BY raw.symbol
        """
    if asset_type == "fx":
        return """
            SELECT
                raw.symbol,
                COALESCE(NULLIF(MAX(raw.name), ''), raw.symbol) AS name,
                'FX' AS market,
                MAX(raw.latest_date) AS latest_date,
                MAX(raw.sort_value) AS sort_value
            FROM (
                SELECT
                    COALESCE(NULLIF(symbol, ''), `代码`) AS symbol,
                    COALESCE(NULLIF(name, ''), `名称`, `代码`) AS name,
                    data_date AS latest_date,
                    ABS(`涨跌幅`) AS sort_value
                FROM FOREX_SPOT_EM
                WHERE COALESCE(NULLIF(symbol, ''), `代码`) IS NOT NULL
                  AND COALESCE(NULLIF(symbol, ''), `代码`) <> ''
            ) AS raw
            GROUP BY raw.symbol
        """
    if asset_type == "option":
        return """
            SELECT
                raw.symbol,
                COALESCE(NULLIF(MAX(raw.name), ''), raw.symbol) AS name,
                'CN' AS market,
                MAX(raw.latest_date) AS latest_date,
                MAX(raw.sort_value) AS sort_value
            FROM (
                SELECT
                    COALESCE(NULLIF(symbol, ''), `代码`) AS symbol,
                    COALESCE(NULLIF(name, ''), `名称`, `代码`) AS name,
                    data_date AS latest_date,
                    `成交量` AS sort_value
                FROM OPTION_CURRENT_EM
                WHERE COALESCE(NULLIF(symbol, ''), `代码`) IS NOT NULL
                  AND COALESCE(NULLIF(symbol, ''), `代码`) <> ''
            ) AS raw
            GROUP BY raw.symbol
        """
    raise ValueError(f"Unsupported cache asset type: {asset_type}")


def _fetch_cache_candidates(
    *,
    asset_type: str,
    limit: int,
    min_rows: int,
    symbols: Iterable[str] | None,
    missing_only: bool,
    period: str,
) -> list[CacheCandidate]:
    symbol_list = [str(symbol).strip() for symbol in (symbols or []) if str(symbol).strip()]
    conn = _connect()
    try:
        _ensure_history_cache_table(conn)
        params: list[object] = [asset_type, period]
        where_clauses: list[str] = []
        if symbol_list:
            placeholders = ", ".join(["%s"] * len(symbol_list))
            where_clauses.append(f"UPPER(s.symbol) IN ({placeholders})")
            params.extend(symbol.upper() for symbol in symbol_list)
        if missing_only:
            where_clauses.append("COALESCE(h.history_rows, 0) < %s")
            params.append(min_rows)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        params.append(limit)
        sql = f"""
            SELECT
                s.symbol,
                COALESCE(s.name, s.symbol) AS name,
                COALESCE(s.market, 'CN') AS market,
                COALESCE(h.history_rows, 0) AS history_rows,
                h.latest_history_date
            FROM ({_cache_source_sql(asset_type)}) AS s
            LEFT JOIN (
                SELECT
                    UPPER(symbol) AS symbol,
                    COUNT(*) AS history_rows,
                    MAX(`date`) AS latest_history_date
                FROM MARKET_INSTRUMENT_HISTORY_CACHE
                WHERE asset_type = %s AND period = %s
                GROUP BY UPPER(symbol)
            ) AS h ON h.symbol = UPPER(s.symbol)
            {where_sql}
            ORDER BY COALESCE(h.history_rows, 0) ASC, s.latest_date DESC, s.sort_value DESC, s.symbol ASC
            LIMIT %s
        """
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [
            CacheCandidate(
                asset_type=asset_type,
                symbol=str(row["symbol"]),
                name=str(row.get("name") or row["symbol"]),
                market=str(row.get("market") or "CN"),
                history_rows=int(row.get("history_rows") or 0),
                latest_history_date=(
                    row.get("latest_history_date").isoformat()
                    if hasattr(row.get("latest_history_date"), "isoformat")
                    else row.get("latest_history_date")
                ),
            )
            for row in rows
        ]
    finally:
        conn.close()


def _update_stock_names(symbol: str, name: str) -> None:
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE STOCK_ZH_A_HIST
                SET name = %s
                WHERE symbol = %s AND (name IS NULL OR name = '' OR name = symbol)
                """,
                (name, symbol),
            )
        conn.commit()
    finally:
        conn.close()


def _backfill_one_stock(
    candidate: StockCandidate,
    args: argparse.Namespace,
    index: int,
    total: int,
) -> bool:
    LOGGER.info(
        "[%s/%s] backfilling stock %s %s",
        index,
        total,
        candidate.symbol,
        candidate.name,
    )
    script = StockZhAHist(logger=LOGGER)
    df = script.fetch_data(
        symbol=candidate.symbol,
        period="daily",
        start_date=args.start_date,
        end_date=args.end_date,
        adjust=args.adjust,
        source=args.stock_source,
        _call_timeout=args.call_timeout,
    )
    if df is not None and not df.empty:
        _update_stock_names(candidate.symbol, candidate.name)
        return True
    return False


def _backfill_stocks(args: argparse.Namespace) -> tuple[int, int]:
    candidates = _fetch_stock_candidates(
        limit=args.stock_limit,
        min_rows=args.stock_min_rows,
        symbols=args.symbols,
        missing_only=not args.stock_include_existing,
    )
    LOGGER.info("selected %s stock candidates", len(candidates))
    if args.dry_run:
        for candidate in candidates[:20]:
            LOGGER.info(
                "dry-run stock candidate: %s %s rows=%s latest=%s",
                candidate.symbol,
                candidate.name,
                candidate.history_rows,
                candidate.latest_history_date,
            )
        return len(candidates), 0

    success = 0
    total = len(candidates)
    workers = max(1, int(args.stock_workers or 1))
    if workers == 1:
        for index, candidate in enumerate(candidates, start=1):
            if _backfill_one_stock(candidate, args, index, total):
                success += 1
            if args.sleep > 0:
                time.sleep(args.sleep)
        return len(candidates), success

    LOGGER.info("using %s stock backfill workers", workers)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_candidate = {
            executor.submit(_backfill_one_stock, candidate, args, index, total): candidate
            for index, candidate in enumerate(candidates, start=1)
        }
        for completed, future in enumerate(as_completed(future_to_candidate), start=1):
            candidate = future_to_candidate[future]
            try:
                if future.result():
                    success += 1
            except Exception:
                LOGGER.exception("stock backfill failed: %s %s", candidate.symbol, candidate.name)
            if args.sleep > 0:
                time.sleep(args.sleep)
            LOGGER.info("stock progress: completed=%s/%s success=%s", completed, total, success)
    return len(candidates), success


def _history_cache_payloads(
    candidate: CacheCandidate,
    period: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    normalized_symbol = candidate.symbol.upper()
    for row in rows:
        row_date = _safe_text(row.get("date"))
        if not row_date:
            continue
        payloads.append(
            {
                "r_id": f"{candidate.asset_type}|{normalized_symbol}|{period}|{row_date}"[:191],
                "asset_type": candidate.asset_type,
                "symbol": normalized_symbol,
                "name": _safe_text(row.get("name")) or candidate.name,
                "market": candidate.market,
                "period": period,
                "date": row_date,
                "open": _safe_float(row.get("open")),
                "high": _safe_float(row.get("high")),
                "low": _safe_float(row.get("low")),
                "close": _safe_float(row.get("close")),
                "price": _safe_float(row.get("price")),
                "volume": _safe_int(row.get("volume")),
                "turnover": _safe_float(row.get("turnover")),
                "change_value": _safe_float(row.get("change")),
                "change_pct": _safe_float(row.get("change_pct")),
                "turnover_rate": _safe_float(row.get("turnover_rate")),
                "open_interest": _safe_int(row.get("open_interest")),
                "settle": _safe_float(row.get("settle")),
                "strike": _safe_float(row.get("strike")),
                "days_to_expiry": _safe_int(row.get("days_to_expiry")),
                "provider": "akshare",
            }
        )
    return payloads


def _save_history_cache(
    candidate: CacheCandidate,
    period: str,
    rows: list[dict[str, Any]],
) -> int:
    payloads = _history_cache_payloads(candidate, period, rows)
    if not payloads:
        return 0

    conn = _connect()
    try:
        _ensure_history_cache_table(conn)
        with conn.cursor() as cursor:
            cursor.executemany(
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
                    %(r_id)s,
                    %(asset_type)s,
                    %(symbol)s,
                    %(name)s,
                    %(market)s,
                    %(period)s,
                    %(date)s,
                    %(open)s,
                    %(high)s,
                    %(low)s,
                    %(close)s,
                    %(price)s,
                    %(volume)s,
                    %(turnover)s,
                    %(change_value)s,
                    %(change_pct)s,
                    %(turnover_rate)s,
                    %(open_interest)s,
                    %(settle)s,
                    %(strike)s,
                    %(days_to_expiry)s,
                    %(provider)s
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
                """,
                payloads,
            )
        conn.commit()
        return len(payloads)
    finally:
        conn.close()


def _lookup_cache_history_online(
    candidate: CacheCandidate,
    args: argparse.Namespace,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    service = MarketInstrumentService()

    rows = _lookup_cache_history_direct(candidate, args, service, warnings)
    if rows:
        return rows, warnings

    rows = service._lookup_history_online(  # noqa: SLF001 - operational backfill reuses page logic.
        asset_type=candidate.asset_type,
        symbol=candidate.symbol,
        start_date=_sql_date_text(args.start_date),
        end_date=_sql_date_text(args.end_date),
        period=args.cache_period,
        market=candidate.market,
        warnings=warnings,
    )
    return rows, warnings


def _lookup_cache_history_direct(
    candidate: CacheCandidate,
    args: argparse.Namespace,
    service: MarketInstrumentService,
    warnings: list[str],
) -> list[dict[str, Any]]:
    if candidate.asset_type == "fund":
        return _lookup_fund_cache_history(candidate, args, service, warnings)
    if candidate.asset_type == "fx":
        return _lookup_fx_cache_history(candidate, args, service, warnings)
    if candidate.asset_type == "bond":
        return _lookup_bond_cache_history(candidate, args, service, warnings)
    return []


def _lookup_bond_cache_history(
    candidate: CacheCandidate,
    args: argparse.Namespace,
    service: MarketInstrumentService,
    warnings: list[str],
) -> list[dict[str, Any]]:
    import akshare as ak

    symbol = candidate.symbol.lower()
    try:
        history_df = ak.bond_zh_hs_cov_daily(symbol=symbol)
    except Exception as exc:
        warnings.append(f"债券历史行情不可用: {exc}")
        return []
    return service._normalize_generic_ohlcv_history(  # noqa: SLF001
        history_df,
        _sql_date_text(args.start_date),
        _sql_date_text(args.end_date),
    )


def _lookup_fund_cache_history(
    candidate: CacheCandidate,
    args: argparse.Namespace,
    service: MarketInstrumentService,
    warnings: list[str],
) -> list[dict[str, Any]]:
    import akshare as ak

    code = _plain_code(candidate.symbol)
    if args.cache_period == "daily":
        sina_symbol = _fund_sina_symbol(code)
        try:
            history_df = ak.fund_etf_hist_sina(symbol=sina_symbol).rename(
                columns={"amount": "turnover"}
            )
            rows = service._normalize_generic_ohlcv_history(  # noqa: SLF001
                history_df,
                _sql_date_text(args.start_date),
                _sql_date_text(args.end_date),
            )
            if rows:
                return rows
            warnings.append(f"新浪 ETF 历史无数据: {sina_symbol}")
        except Exception as exc:
            warnings.append(f"新浪 ETF 历史不可用: {exc}")

    try:
        history_df = ak.fund_etf_hist_em(
            symbol=code,
            period=args.cache_period,
            start_date=args.start_date,
            end_date=args.end_date,
            adjust=args.adjust,
        )
    except Exception as exc:
        warnings.append(f"东方财富 ETF 历史不可用: {exc}")
        return []
    return service._normalize_cn_ohlcv_history(history_df)  # noqa: SLF001


def _lookup_fx_cache_history(
    candidate: CacheCandidate,
    args: argparse.Namespace,
    service: MarketInstrumentService,
    warnings: list[str],
) -> list[dict[str, Any]]:
    currency_column = service._fx_history_column(candidate.symbol)  # noqa: SLF001
    conn = _connect()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(
                f"""
                SELECT `日期` AS date, `{currency_column}` AS close
                FROM CURRENCY_BOC_SAFE
                WHERE STR_TO_DATE(`日期`, '%Y-%m-%d') BETWEEN %s AND %s
                ORDER BY STR_TO_DATE(`日期`, '%Y-%m-%d') ASC
                LIMIT 260
                """,
                (_sql_date_text(args.start_date), _sql_date_text(args.end_date)),
            )
            rows = cursor.fetchall()
            if not rows:
                cursor.execute(
                    f"""
                    SELECT `日期` AS date, `{currency_column}` AS close
                    FROM CURRENCY_BOC_SAFE
                    ORDER BY STR_TO_DATE(`日期`, '%Y-%m-%d') DESC
                    LIMIT 120
                    """
                )
                rows = list(reversed(cursor.fetchall()))
                if rows:
                    warnings.append("所选日期范围无外汇历史数据，已使用最近可用汇率记录")
    except Exception as exc:
        warnings.append(f"外汇本地历史缓存不可用: {exc}")
        return []
    finally:
        conn.close()
    return service._normalize_fx_history(rows)  # noqa: SLF001


def _backfill_one_cache_asset(
    candidate: CacheCandidate,
    args: argparse.Namespace,
    index: int,
    total: int,
) -> int:
    LOGGER.info(
        "[%s/%s] backfilling %s history cache %s %s",
        index,
        total,
        candidate.asset_type,
        candidate.symbol,
        candidate.name,
    )
    thread = FuncThread(_lookup_cache_history_online, candidate, args)
    thread.daemon = True
    thread.start()
    status, result = thread.get_result(timeout=args.call_timeout)
    if status == "timeout":
        LOGGER.warning(
            "%s %s history cache lookup timed out after %ss",
            candidate.asset_type,
            candidate.symbol,
            args.call_timeout,
        )
        return 0
    if status == "error":
        if isinstance(result, BaseException):
            raise result
        raise RuntimeError(result)
    rows, warnings = result
    if warnings:
        LOGGER.debug("%s %s warnings: %s", candidate.asset_type, candidate.symbol, "; ".join(warnings))
    saved = _save_history_cache(candidate, args.cache_period, rows)
    if saved:
        LOGGER.info(
            "saved %s %s history cache rows for %s",
            saved,
            candidate.asset_type,
            candidate.symbol,
        )
    return saved


def _backfill_cache_assets(args: argparse.Namespace) -> tuple[int, int, int]:
    asset_types = [
        asset.strip().lower()
        for asset in str(args.cache_asset_types).split(",")
        if asset.strip()
    ]
    selected = 0
    successful_assets = 0
    saved_rows = 0
    for asset_type in asset_types:
        candidates = _fetch_cache_candidates(
            asset_type=asset_type,
            limit=args.cache_limit,
            min_rows=args.cache_min_rows,
            symbols=args.symbols,
            missing_only=not args.cache_include_existing,
            period=args.cache_period,
        )
        selected += len(candidates)
        LOGGER.info("selected %s %s cache candidates", len(candidates), asset_type)
        if args.dry_run:
            for candidate in candidates[:20]:
                LOGGER.info(
                    "dry-run cache candidate: %s %s %s rows=%s latest=%s",
                    candidate.asset_type,
                    candidate.symbol,
                    candidate.name,
                    candidate.history_rows,
                    candidate.latest_history_date,
                )
            continue

        workers = max(1, int(args.cache_workers or 1))
        if workers == 1:
            for index, candidate in enumerate(candidates, start=1):
                saved = _backfill_one_cache_asset(candidate, args, index, len(candidates))
                saved_rows += saved
                successful_assets += int(saved > 0)
                if args.sleep > 0:
                    time.sleep(args.sleep)
            continue

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_candidate = {
                executor.submit(_backfill_one_cache_asset, candidate, args, index, len(candidates)): candidate
                for index, candidate in enumerate(candidates, start=1)
            }
            for completed, future in enumerate(as_completed(future_to_candidate), start=1):
                candidate = future_to_candidate[future]
                try:
                    saved = future.result()
                except Exception:
                    LOGGER.exception(
                        "cache backfill failed: %s %s %s",
                        candidate.asset_type,
                        candidate.symbol,
                        candidate.name,
                    )
                    saved = 0
                saved_rows += saved
                successful_assets += int(saved > 0)
                if args.sleep > 0:
                    time.sleep(args.sleep)
                LOGGER.info(
                    "cache progress: completed=%s/%s success_assets=%s saved_rows=%s",
                    completed,
                    len(candidates),
                    successful_assets,
                    saved_rows,
                )

    return selected, successful_assets, saved_rows


def _backfill_futures(args: argparse.Namespace) -> None:
    if args.dry_run:
        LOGGER.info(
            "dry-run futures update: markets=%s lookback_days=%s max_windows=%s",
            args.futures_markets,
            args.futures_lookback_days,
            args.futures_max_windows,
        )
        return
    FuturesDailyMarket(logger=LOGGER).run(
        markets=args.futures_markets,
        lookback_days=args.futures_lookback_days,
        max_windows=args.futures_max_windows,
        _call_timeout=args.call_timeout,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", default="stocks", help="Comma list: stocks,futures,cache")
    parser.add_argument("--symbols", nargs="*", help="Specific stock symbols to backfill")
    parser.add_argument("--stock-limit", type=int, default=100)
    parser.add_argument("--stock-min-rows", type=int, default=30)
    parser.add_argument("--stock-include-existing", action="store_true")
    parser.add_argument("--stock-source", default="auto", choices=["auto", "eastmoney", "tencent"])
    parser.add_argument("--stock-workers", type=int, default=1)
    parser.add_argument("--start-date", default=_default_start_date(180), help="YYYYMMDD")
    parser.add_argument("--end-date", default=_default_end_date(), help="YYYYMMDD")
    parser.add_argument("--adjust", default="qfq", choices=["", "qfq", "hfq"])
    parser.add_argument("--call-timeout", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--futures-markets", default=None, help="Comma list, e.g. CFFEX,DCE,SHFE")
    parser.add_argument("--futures-lookback-days", type=int, default=60)
    parser.add_argument("--futures-max-windows", type=int, default=None)
    parser.add_argument("--cache-asset-types", default="bond,fund,fx", help="Comma list: bond,fund,fx,option")
    parser.add_argument("--cache-limit", type=int, default=50)
    parser.add_argument("--cache-min-rows", type=int, default=30)
    parser.add_argument("--cache-include-existing", action="store_true")
    parser.add_argument("--cache-workers", type=int, default=2)
    parser.add_argument("--cache-period", default="daily", choices=["daily", "weekly", "monthly"])
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args = parse_args()
    assets = {asset.strip().lower() for asset in args.assets.split(",") if asset.strip()}
    if "stocks" in assets:
        selected, success = _backfill_stocks(args)
        LOGGER.info("stocks backfill finished: selected=%s success=%s", selected, success)
    if "futures" in assets:
        _backfill_futures(args)
        LOGGER.info("futures backfill finished")
    if "cache" in assets:
        selected, success_assets, saved_rows = _backfill_cache_assets(args)
        LOGGER.info(
            "cache backfill finished: selected=%s success_assets=%s saved_rows=%s",
            selected,
            success_assets,
            saved_rows,
        )


if __name__ == "__main__":
    main()
