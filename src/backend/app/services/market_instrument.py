from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Literal

import pandas as pd

MarketAssetType = Literal["stock", "futures", "bond", "fund", "option", "fx", "crypto"]


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


def _date_text(value: date | str | None, fallback: date) -> str:
    if value is None:
        return fallback.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return value.replace("-", "")


def _iso_date(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value)


def _normalize_plain_code(symbol: str) -> str:
    return symbol.strip().upper().split(".")[0]


def _normalize_exchange_symbol(symbol: str, default_prefix: str = "sh") -> str:
    normalized = symbol.strip().lower()
    if "." in normalized:
        code, exchange = normalized.split(".", 1)
        if exchange in {"sh", "sz", "bj"}:
            return f"{exchange}{code}"
    if normalized.startswith(("sh", "sz", "bj")):
        return normalized
    return f"{default_prefix}{normalized}"


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

    def lookup(
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
                    "update_time": _safe_str(_first_present(row, "更新时间", "时间", "update_time")),
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
    ) -> dict[str, Any]:
        return {
            "asset_type": asset_type,
            "symbol": symbol,
            "name": name,
            "market": market,
            "provider": "akshare",
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
