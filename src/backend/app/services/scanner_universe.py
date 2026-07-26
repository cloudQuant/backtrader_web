from __future__ import annotations

import json
import logging
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.backend_data_paths import get_backend_data_path

logger = logging.getLogger(__name__)

DEFAULT_POOLS: list[dict[str, Any]] = [
    {
        "id": "hs300",
        "name": "沪深300",
        "description": "沪深300指数最新成分股，可从中证指数/AkShare刷新。",
        "category": "equity_index",
        "source": "akshare:index_stock_cons_csindex:000300",
        "is_custom": False,
        "refreshable": True,
        "instruments": [
            {"symbol": "000001.SZ", "name": "平安银行", "asset_type": "equity", "exchange": "SZSE"},
            {"symbol": "000002.SZ", "name": "万科A", "asset_type": "equity", "exchange": "SZSE"},
            {"symbol": "600519.SH", "name": "贵州茅台", "asset_type": "equity", "exchange": "SSE"},
            {"symbol": "601318.SH", "name": "中国平安", "asset_type": "equity", "exchange": "SSE"},
            {"symbol": "300750.SZ", "name": "宁德时代", "asset_type": "equity", "exchange": "SZSE"},
            {"symbol": "600036.SH", "name": "招商银行", "asset_type": "equity", "exchange": "SSE"},
        ],
    },
    {
        "id": "csi500",
        "name": "中证500",
        "description": "中证500指数最新成分股，可从中证指数/AkShare刷新。",
        "category": "equity_index",
        "source": "akshare:index_stock_cons_csindex:000905",
        "is_custom": False,
        "refreshable": True,
        "instruments": [
            {"symbol": "000009.SZ", "name": "中国宝安", "asset_type": "equity", "exchange": "SZSE"},
            {"symbol": "000021.SZ", "name": "深科技", "asset_type": "equity", "exchange": "SZSE"},
            {"symbol": "600761.SH", "name": "安徽合力", "asset_type": "equity", "exchange": "SSE"},
            {"symbol": "600884.SH", "name": "杉杉股份", "asset_type": "equity", "exchange": "SSE"},
            {"symbol": "002050.SZ", "name": "三花智控", "asset_type": "equity", "exchange": "SZSE"},
            {"symbol": "002230.SZ", "name": "科大讯飞", "asset_type": "equity", "exchange": "SZSE"},
        ],
    },
    {
        "id": "credit_bond",
        "name": "信用债",
        "description": "交易所债券与信用债ETF，可从沪深债券行情刷新。",
        "category": "credit_bond",
        "source": "akshare:bond_zh_hs_spot",
        "is_custom": False,
        "refreshable": True,
        "instruments": [
            {
                "symbol": "511030.SH",
                "name": "公司债ETF",
                "asset_type": "credit_bond",
                "exchange": "SSE",
            },
            {"symbol": "511090.SH", "name": "30年国债ETF", "asset_type": "bond", "exchange": "SSE"},
            {"symbol": "511260.SH", "name": "十年国债ETF", "asset_type": "bond", "exchange": "SSE"},
            {
                "symbol": "511220.SH",
                "name": "城投债ETF",
                "asset_type": "credit_bond",
                "exchange": "SSE",
            },
        ],
    },
    {
        "id": "convertible_bond",
        "name": "可转债",
        "description": "沪深可转债与转债ETF，可从沪深可转债行情刷新。",
        "category": "convertible_bond",
        "source": "akshare:bond_zh_hs_cov_spot",
        "is_custom": False,
        "refreshable": True,
        "instruments": [
            {
                "symbol": "000832.CSI",
                "name": "中证转债指数",
                "asset_type": "index",
                "exchange": "CSI",
            },
            {
                "symbol": "511380.SH",
                "name": "可转债ETF",
                "asset_type": "convertible_bond",
                "exchange": "SSE",
            },
            {
                "symbol": "113052.SH",
                "name": "兴业转债",
                "asset_type": "convertible_bond",
                "exchange": "SSE",
            },
            {
                "symbol": "123107.SZ",
                "name": "温氏转债",
                "asset_type": "convertible_bond",
                "exchange": "SZSE",
            },
        ],
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_template() -> dict[str, Any]:
    return {"built_in": {}, "custom": {}, "metric_snapshots": {}}


def _pool_summary(pool: dict[str, Any]) -> dict[str, Any]:
    instruments = list(pool.get("instruments") or [])
    return {
        **pool,
        "instrument_count": len(instruments),
        "instruments": instruments,
    }


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _normalize_change_pct(value: Any) -> float:
    raw = _safe_float(value)
    return raw / 100 if abs(raw) > 1 else raw


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _first_present(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in row and _safe_text(row[name]):
            return row[name]
    return None


def _detect_exchange(code: str, exchange: str = "") -> str:
    exchange_text = exchange.lower()
    if "深圳" in exchange or "sz" in exchange_text:
        return "SZSE"
    if "上海" in exchange or "sh" in exchange_text:
        return "SSE"
    if "北京" in exchange or "bj" in exchange_text:
        return "BSE"
    if code.startswith(("11", "13")):
        return "SSE"
    if code.startswith("12"):
        return "SZSE"
    if code.startswith(("6", "9")):
        return "SSE"
    if code.startswith(("0", "2", "3", "1")):
        return "SZSE"
    if code.startswith(("4", "8")):
        return "BSE"
    return exchange or ""


def _canonical_symbol(code: str, exchange: str = "") -> str:
    raw = _safe_text(code).upper()
    if not raw:
        return ""
    if "." in raw:
        return raw
    if raw.startswith(("SH", "SZ", "BJ")):
        prefix, digits = raw[:2], raw[2:]
        suffix = {"SH": "SH", "SZ": "SZ", "BJ": "BJ"}.get(prefix, "")
        return f"{digits}.{suffix}" if digits and suffix else raw
    exchange_code = _detect_exchange(raw, exchange)
    suffix = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}.get(exchange_code, "")
    return f"{raw}.{suffix}" if suffix else raw


def _code_key(symbol: str) -> str:
    raw = _safe_text(symbol).upper()
    if raw.startswith(("SH", "SZ", "BJ")):
        raw = raw[2:]
    if "." in raw:
        raw = raw.split(".", 1)[0]
    return raw


def _asset_type_for_pool(pool_id: str) -> str:
    if pool_id in {"hs300", "csi500"}:
        return "equity"
    if pool_id == "credit_bond":
        return "credit_bond"
    if pool_id == "convertible_bond":
        return "convertible_bond"
    return "custom"


def _normalize_instrument(
    item: dict[str, Any], *, default_asset_type: str = "custom"
) -> dict[str, Any]:
    symbol = _canonical_symbol(
        _safe_text(item.get("symbol") or item.get("code") or item.get("成分券代码")),
        _safe_text(item.get("exchange") or item.get("交易所")),
    )
    if not symbol:
        return {}
    exchange = _safe_text(
        item.get("exchange") or item.get("交易所") or _detect_exchange(_code_key(symbol))
    )
    return {
        "symbol": symbol,
        "name": _safe_text(
            item.get("name") or item.get("成分券名称") or item.get("名称") or symbol
        ),
        "asset_type": _safe_text(item.get("asset_type") or default_asset_type),
        "exchange": exchange,
        "source": _safe_text(item.get("source") or item.get("数据来源") or "custom"),
    }


def _dedupe_instruments(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for item in items:
        normalized = _normalize_instrument(item)
        symbol = normalized.get("symbol")
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        results.append(normalized)
    return results


def _records(frame: Any, limit: int = 500) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "head") and hasattr(frame, "to_dict"):
        return list(frame.head(limit).to_dict("records"))
    if isinstance(frame, list):
        return [item for item in frame[:limit] if isinstance(item, dict)]
    return []


class AkshareScannerMarketDataClient:
    """AkShare-backed loader for scanner universe constituents and quote factors."""

    def fetch_pool_constituents(self, pool_id: str) -> list[dict[str, Any]]:
        import akshare as ak

        if pool_id in {"hs300", "csi500"}:
            index_symbol = "000300" if pool_id == "hs300" else "000905"
            rows = _records(ak.index_stock_cons_csindex(symbol=index_symbol), limit=800)
            return [
                {
                    **_normalize_instrument(row, default_asset_type="equity"),
                    "source": "akshare:index_stock_cons_csindex",
                }
                for row in rows
                if _normalize_instrument(row, default_asset_type="equity")
            ]

        if pool_id == "convertible_bond":
            rows = _records(ak.bond_zh_hs_cov_spot(), limit=500)
            return [self._instrument_from_quote(row, "convertible_bond") for row in rows]

        if pool_id == "credit_bond":
            rows = _records(ak.bond_zh_hs_spot(start_page="1", end_page="5"), limit=500)
            return [self._instrument_from_quote(row, "credit_bond") for row in rows]

        return []

    def build_symbol_contexts(
        self,
        instruments: list[dict[str, Any]],
        *,
        lookback_days: int,
        timeframe: str,
    ) -> list[dict[str, Any]]:
        snapshots = self._load_snapshot_maps()
        contexts: list[dict[str, Any]] = []
        for instrument in instruments:
            contexts.append(
                self._context_for_instrument(
                    instrument,
                    snapshots=snapshots,
                    lookback_days=lookback_days,
                    timeframe=timeframe,
                )
            )
        return contexts

    def _load_snapshot_maps(self) -> dict[str, dict[str, dict[str, Any]]]:
        maps: dict[str, dict[str, dict[str, Any]]] = {}
        try:
            import akshare as ak
        except ImportError:
            logger.warning("akshare not installed; scanner uses seed universe data")
            return maps

        loaders = {
            "equity": lambda: ak.stock_zh_a_spot_em(),
            "etf": lambda: ak.fund_etf_spot_em(),
            "convertible_bond": lambda: ak.bond_zh_hs_cov_spot(),
            "credit_bond": lambda: ak.bond_zh_hs_spot(start_page="1", end_page="5"),
        }
        for key, loader in loaders.items():
            try:
                maps[key] = self._quote_map(_records(loader(), limit=6000))
            except Exception as exc:  # pragma: no cover - depends on live vendor availability
                logger.warning("Failed to load akshare scanner snapshot %s: %s", key, exc)
                maps[key] = {}
        return maps

    def _context_for_instrument(
        self,
        instrument: dict[str, Any],
        *,
        snapshots: dict[str, dict[str, dict[str, Any]]],
        lookback_days: int,
        timeframe: str,
    ) -> dict[str, Any]:
        symbol = _safe_text(instrument.get("symbol"))
        key = _code_key(symbol)
        asset_type = _safe_text(instrument.get("asset_type"))
        candidates = [asset_type, "equity", "etf", "convertible_bond", "credit_bond"]
        row = next((snapshots.get(candidate, {}).get(key) for candidate in candidates if key), None)

        if row:
            price = _safe_float(
                _first_present(row, ["最新价", "price", "trade", "最新", "收盘", "close"]),
                self._fallback_price(symbol),
            )
            volume = _safe_float(_first_present(row, ["成交量", "volume"]), 0.0)
            amount = _safe_float(_first_present(row, ["成交额", "amount"]), 0.0)
            change_pct = _normalize_change_pct(
                _first_present(row, ["涨跌幅", "changepercent", "change_pct"])
            )
            provider = "akshare"
            updated_at = utc_now()
        else:
            price = self._fallback_price(symbol)
            volume = float(abs(hash(symbol)) % 900000 + 100000)
            amount = price * volume
            change_pct = ((abs(hash(symbol)) % 700) - 250) / 10000
            provider = "seed_fallback"
            updated_at = utc_now()

        indicator = _clamp(0.5 + change_pct * 6)
        factor = _clamp(0.5 + change_pct * 4 + min(volume / 10_000_000, 0.2))
        return {
            **instrument,
            "price": round(price, 4),
            "volume": int(volume),
            "amount": round(amount, 2),
            "change_pct": round(change_pct, 6),
            "indicator": round(indicator, 6),
            "factor": round(factor, 6),
            "news_sentiment": 0.5,
            "portfolio_exposure": 0.0,
            "provider": provider,
            "updated_at": updated_at,
            "lookback_days": int(lookback_days),
            "timeframe": timeframe,
        }

    @staticmethod
    def _quote_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            code = _safe_text(
                _first_present(row, ["代码", "code", "symbol", "成分券代码", "证券代码"])
            )
            key = _code_key(code)
            if key:
                result[key] = row
        return result

    @staticmethod
    def _instrument_from_quote(row: dict[str, Any], asset_type: str) -> dict[str, Any]:
        return _normalize_instrument(
            {
                "symbol": _first_present(row, ["symbol", "code", "代码"]),
                "name": _first_present(row, ["name", "名称"]),
                "asset_type": asset_type,
                "source": "akshare",
            },
            default_asset_type=asset_type,
        )

    @staticmethod
    def _fallback_price(symbol: str) -> float:
        base = abs(hash(symbol)) % 10000
        return round(10 + base / 100, 2)


class ScannerUniverseService:
    def __init__(
        self,
        *,
        storage_path: Path | None = None,
        market_client: Any | None = None,
    ) -> None:
        self.storage_path = storage_path or get_backend_data_path("scanner_universe_pools.json")
        self.market_client = market_client or AkshareScannerMarketDataClient()

    def list_pools(self, user_id: str) -> dict[str, Any]:
        items = [
            self._with_latest_snapshot(user_id, _pool_summary(pool))
            for pool in self._built_in_pools()
        ]
        items.extend(
            self._with_latest_snapshot(user_id, _pool_summary(pool))
            for pool in self._custom_pools(user_id)
        )
        return {"items": items, "total": len(items)}

    def refresh_pool(self, pool_id: str, user_id: str) -> dict[str, Any]:
        pool = self.get_pool(pool_id, user_id)
        if pool is None:
            raise ValueError("universe_pool_not_found")
        if pool.get("is_custom") or not pool.get("refreshable"):
            raise ValueError("universe_pool_not_refreshable")

        try:
            instruments = self.market_client.fetch_pool_constituents(pool_id)
            instruments = _dedupe_instruments(instruments)
            if not instruments:
                raise ValueError("empty_constituents")
            status = "ok"
            error = None
        except Exception as exc:
            logger.warning("Failed to refresh scanner universe pool %s: %s", pool_id, exc)
            instruments = _dedupe_instruments(list(pool.get("instruments") or []))
            status = "fallback"
            error = str(exc)

        refreshed = {
            **pool,
            "instruments": instruments,
            "updated_at": utc_now(),
            "last_refresh_status": status,
            "last_refresh_error": error,
        }
        state = self._load_state()
        state.setdefault("built_in", {})[pool_id] = {
            "instruments": instruments,
            "updated_at": refreshed["updated_at"],
            "last_refresh_status": status,
            "last_refresh_error": error,
        }
        self._drop_metric_snapshots(state, user_id=user_id, pool_id=pool_id)
        self._save_state(state)
        return _pool_summary(refreshed)

    def save_custom_pool(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        name = _safe_text(payload.get("name"))
        if not name:
            raise ValueError("universe_pool_name_required")
        instruments = _dedupe_instruments(list(payload.get("instruments") or []))
        if not instruments:
            raise ValueError("universe_pool_instruments_required")

        state = self._load_state()
        user_pools = state.setdefault("custom", {}).setdefault(user_id, [])
        pool_id = _safe_text(payload.get("id")) or f"custom-{uuid.uuid4().hex[:10]}"
        existing_index = next(
            (index for index, item in enumerate(user_pools) if item.get("id") == pool_id),
            None,
        )
        pool = {
            "id": pool_id,
            "name": name,
            "description": _safe_text(payload.get("description")),
            "category": "custom",
            "source": "custom",
            "is_custom": True,
            "refreshable": False,
            "updated_at": utc_now(),
            "instruments": instruments,
        }
        if existing_index is None:
            user_pools.append(pool)
        else:
            user_pools[existing_index] = pool
            self._drop_metric_snapshots(state, user_id=user_id, pool_id=pool_id)
        self._save_state(state)
        return _pool_summary(pool)

    def get_pool(self, pool_id: str, user_id: str) -> dict[str, Any] | None:
        for pool in self._built_in_pools():
            if pool.get("id") == pool_id:
                return pool
        for pool in self._custom_pools(user_id):
            if pool.get("id") == pool_id:
                return pool
        return None

    def get_instruments_for_scan(
        self,
        *,
        user_id: str,
        pool_id: str | None = None,
        universe: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if pool_id:
            pool = self.get_pool(pool_id, user_id)
            if pool is None:
                raise ValueError("universe_pool_not_found")
            return _dedupe_instruments(list(pool.get("instruments") or [])), pool_id
        instruments = [
            {"symbol": symbol, "name": symbol, "asset_type": "custom"} for symbol in universe or []
        ]
        return _dedupe_instruments(instruments), None

    def build_symbol_contexts(
        self,
        instruments: list[dict[str, Any]],
        *,
        lookback_days: int,
        timeframe: str,
    ) -> list[dict[str, Any]]:
        return self.market_client.build_symbol_contexts(
            instruments,
            lookback_days=lookback_days,
            timeframe=timeframe,
        )

    def precompute_pool_metrics(
        self,
        *,
        user_id: str,
        pool_id: str,
        lookback_days: int,
        timeframe: str,
    ) -> dict[str, Any]:
        pool = self.get_pool(pool_id, user_id)
        if pool is None:
            raise ValueError("universe_pool_not_found")
        instruments = _dedupe_instruments(list(pool.get("instruments") or []))
        contexts = self.build_symbol_contexts(
            instruments,
            lookback_days=lookback_days,
            timeframe=timeframe,
        )
        snapshot = self._store_metric_snapshot(
            user_id=user_id,
            pool_id=pool_id,
            lookback_days=lookback_days,
            timeframe=timeframe,
            contexts=contexts,
        )
        return {**self._snapshot_summary(snapshot), "cache_status": "updated"}

    def get_or_build_symbol_contexts(
        self,
        *,
        user_id: str,
        pool_id: str,
        instruments: list[dict[str, Any]],
        lookback_days: int,
        timeframe: str,
    ) -> tuple[list[dict[str, Any]], str]:
        cached = self._get_metric_snapshot(
            user_id=user_id,
            pool_id=pool_id,
            lookback_days=lookback_days,
            timeframe=timeframe,
        )
        if cached is not None:
            return list(cached.get("items") or []), "hit"

        contexts = self.build_symbol_contexts(
            instruments,
            lookback_days=lookback_days,
            timeframe=timeframe,
        )
        self._store_metric_snapshot(
            user_id=user_id,
            pool_id=pool_id,
            lookback_days=lookback_days,
            timeframe=timeframe,
            contexts=contexts,
        )
        return contexts, "miss"

    def _store_metric_snapshot(
        self,
        *,
        user_id: str,
        pool_id: str,
        lookback_days: int,
        timeframe: str,
        contexts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        state = self._load_state()
        snapshot = {
            "user_id": user_id,
            "pool_id": pool_id,
            "lookback_days": int(lookback_days),
            "timeframe": timeframe,
            "computed_at": utc_now(),
            "total": len(contexts),
            "items": list(contexts),
        }
        state.setdefault("metric_snapshots", {})[
            self._snapshot_key(
                user_id=user_id,
                pool_id=pool_id,
                lookback_days=lookback_days,
                timeframe=timeframe,
            )
        ] = snapshot
        self._save_state(state)
        return snapshot

    def _get_metric_snapshot(
        self,
        *,
        user_id: str,
        pool_id: str,
        lookback_days: int,
        timeframe: str,
    ) -> dict[str, Any] | None:
        state = self._load_state()
        snapshot = (state.get("metric_snapshots") or {}).get(
            self._snapshot_key(
                user_id=user_id,
                pool_id=pool_id,
                lookback_days=lookback_days,
                timeframe=timeframe,
            )
        )
        return snapshot if isinstance(snapshot, dict) else None

    def _with_latest_snapshot(self, user_id: str, pool: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state()
        snapshots = [
            item
            for item in (state.get("metric_snapshots") or {}).values()
            if isinstance(item, dict)
            and item.get("user_id") == user_id
            and item.get("pool_id") == pool.get("id")
        ]
        if not snapshots:
            return pool
        latest = max(snapshots, key=lambda item: str(item.get("computed_at") or ""))
        return {**pool, "metric_snapshot": self._snapshot_summary(latest)}

    @staticmethod
    def _snapshot_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "pool_id": snapshot.get("pool_id"),
            "lookback_days": int(snapshot.get("lookback_days") or 0),
            "timeframe": snapshot.get("timeframe") or "",
            "computed_at": snapshot.get("computed_at") or "",
            "total": int(snapshot.get("total") or len(snapshot.get("items") or [])),
        }

    @staticmethod
    def _snapshot_key(*, user_id: str, pool_id: str, lookback_days: int, timeframe: str) -> str:
        return f"{user_id}:{pool_id}:{int(lookback_days)}:{timeframe}"

    @staticmethod
    def _drop_metric_snapshots(state: dict[str, Any], *, user_id: str, pool_id: str) -> None:
        snapshots = state.setdefault("metric_snapshots", {})
        for key, item in list(snapshots.items()):
            if not isinstance(item, dict):
                continue
            if item.get("user_id") == user_id and item.get("pool_id") == pool_id:
                snapshots.pop(key, None)

    def _built_in_pools(self) -> list[dict[str, Any]]:
        state = self._load_state()
        overrides = state.get("built_in") or {}
        pools = []
        for pool in DEFAULT_POOLS:
            override = overrides.get(pool["id"]) or {}
            pools.append({**pool, **override})
        return pools

    def _custom_pools(self, user_id: str) -> list[dict[str, Any]]:
        state = self._load_state()
        custom = state.get("custom") or {}
        return list(custom.get(user_id) or [])

    def _load_state(self) -> dict[str, Any]:
        if not self.storage_path.is_file():
            return _state_template()
        try:
            payload = json.loads(self.storage_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return _state_template()
        if not isinstance(payload, dict):
            return _state_template()
        payload.setdefault("built_in", {})
        payload.setdefault("custom", {})
        payload.setdefault("metric_snapshots", {})
        return payload

    def _save_state(self, payload: dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def parse_symbol_text(value: str) -> list[dict[str, Any]]:
    symbols = [item.strip() for item in re.split(r"[,\s，、]+", value or "") if item.strip()]
    return [{"symbol": symbol, "name": symbol, "asset_type": "custom"} for symbol in symbols]
